# -*- coding: utf-8 -*-
"""Тикеты: вопрос, заявка в стафф, жалоба."""

import datetime
import logging
import discord
from discord import app_commands
from discord.ext import commands

from storage import load, save

log = logging.getLogger(__name__)

TICKETS_FILE = "tickets.json"
SETTINGS_FILE = "settings.json"

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
        label="Новичок не понял правила и злится. Что делаешь?",
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
        label="Участник оскорбляет людей в войсе. Твои действия?",
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
    target = category or guild
    if not target.permissions_for(guild.me).manage_channels:
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

    await channel.send(content=member.mention, embed=embed, view=TicketCloseView())

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
            await log_ch.send(embed=log_embed)

    import asyncio
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Тикет закрыт {closer}")
    except discord.HTTPException:
        pass


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


# ── Регистрация persistent-вьюх (один раз, до подключения к гейтвею) ──────────

_VIEWS_DONE = False


def register_views(bot: commands.Bot):
    """Регистрирует кнопки, чтобы они работали после рестарта бота."""
    global _VIEWS_DONE
    if _VIEWS_DONE:
        return
    try:
        bot.add_view(TicketTypeView())
        bot.add_view(TicketCloseView())
        bot.add_view(StaffRoleView())
        for t in ("question", "staff_app", "complaint"):
            bot.add_view(SingleTicketView(t))
        _VIEWS_DONE = True
        log.info("Тикет-кнопки зарегистрированы")
    except Exception:
        log.exception("Не удалось зарегистрировать persistent-вьюхи")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
    register_views(bot)

