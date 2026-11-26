# -*- coding: utf-8 -*-
"""Тикеты: вопрос, заявка в стафф, жалоба."""

import datetime
import io
import logging
import discord
from discord import app_commands
from discord.ext import commands

from storage import load, save

log = logging.getLogger(__name__)

TICKETS_FILE = "tickets.json"
SETTINGS_FILE = "settings.json"
RATINGS_FILE = "ratings.json"

STAFF_ROLE_IDS = [
    1573422779376865280,  # Хелпер
    1573422776919007424,  # Модератор
    1573680792679489556,  # Старший модератор
    1573422768421077063,  # Администратор
    1573680796475195482,  # Главный администратор
    1573422762205257763,  # Владелец
    1573680800233426984,  # Владелица
]

TICKET_TYPES = {
    "question":    {"emoji": "❓", "label": "Вопрос",         "color": 0xa9c9ff, "desc": "Общий вопрос к стаффу"},
    "staff_app":   {"emoji": "📋", "label": "Заявка в стафф", "color": 0x57f287, "desc": "Хочу вступить в команду"},
    "complaint":   {"emoji": "⚠️", "label": "Жалоба",         "color": 0xed4245, "desc": "Жалоба на участника или стафф"},
}


def _now_str():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


def _is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_ROLE_IDS for r in member.roles)


def _cfg(guild_id: int) -> dict:
    return load(SETTINGS_FILE, {}).get(str(guild_id), {})


SEND_PERMS = [
    ("view_channel", "Смотреть канал"),
    ("send_messages", "Отправлять сообщения"),
    ("embed_links", "Встраивать ссылки"),
]


def _missing_send(channel, me) -> list:
    """Что боту мешает писать в канал — по-человечески."""
    if me is None:
        return ["роль бота не найдена на сервере"]
    perms = channel.permissions_for(me)
    return [label for attr, label in SEND_PERMS if not getattr(perms, attr, False)]


async def _submit(interaction: discord.Interaction, ticket_type: str, fields: dict):
    """Обёртка над созданием тикета: любая ошибка видна пользователю и в логе."""
    try:
        await _create_ticket(interaction, ticket_type, fields)
    except Exception as e:
        log.exception("Ошибка создания тикета [%s]", ticket_type)
        msg = f"⚠️ Не смог создать тикет: `{type(e).__name__}: {e}`"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            log.exception("Не смог отправить сообщение об ошибке")


# ── Модалки для каждого типа ──────────────────────────────────────────────────

