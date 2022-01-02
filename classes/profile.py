import re

from datetime import date

import discord

from asyncpg import Record

from utils import emojis

from .context import Context
from .request import Request

ROLES = {
    "tank": emojis.tank,
    "damage": emojis.damage,
    "support": emojis.support,
}


class ProfileException(Exception):

    pass


class NoStats(ProfileException):
    def __init__(self):
        super().__init__("This profile has no quick play nor competitive stats to display.")


class NoHeroStats(ProfileException):
    def __init__(self, hero):
        super().__init__(
            f"This profile has no quick play nor competitive stast for **{hero}** to display."
        )


class Profile:

    __slots__ = ("data", "id", "platform", "username", "ctx", "record", "pages")

    def __init__(
        self,
        platform: None | str = None,
        username: None | str = None,
        *,
        ctx: "Context",
        record: None | Record = None,
    ):
        self.data = None

        if record:
            self.id = record["id"]
            self.platform = record["platform"]
            self.username = record["username"]
        else:
            self.id = None
            self.platform = platform
            self.username = username

        self.ctx = ctx
        self.pages = []

    async def compute_data(self):
        self.data = await Request(self.platform, self.username).get()

    def __str__(self):
        return self.data["name"]

    @property
    def avatar(self):
        return self.data["icon"]

    @property
    def level_icon(self):
        return self.data["levelIcon"]

    @staticmethod
    def to_pascal(key):
        """From camel case to pascal case (testTest -> Test Test)."""
        return (
            re.sub("([a-z])([A-Z])", r"\g<1> \g<2>", key)
            .replace(" Avg Per10Min", "")
            .replace(" Most In Game", "")
            .title()
        )

    def format_key(self, key):
        match key:
            case "best":
                return key.capitalize() + " (Most in game)"
            case "average":
                return key.capitalize() + " (per 10 minutes)"
            case _:
                return self.to_pascal(key)

    @staticmethod
    def get_rating_icon(rating):
        if 0 < rating < 1500:
            return emojis.bronze
        elif 1500 <= rating < 2000:
            return emojis.silver
        elif 2000 <= rating < 2500:
            return emojis.gold
        elif 2500 <= rating < 3000:
            return emojis.platinum
        elif 3000 <= rating < 3500:
            return emojis.diamond
        elif 3500 <= rating < 4000:
            return emojis.master
        return emojis.grand_master

    def is_private(self):
        return self.data["private"]

    def has_stats(self):
        return (
            self.data["quickPlayStats"]["careerStats"]
            or self.data["competitiveStats"]["careerStats"]
        )

    async def save_ratings(self, profile_id, **kwargs):
        tank = kwargs.get("tank", 0)
        damage = kwargs.get("damage", 0)
        support = kwargs.get("support", 0)

        query = """SELECT tank, damage, support
                   FROM rating
                   INNER JOIN profile
                           ON profile.id = rating.profile_id
                   WHERE profile.id = $1
                   AND rating.date = $2;
                """

        requested_at = date.today()
        roles = await self.ctx.bot.pool.fetch(query, profile_id, requested_at)

        if roles:
            # Assuming a user uses `-profile rating` multiple times within
            # the same day, we don't want duplicate ratings. If only 1 rating
            # differs, then we insert the new ratings into the database.
            all_equals = False
            for t, d, s in roles:
                if t == tank and d == damage and s == support:
                    all_equals = True

        if not roles or not all_equals:
            query = (
                "INSERT INTO rating (tank, damage, support, profile_id) VALUES ($1, $2, $3, $4);"
            )
            await self.ctx.bot.pool.execute(query, tank, damage, support, profile_id)

    def resolve_ratings(self):
        if not self.data["ratings"]:
            return None
        ratings = {}
        for key, value in self.data["ratings"].items():
            ratings[key.lower()] = value["level"]
        return ratings

    def resolve_stats(self, hero):
        if not self.has_stats():
            raise NoStats()

        # quickplay stats
        q = self.data.get("quickPlayStats").get("careerStats").get(hero) or {}
        # competitive stats
        c = self.data.get("competitiveStats").get("careerStats").get(hero) or {}

        if hero != "allHeroes" and not q and not c:
            raise NoHeroStats(hero)

        keys = list({*q, *c})
        keys.sort()

        for i, key in enumerate(keys):
            if not q.get(key) and not c.get(key):
                del keys[i]

        return keys, q, c

    def format_stats(self, embed, key, quickplay, competitive):
        if quickplay and quickplay[key]:
            q_t = "\n".join(f"{k}: **{v}**" for k, v in quickplay[key].items())
            embed.add_field(name="Quick Play", value=self.to_pascal(q_t))
        if competitive and competitive[key]:
            c_t = "\n".join(f"{k}: **{v}**" for k, v in competitive[key].items())
            embed.add_field(name="Competitive", value=self.to_pascal(c_t))

    async def embed_ratings(self, *, save=False, profile_id=None):
        embed = discord.Embed(color=self.ctx.bot.color(self.ctx.author.id))
        embed.set_author(name=str(self), icon_url=self.avatar)

        ratings = self.resolve_ratings()

        if not ratings:
            embed.description = "This profile is unranked."
            return embed

        for key, value in ratings.items():
            role_icon = ROLES.get(key)
            role_name = key.upper()
            rating_icon = self.get_rating_icon(value)
            embed.add_field(
                name=f"{role_icon} {role_name}",
                value=f"{rating_icon} {value}{emojis.sr}",
            )
        embed.set_footer(
            text="Average: {average}".format(average=self.data.get("rating")),
            icon_url=self.data.get("ratingIcon"),
        )

        if save:
            await self.save_ratings(profile_id, **ratings)

        return embed

    def embed_stats(self, hero):
        keys, quickplay, competitive = self.resolve_stats(hero)

        for i, key in enumerate(keys, start=1):
            embed = discord.Embed(color=self.ctx.bot.color(self.ctx.author.id))
            embed.title = self.format_key(key)
            embed.set_author(name=str(self), icon_url=self.avatar)
            if hero == "allHeroes":
                embed.set_thumbnail(url=self.level_icon)
            else:
                embed.set_thumbnail(url=self.ctx.bot.config.hero_url.format(hero.lower()))
            embed.set_footer(text=f"Page {i}/{len(keys)}")
            self.format_stats(embed, key, quickplay, competitive)
            self.pages.append(embed)
        return self.pages

    def embed_summary(self):
        embed = discord.Embed(color=self.ctx.bot.color(self.ctx.author.id))
        embed.set_author(name=str(self), icon_url=self.avatar)
        embed.set_thumbnail(url=self.level_icon)

        ratings = self.resolve_ratings()

        if ratings:
            ratings_ = []
            for key, value in ratings.items():
                role_icon = ROLES.get(key.lower())
                rating_icon = self.get_rating_icon(value)
                ratings_.append(f"{role_icon} {rating_icon}{value}{emojis.sr}")
            embed.description = " ".join(ratings_)

        summary = {}
        summary["level"] = str(self.data.get("prestige")) + str(self.data.get("level"))
        summary["endorsement"] = self.data.get("endorsement")
        summary["gamesWon"] = self.data.get("gamesWon")

        for key, value in summary.items():
            embed.add_field(name=self.to_pascal(key), value=value)

        def format_dict(source):
            d = {}
            d["game"] = source.get("game")
            to_keep = ("deaths", "eliminations", "damageDone")
            d["combat"] = {k: v for k, v in source.get("combat").items() if k in to_keep}
            d["awards"] = source.get("matchAwards")
            return d

        def format_embed(source, embed, *, category):
            for key, value in source.items():
                key = f"{self.to_pascal(key)} ({category.title()})"
                if isinstance(value, dict):
                    v = "\n".join(f"{k}: **{v}**" for k, v in value.items())
                    embed.add_field(name=key, value=self.to_pascal(v))
                else:
                    embed.add_field(name=key, value=value)

        q = self.data.get("quickPlayStats").get("careerStats").get("allHeroes")  # quick play
        c = self.data.get("competitiveStats").get("careerStats").get("allHeroes")  # competitive

        if q:
            quickplay = format_dict(q)
            format_embed(quickplay, embed, category="quick play")

        if c:
            competitive = format_dict(c)
            format_embed(competitive, embed, category="competitive")

        return embed

    def embed_private(self):
        embed = discord.Embed(color=discord.Color.red())
        embed.title = "This profile is set to private"
        embed.description = (
            "Profiles are set to private by default."
            " You can modify this setting in Overwatch under `Options > Social`."
            " Please note that this change may take effect within approximately 30 minutes."
        )
        embed.set_author(name=str(self), icon_url=self.avatar)
        return embed