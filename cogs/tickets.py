# -*- coding: utf-8 -*-
"""Тикеты: вопрос, заявка в стафф, жалоба."""

import datetime
import discord
from discord import app_commands
from discord.ext import commands

from storage import load, save

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
        await _create_ticket(interaction, "question", {"question": self.question.value})


class StaffAppModal(discord.ui.Modal, title="📋 Заявка в стафф"):
    age = discord.ui.TextInput(label="Возраст", placeholder="например: 17", max_length=3)
    timezone = discord.ui.TextInput(label="Часовой пояс / активность", placeholder="например: МСК, онлайн 18:00–23:00", max_length=100)
    experience = discord.ui.TextInput(
        label="Опыт модерации",
        placeholder="Был ли опыт на других серверах?",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )
    why = discord.ui.TextInput(
        label="Почему хочешь в стафф?",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=500,
    )
    role = discord.ui.TextInput(
        label="На какую роль подаёшь заявку?",
        placeholder="Хелпер / Модератор",
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await _create_ticket(interaction, "staff_app", {
            "age": self.age.value,
            "timezone": self.timezone.value,
            "experience": self.experience.value,
            "why": self.why.value,
            "role": self.role.value,
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
        await _create_ticket(interaction, "complaint", {
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
        embed.description = "Заявка принята. Стафф рассмотрит её и даст ответ."
        embed.add_field(name="Возраст", value=fields["age"], inline=True)
        embed.add_field(name="Часовой пояс", value=fields["timezone"], inline=True)
        embed.add_field(name="На роль", value=fields["role"], inline=True)
        embed.add_field(name="Опыт", value=fields["experience"], inline=False)
        embed.add_field(name="Почему хочешь в стафф", value=fields["why"], inline=False)

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

class TicketTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❓ Вопрос", style=discord.ButtonStyle.primary, custom_id="ticket_question")
    async def question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuestionModal())

    @discord.ui.button(label="📋 Заявка в стафф", style=discord.ButtonStyle.success, custom_id="ticket_staff_app")
    async def staff_app(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StaffAppModal())

    @discord.ui.button(label="⚠️ Жалоба", style=discord.ButtonStyle.danger, custom_id="ticket_complaint")
    async def complaint(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ComplaintModal())


# ── Ког ───────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketTypeView())
        self.bot.add_view(TicketCloseView())

    @app_commands.command(name="setup_tickets", description="Поставить панель тикетов в канал")
    @app_commands.describe(
        channel="Канал где будет кнопка тикетов",
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
