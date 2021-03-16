import aiohttp

import config
from utils.i18n import _


class RequestError(Exception):
    """Base exception class for data.py."""

    pass


class NotFound(RequestError):
    """Exception raised when a profile is not found."""

    def __init__(self):
        super().__init__(_("Player not found."))


class BadRequest(RequestError):
    """Exception raised when a request sucks."""

    def __init__(self):
        super().__init__(
            _("Wrong BattleTag format entered! Correct format: `name#0000`")
        )


class InternalServerError(RequestError):
    """Exception raised when the API returns 500 status code."""

    def __init__(self):
        super().__init__(
            _(
                "The API is having internal server problems. Please be patient and try again later."
            )
        )


class ServiceUnavailable(RequestError):
    """Exception raised when the server API is under maintenance."""

    def __init__(self):
        super().__init__(
            "The API is under maintenance. Please be patient and try again later."
        )


class TooManyAccounts(RequestError):
    """Exception raised when the API found too many accounts under that name."""

    def __init__(self, platform, username, players):
        if platform == "pc":
            message = _(
                f"**{players}** accounts found under the name of `{username}`"
                f" playing on `{platform}`. Please be more specific by entering"
                " the full BattleTag in the following format: `name#0000`"
            )
        else:
            message = _(
                f"**{players}** accounts found under the name of `{username}`"
                f" playing on `{platform}`. Please be more specific."
            )
        super().__init__(message)


class Request:

    __slots__ = ("platform", "username")

    def __init__(self, *, platform: str, username: str):
        self.platform = platform
        self.username = username

    @property
    def account_url(self):
        return config.overwatch["account"] + "/" + self.username + "/"

    async def resolve_name(self, players):
        if len(players) == 1:
            return players[0]["urlName"]
        elif len(players) > 1:
            total_players = []
            for player in players:
                if (
                    player["name"].lower() == self.username.lower()
                    and player["platform"] == self.platform
                ):
                    return player["urlName"]
                if player["platform"] == self.platform:
                    total_players.append(player["name"].lower())
            if (
                len(total_players) == 0
                or "#" in self.username
                and self.username.lower() not in total_players
            ):
                raise NotFound()
            else:
                raise TooManyAccounts(self.platform, self.username, len(total_players))
        else:
            # return the username and let `resolve_response` handle it
            return self.username

    async def get_name(self):
        async with aiohttp.ClientSession() as s:
            async with s.get(self.account_url) as r:
                name = await r.json()
                return await self.resolve_name(name)

    async def url(self):
        """Returns the resolved url."""
        name = await self.get_name()
        return f"{config.base_url}/{self.platform}/{name}/complete"

    async def resolve_response(self, response):
        """Resolve the response."""
        if response.status == 200:
            return await response.json()
        elif response.status == 400:
            raise BadRequest()
        elif response.status == 404:
            raise NotFound()
        elif response.status == 500:
            raise InternalServerError()
        else:
            raise ServiceUnavailable()

    async def response(self):
        """Returns the aiohttp response."""
        url = await self.url()
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                return await self.resolve_response(r)

    async def get(self):
        """Returns resolved response."""
        return await self.response()
