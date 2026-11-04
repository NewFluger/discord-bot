import asyncio
import os
import random

import discord
from discord import app_commands
from discord.ext import commands

from utils import parse_duration

MAX_REMINDER_SECONDS = 30 * 24 * 3600  # 30 дней

EIGHT_BALL_ANSWERS = (
    "Бесспорно.",
    "Да — определённо.",
    "Можешь положиться на это.",
    "Точно да.",
    "Скорее всего.",
    "Хорошие перспективы.",
    "Да.",
    "Знаки говорят «да».",
    "Пока неясно, попробуй ещё раз.",
    "Спроси позже.",
    "Лучше не рассказывать.",
    "Сейчас нельзя предсказать.",
    "Сконцентрируйся и спроси снова.",
    "Не рассчитывай на это.",
    "Мой ответ — нет.",
    "Вряд ли.",
    "Скорее всего нет.",
    "Перспективы не очень.",
    "Весьма сомнительно.",
    "Нет, и не надейся.",
)


def _env_int(name: str) -> int:
    """Читает int из переменной окружения (0, если пусто или мусор)."""
    try:
        return int((os.getenv(name) or "0").strip())
    except ValueError:
        return 0


class Utility(commands.Cog):
    """Утилиты и развлечения."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._reminders: set[asyncio.Task] = set()
        self.owner_id = _env_int("OWNER_ID")
        self.ghost_channel_id = _env_int("GHOST_CHANNEL_ID")

    @app_commands.command(name="say", description="Повторить сообщение от имени бота")
    @app_commands.describe(text="Текст сообщения")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.send_message(text)

    @app_commands.command(
        name="ghost",
        description="Тайно отправить текст в канал от имени бота (используй в ЛС боту)",
    )
    @app_commands.describe(text="Текст сообщения")
    async def ghost(self, interaction: discord.Interaction, text: str) -> None:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "⛔ Эта команда доступна только владельцу.", ephemeral=True
            )
            return
        if not self.ghost_channel_id:
            await interaction.response.send_message(
                "❌ Не задан GHOST_CHANNEL_ID в .env.", ephemeral=True
            )
            return

        try:
            channel = await self.bot.fetch_channel(self.ghost_channel_id)
        except (discord.NotFound, discord.Forbidden):
            await interaction.response.send_message(
                "❌ Канал не найден или у бота нет к нему доступа.", ephemeral=True
            )
            return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "❌ Это не текстовый канал.", ephemeral=True
            )
            return

        try:
            await channel.send(text)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Нет прав писать в этот канал.", ephemeral=True
            )
            return

        note = "✅ Отправлено в канал."
        if interaction.guild is not None:
            note += (
                "\n⚠️ На сервере видно, кто вызвал команду. "
                "Для скрытности пиши `/ghost` **в ЛС боту**."
            )
        await interaction.response.send_message(note, ephemeral=True)

    @app_commands.command(name="poll", description="Создать опрос (✅/❌)")
    @app_commands.describe(question="Вопрос опроса")
    async def poll(self, interaction: discord.Interaction, question: str) -> None:
        embed = discord.Embed(
            title="📊 Опрос",
            description=question,
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Автор: {interaction.user}")
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        await message.add_reaction("✅")
        await message.add_reaction("❌")

    @app_commands.command(name="remind", description="Напомнить о чём-либо")
    @app_commands.describe(
        duration="Через сколько: 10m, 1h30m, 2d",
        text="О чём напомнить",
    )
    async def remind(
        self, interaction: discord.Interaction, duration: str, text: str
    ) -> None:
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        if seconds > MAX_REMINDER_SECONDS:
            await interaction.response.send_message(
                "❌ Слишком долго — максимум 30 дней.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"⏰ Напомню через **{duration}**: {text}"
        )

        channel = interaction.channel
        user = interaction.user

        async def _remind() -> None:
            await asyncio.sleep(seconds)
            if channel is not None:
                await channel.send(f"⏰ {user.mention}, напоминание: **{text}**")

        task = asyncio.create_task(_remind())
        self._reminders.add(task)
        task.add_done_callback(self._reminders.discard)

    @app_commands.command(name="8ball", description="Магический шар ответов")
    @app_commands.describe(question="Вопрос да/нет")
    async def eight_ball(
        self, interaction: discord.Interaction, question: str
    ) -> None:
        embed = discord.Embed(
            title="🎱 Магический шар",
            description=(
                f"**Вопрос:** {question}\n"
                f"**Ответ:** {random.choice(EIGHT_BALL_ANSWERS)}"
            ),
            color=discord.Color.dark_purple(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coinflip", description="Подбросить монетку")
    async def coinflip(self, interaction: discord.Interaction) -> None:
        result = random.choice(("Орёл", "Решка"))
        await interaction.response.send_message(f"🪙 **{result}**")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
