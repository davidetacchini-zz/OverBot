import discord
from discord.ext import commands


class ProfileNotLinked(commands.CheckFailure):
    """Exception raised when a user have not linked a profile."""

    pass


class ProfileLimitReached(commands.CheckFailure):
    """Exception raised when a user try to link a 6th profile."""

    pass


class MemberIsNotPremium(commands.CheckFailure):
    """Exception raised when a user is not premium."""

    pass


async def get_profiles(ctx):
    query = """SELECT platform, username
            FROM profile
            INNER JOIN member
                    ON member.id = profile.member_id
            WHERE member.id = $1;
            """
    return await ctx.bot.pool.fetch(query, ctx.author.id)


def has_profile():
    """Check for a user to have linked atleast a profile."""

    async def predicate(ctx):
        if await get_profiles(ctx):
            return True
        raise ProfileNotLinked()

    return commands.check(predicate)


def can_add_profile():
    """Check for a user to have no profiles linked."""

    async def predicate(ctx):
        profiles = await get_profiles(ctx)
        if len(profiles) < 5:
            return True
        raise ProfileLimitReached()

    return commands.check(predicate)


def is_premium():
    """Check for a user to be a premium member."""

    async def predicate(ctx):
        guild = ctx.bot.get_guild(ctx.bot.config.support_server_id)
        member = await guild.fetch_member(ctx.author.id)

        if not member:
            return False

        role = discord.utils.get(member.roles, name="Premium")

        if role:
            return True
        raise MemberIsNotPremium()

    return commands.check(predicate)
