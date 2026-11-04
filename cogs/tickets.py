"""Тикет-система: панель, создание, пинг модераторов, закрытие и удаление тикетов."""
from __future__ import annotations

import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("bot")

CREATE_ID = "ticket:create"
CLOSE_ID = "ticket:close"
DELETE_ID = "ticket:delete"

CATEGORY_NAME = "🎫 Тикеты"
# тикет-12 / закрыт-тикет-12
TICKET_RE = re.compile(r"^(?:закрыт-)?тикет-(\d+)$")
AUTHOR_RE = re.compile(r"\((\d+)\)\s*$")


def _is_staff(member: discord.Member) -> bool:
    """Модератор: владелец сервера или право «Управление каналами»."""
    return member.guild_permissions.manage_channels


def _author_id(channel: discord.abc.GuildChannel) -> int | None:
    """Достаёт ID автора тикета из topic канала."""
    match = AUTHOR_RE.search(getattr(channel, "topic", "") or "")
    return int(match.group(1)) if match else None


def _next_number(guild: discord.Guild, config: dict) -> int:
    scanned = 0
    for channel in guild.channels:
        match = TICKET_RE.match(channel.name)
        if match:
            scanned = max(scanned, int(match.group(1)))
    stored = config.get("ticket_counter", 0)
    try:
        stored = int(stored)
    except (TypeError, ValueError):
        stored = 0
    return max(scanned, stored) + 1


def _int_ids(raw: object) -> list[int]:
    ids: list[int] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


