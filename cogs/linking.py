"""Привязка Minecraft ↔ Discord: двухэтапная (код из игры → ввод в Discord).

Как это работает:
  1. Игрок в майнкрафте пишет /link → плагин шлёт код в скрытый канал-мост
     (LINK_CHANNEL_ID) через webhook.
  2. Игрок в Discord пишет /link код:XXXXXX → бот находит код, привязывает
     аккаунт (конфиг хранится в config.json репозитория) и удаляет код.
  3. Плагин периодически читает config.json и применяет роли → ранги в игре.

Отвязка: /unlink в Discord или /unlink в майнкрафте (плагин шлёт запрос
в канал-мост, бот его обрабатывает).
"""
from __future__ import annotations

import copy
import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("bot")

# Скрытый канал-мост: плагин шлёт сюда коды/запросы через webhook,
# бот публикует подтверждения.
LINK_CHANNEL_ID = 1567518850600276220

CODE_EMBED_TITLE = "Привязка аккаунта"
UNLINK_REQUEST_TITLE = "Запрос на отвязку"
CODE_TTL = timedelta(minutes=10)


def _embed_fields(emb: discord.Embed) -> dict[str, str]:
    return {f.name: (f.value or "").strip() for f in emb.fields}


class Linking(commands.Cog):
    """Двухэтапная привязка Minecraft-аккаунтов."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _links(self, guild_id: int) -> dict:
        guild_cfg = self.bot.config.setdefault(str(guild_id), {})
        return guild_cfg.setdefault("mc_links", {})

    async def _bridge(self, guild: discord.Guild):
        channel = guild.get_channel(LINK_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(LINK_CHANNEL_ID)
            except discord.DiscordException:
                log.warning("Канал-мост %s не найден", LINK_CHANNEL_ID)
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    # ----------------------------------------------------------- команды

    @app_commands.command(
        name="link",
        description="Привязать Minecraft-аккаунт: введи код, полученный в игре",
    )
    @app_commands.describe(code="Код из игры (сначала напиши /link в майнкрафте)")
    async def link(self, interaction: discord.Interaction, code: str) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return

        code = code.strip().upper()
        if not code or len(code) > 16:
            await interaction.response.send_message("❌ Некорректный код.", ephemeral=True)
            return

        # Дальше — сетевые операции (канал-мост, история, сохранение),
        # отвечаем сразу defer, а результат — followup'ом
        await interaction.response.defer(ephemeral=True)

        bridge = await self._bridge(guild)
        if bridge is None:
            await interaction.followup.send(
                "❌ Канал привязки недоступен — сообщи администрации.", ephemeral=True
            )
            return

        # Этап 1 → 2: ищем сообщение плагина с этим кодом
        target: discord.Message | None = None
        fields: dict[str, str] | None = None
        try:
            async for message in bridge.history(limit=50):
                for emb in message.embeds:
                    if emb.title != CODE_EMBED_TITLE:
                        continue
                    found = _embed_fields(emb)
                    if found.get("Код", "").upper() == code:
                        target, fields = message, found
                        break
                if target is not None:
                    break
        except discord.HTTPException:
            log.exception("Не удалось прочитать канал-мост")
            await interaction.followup.send(
                "⚠️ Канал привязки недоступен — попробуй позже.", ephemeral=True
            )
            return

        if target is None or fields is None:
            await interaction.followup.send(
                "❌ Код не найден или уже использован. Получи новый: `/link` в майнкрафте.",
                ephemeral=True,
            )
            return

        if discord.utils.utcnow() - target.created_at > CODE_TTL:
            try:
                await target.delete()
            except discord.HTTPException:
                pass
            await interaction.followup.send(
                "⏰ Код истёк (10 минут). Получи новый: `/link` в майнкрафте.",
                ephemeral=True,
            )
            return

        nick = fields.get("Игрок", "")
        uuid = fields.get("UUID", "")
        if not nick:
            await interaction.followup.send(
                "❌ В коде не указан ник — сгенерируй новый код.", ephemeral=True
            )
            return

        links = self._links(guild.id)
        previous = copy.deepcopy(links)

        # Один Minecraft-аккаунт — один Discord: снимаем привязку у прежнего владельца
        if uuid:
            for other in list(links):
                entry = links[other]
                if other != str(member.id) and str(entry.get("uuid", "")).lower() == uuid.lower():
                    links.pop(other)
                    log.info("Привязка %s перепривязана (Discord %s отвязан)", nick, other)

        links[str(member.id)] = {
            "nick": nick,
            "uuid": uuid,
            "roles": [str(r.id) for r in member.roles if not r.is_default()],
            "at": discord.utils.utcnow().isoformat(),
        }

        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить привязку")
            links.clear()
            links.update(previous)
            await interaction.followup.send(
                "⚠️ Не удалось сохранить привязку — попробуй через минуту.",
                ephemeral=True,
            )
            return

        # Подтверждение в мост + удаление кода (одноразовый)
        confirm = discord.Embed(
            title="✅ Привязка подтверждена",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
            fields=[
                discord.EmbedField(name="Игрок", value=nick, inline=True),
                discord.EmbedField(name="UUID", value=uuid or "—", inline=True),
                discord.EmbedField(name="Discord", value=f"{member} ({member.id})", inline=False),
            ],
        )
        try:
            await bridge.send(embed=confirm)
        except discord.HTTPException:
            log.exception("Не удалось отправить подтверждение в мост")
        try:
            await target.delete()
        except discord.HTTPException:
            log.exception("Не удалось удалить использованный код")

        await interaction.followup.send(
            f"✅ Привязано: **{nick}** → {member.mention}\n"
            "Роли Discord будут синхронизированы с рангами в Minecraft автоматически.",
            ephemeral=True,
        )

    @app_commands.command(name="unlink", description="Отвязать Minecraft-аккаунт")
    async def unlink(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return

        links = self._links(guild.id)
        uid = str(interaction.user.id)
        entry = links.get(uid)
        if entry is None:
            await interaction.response.send_message(
                "ℹ️ У тебя нет привязанного аккаунта Minecraft.", ephemeral=True
            )
            return

        # Сохранение конфига — в GitHub, отвечаем сразу defer
        await interaction.response.defer(ephemeral=True)

        previous = copy.deepcopy(links)
        links.pop(uid)
        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить отвязку")
            links.clear()
            links.update(previous)
            await interaction.followup.send(
                "⚠️ Не удалось сохранить — попробуй позже.", ephemeral=True
            )
            return

        bridge = await self._bridge(guild)
        if bridge is not None:
            embed = discord.Embed(
                title="❌ Отвязка выполнена",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
                fields=[
                    discord.EmbedField(name="Игрок", value=entry.get("nick", "—"), inline=True),
                    discord.EmbedField(name="UUID", value=entry.get("uuid", "—"), inline=True),
                ],
            )
            try:
                await bridge.send(embed=embed)
            except discord.HTTPException:
                log.exception("Не удалось отправить отвязку в мост")

        await interaction.followup.send(
            f"✅ **{entry.get('nick', '?')}** отвязан. Ранг из Discord будет снят.",
            ephemeral=True,
        )

    # ------------------------------------------------- события моста/ролей

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Запрос на отвязку из игры (через webhook плагина)."""
        if message.channel.id != LINK_CHANNEL_ID or not message.webhook_id:
            return
        guild = message.guild
        if guild is None:
            return

        for emb in message.embeds:
            if emb.title != UNLINK_REQUEST_TITLE:
                continue
            fields = _embed_fields(emb)
            uuid = str(fields.get("UUID", "")).lower()
            nick = fields.get("Игрок", "—")

            links = self._links(guild.id)
            victim = next(
                (
                    did
                    for did, entry in links.items()
                    if uuid and str(entry.get("uuid", "")).lower() == uuid
                ),
                None,
            )
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            if victim is None:
                continue  # уже отвязан из Discord — просто забрали запрос

            previous = copy.deepcopy(links)
            links.pop(victim)
            try:
                await self.bot.save_config()
            except Exception:
                log.exception("Не удалось сохранить отвязку из игры")
                links.clear()
                links.update(previous)
                continue

            confirm = discord.Embed(
                title="❌ Отвязка выполнена (запрос из игры)",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
                fields=[
                    discord.EmbedField(name="Игрок", value=nick, inline=True),
                    discord.EmbedField(name="UUID", value=fields.get("UUID", "—"), inline=True),
                ],
            )
            try:
                await message.channel.send(embed=confirm)
            except discord.HTTPException:
                log.exception("Не удалось подтвердить отвязку в мосте")
            log.info("Отвязка из игры: %s (Discord %s)", nick, victim)
            break

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Роли изменились у привязанного игрока → обновляем конфиг для плагина."""
        if {r.id for r in before.roles} == {r.id for r in after.roles}:
            return
        links = self._links(after.guild.id)
        entry = links.get(str(after.id))
        if entry is None:
            return
        entry["roles"] = [str(r.id) for r in after.roles if not r.is_default()]
        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить роли привязанного игрока")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Linking(bot))