class QuestionModal(discord.ui.Modal, title="❓ Вопрос"):
    question = discord.ui.TextInput(
        label="Твой вопрос",
        placeholder="Опиши что хочешь узнать...",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _submit(interaction, "question", {"question": self.question.value})


class HelperAppModal(discord.ui.Modal, title="🧰 Заявка: Хелпер"):
    """Анкета на хелпера — про помощь новичкам и общение."""

    age = discord.ui.TextInput(label="Возраст", placeholder="например: 17", max_length=3)
    timezone = discord.ui.TextInput(
        label="Часовой пояс и когда ты онлайн",
        placeholder="например: МСК, будни 18:00–23:00, выходные днём",
        max_length=100,
    )
    experience = discord.ui.TextInput(
        label="Опыт: где был хелпером или модератором?",
        placeholder="Сервер, роль, сколько времени. Если опыта нет — напиши «нет»",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )
    why = discord.ui.TextInput(
        label="Почему хочешь в хелперы?",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=500,
    )
    newcomer = discord.ui.TextInput(
        label="Новичок не понял правила и злится. Действия?",
        placeholder="Опиши, как именно будешь объяснять и что сделаешь дальше",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=400,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _submit(interaction, "staff_app", {
            "__role": "Хелпер",
            "Возраст": self.age.value,
            "Часовой пояс и активность": self.timezone.value,
            "Опыт": self.experience.value,
            "Почему в хелперы": self.why.value,
            "Ситуация: новичок и правила": self.newcomer.value,
        })


class ModeratorAppModal(discord.ui.Modal, title="🛡 Заявка: Модератор"):
    """Анкета на модератора — про наказания, конфликты и знание правил."""

    age = discord.ui.TextInput(label="Возраст", placeholder="например: 19", max_length=3)
    timezone = discord.ui.TextInput(
        label="Часовой пояс и когда ты онлайн",
        placeholder="например: МСК, будни 20:00–02:00, выходные весь день",
        max_length=100,
    )
    experience = discord.ui.TextInput(
        label="Опыт модерации: где, какая нагрузка?",
        placeholder="Сервер, роль, сколько участников было под тобой. Нет опыта — напиши «нет»",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )
    why = discord.ui.TextInput(
        label="Почему хочешь в модераторы?",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=500,
    )
    situation = discord.ui.TextInput(
        label="Оскорбления в войсе. Твои действия?",
        placeholder="По шагам: что говоришь, что делаешь, какой срок наказания и почему",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=400,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _submit(interaction, "staff_app", {
            "__role": "Модератор",
            "Возраст": self.age.value,
            "Часовой пояс и активность": self.timezone.value,
            "Опыт модерации": self.experience.value,
            "Почему в модераторы": self.why.value,
            "Ситуация: оскорбления в войсе": self.situation.value,
        })


class ComplaintModal(discord.ui.Modal, title="⚠️ Жалоба"):
    target = discord.ui.TextInput(
        label="На кого жалоба (ник или ID)",
        placeholder="например: username#0000 или 123456789",
        max_length=100,
    )
    reason = discord.ui.TextInput(
        label="Причина жалобы",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=500,
    )
    proof = discord.ui.TextInput(
        label="Доказательства (ссылки на скрины)",
        placeholder="Вставь ссылки через запятую или напиши 'нет'",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _submit(interaction, "complaint", {
            "target": self.target.value,
            "reason": self.reason.value,
            "proof": self.proof.value,
        })


# ── Создание тикета ───────────────────────────────────────────────────────────

async def _create_ticket(interaction: discord.Interaction, ticket_type: str, fields: dict):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    member = interaction.user
    cfg = _cfg(guild.id)
    data = load(TICKETS_FILE, {})

    # Проверить открытый тикет того же типа
    for ch_id, info in data.items():
        if str(info.get("user_id")) == str(member.id) and info.get("open") and info.get("type") == ticket_type:
            ch = guild.get_channel(int(ch_id))
            if ch:
                await interaction.followup.send(
                    f"У тебя уже есть открытый тикет этого типа: {ch.mention}", ephemeral=True
                )
                return

    tinfo = TICKET_TYPES[ticket_type]
    cat_id = cfg.get("ticket_category_id")
    category = guild.get_channel(int(cat_id)) if cat_id else None

    # Права на создание канала
    if guild.me is None:
        await interaction.followup.send("⚠️ Не вижу себя на сервере — перезайди ботом.", ephemeral=True)
        return
    if category is not None:
        can_manage = category.permissions_for(guild.me).manage_channels
    else:
        can_manage = guild.me.guild_permissions.manage_channels
    if not can_manage:
        where = f"в категории {category.mention}" if category else "на сервере"
        await interaction.followup.send(
            f"⚠️ Не могу создать канал для тикета: нет права **«Управлять каналами»** {where}.\n"
            "Дай это право роли бота — иначе тикеты не открываются.",
            ephemeral=True,
        )
        return

    # Права канала
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for rid in STAFF_ROLE_IDS:
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    safe_name = member.display_name.lower().replace(" ", "-")[:15]
    ch_name = f"{tinfo['emoji']}-{safe_name}"
    try:
        channel = await guild.create_text_channel(
            ch_name, category=category, overwrites=overwrites,
            reason=f"Тикет [{ticket_type}] от {member}",
        )
    except discord.HTTPException as e:
        await interaction.followup.send(f"Не удалось создать канал: {e}", ephemeral=True)
        return

    # Сохранить
    data[str(channel.id)] = {
        "user_id": member.id,
        "user_name": str(member),
        "type": ticket_type,
        "open": True,
        "created_at": _now_str(),
        "fields": fields,
    }
    save(TICKETS_FILE, data)

    # Embed в тикете
    embed = discord.Embed(
        title=f"{tinfo['emoji']} {tinfo['label']}",
        color=tinfo["color"],
        timestamp=datetime.datetime.now(),
    )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)

    if ticket_type == "question":
        embed.add_field(name="Вопрос", value=fields["question"], inline=False)
        embed.description = "Стафф ответит в ближайшее время. Когда вопрос решён — нажми «🔒 Закрыть»."

    elif ticket_type == "staff_app":
        role = fields.get("__role", "—")
        embed.description = f"Заявка на роль **{role}**. Стафф рассмотрит её и даст ответ."
        embed.add_field(name="На роль", value=role, inline=True)
        embed.add_field(name="Возраст", value=fields.get("Возраст", "—"), inline=True)
        embed.add_field(name="Активность", value=fields.get("Часовой пояс и активность", "—"), inline=True)
        for name, value in fields.items():
            if name.startswith("__") or name in ("Возраст", "Часовой пояс и активность"):
                continue
            embed.add_field(name=name, value=str(value) or "—", inline=False)

    elif ticket_type == "complaint":
        embed.description = "Жалоба принята. Стафф разберётся и даст ответ."
        embed.add_field(name="На кого", value=fields["target"], inline=True)
        embed.add_field(name="Причина", value=fields["reason"], inline=False)
        embed.add_field(name="Доказательства", value=fields["proof"], inline=False)

    view = StaffAppActionView() if ticket_type == "staff_app" else AnswerView()
    await channel.send(content=member.mention, embed=embed, view=view)

    # Лог
    log_ch_id = cfg.get("ticket_log_channel_id")
    if log_ch_id:
        log_ch = guild.get_channel(int(log_ch_id))
        if log_ch:
            log_embed = discord.Embed(
                title=f"📩 Новый тикет — {tinfo['label']}",
                description=f"{member.mention} открыл {channel.mention}",
                color=tinfo["color"],
                timestamp=datetime.datetime.now(),
            )
            if ticket_type == "staff_app":
                log_embed.add_field(name="Роль", value=fields.get("__role", "—"), inline=True)
            await log_ch.send(embed=log_embed)

    await interaction.followup.send(f"Тикет создан: {channel.mention}", ephemeral=True)


# ── Транскрипт тикета ─────────────────────────────────────────────────────────

TRANSCRIPT_LIMIT = 200          # сколько последних сообщений выгружаем
TRANSCRIPT_MAX_CHARS = 6_000_000  # ~6 МБ текста: лимит Discord на файл — 8 МБ


def _transcript_line(msg: discord.Message) -> str:
    """Одна строка истории: время, автор, текст/вложения."""
    ts = msg.created_at.strftime("%d.%m.%Y %H:%M")
    author = f"{msg.author.display_name} ({msg.author.id})"
    parts = []
    content = (getattr(msg, "system_content", "") or msg.content or "").strip()
    if content:
        parts.append(content)
    for att in msg.attachments:
        parts.append(f"[вложение] {att.filename} — {att.url}")
    for emb in msg.embeds:
        title = emb.title or (emb.description or "")[:100]
        parts.append(f"[embed] {title}".strip())
    if msg.stickers:
        parts.append("[стикер] " + ", ".join(s.name for s in msg.stickers))
    return f"[{ts}] {author}: {' | '.join(parts) or '[без текста]'}"


async def _build_transcript(channel, info: dict, closer, tinfo: dict):
    """История тикета файлом. Возвращает (файл или None, число сообщений)."""
    try:
        messages = [m async for m in channel.history(limit=TRANSCRIPT_LIMIT)]
    except discord.HTTPException as exc:
        log.warning("Не удалось прочитать историю тикета %s: %s", channel.id, exc)
        return None, 0
    messages.reverse()  # история приходит от новых к старым

    closer_name = getattr(closer, "display_name", None) or str(closer)
    header = [
        f"Тикет: #{channel.name}",
        f"Тип: {tinfo['label']}",
        f"Создал: <@{info.get('user_id')}>",
        f"Создан: {info.get('created_at', '—')}",
        f"Закрыл: {closer_name} ({closer.id})",
        f"Закрыт: {info.get('closed_at', '—')}",
        f"Сообщений в выгрузке: {len(messages)}",
        "-" * 60,
    ]
    text = "\n".join(header) + "\n\n" + "\n".join(_transcript_line(m) for m in messages)
    if len(text) > TRANSCRIPT_MAX_CHARS:
        text = text[:TRANSCRIPT_MAX_CHARS] + "\n\n… выгрузка обрезана по размеру"
    buf = io.BytesIO(text.encode("utf-8"))
    return discord.File(buf, filename=f"ticket-{channel.id}.txt"), len(messages)


# ── Кнопка закрытия ───────────────────────────────────────────────────────────

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_close(interaction.channel, interaction.user, interaction)


async def _do_close(channel: discord.TextChannel, closer: discord.Member, interaction=None):
    data = load(TICKETS_FILE, {})
    info = data.get(str(channel.id))

    if not info or not info.get("open"):
        if interaction:
            await interaction.response.send_message("Это не активный тикет.", ephemeral=True)
        return

    if str(closer.id) != str(info.get("user_id")) and not _is_staff(closer):
        if interaction:
            await interaction.response.send_message("Нет прав для закрытия.", ephemeral=True)
        return

    if interaction:
        await interaction.response.defer()

    info["open"] = False
    info["closed_at"] = _now_str()
    info["closed_by"] = str(closer)
    save(TICKETS_FILE, data)

    tinfo = TICKET_TYPES.get(info.get("type", "question"), TICKET_TYPES["question"])
    embed = discord.Embed(
        title="🔒 Тикет закрыт",
        description=f"Закрыт пользователем {closer.mention}. Канал удалится через 5 секунд.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(),
    )
    await channel.send(embed=embed)

    cfg = _cfg(channel.guild.id)
    log_ch_id = cfg.get("ticket_log_channel_id")
    if log_ch_id:
        log_ch = channel.guild.get_channel(int(log_ch_id))
        if log_ch:
            transcript, count = await _build_transcript(channel, info, closer, tinfo)
            log_embed = discord.Embed(
                title=f"🔒 Тикет закрыт — {tinfo['label']}",
                description=(
                    f"Канал: **{channel.name}**\n"
                    f"Создал: <@{info['user_id']}>\n"
                    f"Закрыл: {closer.mention}\n"
                    f"Создан: {info.get('created_at', '—')}\n"
                    f"Закрыт: {info.get('closed_at', '—')}"
                ),
                color=discord.Color.red(),
            )
            if transcript:
                log_embed.add_field(
                    name="📄 Выгрузка",
                    value=f"{count} сообщений — в файле ниже",
                    inline=False,
                )
            try:
                if transcript:
                    await log_ch.send(embed=log_embed, file=transcript)
                else:
                    await log_ch.send(embed=log_embed)
            except discord.HTTPException as exc:
                log.warning("Лог тикета %s не отправлен: %s", channel.id, exc)

    # Просим автора оценить хелпера (в ЛС), если ответ был
    helper_id = info.get("answered_by_id")
    author_id = int(info.get("user_id") or 0)
    if helper_id and author_id and author_id != int(helper_id):
        author = channel.guild.get_member(author_id)
        helper = channel.guild.get_member(int(helper_id))
        helper_name = (helper.display_name if helper else None) or str(info.get("answered_by") or "стафф")
        view = RatingView(
            channel.guild.id, channel.id, author_id, int(helper_id)
        )._arm_custom_ids()
        bot = getattr(interaction, "client", None) if interaction is not None else None
        if author is not None and bot is not None:
            bot.add_view(view)
            await _dm(author, _rating_embed(helper_name), view=view)

    import asyncio
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Тикет закрыт {closer}")
    except discord.HTTPException:
        pass


# ── Ответ стаффа на вопрос/жалобу ─────────────────────────────────────────────

def _get_ticket(channel_id: int):
    """Данные тикета по id канала."""
    data = load(TICKETS_FILE, {})
    return data, data.get(str(channel_id))


async def _dm(member, embed, view=None) -> bool:
    if member is None:
        return False
    try:
        if view is not None:
            await member.send(embed=embed, view=view)
        else:
            await member.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


# ── Оценка хелпера после закрытия тикета ──────────────────────────────────────

def _save_rating(guild_id: int, ticket_id: int, helper_id: int, stars: int, by_id: int) -> bool:
    """Сохранить оценку. False — за этот тикет уже оценивали."""
    data = load(RATINGS_FILE, {})
    guild = data.setdefault(str(guild_id), {})
    key = str(ticket_id)
    if key in guild:
        return False
    guild[key] = {
        "helper_id": helper_id,
        "stars": int(stars),
        "by": by_id,
        "ts": _now_str(),
    }
    save(RATINGS_FILE, data)
    return True


def _ratings_summary(guild_id: int):
    """[(helper_id, средняя, число оценок)] по убыванию средней."""
    guild = load(RATINGS_FILE, {}).get(str(guild_id), {})
    per = {}
    for r in guild.values():
        try:
            hid = int(r.get("helper_id") or 0)
            stars = int(r.get("stars") or 0)
        except (TypeError, ValueError):
            continue
        if hid <= 0 or not 1 <= stars <= 5:
            continue
        total, count = per.get(hid, (0, 0))
        per[hid] = (total + stars, count + 1)
    rows = [(hid, total / count, count) for hid, (total, count) in per.items()]
    rows.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return rows


class RatingView(discord.ui.View):
    """Приходит автору тикета в ЛС после закрытия: оцени работу хелпера."""

    def __init__(self, guild_id: int, ticket_id: int, author_id: int, helper_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.ticket_id = ticket_id
        self.author_id = author_id
        self.helper_id = helper_id

    async def _rate(self, interaction: discord.Interaction, stars: int):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Оценить может только автор тикета.", ephemeral=True
            )
            return
        saved = _save_rating(self.guild_id, self.ticket_id, self.helper_id, stars, self.author_id)
        if not saved:
            await interaction.response.edit_message(
                content="Этот тикет ты уже оценил. Спасибо! ⭐", embed=None, view=None
            )
            return
        await interaction.response.edit_message(
            content=f"Спасибо! Оценка **{stars}⭐** записана.", embed=None, view=None
        )

    @discord.ui.button(label="1⭐", custom_id="trate_placeholder_1")
    async def star1(self, interaction, button):
        await self._rate(interaction, 1)

    @discord.ui.button(label="2⭐", custom_id="trate_placeholder_2")
    async def star2(self, interaction, button):
        await self._rate(interaction, 2)

    @discord.ui.button(label="3⭐", custom_id="trate_placeholder_3")
    async def star3(self, interaction, button):
        await self._rate(interaction, 3)

    @discord.ui.button(label="4⭐", custom_id="trate_placeholder_4")
    async def star4(self, interaction, button):
        await self._rate(interaction, 4)

    @discord.ui.button(label="5⭐", custom_id="trate_placeholder_5")
    async def star5(self, interaction, button):
        await self._rate(interaction, 5)

    def _arm_custom_ids(self):
        """Уникальные custom_id под конкретный тикет (для persistent после рестарта)."""
        for i, child in enumerate(self.children, start=1):
            child.custom_id = f"trate_{self.ticket_id}_{i}"
        return self


def _rating_embed(helper_name: str) -> discord.Embed:
    embed = discord.Embed(
        title="⭐ Как всё прошло?",
        description=(
            f"Твой тикет закрыл **{helper_name}**.\n"
            f"Оцени работу хелпера — это займет 2 секунды."
        ),
        color=0xffd166,
    )
    embed.set_footer(text="Твоя оценка видна только стаффу")
    return embed


def _rearm_rating_views(bot: commands.Bot):
    """После рестарта снова включаем кнопки в ЛС у тех, кто ещё не оценил."""
    tickets = load(TICKETS_FILE, {})
    ratings = load(RATINGS_FILE, {})
    for guild_id, guild_tickets in tickets.items():
        rated = ratings.get(guild_id, {})
        for ticket_id, info in guild_tickets.items():
            if info.get("open"):
                continue
            helper_id = info.get("answered_by_id")
            if not helper_id or ticket_id in rated:
                continue
            try:
                view = RatingView(
                    int(guild_id), int(ticket_id), int(info.get("user_id") or 0), int(helper_id)
                )._arm_custom_ids()
                bot.add_view(view)
            except (TypeError, ValueError):
                continue


class AnswerModal(discord.ui.Modal, title="✍️ Ответ на обращение"):
    answer = discord.ui.TextInput(
        label="Твой ответ",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _submit_answer(interaction, self.answer.value)


async def _submit_answer(interaction: discord.Interaction, text: str):
    data, info = _get_ticket(interaction.channel.id)
    if not info or not info.get("open"):
        await interaction.response.send_message("Это не активный тикет.", ephemeral=True)
        return
    if not _is_staff(interaction.user):
        await interaction.response.send_message("Отвечает только стафф.", ephemeral=True)
        return

    await interaction.response.defer()
    info["answered"] = True
    info["answered_by"] = str(interaction.user)
    info["answered_by_id"] = interaction.user.id
    info["answered_at"] = _now_str()
    info["answer"] = text
    save(TICKETS_FILE, data)

    embed = discord.Embed(
        title="✍️ Ответ стаффа",
        description=text,
        color=0x57f287,
        timestamp=datetime.datetime.now(),
    )
    embed.set_footer(text=f"Ответил: {interaction.user}")
    await interaction.channel.send(content=f"<@{info['user_id']}>", embed=embed)

    member = interaction.guild.get_member(int(info["user_id"]))
    tinfo = TICKET_TYPES.get(info.get("type", "question"), TICKET_TYPES["question"])
    dm_embed = discord.Embed(
        title=f"✍️ Ответ на твоё обращение ({tinfo['label']})",
        description=text,
        color=0x57f287,
        timestamp=datetime.datetime.now(),
    )
    dm_embed.set_footer(text=f"Сервер: {interaction.guild.name}")
    sent = await _dm(member, dm_embed)
    if not sent:
        await interaction.followup.send(
            "Ответ отправлен, но в ЛС написать не смог — у автора закрыты личные сообщения.",
            ephemeral=True,
        )


class AnswerView(discord.ui.View):
    """Кнопки в тикете-вопросе и тикете-жалобе."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✍️ Ответить", style=discord.ButtonStyle.success, custom_id="ticket_answer")
    async def answer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_staff(interaction.user):
            await interaction.response.send_message("Отвечает только стафф.", ephemeral=True)
            return
        await _open_modal(interaction, AnswerModal())

    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.secondary, custom_id="ticket_close_ans")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_close(interaction.channel, interaction.user, interaction)


# ── Заявка в стафф: принять / отклонить ───────────────────────────────────────

ROLE_BY_NAME = {
    "Хелпер": 1573422779376865280,
    "Модератор": 1573422776919007424,
}


class RejectModal(discord.ui.Modal, title="❌ Отказ по заявке"):
    reason = discord.ui.TextInput(
        label="Причина отказа",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _reject_app(interaction, self.reason.value)


async def _accept_app(interaction: discord.Interaction):
    data, info = _get_ticket(interaction.channel.id)
    if not info or not info.get("open"):
        await interaction.response.send_message("Это не активный тикет.", ephemeral=True)
        return
    if not _is_staff(interaction.user):
        await interaction.response.send_message("Решать по заявке может только стафф.", ephemeral=True)
        return

    guild = interaction.guild
    member = guild.get_member(int(info["user_id"]))
    role_name = (info.get("fields") or {}).get("__role", "")
    role = guild.get_role(ROLE_BY_NAME.get(role_name, 0))

    if member is None:
        await interaction.response.send_message(
            "Не нашёл участника на сервере — возможно, он уже вышел.", ephemeral=True
        )
        return
    if role is None:
        await interaction.response.send_message(
            f"Не нашёл роль «{role_name}». Проверь ID ролей в коде бота.", ephemeral=True
        )
        return

    await interaction.response.defer()
    try:
        await member.add_roles(role, reason=f"Заявка принята: {interaction.user}")
    except discord.Forbidden:
        await interaction.followup.send(
            "Не могу выдать роль: она выше моей в списке ролей или у меня нет права "
            "«Управлять ролями».",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="✅ Заявка принята",
        description=f"{member.mention} получил роль **{role.name}**.",
        color=0x57f287,
        timestamp=datetime.datetime.now(),
    )
    embed.set_footer(text=f"Принял: {interaction.user}")
    await interaction.channel.send(embed=embed)

    dm_embed = discord.Embed(
        title="✅ Твою заявку приняли",
        description=(
            f"Поздравляю! Тебе выдана роль **{role.name}** на сервере **{guild.name}**.\n"
            "Загляни в канал для стаффа — там задачи и общение команды."
        ),
        color=0x57f287,
    )
    await _dm(member, dm_embed)

    info["decision"] = "accepted"
    info["decided_by"] = str(interaction.user)
    save(TICKETS_FILE, data)

    await _do_close(interaction.channel, interaction.user)


async def _reject_app(interaction: discord.Interaction, reason: str):
    data, info = _get_ticket(interaction.channel.id)
    if not info or not info.get("open"):
        await interaction.response.send_message("Это не активный тикет.", ephemeral=True)
        return
    if not _is_staff(interaction.user):
        await interaction.response.send_message("Решать по заявке может только стафф.", ephemeral=True)
        return

    await interaction.response.defer()
    guild = interaction.guild
    member = guild.get_member(int(info["user_id"]))
    role_name = (info.get("fields") or {}).get("__role", "—")

    embed = discord.Embed(
        title="❌ Заявка отклонена",
        description=f"Роль: **{role_name}**\nПричина: {reason}",
        color=0xed4245,
        timestamp=datetime.datetime.now(),
    )
    embed.set_footer(text=f"Отклонил: {interaction.user}")
    await interaction.channel.send(embed=embed)

    dm_embed = discord.Embed(
        title="❌ Заявка отклонена",
        description=(
            f"Твоя заявка на роль **{role_name}** на сервере **{guild.name}** отклонена.\n\n"
            f"**Причина:** {reason}\n\n"
            "Можешь попробовать позже — например, когда подрастёт активность."
        ),
        color=0xed4245,
    )
    sent = await _dm(member, dm_embed)
    if not sent:
        await interaction.followup.send(
            "Отказ записан, но в ЛС написать не смог — у автора закрыты личные сообщения.",
            ephemeral=True,
        )

    info["decision"] = "rejected"
    info["decision_reason"] = reason
    info["decided_by"] = str(interaction.user)
    save(TICKETS_FILE, data)

    await _do_close(interaction.channel, interaction.user)


class StaffAppActionView(discord.ui.View):
    """Кнопки в тикете-заявке."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success, custom_id="ticket_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _accept_app(interaction)

    @discord.ui.button(label="❌ Отклонить", style=discord.ButtonStyle.danger, custom_id="ticket_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _is_staff(interaction.user):
            await interaction.response.send_message("Решает только стафф.", ephemeral=True)
            return
        await _open_modal(interaction, RejectModal())

    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.secondary, custom_id="ticket_close_app")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_close(interaction.channel, interaction.user, interaction)


# ── Выбор типа тикета ─────────────────────────────────────────────────────────

async def _open_modal(interaction: discord.Interaction, modal: discord.ui.Modal):
    """Открывает модалку, а если не получилось — говорит почему, а не молчит."""
    try:
        await interaction.response.send_modal(modal)
    except Exception as e:
        log.exception("Не удалось открыть модалку %s", type(modal).__name__)
        msg = f"⚠️ Анкета не открылась: `{type(e).__name__}: {e}`"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            log.exception("Не смог сообщить об ошибке модалки")


class StaffRoleView(discord.ui.View):
    """Выбор роли перед заявкой: Хелпер или Модератор."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🧰 Хелпер", style=discord.ButtonStyle.primary, custom_id="staff_role_helper")
    async def helper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_modal(interaction, HelperAppModal())

    @discord.ui.button(label="🛡 Модератор", style=discord.ButtonStyle.success, custom_id="staff_role_moderator")
    async def moderator(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_modal(interaction, ModeratorAppModal())


class SingleTicketView(discord.ui.View):
    """Одна кнопка для конкретного типа тикета."""

    LABELS = {
        "question":  ("❓ Задать вопрос",    discord.ButtonStyle.primary),
        "staff_app": ("📋 Подать заявку",    discord.ButtonStyle.success),
        "complaint": ("⚠️ Написать жалобу", discord.ButtonStyle.danger),
    }
    MODALS = {
        "question":  QuestionModal,
        "complaint": ComplaintModal,
    }

    def __init__(self, ticket_type: str):
        super().__init__(timeout=None)
        label, style = self.LABELS[ticket_type]
        btn = discord.ui.Button(
            label=label,
            style=style,
            custom_id=f"ticket_single_{ticket_type}",
        )
        btn.callback = self._make_callback(ticket_type)
        self.add_item(btn)

    def _make_callback(self, ticket_type: str):
        async def callback(interaction: discord.Interaction):
            if ticket_type == "staff_app":
                await interaction.response.send_message(
                    "📋 Куда подаёшь заявку?",
                    view=StaffRoleView(),
                    ephemeral=True,
                )
                return
            await _open_modal(interaction, self.MODALS[ticket_type]())
        return callback


class TicketTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❓ Вопрос", style=discord.ButtonStyle.primary, custom_id="ticket_question")
    async def question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_modal(interaction, QuestionModal())

    @discord.ui.button(label="📋 Заявка в стафф", style=discord.ButtonStyle.success, custom_id="ticket_staff_app")
    async def staff_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📋 Куда подаёшь заявку?",
            view=StaffRoleView(),
            ephemeral=True,
        )

    @discord.ui.button(label="⚠️ Жалоба", style=discord.ButtonStyle.danger, custom_id="ticket_complaint")
    async def complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_modal(interaction, ComplaintModal())



# ── Ког ───────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        register_views(self.bot)

    @app_commands.command(name="setup_tickets", description="Поставить все три кнопки тикетов в один канал")
    @app_commands.describe(
        channel="Канал где будут все три кнопки",
        log_channel="Канал логов",
        category="Категория для тикетов (необязательно)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        log_channel: discord.TextChannel,
        category: discord.CategoryChannel = None,
    ):
        cfg = load(SETTINGS_FILE, {})
        gcfg = cfg.setdefault(str(interaction.guild.id), {})
        gcfg["ticket_log_channel_id"] = log_channel.id
        if category:
            gcfg["ticket_category_id"] = category.id
        save(SETTINGS_FILE, cfg)

        missing = _missing_send(channel, interaction.guild.me)
        if missing:
            await interaction.response.send_message(
                f"⚠️ Не могу писать в {channel.mention}. Не хватает прав: **{', '.join(missing)}**.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎫 Поддержка",
            description=(
                "Выбери тип обращения и заполни форму.\n"
                "Стафф ответит в ближайшее время.\n\n"
                "❓ **Вопрос** — общий вопрос к команде\n"
                "📋 **Заявка в стафф** — хочу вступить в команду\n"
                "⚠️ **Жалоба** — на участника или стафф"
            ),
            color=discord.Color.from_str("#a9c9ff"),
        )
        await channel.send(embed=embed, view=TicketTypeView())
        await interaction.response.send_message("✅ Готово!", ephemeral=True)

    @app_commands.command(name="post_question", description="Поставить кнопку «Задать вопрос» в канал")
    @app_commands.describe(channel="Канал", log_channel="Канал логов", category="Категория для тикетов")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_question(self, interaction: discord.Interaction, channel: discord.TextChannel, log_channel: discord.TextChannel, category: discord.CategoryChannel = None):
        await self._post_panel(
            interaction, channel, log_channel, category, "question",
            title="❓ Вопросы",
            description="Есть вопрос к стаффу? Нажми кнопку — мы ответим.",
            color=0xa9c9ff,
        )

    @app_commands.command(name="post_staff_app", description="Поставить кнопку «Заявка в стафф» в канал")
    @app_commands.describe(channel="Канал", log_channel="Канал логов", category="Категория для тикетов")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_staff_app(self, interaction: discord.Interaction, channel: discord.TextChannel, log_channel: discord.TextChannel, category: discord.CategoryChannel = None):
        await self._post_panel(
            interaction, channel, log_channel, category, "staff_app",
            title="📋 Заявка в стафф",
            description="Хочешь стать частью команды? Жми кнопку и выбери: Хелпер или Модератор.",
            color=0x57f287,
        )

    @app_commands.command(name="post_complaint", description="Поставить кнопку «Жалоба» в канал")
    @app_commands.describe(channel="Канал", log_channel="Канал логов", category="Категория для тикетов")
    @app_commands.checks.has_permissions(administrator=True)
    async def post_complaint(self, interaction: discord.Interaction, channel: discord.TextChannel, log_channel: discord.TextChannel, category: discord.CategoryChannel = None):
        await self._post_panel(
            interaction, channel, log_channel, category, "complaint",
            title="⚠️ Жалобы",
            description="Есть жалоба на участника или стафф? Нажми кнопку и опиши ситуацию.",
            color=0xed4245,
        )

    async def _post_panel(self, interaction, channel, log_channel, category, kind, *, title, description, color):
        """Общая логика постинга панели: сохранить конфиг, проверить права, отправить."""
        missing = _missing_send(channel, interaction.guild.me)
        if missing:
            await interaction.response.send_message(
                f"⚠️ Не могу писать в {channel.mention}. Не хватает прав: "
                f"**{', '.join(missing)}**.\n"
                "Проверь настройки канала для роли бота (или дай роль бота в правах канала).",
                ephemeral=True,
            )
            return

        self._save_cfg(interaction.guild.id, log_channel, category)
        embed = discord.Embed(title=title, description=description, color=color)
        try:
            await channel.send(embed=embed, view=SingleTicketView(kind))
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⚠️ Discord не дал отправить сообщение в {channel.mention} — прав нет у роли бота в этом канале.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(f"✅ Готово! Панель в {channel.mention}", ephemeral=True)


    @app_commands.command(name="check_perms", description="Проверить, хватает ли боту прав")
    @app_commands.describe(
        channel="Канал с кнопками (проверить)",
        log_channel="Канал логов (проверить)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def check_perms(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        log_channel: discord.TextChannel = None,
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        me = guild.me
        if me is None:
            await interaction.followup.send("⚠️ Не вижу себя на сервере.", ephemeral=True)
            return

        rows = []
        gp = me.guild_permissions
        rows.append(("Управлять каналами (сервер)", gp.manage_channels))
        rows.append(("Управлять сообщениями (сервер)", gp.manage_messages))

        targets = [ch for ch in (channel, log_channel) if ch]
        if not targets:
            cfg = _cfg(guild.id)
            for key in ("ticket_log_channel_id",):
                cid = cfg.get(key)
                ch = guild.get_channel(int(cid)) if cid else None
                if ch:
                    targets.append(ch)

        for ch in targets:
            p = ch.permissions_for(me)
            rows.append((f"{ch.name}: смотреть канал", p.view_channel))
            rows.append((f"{ch.name}: отправлять сообщения", p.send_messages))
            rows.append((f"{ch.name}: embed-ссылки", p.embed_links))
            rows.append((f"{ch.name}: читать историю", p.read_message_history))

        embed = discord.Embed(
            title="🔧 Права бота",
            description="\n".join(("✅ " if ok else "❌ ") + name for name, ok in rows),
            color=discord.Color.from_str("#a9c9ff"),
        )
        embed.set_footer(text="❌ — дай это право роли бота в настройках канала/сервера")
        await interaction.followup.send(embed=embed, ephemeral=True)

    def _save_cfg(self, guild_id: int, log_channel: discord.TextChannel, category: discord.CategoryChannel = None):
        cfg = load(SETTINGS_FILE, {})
        gcfg = cfg.setdefault(str(guild_id), {})
        gcfg["ticket_log_channel_id"] = log_channel.id
        if category:
            gcfg["ticket_category_id"] = category.id
        save(SETTINGS_FILE, cfg)

    @app_commands.command(name="close", description="Закрыть текущий тикет")
    async def close(self, interaction: discord.Interaction):
        await _do_close(interaction.channel, interaction.user, interaction)

    @app_commands.command(name="tickets", description="Список открытых тикетов")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def tickets_list(self, interaction: discord.Interaction):
        data = load(TICKETS_FILE, {})
        open_tickets = [(ch_id, info) for ch_id, info in data.items() if info.get("open")]
        if not open_tickets:
            await interaction.response.send_message("Открытых тикетов нет.", ephemeral=True)
            return
        lines = []
        for ch_id, info in open_tickets:
            ch = interaction.guild.get_channel(int(ch_id))
            tinfo = TICKET_TYPES.get(info.get("type", "question"), TICKET_TYPES["question"])
            ch_ref = ch.mention if ch else f"#{ch_id}"
            lines.append(f"{tinfo['emoji']} {ch_ref} — <@{info['user_id']}> ({info.get('created_at', '—')})")
        embed = discord.Embed(
            title=f"🎫 Открытые тикеты: {len(open_tickets)}",
            description="\n".join(lines),
            color=discord.Color.from_str("#a9c9ff"),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ticket_ratings", description="Рейтинг хелперов по оценкам из тикетов ⭐")
    async def ticket_ratings(self, interaction: discord.Interaction):
        rows = _ratings_summary(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(
                "Пока нет оценок. Они приходят авторам тикетов после закрытия.", ephemeral=True
            )
            return
        medals = ["🥇", "🥈", "🥉"] + ["⭐"] * 7
        lines = []
        for i, (helper_id, avg, count) in enumerate(rows[:10]):
            stars = "⭐" * max(1, min(5, round(avg)))
            lines.append(
                f"{medals[i]} <@{helper_id}> — {stars} **{avg:.1f}** ({count} оценок)"
            )
        embed = discord.Embed(
            title="⭐ Рейтинг хелперов",
            description="\n".join(lines),
            color=0xffd166,
        )
        embed.set_footer(text="Оценки ставят авторы тикетов после закрытия")
        await interaction.response.send_message(embed=embed)


# ── Регистрация persistent-вьюх (один раз, до подключения к гейтвею) ──────────

_VIEWS_DONE = False


def register_views(bot: commands.Bot):
    """Регистрирует кнопки, чтобы они работали после рестарта бота."""
    global _VIEWS_DONE
    try:
        bot.add_view(TicketTypeView())
        bot.add_view(TicketCloseView())
        bot.add_view(StaffRoleView())
        bot.add_view(AnswerView())
        bot.add_view(StaffAppActionView())
        for t in ("question", "staff_app", "complaint"):
            bot.add_view(SingleTicketView(t))
        _rearm_rating_views(bot)
        if not _VIEWS_DONE:
            _VIEWS_DONE = True
            log.info("Тикет-кнопки зарегистрированы")
    except Exception:
        log.exception("Не удалось зарегистрировать persistent-вьюхи")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
    register_views(bot)