async def _create_ticket(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
        return
    author = interaction.user

    # Защита от спама: один открытый тикет на пользователя
    for channel in guild.text_channels:
        match = TICKET_RE.match(channel.name)
        if match and not channel.name.startswith("закрыт-"):
            if channel.overwrites_for(author).view_channel:
                await interaction.response.send_message(
                    f"⚠️ У тебя уже есть открытый тикет: {channel.mention}",
                    ephemeral=True,
                )
                return

    category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if category is None:
        try:
            category = await guild.create_category(
                CATEGORY_NAME, reason="Тикет-система: категория для тикетов"
            )
        except discord.HTTPException:
            log.exception("Не удалось создать категорию тикетов")
            await interaction.response.send_message(
                "❌ Не удалось создать категорию тикетов — проверь права бота.",
                ephemeral=True,
            )
            return

    config = interaction.client.config.setdefault(str(guild.id), {})
    number = _next_number(guild, config)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        author: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            embed_links=True,
            attach_files=True,
            use_external_emojis=True,
        ),
    }

    try:
        channel = await guild.create_text_channel(
            f"тикет-{number}",
            category=category,
            overwrites=overwrites,
            topic=f"Тикет #{number} — {author} ({author.id})",
            reason=f"Создан тикет #{number} для {author}",
        )
    except discord.HTTPException:
        log.exception("Не удалось создать канал тикета")
        await interaction.response.send_message(
            "❌ Не удалось создать канал тикета — попробуй позже.", ephemeral=True
        )
        return

    config["ticket_counter"] = number
    try:
        await interaction.client.save_config()
    except Exception:
        log.exception("Не удалось сохранить счётчик тикетов")

    embed = discord.Embed(
        title=f"🎫 Тикет #{number}",
        description=(
            f"{author.mention}, **опиши свою проблему или вопрос** — "
            "модераторы скоро ответят.\n\n"
            "Как только ты опишешь ситуацию, модераторы получат уведомление.\n"
            "Когда помощь больше не нужна, нажми **Закрыть тикет**."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"Автор: {author}")
    await channel.send(author.mention, embed=embed, view=TicketActionsView())
    await interaction.response.send_message(
        f"🎫 Тикет создан: {channel.mention}", ephemeral=True
    )


class TicketPanelView(discord.ui.View):
    """Кнопка на панели — постоянная (custom_id фиксированный)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Создать тикет",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id=CREATE_ID,
    )
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _create_ticket(interaction)


class TicketActionsView(discord.ui.View):
    """Кнопки внутри тикета: закрыть / удалить."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Закрыть тикет",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id=CLOSE_ID,
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if (
            guild is None
            or not isinstance(channel, discord.TextChannel)
            or not isinstance(interaction.user, discord.Member)
        ):
            await interaction.response.send_message("❌ Нельзя здесь.", ephemeral=True)
            return

        if channel.name.startswith("закрыт-"):
            await interaction.response.send_message(
                "ℹ️ Этот тикет уже закрыт.", ephemeral=True
            )
            return

        author_id = _author_id(channel)
        if not _is_staff(interaction.user) and interaction.user.id != author_id:
            await interaction.response.send_message(
                "⛔ Закрыть тикет может только его автор или модератор.",
                ephemeral=True,
            )
            return

        match = TICKET_RE.match(channel.name)
        number = match.group(1) if match else "?"

        await interaction.response.send_message(
            "🔒 Тикет закрыт. Спасибо за обращение!", ephemeral=True
        )

        # Автор теряет доступ, канал помечается закрытым
        if author_id is not None:
            author_member = guild.get_member(author_id)
            if author_member is not None:
                over = channel.overwrites_for(author_member)
                over.view_channel = False
                over.send_messages = False
                over.read_message_history = False
                try:
                    await channel.set_permissions(
                        author_member, overwrite=over, reason="Тикет закрыт"
                    )
                except discord.HTTPException:
                    log.exception("Не удалось отобрать доступ у %s", author_member)

        try:
            await channel.edit(
                name=f"закрыт-тикет-{number}",
                topic=f"Закрыт тикет #{number} ({author_id or ''})".rstrip(),
                reason="Тикет закрыт",
            )
        except discord.HTTPException:
            log.exception("Не удалось переименовать тикет")

        embed = discord.Embed(
            title="🔒 Тикет закрыт",
            description=(
                "Обращение закрыто. Если нужна помощь снова — вернись к панели "
                "и создай новый тикет.\n\n"
                "Модератор: можешь удалить канал кнопкой ниже."
            ),
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await channel.send(embed=embed, view=TicketActionsView())
        except discord.HTTPException:
            log.exception("Не удалось отправить сообщение о закрытии тикета")

    @discord.ui.button(
        label="Удалить тикет",
        emoji="🗑️",
        style=discord.ButtonStyle.secondary,
        custom_id=DELETE_ID,
    )
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if (
            guild is None
            or not isinstance(channel, discord.TextChannel)
            or not isinstance(interaction.user, discord.Member)
        ):
            await interaction.response.send_message("❌ Нельзя здесь.", ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message(
                "⛔ Удалять тикет может только модератор.", ephemeral=True
            )
            return

        await interaction.response.send_message("🗑 Удаляю тикет…", ephemeral=True)
        try:
            await channel.delete(reason="Тикет удалён модератором")
        except discord.HTTPException:
            log.exception("Не удалось удалить тикет %s", channel.name)
            return

        # Забываем канал из списка уведомлений
        config = interaction.client.config.setdefault(str(guild.id), {})
        pinged = config.get("pinged_tickets")
        if isinstance(pinged, list) and str(channel.id) in pinged:
            pinged.remove(str(channel.id))
            try:
                await interaction.client.save_config()
            except Exception:
                log.exception("Не удалось сохранить конфиг после удаления тикета")


class Tickets(commands.Cog):
    """Тикет-система сервера."""

    ticketstaff = app_commands.Group(
        name="ticketstaff",
        description="Роли модераторов для пинга в тикетах",
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _guild_config(self, guild_id: int) -> dict:
        return self.bot.config.setdefault(str(guild_id), {})

    def _staff_roles(self, guild: discord.Guild) -> list[discord.Role]:
        config = self._guild_config(guild.id)
        roles = []
        for role_id in _int_ids(config.get("ticket_staff_roles")):
            role = guild.get_role(role_id)
            if role is not None and not role.is_default():
                roles.append(role)
        return roles

    # ------------------------------------------------------------------ команды

    @app_commands.command(
        name="ticketpanel", description="Панель с кнопкой создания тикета"
    )
    @app_commands.describe(channel="Канал для панели (по умолчанию — текущий)")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticketpanel(
        self, interaction: discord.Interaction, channel: discord.TextChannel | None = None
    ) -> None:
        target = channel
        if target is None and isinstance(interaction.channel, discord.TextChannel):
            target = interaction.channel
        if target is None or interaction.guild is None:
            await interaction.response.send_message(
                "❌ Укажи канал: `/ticketpanel канал:#название`.", ephemeral=True
            )
            return

        me = interaction.guild.me
        if me is not None:
            perms = target.permissions_for(me)
            if not (perms.send_messages and perms.embed_links):
                await interaction.response.send_message(
                    f"❌ У бота нет прав писать в {target.mention}.", ephemeral=True
                )
                return

        embed = discord.Embed(
            title="🎫 Тикет-система",
            description=(
                "Нужна помощь или есть вопрос? Нажми кнопку ниже — "
                "будет создан личный канал, куда зашли только ты и модераторы.\n\n"
                "Опиши проблему, дождись ответа и закрой тикет, когда всё решено."
            ),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="Один открытый тикет на пользователя")
        await target.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message(
            f"✅ Панель отправлена в {target.mention}.", ephemeral=True
        )

    @ticketstaff.command(
        name="set", description="Указать роли, которых пинговать при описании проблемы"
    )
    @app_commands.describe(
        role1="Основная роль модераторов",
        role2="Ещё роль (необязательно)",
        role3="Ещё роль (необязательно)",
        role4="Ещё роль (необязательно)",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ts_set(
        self,
        interaction: discord.Interaction,
        role1: discord.Role,
        role2: discord.Role | None = None,
        role3: discord.Role | None = None,
        role4: discord.Role | None = None,
    ) -> None:
        roles = [r for r in (role1, role2, role3, role4) if r is not None]
        if any(r.is_default() for r in roles):
            await interaction.response.send_message(
                "❌ @everyone пинговать нельзя.", ephemeral=True
            )
            return
        self._guild_config(interaction.guild.id)["ticket_staff_roles"] = [
            str(r.id) for r in roles
        ]
        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить ticket_staff_roles")
        await interaction.response.send_message(
            "✅ При описании проблемы в тикете будут пинговаться: "
            + ", ".join(r.mention for r in roles),
            ephemeral=True,
        )

    @ticketstaff.command(name="show", description="Показать роли для пинга в тикетах")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ts_show(self, interaction: discord.Interaction) -> None:
        roles = self._staff_roles(interaction.guild)
        if not roles:
            await interaction.response.send_message(
                "ℹ️ Роли для пинга не заданы. Задай: `/ticketstaff set role1:...`",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "ℹ️ Пингуем: " + ", ".join(r.mention for r in roles), ephemeral=True
        )

    @ticketstaff.command(name="off", description="Отключить пинг модераторов в тикетах")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ts_off(self, interaction: discord.Interaction) -> None:
        if not self._guild_config(interaction.guild.id).pop("ticket_staff_roles", None):
            await interaction.response.send_message(
                "ℹ️ Пинг и так не настроен.", ephemeral=True
            )
            return
        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить конфиг после ticketstaff off")
        await interaction.response.send_message(
            "✅ Пинг модераторов в тикетах отключён.", ephemeral=True
        )

    # --------------------------------------------------------------- слушатели

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Автор написал в тикете → пингуем роли модераторов (один раз)."""
        if message.author.bot or message.guild is None:
            return
        channel = message.channel
        if not isinstance(channel, discord.TextChannel):
            return
        if not TICKET_RE.match(channel.name) or channel.name.startswith("закрыт-"):
            return
        if not isinstance(message.author, discord.Member):
            return
        if message.author.id != _author_id(channel):
            return

        config = self._guild_config(message.guild.id)
        pinged = config.setdefault("pinged_tickets", [])
        if str(channel.id) in pinged:
            return

        roles = self._staff_roles(message.guild)
        if not roles:
            return  # роли не заданы — не пингуем и не помечаем

        # Помечаем ДО отправки, чтобы параллельные сообщения не задублировали пинг
        pinged.append(str(channel.id))
        embed = discord.Embed(
            title="📨 Автор описал проблему",
            description=(
                f"Загляни в {channel.mention}: {message.author.mention} "
                "описал суть обращения."
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await channel.send(
                " ".join(r.mention for r in roles),
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    roles=True, users=False, everyone=False
                ),
            )
        except discord.HTTPException:
            pinged.remove(str(channel.id))
            log.exception("Не удалось отправить пинг модераторов в %s", channel.name)
            return
        log.info("Пинг модераторов отправлен в %s", channel.name)
        try:
            await self.bot.save_config()
        except Exception:
            log.exception("Не удалось сохранить pinged_tickets")


async def setup(bot: commands.Bot) -> None:
    # Постоянные view: кнопки работают после любого перезапуска бота
    bot.add_view(TicketPanelView())
    bot.add_view(TicketActionsView())
    await bot.add_cog(Tickets(bot))
