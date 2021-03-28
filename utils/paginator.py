import asyncio
from typing import Union, Optional
from contextlib import suppress

import discord
from discord.ext.commands import CommandInvokeError

from config import main_color
from utils.i18n import _

PLATFORMS = {
    "pc": "PC",
    "psn": "Playstation",
    "xbl": "Xbox",
    "nintendo-switch": "Switch",
}


class NoChoice(CommandInvokeError):
    """Exception raised when no choice is given."""

    pass


class BasePaginator:

    __slots__ = (
        "entries",
        "timeout",
        "title",
        "footer",
        "image",
        "color",
        "reactions",
        "embed",
        "description",
        "ctx",
        "bot",
        "author",
        "message",
    )

    def __init__(
        self,
        entries: Optional[Union[list, tuple]] = None,
        *,
        timeout: float = 30.0,
        title: Optional[str] = None,
        image: Optional[str] = None,
        footer: Optional[str] = None,
    ):
        self.entries = entries
        self.timeout = timeout
        self.title = title
        self.image = image
        self.footer = footer

        self.color = main_color
        self.reactions = None
        self.embed = None
        self.description = []
        self.ctx = None
        self.bot = None
        self.author = None
        self.message = None

    def init_embed(self):
        embed = discord.Embed(color=self.bot.color(self.author.id))
        embed.set_author(name=str(self.author), icon_url=self.author.avatar_url)

        # if self.title and len(self.title) <= 256:
        #     embed.title = self.title
        # elif self.title and len(self.title) > 256:
        #     self.description.append(self.title)

        if self.title:
            embed.title = self.title

        if self.image:
            embed.set_image(url=self.image)

        if self.footer:
            embed.set_footer(text=self.footer)

        return embed

    def result(self, reaction):
        raise NotImplementedError

    async def add_reactions(self):
        for reaction in self.reactions:
            try:
                await self.message.add_reaction(reaction)
            except (discord.HTTPException, discord.Forbidden):
                return

    async def cleanup(self):
        with suppress(discord.HTTPException, discord.Forbidden):
            await self.message.delete()

    async def paginator(self):
        self.message = await self.ctx.send(embed=self.embed)
        self.bot.loop.create_task(self.add_reactions())

        def check(r, u):
            if u.id != self.author.id:
                return False
            if u.id == self.bot.user.id:
                return False
            if r.message.id != self.message.id:
                return False
            if str(r.emoji) not in self.reactions:
                return False
            return True

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add", check=check, timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise NoChoice("You took too long to reply.")
        else:
            return self.result(reaction)
        finally:
            await self.cleanup()

    async def start(self, ctx):
        raise NotImplementedError


class Link(BasePaginator):
    def __init__(self):
        title = _("Platform")
        footer = _("React with the platform you play on...")
        super().__init__(title=title, footer=footer)
        self.reactions = {
            "<:battlenet:679469162724196387>": "pc",
            "<:psn:679468542541693128>": "psn",
            "<:xbl:679469487623503930>": "xbl",
            "<:nsw:752653766377078817>": "nintendo-switch",
            "❌": None,
        }

    def result(self, reaction):
        return self.reactions.get(str(reaction.emoji))

    async def start(self, ctx):
        self.ctx = ctx
        self.bot = ctx.bot
        self.author = ctx.author
        self.embed = self.init_embed()

        for key, value in self.reactions.items():
            if value is None:
                continue
            value = PLATFORMS.get(value)
            self.description.append(f"{key} - {value}")
        self.embed.description = "\n".join(self.description)

        return await self.paginator()


class Update(Link):

    __slots__ = ("platform", "username")

    def __init__(self, platform, username, **kwargs):
        super().__init__(**kwargs)
        self.platform = platform
        self.username = username

    async def start(self, ctx):
        self.ctx = ctx
        self.bot = ctx.bot
        self.author = ctx.author
        self.embed = self.init_embed()

        for key, value in self.reactions.items():
            if value is None:
                continue
            value = PLATFORMS.get(value)
            self.description.append(f"{key} - {value}")

        self.description.append("\nProfile to update:")
        self.embed.description = "\n".join(self.description)

        self.embed.add_field(name=_("Platform"), value=self.platform)
        self.embed.add_field(name=_("Username"), value=self.username)

        return await self.paginator()


class Choose(BasePaginator):

    __slots__ = ("entries", "timeout", "title", "image", "footer")

    def __init__(self, entries, *, timeout, title, image, footer):
        super().__init__(
            entries, timeout=timeout, title=title, image=image, footer=footer
        )
        self.reactions = []

    def result(self, reaction):
        return self.entries[self.reactions.index(str(reaction))]

    async def start(self, ctx):
        self.ctx = ctx
        self.bot = ctx.bot
        self.author = ctx.author
        self.embed = self.init_embed()

        for index, entry in enumerate(self.entries, start=1):
            self.reactions.append(f"{index}\u20e3")
            self.description.append(f"{index}. {entry}")

        self.embed.description = "\n".join(self.description)

        return await self.paginator()


class ChooseLocale(BasePaginator):

    __slots__ = "title"

    def __init__(self, *, title):
        super().__init__(title=title)
        self.reactions = {
            "🇩🇪": "de_DE",
            "🇺🇸": "en_US",
            "🇫🇷": "fr_FR",
            "🇮🇹": "it_IT",
            "🇯🇵": "ja_JP",
            "🇰🇷": "ko_KR",
            "🇷🇺": "ru_RU",
            "❌": None,
        }

    def result(self, reaction):
        return self.reactions.get(str(reaction.emoji))

    async def start(self, ctx):
        self.ctx = ctx
        self.bot = ctx.bot
        self.author = ctx.author
        self.embed = self.init_embed()

        for key, value in self.reactions.items():
            self.description.append(f"{key} - `{value}`")

        self.embed.description = "\n".join(self.description)

        return await self.paginator()
