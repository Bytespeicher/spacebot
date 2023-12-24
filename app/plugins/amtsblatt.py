import aiocron
import aiohttp
import asyncio
import datetime
import feedparser

from time import mktime
from datetime import datetime, timezone

import app.plugin
from app.config import config


class amtsblatt(app.plugin.plugin):
    """
    Plugin to announce current link to Amtsblatt der Landeshauptstadt Erfurt
    """

    # Keyword
    _keywords = {
        'amtsblatt': {
            'description': 'Link to latest "Amtsblatt der Landeshauptstadt Erfurt"',
        }
    }

    # Default config
    _configDefault = {
        'published': 0
    }

    # Required configuration values
    _configRequired = [
        'rss',
    ]

    # RSS object
    __rss = None

    def __init__(self, matrixApi):
        """Start base class constructor"""
        try:
            super().__init__(matrixApi)
        except LookupError as e:
            print(e)
            raise e

        # Get RSS once and refresh by cron
        asyncio.get_event_loop().run_until_complete(self.__getRss())
        aiocron.crontab('0 */4 * * *', func=self.__getRss)

    def amtsblatt(self, parameter, roomId):
        """Return answer

        Return
        ----------
        string
            Current link to latest Amtsblatt
        """
        try:
            return self.__rss.entries[0].link
        except IndexError:
            return "No valid RSS feed available. Please try again later"

    def __getRssLastEntryPublished(self):
        return \
            int(
                datetime.fromtimestamp(
                    mktime(self.__rss.entries[0].published_parsed),
                    timezone.utc
                ).timestamp()
            )

    async def __announce(self):
        # No new entry
        if self.__getRssLastEntryPublished() <= self._config['published']:
            return

        await self._sendMessage(
            "%s: %s\n%s" % (
                "Neu veröffentlicht",
                self.__rss.entries[0].title,
                self.__rss.entries[0].link
            ),
            messageType="notice"
        )
        self._config['published'] = self.__getRssLastEntryPublished()
        self._setConfig()

    async def __getRss(self, announce=True):
        """Get and parse latest RSS feed"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self._config['rss']) as response:
                print(
                    "[%s] Refreshing RSS feed from %s"
                    % (self.getName(), self._config['rss'])
                )
                self.__rss = feedparser.parse(await response.text())

        if announce:
            await self.__announce()
