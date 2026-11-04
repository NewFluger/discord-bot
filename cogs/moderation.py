from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from utils import parse_duration

MAX_TIMEOUT_SECONDS = 28 * 24 * 3600  # лимит Discord


def _check_target(interaction: discord.Interaction, member: discord.Member) -> str | None:
    """Проверка иерархии. Возвращает текст ошибки или None."""
    guild = interaction.guild
    if guild is None:
        return "Команда только на сервере."
    if member.id == interaction.user.id:
        return "Нельзя применять команду к себе."
    if interaction.client.user and member.id == interaction.client.user.id:
        return "Нельзя применять команду к боту."
    if member.id == guild.owner_id:
        return "Нельзя применять команду к владельцу сервера."
    if (
        interaction.user.id != guild.owner_id
        and member.top_role >= interaction.user.top_role
    ):
        return "Участник не ниже тебя по ролям."
    me = guild.me
    if me is not None and guild.owner_id != me.id and member.top_role >= me.top_role:
        return "Роль участника не ниже роли бота — я не смогу действовать."
    return None


class Moderation(commands.Cog):
    """Модерация сервера."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="kick", description="Кикнуть участника с сервера")
    @app_commands.describe(member="Кого кикнуть", reason="Причина")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Не указана",
    ) -> None:
        problem = _check_target(interaction, member)
        if problem:
            await interaction.response.send_message(f"❌ {problem}", ephemeral=True)
            return
        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Нет прав: проверь роль бота и свою иерархию.", ephemeral=True
            )
            return

        embed = discord.Embed(title="👢 Участник кикнут", color=discord.Color.orange())
        embed.add_field(name="Участник", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="Модератор", value=str(interaction.user), inline=True)
        embed.add_field(name="Причина", value=reason, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ban", description="Забанить участника")
    @app_commands.describe(member="Кого забанить", reason="Причина")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Не указана",
    ) -> None:
        problem = _check_target(interaction, member)
        if problem:
            await interaction.response.send_message(f"❌ {problem}", ephemeral=True)
            return
        try:
            await member.ban(reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Нет прав: проверь роль бота и свою иерархию.", ephemeral=True
            )
            return

        embed = discord.Embed(title="🔨 Участник забанен", color=discord.Color.red())
        embed.add_field(name="Участник", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="Модератор", value=str(interaction.user), inline=True)
        embed.add_field(name="Причина", value=reason, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unban", description="Снять бан с пользователя")
    @app_commands.describe(user="Пользователь", reason="Причина")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str = "Не указана",
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Команда только на сервере.", ephemeral=True
            )
            return
        try:
            await guild.unban(user, reason=reason)
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ Этот пользователь не в бане.", ephemeral=True
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Нет прав разбанить.", ephemeral=True
            )
            return

        embed = discord.Embed(title="🔓 Бан снят", color=discord.Color.green())
        embed.add_field(name="Пользователь", value=f"{user} (`{user.id}`)", inline=False)
        embed.add_field(name="Модератор", value=str(interaction.user), inline=True)
        embed.add_field(name="Причина", value=reason, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="timeout", description="Таймаут (мьют) участника")
    @app_commands.describe(
        member="Участник",
        duration="Длительность: 10m, 1h, 1d (максимум 28d)",
        reason="Причина",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str = "Не указана",
    ) -> None:
        problem = _check_target(interaction, member)
        if problem:
            await interaction.response.send_message(f"❌ {problem}", ephemeral=True)
            return
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        if seconds > MAX_TIMEOUT_SECONDS:
            await interaction.response.send_message(
                "❌ Максимальный таймаут — 28 дней.", ephemeral=True
            )
            return
        try:
            await member.timeout(timedelta(seconds=seconds), reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Нет прав: проверь роль бота и свою иерархию.", ephemeral=True
            )
            return

        until = int((discord.utils.utcnow() + timedelta(seconds=seconds)).timestamp())
        embed = discord.Embed(title="🔇 Таймаут выдан", color=discord.Color.dark_red())
        embed.add_field(name="Участник", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="Длительность", value=duration, inline=True)
        embed.add_field(name="До", value=f"<t:{until}:R>", inline=True)
        embed.add_field(name="Модератор", value=str(interaction.user), inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="untimeout", description="Снять таймаут с участника")
    @app_commands.describe(member="Участник", reason="Причина")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Не указана",
    ) -> None:
        problem = _check_target(interaction, member)
        if problem:
            await interaction.response.send_message(f"❌ {problem}", ephemeral=True)
            return
        try:
            await member.timeout(None, reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Нет прав: проверь роль бота и свою иерархию.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔊 Таймаут снят", color=discord.Color.green()
        )
        embed.add_field(name="Участник", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="Модератор", value=str(interaction.user), inline=True)
        embed.add_field(name="Причина", value=reason, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clear", description="Удалить сообщения из канала")
    @app_commands.describe(amount="Сколько удалить (1–100)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def clear(
        self, interaction: discord.Interaction, amount: int = 10
    ) -> None:
        if not 1 <= amount <= 100:
            await interaction.response.send_message(
                "❌ Укажи число от 1 до 100.", ephemeral=True
            )
            return
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "❌ Только в текстовых каналах.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await channel.purge(limit=amount)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Нет прав удалять сообщения (нужен Manage Messages).",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"🗑 Удалено сообщений: **{len(deleted)}**", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
