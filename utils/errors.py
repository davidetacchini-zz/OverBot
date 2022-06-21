import traceback

from typing import Union

import discord

from asyncpg import DataError
from discord import app_commands

from utils import checks
from classes.profile import ProfileException
from classes.request import RequestError
from classes.exceptions import NoChoice, PaginationError


async def error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError):
    bot = interaction.client

    async def send(payload: Union[str, discord.Embed], ephemeral: bool = True):
        if interaction.response.is_done():
            await interaction.followup.send(payload, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(payload, ephemeral=ephemeral)

    if isinstance(error, app_commands.CommandNotFound):
        return

    elif isinstance(error, app_commands.TransformerError):
        await send(error)

    elif isinstance(error, app_commands.CheckFailure):
        if type(error) == checks.ProfileNotLinked:
            await send('You haven\'t linked a profile yet. Use "/profile link" to start.')

        elif type(error) == checks.ProfileLimitReached:
            if error.limit == 5:
                premium = bot.config.premium
                embed = discord.Embed(color=discord.Color.red())
                embed.description = (
                    "Maximum limit of profiles reached.\n"
                    f"[Upgrade to Premium]({premium}) to be able to link up to 25 profiles."
                )
                await send(embed=embed)
            else:
                await send("Maximum limit of profiles reached.")

        elif type(error) == checks.MemberNotPremium:
            premium = bot.config.premium
            embed = discord.Embed(color=discord.Color.red())
            embed.description = (
                "This command requires a Premium membership.\n"
                f"[Click here]({premium}) to have a look at the Premium plans."
            )
            await send(embed=embed)

        elif type(error) == app_commands.NoPrivateMessage:
            await interaction.user.send("This command can't be used in direct messages.")

        elif type(error) == app_commands.CommandOnCooldown:
            command = interaction.command.qualified_name
            seconds = round(error.retry_after, 2)
            await send(f"You can't use `{command}` command for `{seconds}s`.")

    elif isinstance(error, app_commands.CommandInvokeError):
        original = error.original
        group = (RequestError, ProfileException, NoChoice, PaginationError)
        if isinstance(original, DataError):
            await send("The argument you entered cannot be handled.")
        elif isinstance(original, group):
            await send(original)
        else:
            embed = discord.Embed(color=discord.Color.red())
            embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar)
            embed.add_field(name="Command", value=interaction.command.qualified_name)
            if interaction.guild:
                guild = f"{str(interaction.guild)} ({interaction.guild.id})"
                embed.add_field(name="Guild", value=guild, inline=False)
            try:
                exc = "".join(
                    traceback.format_exception(
                        type(original),
                        original,
                        original.__traceback__,
                        chain=False,
                    )
                )
            except AttributeError:
                exc = f"{type(original)}\n{original}"
            embed.description = f"```py\n{exc}\n```"
            embed.timestamp = interaction.created_at
            if not bot.debug:
                await bot.webhook.send(embed=embed)
            else:
                print(original, type(original))
            await send(
                "This command ran into an error. The incident has been reported and will be fixed as soon as possible!"
            )
