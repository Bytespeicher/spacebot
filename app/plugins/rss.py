import aiocron
import aiohttp
import asyncio
import datetime
import feedparser
import time

import app.plugin
from app.config import config


class rss(app.plugin.plugin):
    """
    Plugin to post information from rss feeds
    """

    # Keyword
    _keywords = {
        'rss': 'Return latest entries from RSS feeds',
    }

    # Default config
    _configDefault = {
        'count': {
            'merged': 1,
            'single': 3
        }
    }

    # Required configuration values
    _configRequired = [
        'feeds',
    ]

    # RSS objects
    __rss = {}

    def __init__(self, matrixApi):
        """Start base class constructor"""
        try:
            super().__init__(matrixApi)
        except LookupError as e:
            print(e)
            raise e

        # Check last published timestamp and set to current timestamp if empty
        for feed in self._config['feeds']:
            try:
                feed['published']
            except KeyError:
                feed['published'] = int(datetime.datetime.now().timestamp())

        # Get RSS once and refresh by cron
        asyncio.get_event_loop().run_until_complete(self.__getRss())
        aiocron.crontab('R/15 * * * *', func=self.__getRss)
        aiocron.crontab('* * * * *', func=self.__announce)

    def rss(self, parameter, roomId):
        """Return answer

        Return
        ----------
        string
            Information and links of latest feed item(s)
        """

        # No parsed RSS found
        if len(self.__rss) == 0:
            return "No valid RSS feed available. Please try again later"

        # Use merged count by default
        feedEntryCount = self._config['count']['merged']

        if parameter is None:
            feedIds = self._getIdsByRoomId('feeds', roomId)
        elif parameter == "all":
            feedIds = self._getIds('feeds')
        elif parameter in self._getIds('feeds'):
            feedIds = [parameter]
            feedEntryCount = self._config['count']['single']
        else:
            return "Invalid parameter for !rss"

        # No feeds to check
        if len(feedIds) == 0:
            return "No RSS feeds found."

        # Check each feed
        output = ''
        for feed in self._config['feeds']:
            # Skip feed not in feedIds
            if feed['id'] not in feedIds:
                continue

            # Output configured number of entries
            for x in range(0, feedEntryCount):
                try:
                    output += self.__formatOutput(
                         feed, self.__rss[feed['id']].entries[x]

                         )
                except IndexError:
                    pass

        return output

    def help(self, controlsign: str, roomId: str):

        # Get sorted list of feed configuration
        feedConfig = sorted(
            self._config['feeds'],
            key=lambda c: c['id'],
            reverse=False
        )

        # Get rss used in this room
        feedIdsRoom = self._getIdsByRoomId('feeds', roomId)

        # Generate output
        output = \
            "You can query a single RSS feed using " \
            "\"%srss [feed id]\".\n" % controlsign
        output += \
            "To get a combination from all feeds " \
            "use \"%srss all\".\n" % controlsign
        output += "Available feeds:\n"
        for feed in feedConfig:
            output += '\n'
            output += '[%s] %s' % (feed['id'], feed['name'])
            if feed['id'] in feedIdsRoom:
                output += " (*)"

        output += "\n\n"
        output += \
            "RSS feeds with (*) will be used on command \"%srss\"" \
            " and auto announcements." % controlsign

        return output

    def __getRssEntryPublished(self, feedId: str, entryId):

        return \
            int(
                datetime.datetime.fromtimestamp(
                    time.mktime(
                        self.__rss[feedId].entries[entryId].published_parsed
                    ),
                    datetime.timezone.utc
                ).timestamp()
            )

    async def __announce(self):

        # Check all feeds
        for feed in self._config['feeds']:

            # No new entry
            if self.__getRssEntryPublished(feed['id'], 0) <= feed['published']:
                continue

            # No rooms to auto announce, skip feed
            if 'rooms' not in feed:
                continue

            for x in reversed(range(0, len(self.__rss[feed['id']].entries))):
                if self.__getRssEntryPublished(
                        feed['id'], x) > feed['published']:
                    for roomId in feed['rooms']:
                        await self._sendMessage(
                            self.__formatOutput(
                                feed,
                                self.__rss[feed['id']].entries[x]
                            ),
                            roomId
                        )

                    feed['published'] = \
                        self.__getRssEntryPublished(feed['id'], x)

        self._setConfig()

    async def __getRss(self):
        """Get and parse latest RSS feeds"""
        for feed in self._config['feeds']:
            async with aiohttp.ClientSession() as session:
                async with session.get(feed['url']) as response:
                    print(
                        "[%s] Refreshing RSS feed for %s from %s"
                        % (self.getName(), feed['name'], feed['url'])
                    )
                    if response.status == 200:
                        self.__rss[feed['id']] = \
                            feedparser.parse(await response.text())

    def __formatOutput(self, feed: dict, entry: dict) -> str:
        """Format RSS entry"""

        # Format Dokuwiki
        if feed['type'] == 'dokuwiki':
            message = \
                "%s changed %s" % (
                    entry.author.split("@", 1)[0],
                    entry.title.split(" - ", 1)[0]
                )
            if len(entry.title.split(" - ", 1)) == 2:
                message += " (comment: %s)" % entry.title.split(" - ", 1)[1]
            message2 = "%s" % entry.link.split("?", 1)[0]
        # Format Wordpress
        elif feed['type'] == 'wordpress':
            message = "%s added %s" % (entry.author, entry.title)
            message2 = "%s" % entry.link.split("?", 1)[0]
        else:
            print(entry)
            message = "%s: %s" % (entry.author, entry.title)
            message2 = "%s" % entry.link

        return \
            "%s | %s\n%s\n" % (
                feed['name'].upper(),
                message,
                message2
            )
