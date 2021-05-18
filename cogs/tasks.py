import re
import platform
from contextlib import suppress

import distro
import psutil
import discord
from discord.ext import tasks, commands

from utils.scrape import get_overwatch_news


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update.start()
        self.statistics.start()
        self.subscriptions.start()
        self.send_overwatch_news.start()

    def get_shards(self):
        shards = []
        for i in range(self.bot.shard_count):
            shard = self.bot.get_shard(i)
            if not shard:
                break
            total_members = 0
            guilds = [g for g in self.bot.guilds if g.shard_id == shard.id]
            try:
                total_members = sum(g.member_count for g in guilds)
            except AttributeError:
                total_members += 0
            shards.append(
                dict(
                    id=shard.id + 1,
                    latency=round(shard.latency * 1000, 2),
                    guild_count=len(guilds),
                    member_count=total_members,
                )
            )
        return shards

    async def get_bot_statistics(self):
        total_commands = await self.bot.total_commands()
        try:
            total_members = sum(g.member_count for g in self.bot.guilds)
        except AttributeError:
            total_members = 0
        large_servers = sum(1 for g in self.bot.guilds if g.large)

        with suppress(OverflowError):
            shards = self.get_shards()
            ping = f"{round(self.bot.latency * 1000, 2)}ms"

        async with self.bot.pool.acquire() as conn:
            pg_version = conn.get_server_version()
        pg_version = f"{pg_version.major}.{pg_version.micro} {pg_version.releaselevel}"
        py_version = platform.python_version()

        os_name = distro.linux_distribution()[0]
        os_version = distro.linux_distribution()[1]
        cpu_perc = f"{psutil.cpu_percent()}%"
        cpu_cores = psutil.cpu_count()
        cpu_freq = f"{round(psutil.cpu_freq()[0] / 1000, 2)}GHz"
        ram = f"{psutil.virtual_memory()[2]}%"

        statistics = {
            "host": {
                "Postgres Version": pg_version,
                "Python Version": py_version,
                "O.S. Name": os_name,
                "O.S. Version": os_version,
                "CPU Percent": cpu_perc,
                "CPU Cores": cpu_cores,
                "CPU Frequency": cpu_freq,
                "RAM Usage": ram,
            },
            "bot": {
                "Servers": len(self.bot.guilds),
                "Shards": self.bot.shard_count,
                "Members": total_members,
                "Large Servers": large_servers,
                "Total Commands": total_commands,
                "Uptime": str(self.bot.get_uptime(brief=True)),
                "Ping": ping,
                "Lines of code": self.bot.total_lines,
            },
            "shards": shards,
        }
        return statistics

    async def get_bot_commands(self):
        all_commands = []
        for command in self.bot.walk_commands():
            if command.hidden:
                continue
            is_premium = False
            if command.short_doc.startswith("`[Premium]`"):
                is_premium = True
            all_commands.append(
                dict(
                    cog=command.cog_name,
                    name=command.qualified_name,
                    aliases=command.aliases or None,
                    signature=command.signature or None,
                    is_premium=is_premium,
                    short_desc=command.short_doc or "No help found...",
                    long_desc=command.help or "No help found...",
                )
            )
        return all_commands

    async def get_top_servers(self):
        query = """SELECT guild_id, COUNT(*) as commands
                   FROM command
                   GROUP BY guild_id
                   HAVING guild_id <> ALL($1::bigint[])
                   ORDER BY commands DESC LIMIT 5;
                """
        guilds = await self.bot.pool.fetch(query, self.bot.config.ignored_guilds)
        servers = []
        for guild in guilds:
            is_premium = False
            g = self.bot.get_guild(guild["guild_id"])
            if g is None:
                continue
            if g.id in self.bot.premiums:
                is_premium = True
            servers.append(
                dict(
                    id=g.id,
                    name=str(g),
                    icon=str(g.icon_url_as(format="webp", size=128)),
                    region=str(g.region),
                    members=g.member_count,
                    commands_run=guild["commands"],
                    shard_id=g.shard_id + 1,
                    joined_at=str(g.me.joined_at),
                    is_premium=is_premium,
                )
            )
        return servers

    @tasks.loop(seconds=30.0)
    async def statistics(self):
        """POST bot statistics to private API."""
        if self.bot.debug:
            return

        await self.bot.wait_until_ready()

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.bot.config.obapi["token"],
        }

        payload_statistics = await self.get_bot_statistics()
        payload_commands = await self.get_bot_commands()
        payload_servers = await self.get_top_servers()

        await self.bot.session.post(
            f'{self.bot.config.obapi["url"]}/statistics',
            json=payload_statistics,
            headers=headers,
        )
        await self.bot.session.post(
            f'{self.bot.config.obapi["url"]}/commands',
            json=payload_commands,
            headers=headers,
        )
        await self.bot.session.post(
            f'{self.bot.config.obapi["url"]}/servers',
            json=payload_servers,
            headers=headers,
        )

    @tasks.loop(minutes=30.0)
    async def update(self):
        """Updates Bot stats on Discord portals."""
        if self.bot.debug:
            return

        await self.bot.wait_until_ready()

        # POST stats on top.gg
        payload = {
            "server_count": len(self.bot.guilds),
            "shard_count": self.bot.shard_count,
        }

        top_gg_headers = {"Authorization": self.bot.config.top_gg["token"]}

        await self.bot.session.post(
            self.bot.config.top_gg["url"], data=payload, headers=top_gg_headers
        )

        # POST stats on discord.bots.gg
        payload = {
            "guildCount": len(self.bot.guilds),
            "shardCount": self.bot.shard_count,
        }

        headers = {
            "Authorization": self.bot.config.discord_bots["token"],
            "Content-Type": "application/json",
        }

        await self.bot.session.post(
            self.bot.config.discord_bots["url"], json=payload, headers=headers
        )

    async def set_premium_for(self, target_id, *, server=True):
        server_query = """INSERT INTO server (id, prefix)
                          VALUES ($1, $2)
                          ON CONFLICT (id) DO
                          UPDATE SET premium = true;
                       """
        member_query = """INSERT INTO member (id)
                          VALUES ($1)
                          ON CONFLICT (id) DO
                          UPDATE SET premium = true;
                       """
        if server:
            await self.bot.pool.execute(server_query, target_id, self.bot.prefix)
        else:
            await self.bot.pool.execute(member_query, target_id)

    @tasks.loop(minutes=5.0)
    async def subscriptions(self):
        if self.bot.debug:
            return

        await self.bot.wait_until_ready()

        # endpoint to check for new donations
        url_new = self.bot.config.dbot["new"]
        product_server_id = self.bot.config.dbot["product_ids"]["server"]

        headers = {"Authorization": self.bot.config.dbot["api_key"]}

        async with self.bot.session.get(url_new, headers=headers) as r:
            subs = await r.json()

        if not subs["donations"]:
            return

        for sub in subs["donations"]:
            if sub["product_id"] == product_server_id:
                guild_id = int(
                    sub["seller_customs"]["Server ID (to be set as premium)"]
                )
                await self.set_premium_for(guild_id)
                self.bot.premiums.add(guild_id)
            else:
                member_id = int(sub["buyer_id"])
                await self.set_premium_for(member_id, server=False)
                self.bot.premiums.add(member_id)

            # endpoint to mark donation as processed
            url_mark = self.bot.config.dbot["mark"].format(sub["txn_id"])
            payload = {"markProcessed": True}
            async with self.bot.session.post(
                url_mark, json=payload, headers=headers
            ) as r:
                print(f'Donation {sub["txn_id"]} has been processed. Status {r.status}')

    @tasks.loop(minutes=5.0)
    async def send_overwatch_news(self):
        if self.bot.debug:
            return

        await self.bot.wait_until_ready()

        try:
            title, link, img, date = await get_overwatch_news("en_US", amount=1)
        except AttributeError:
            return
        # Get the news id from the URL
        news_id = re.search(r"\d+", link[0]).group(0)

        # Returns whether the news_id it's equals to the one stored in the database.
        # If it's equals, that specific news has already been sent.
        if int(news_id) == await self.bot.pool.fetchval(
            "SELECT news_id FROM news WHERE id=1;"
        ):
            return

        embed = discord.Embed()
        embed.title = title[0]
        embed.url = link[0]
        embed.set_author(name="Blizzard Entertainment")
        embed.set_image(url=f"https:{img[0]}")
        embed.set_footer(text=date[0])

        channel = self.bot.get_channel(self.bot.config.news_channel)

        if not channel:
            return

        await channel.send(embed=embed)

        # Once the latest news has been sent, update the older
        # news_id stored in the database with the new one.
        await self.bot.pool.execute(
            "UPDATE news SET news_id=$1 WHERE id=1;", int(news_id)
        )

    def cog_unload(self):
        self.update.cancel()
        self.statistics.cancel()
        self.subscriptions.cancel()
        self.send_overwatch_news.cancel()


def setup(bot):
    bot.add_cog(Tasks(bot))
