from discord.ext import commands

from utils import i18n
from utils.i18n import _, locale


class Locale(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.locales = {}

    async def set_locale(self, member_id, locale):
        query = """INSERT INTO member(id, locale)
                VALUES($1, $2)
                ON CONFLICT (id) DO
                UPDATE SET locale = $2;
                """
        await self.bot.pool.execute(query, member_id, locale)
        self.bot.locales[member_id] = locale

    async def get_locale(self, member_id):
        return await self.bot.pool.fetchval(
            "SELECT locale FROM member WHERE id = $1;", member_id
        )

    async def update_locale(self, member_id):
        locale = self.bot.locales.get(member_id)
        if not locale:
            locale = await self.get_locale(member_id)
            self.bot.locales[member_id] = locale
        return locale

    @commands.command(aliases=["locale", "lang"])
    # @commands.cooldown(1, 5.0, commands.BucketType.member)
    @locale
    async def language(self, ctx, locale=None):
        _(
            """Show or update the bot language.

        `[locale] - The language you want the bot to use.
        """
        )
        if not locale:
            locales = ", ".join(i18n.locales)
            current_locale = self.bot.locales.get(ctx.author.id) or i18n.current_locale
            return await ctx.send(
                _(f"Current locale `{current_locale}`.\nAvailable locales:\n{locales}")
            )
        if locale not in i18n.locales:
            return await ctx.send(_("Invalid language entered."))
        try:
            await self.set_locale(ctx.author.id, locale)
            i18n.current_locale.set(locale)
            self.bot.locales[ctx.author.id] = locale
        except Exception as e:
            await ctx.send(embed=self.bot.embed_exception(e))
        else:
            await ctx.send(_(f"Language successfully changed to: `{locale}`"))


def setup(bot):
    bot.add_cog(Locale(bot))