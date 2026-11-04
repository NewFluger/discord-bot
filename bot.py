import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import storage

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = os.getenv("GUILD_ID", "").strip()
# Локальный тест через VPN/прокси (на AWS не задаётся — там прямой доступ)
PROXY = os.getenv("BOT_PROXY", "").strip()

if PROXY:
    import aiohttp

    _original_ws_connect = aiohttp.ClientSession.ws_connect

    async def _ws_connect_via_proxy(self, url, **kwargs):
        if kwargs.get("proxy") is None:
            kwargs["proxy"] = PROXY
        return await _original_ws_connect(self, url, **kwargs)

    aiohttp.ClientSession.ws_connect = _ws_connect_via_proxy
    log_setup = f"Прокси: {PROXY}"
else:
    log_setup = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot")

EXTENSIONS = (
    "cogs.general",
    "cogs.moderation",
    "cogs.utility",
    "cogs.settings",
    "cogs.tickets",
)


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Единая обработка ошибок slash-команд."""
    original = getattr(error, "original", error)

    if isinstance(original, app_commands.MissingPermissions):
        text = "❌ У вас недостаточно прав для этой команды."
    elif isinstance(original, app_commands.BotMissingPermissions):
        text = "❌ У бота не хватает прав. Проверь роль бота на сервере."
    elif isinstance(original, ValueError) and str(original):
        text = f"❌ {original}"
    else:
        log.exception("Ошибка в команде %s", interaction.command, exc_info=original)
        text = "⚠️ Произошла ошибка при выполнении команды."

    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


class HelperBot(commands.Bot):
    """Бот-помощник: инфо, модерация, утилиты."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True  # требует включённого Server Members Intent в портале
        proxy_options = {"proxy": PROXY} if PROXY else {}
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
            **proxy_options,
        )
        # Конфигурация (автороль, счётчики тикетов):
        # локально — config.json, на Actions — коммит в репозиторий
        self.config: dict = storage.load_local()

    async def save_config(self) -> None:
        """Сохраняет конфигурацию (в репозиторий на Actions или локальный файл)."""
        await storage.save(self.config)

    async def setup_hook(self) -> None:
        self.tree.on_error = on_app_command_error

        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info("Загружено расширение: %s", ext)

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Команды привязаны к серверу %s: %d", GUILD_ID, len(synced))
            global_synced = await self.tree.sync()
            log.info(
                "Глобальная синхронизация: %d (для ЛС; до ~1 часа)",
                len(global_synced),
            )
        else:
            synced = await self.tree.sync()
            log.info("Синхронизация команд: %d (до ~1 часа)", len(synced))

    async def on_ready(self) -> None:
        if self.user:
            log.info("Бот запущен: %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="за сервером"
            )
        )


def main() -> None:
    if not TOKEN:
        raise SystemExit("Не задан DISCORD_TOKEN — заполни файл .env")
    bot = HelperBot()
    bot.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
