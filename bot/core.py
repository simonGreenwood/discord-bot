import datetime
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import settings
from utils.time import human_timedelta

log = logging.getLogger(__name__)

os.environ.update(JISHAKU_NO_UNDERSCORE="True", JISHAKU_NO_DM_TRACEBACK="True", JISHAKU_HIDE="True")
ALLOWED_MENTIONS = discord.AllowedMentions(everyone=False, roles=False, users=False)


class DiscordBot(commands.Bot):
    def __init__(self, prefixes: tuple[str, ...], extensions: tuple[str, ...], intents: discord.Intents):
        super().__init__(
            intents=intents, command_prefix=prefixes, case_insensitive=True, allowed_mentions=ALLOWED_MENTIONS
        )
        self.start_time = datetime.datetime.utcnow()
        self.initial_extensions = extensions

    async def resolve_user(self, user_id: int) -> discord.User | None:
        """Resolve a user from their ID."""
        user = self.get_user(user_id)
        if user is None:
            try:
                user = await self.fetch_user(user_id)
            except discord.NotFound:
                return None

        return user

    @property
    def guild(self) -> discord.Guild | None:
        return self.get_guild(settings.guild.id)

    async def setup_hook(self) -> None:
        """Connect DB before bot is ready to assure that no calls are made before its ready"""
        self.loop.create_task(self.when_online())
        self.presence.start()

        self.tree.on_error = self.on_app_command_error

    async def when_online(self):
        log.info("Waiting until bot is ready to load extensions and app commands.")
        await self.wait_until_ready()

        await self.load_extensions()
        await self.sync_commands()

    async def load_extensions(self):
        for ext in self.initial_extensions:
            try:
                await self.load_extension(ext)
            except Exception as error:
                log.error(f"Failed to load extension {ext!r}:", exc_info=error)

        log.info(f"Loaded all extensions after {human_timedelta(self.start_time, brief=True, suffix=False)}")

    async def sync_commands(self) -> None:
        self.tree.copy_global_to(guild=self.guild)
        await self.tree.sync(guild=self.guild)

        log.info("Commands synced.")
        log.info(f"Successfully logged in as {self.user}. In {len(self.guilds)} guilds")

    async def on_message(self, message):
        await self.wait_until_ready()

        if message.author.bot:
            return

        log.debug(f"{message.channel}: {message.author}: {message.clean_content}")

        await self.process_commands(message)

    async def process_commands(self, message: discord.Message, /):
        ctx = await self.get_context(message)

        if ctx.command is None:
            return

        log.info(f"{ctx.author} invoking command: {ctx.clean_prefix}{ctx.command.qualified_name}")
        await self.invoke(ctx)

    async def on_app_command_error(self, interaction: "InteractionType", error: app_commands.AppCommandError):
        """Handle errors in app commands."""
        if interaction.command is None:
            return log.error("Ignoring exception in command tree.", exc_info=error)

        if interaction.command._has_any_error_handlers():
            return

        if isinstance(error, app_commands.CheckFailure):
            log.info(f"{interaction.user} failed to use the command {interaction.command.qualified_name}")
            return

        log.error("Ignoring unhandled exception", exc_info=error)

    @tasks.loop(hours=24)
    async def presence(self):
        await self.wait_until_ready()
        await self.change_presence(activity=discord.Game(name='use the prefix "tim."'))


InteractionType = discord.Interaction[DiscordBot]