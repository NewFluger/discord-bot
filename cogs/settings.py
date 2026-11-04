"""Авто-роль для новых участников (команды /autorole)."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("bot")


class Settings(commands.Cog):
    """Настройки сервера: авто-роль новеньким при входе."""

    autorole = app_commands.Group(
        name="autorole",
        description="Роль, которая выдаётся новеньким при входе на сервер",
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _current_role_id(self, guild_id: int) -> int | None:
        entry = self.bot.config.get(str(guild_id), {})
        raw = entry.get("autorole")
        if not raw:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            log.warning("autorole: некорректный ID в конфиге: %r", raw)
            return None

    @autorole.command(name="set", description="Выдавать эту роль каждому новому участнику")
    @app_commands.describe(role="Роль, которую получат новенькие")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        if role.is_default():
            await interaction.response.send_message(
                "❌ Нельзя выдавать @everyone.", ephemeral=True
            )
            return
        if role.managed:
            await interaction.response.send_message(
                "❌ Это служебная роль (бот или буст) — её нельзя выдать вручную.",
                ephemeral=True,
            )
            return
        me = guild.me
        if me is not None and role >= me.top_role:
            await interaction.response.send_message(
                "❌ Роль должна быть **ниже** верхней роли бота, иначе бот её не выдаст.",
                ephemeral=True,
            )
            return

        self.bot.config.setdefault(str(guild.id), {})["autorole"] = str(role.id)
        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить autorole в хранилище")
            await interaction.response.send_message(
                "⚠️ Роль запомнена до перезапуска, но сохранить её не удалось — "
                "попробуй ещё раз чуть позже.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ Каждый новенький теперь получит роль {role.mention}.",
            ephemeral=True,
        )

    @autorole.command(name="show", description="Показать текущую авто-роль")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def show(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        role_id = self._current_role_id(guild.id) if guild else None
        if role_id is None:
            await interaction.response.send_message(
                "ℹ️ Автороль не настроена. Задай: `/autorole set роль:...`",
                ephemeral=True,
            )
            return
        role = guild.get_role(role_id) if guild else None
        if role is None:
            await interaction.response.send_message(
                f"⚠️ Сохранённая роль (ID `{role_id}`) удалена с сервера — задай новую: "
                "`/autorole set роль:...`",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"ℹ️ Новеньким выдаётся: {role.mention}", ephemeral=True
        )

    @autorole.command(name="off", description="Перестать выдавать роль при входе")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def off(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        entry = self.bot.config.get(str(guild.id), {})
        if not entry.pop("autorole", None):
            await interaction.response.send_message(
                "ℹ️ Автороль и так не настроена.", ephemeral=True
            )
            return
        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить конфиг после off")
        await interaction.response.send_message(
            "✅ Выдача роли при входе отключена.", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        role_id = self._current_role_id(member.guild.id)
        if role_id is None:
            return
        role = member.guild.get_role(role_id)
        if role is None:
            log.warning(
                "Автороль: роль %s не найдена на сервере %s", role_id, member.guild.id
            )
            return
        me = member.guild.me
        if me is not None and role >= me.top_role:
            log.warning("Автороль: роль %s выше роли бота — пропуск", role.name)
            return
        try:
            await member.add_roles(role, reason="Авто-роль для новеньких")
            log.info("Новенькому %s выдана роль %s", member, role.name)
        except discord.HTTPException:
            log.exception("Не удалось выдать роль %s участнику %s", role.name, member)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
