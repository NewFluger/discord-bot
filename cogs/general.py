import discord
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    """Общие команды."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Задержка бота")
    async def ping(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Задержка: **{round(self.bot.latency * 1000)} мс**",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Список команд бота")
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🤖 Команды бота",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🔹 Общие",
            value="`/ping` `/help` `/serverinfo` `/userinfo` `/avatar`",
            inline=False,
        )
        embed.add_field(
            name="🛡 Модерация",
            value="`/kick` `/ban` `/unban` `/timeout` `/untimeout` `/clear`",
            inline=False,
        )
        embed.add_field(
            name="🧰 Утилиты",
            value="`/say` `/poll` `/remind` `/8ball` `/coinflip`",
            inline=False,
        )
        embed.set_footer(text="Команды без нужных прав могут быть скрыты")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Информация о сервере")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Только на сервере.", ephemeral=True
            )
            return

        owner = guild.get_member(guild.owner_id)
        embed = discord.Embed(
            title=f"📋 {guild.name}",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(
            name="Владелец",
            value=(owner.mention if owner else f"<@{guild.owner_id}>"),
            inline=True,
        )
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Участников", value=str(guild.member_count), inline=True)
        embed.add_field(name="Каналов", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Ролей", value=str(len(guild.roles)), inline=True)
        embed.add_field(
            name="Создан",
            value=f"<t:{int(guild.created_at.timestamp())}:D>",
            inline=True,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Информация об участнике")
    @app_commands.describe(member="Участник (по умолчанию — ты)")
    @app_commands.guild_only()
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        member = member or interaction.user  # type: ignore[assignment]
        embed = discord.Embed(
            title=f"👤 {member}",
            color=member.color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(
            name="Аккаунт создан",
            value=f"<t:{int(member.created_at.timestamp())}:D>",
            inline=True,
        )
        if member.joined_at:
            embed.add_field(
                name="Зашёл на сервер",
                value=f"<t:{int(member.joined_at.timestamp())}:D>",
                inline=True,
            )
        embed.add_field(name="Топ-роль", value=member.top_role.mention, inline=True)
        embed.add_field(name="Бот", value="Да" if member.bot else "Нет", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Аватар участника")
    @app_commands.describe(member="Участник (по умолчанию — ты)")
    @app_commands.guild_only()
    async def avatar(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        member = member or interaction.user  # type: ignore[assignment]
        embed = discord.Embed(
            title=f"🖼 Аватар — {member}",
            color=member.color,
        )
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
