# -*- coding: utf-8 -*-
"""Тикеты: кнопка создаёт приватный канал, стафф отвечает, /close закрывает."""

import datetime

import discord
from discord import app_commands
from discord.ext import commands

from storage import load, save

TICKETS_FILE = "tickets.json"

# Роли, которые видят тикеты (id сервера Roet)
STAFF_ROLE_IDS = [
    1573422779376865280,  # Хелпер
    1573422776919007424,  # Модератор
    1573680792679489556,  # Старший модератор
    1573422768421077063,  # Администратор
    1573680796475195482,  # Главный администратор
    1573422762205257763,  # Владелец
    1573680800233426984,  # Владелица
]


def _now_str():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


def _is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.id in STAFF_ROLE_IDS for r in member.roles)


# --- Persistent Views ---

class TicketOpenView(discord.ui.View):
    """Кнопка «Создать тикет» в канале."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📩 Создать тикет",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_open",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user

        # Проверить, нет ли уже открытого тикета
        data = load(TICKETS_FILE, {})
        for ch_id, info in data.items():
            if str(info.get("user_id")) == str(member.id) and info.get("open"):
                ch = guild.get_channel(int(ch_id))
                if ch:
                    await interaction.followup.send(
                        f"У тебя уже есть открытый тикет: {ch.mention}", ephemeral=True
                    )
                    return

        # Найти категорию тикетов (или создать без категории)
        cfg = load("settings.json", {})
        cat_id = cfg.get("ticket_category_id")
        category = guild.get_channel(int(cat_id)) if cat_id else None

        # Права канала: только пользователь и стафф
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
            ),
        }
        for rid in STAFF_ROLE_IDS:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

        safe_name = member.display_name.lower().replace(" ", "-")[:20]
        ch_name = f"тикет-{safe_name}"
        try:
            channel = await guild.create_text_channel(
                ch_name,
                category=category,
                overwrites=overwrites,
                reason=f"Тикет от {member}",
            )
        except discord.HTTPException as e:
            await interaction.followup.send(f"Не удалось создать канал: {e}", ephemeral=True)
            return

        # Сохранить тикет
        data[str(channel.id)] = {
            "user_id": member.id,
            "user_name": str(member),
            "open": True,
            "created_at": _now_str(),
        }
        save(TICKETS_FILE, data)

        # Первое сообщение в тикете
        embed = discord.Embed(
            title="🎫 Тикет открыт",
            description=(
                f"Привет, {member.mention}! Опиши свой вопрос, стафф скоро ответит.\n\n"
                f"Когда вопрос решён — нажми кнопку ниже или используй `/close`."
            ),
            color=discord.Color.from_str("#a9c9ff"),
            timestamp=datetime.datetime.now(),
        )
        embed.set_footer(text=f"Тикет создан • {member}")
        await channel.send(
            content=f"{member.mention}",
            embed=embed,
            view=TicketCloseView(),
        )

        log_ch = guild.get_channel(int(cfg.get("ticket_log_channel_id", 0) or 0))
        if log_ch:
            log_embed = discord.Embed(
                title="📩 Новый тикет",
                description=f"{member.mention} открыл тикет {channel.mention}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(),
            )
            await log_ch.send(embed=log_embed)

        await interaction.followup.send(f"Тикет создан: {channel.mention}", ephemeral=True)


class TicketCloseView(discord.ui.View):
    """Кнопка «Закрыть тикет» внутри канала тикета."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Закрыть тикет",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_close(interaction.channel, interaction.user, interaction)


async def _do_close(channel: discord.TextChannel, closer: discord.Member, interaction=None):
    data = load(TICKETS_FILE, {})
    info = data.get(str(channel.id))

    if not info or not info.get("open"):
        if interaction:
            await interaction.response.send_message("Это не активный тикет.", ephemeral=True)
        return

    # Закрыть может владелец тикета или стафф
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

    embed = discord.Embed(
        title="🔒 Тикет закрыт",
        description=f"Тикет закрыт пользователем {closer.mention}.\nКанал будет удалён через 5 секунд.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(),
    )
    await channel.send(embed=embed)

    cfg = load("settings.json", {})
    log_ch_id = cfg.get("ticket_log_channel_id")
    if log_ch_id:
        log_ch = channel.guild.get_channel(int(log_ch_id))
        if log_ch:
            log_embed = discord.Embed(
                title="🔒 Тикет закрыт",
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


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketOpenView())
        self.bot.add_view(TicketCloseView())

    @app_commands.command(name="setup_tickets", description="Поставить кнопку тикетов в канал")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(
        self,
        interaction: discord.Interaction,
        log_channel: discord.TextChannel,
        category: discord.CategoryChannel = None,
    ):
        cfg = load("settings.json", {})
        cfg["ticket_log_channel_id"] = log_channel.id
        if category:
            cfg["ticket_category_id"] = category.id
        save("settings.json", cfg)

        embed = discord.Embed(
            title="🎫 Поддержка",
            description=(
                "Если у тебя есть вопрос или проблема — создай тикет.\n"
                "Стафф ответит в течение нескольких минут."
            ),
            color=discord.Color.from_str("#a9c9ff"),
        )
        await interaction.channel.send(embed=embed, view=TicketOpenView())
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
            ch_ref = ch.mention if ch else f"#{ch_id}"
            lines.append(f"{ch_ref} — <@{info['user_id']}> ({info.get('created_at', '—')})")
        embed = discord.Embed(
            title=f"🎫 Открытые тикеты: {len(open_tickets)}",
            description="\n".join(lines),
            color=discord.Color.from_str("#a9c9ff"),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
