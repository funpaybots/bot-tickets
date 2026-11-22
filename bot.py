# -*- coding: utf-8 -*-
import asyncio, json, logging, os, sys
import discord
from discord.ext import commands

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
    force=True,
)
log = logging.getLogger(__name__)


def _load_token():
    token = os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if token:
        return token.strip()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return str(json.load(f).get("token", "")).strip()
        except Exception:
            pass
    log.error("Токен не найден. Задай DISCORD_BOT_TOKEN или config.json")
    sys.exit(1)


intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def on_ready():
    guild_id = int(os.environ.get("GUILD_ID", "0"))
    if not guild_id and os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                guild_id = int(json.load(f).get("guild_id", 0))
        except Exception:
            pass
    if not guild_id:
        guild_id = 1573386089467748482
    guild = discord.Object(id=guild_id)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    log.info("Tickets-бот запущен: %s | Синкнуто %d команд на гильдию %d", bot.user, len(synced), guild_id)


async def main():
    async with bot:
        try:
            await bot.load_extension("cogs.tickets")
            log.info("Cog tickets загружен")
        except Exception as e:
            log.error("ОШИБКА загрузки cog: %s", e)
            raise
        await bot.start(_load_token())


if __name__ == "__main__":
    asyncio.run(main())
