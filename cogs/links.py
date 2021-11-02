from discord.ext import commands


class Links(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def support(self, ctx):
        """Returns the official bot support server invite link."""
        await ctx.send(self.bot.config.support)

    @commands.command()
    async def vote(self, ctx):
        """Returns bot vote link."""
        await ctx.send(self.bot.config.vote)

    @commands.command()
    async def invite(self, ctx):
        """Returns bot invite link."""
        await ctx.send(self.bot.config.invite)

    @commands.command(aliases=["git"])
    async def github(self, ctx):
        """Returns the bot GitHub repository."""
        await ctx.send(self.bot.config.github["repo"])


def setup(bot):
    bot.add_cog(Links(bot))
