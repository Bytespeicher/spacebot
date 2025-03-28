import aiocron
import aiohttp
import asyncio
import datetime
import feedparser
import random
import time

import app.plugin
from app.config import config


class rss(app.plugin.plugin):
    """
    Plugin to post information from rss feeds
    """

    # Keyword
    _keywords = {
        'rss': {
            'description': 'Latest entries from RSS feeds',
            'help': True,
        }
    }

    # Default config
    _configDefault = {
        'count': {
            'merged': 1,
            'single': 3,
        },
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

        # Configuration check for feeds
        self.__configCheck()

        # Get all RSS feeds once
        asyncio.get_event_loop().run_until_complete(self.__getRss())

        # Initialize crons to refresh RSS feeds
        feedIdsDefaultCron = []
        for feed in self._config['feeds']:
            if 'cron' in feed:
                # Feed has cron definition, so run as seperate cron
                aiocron.crontab(
                    feed['cron'],
                    func=self.__getRss,
                    args=(True, [feed['id']])
                )
            else:
                # collect feed ids without cron definition
                feedIdsDefaultCron.append(feed['id'])

        # Run collected feed ids in standard cron every 15 minutes
        if len(feedIdsDefaultCron) > 0:
            randomMinute = random.randint(0,14)
            aiocron.crontab(
                '%s/15 * * * *' % randomMinute,
                func=self.__getRss,
                args=(True, feedIdsDefaultCron)
            )

        del feedIdsDefaultCron

    def __configCheck(self):
        """ Check default configuration for feeds """
        for feed in self._config['feeds']:
            # Set last published to current timestamp if empty
            try:
                feed['published']
            except KeyError:
                feed['published'] = int(datetime.datetime.now().timestamp())
            # Set summarize treshold to 0 (disabled) if empty
            try:
                feed['summarize']
            except KeyError:
                feed['summarize'] = {}
            try:
                feed['summarize']['treshold']
            except KeyError:
                feed['summarize']['treshold'] = 0

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
                if x <= feedEntryCount:
                    output += "\n"

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

        # Get max length of feed ids or "FEED-ID"
        idMaxLength = max(7, len(max(self._getIds('feeds'), key=len)))+1

        # Generate output
        output = \
            "You can query a single RSS feed using " \
            "\"%srss FEED-ID\".\n" % controlsign
        output += \
            "To get a combination from all feeds " \
            "use \"%srss all\".\n\n" % controlsign
        output += "%s | NAME" % 'FEED-ID'.rjust(idMaxLength, ' ')
        for feed in feedConfig:
            output += '\n'
            output += '%s | %s' % (feed['id'].rjust(idMaxLength), feed['name'])
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

    async def __announce(self, feedIds: list = None):

        # Check all feeds
        for feed in self._config['feeds']:

            # check if feed id list is not empty and id in list
            if feedIds is not None and feed['id'] not in feedIds:
                continue

            # No new entry
            if self.__getRssEntryPublished(feed['id'], 0) <= feed['published']:
                continue

            # No rooms to auto announce, skip feed
            if 'rooms' not in feed:
                continue

            # Get new entries
            entries = [
                entry
                for x, entry in enumerate(self.__rss[feed['id']].entries)
                if (
                    self.__getRssEntryPublished(feed['id'], x) >
                    feed['published']
                )
            ]

            # Generate output for entries
            output = ""
            for x in reversed(range(0, len(entries))):
                output += \
                    self.__formatOutput(
                        feed,
                        entries[x],
                        (feed['summarize']['treshold'] != 0)
                        and (len(entries) > feed['summarize']['treshold'])
                    )
                if x > 0:
                    output += "\n"

            # Set last published to latest entry and save config
            feed['published'] = \
                self.__getRssEntryPublished(feed['id'], 0)
            self._setConfig()

            # Add header and footer for summarize
            if (feed['summarize']['treshold'] != 0 and
                    len(entries) > feed['summarize']['treshold']):
                output = \
                    "%s | %d entries in RSS feed found:\n" % (
                        feed['name'].upper(), len(entries)
                    ) + output
                if 'link' in feed['summarize']:
                    output += "\n%s" % feed['summarize']['link']

            # Delete entries
            del entries

            # Announce message in rooms
            for roomId in feed['rooms']:
                await self._sendMessage(output, roomId, messageType="notice")

    async def __getRss(self, announce: bool = True, feedIds: list = None):

        """Get and parse latest RSS feeds"""
        for feed in self._config['feeds']:

            # check if feed id list is not empty and id in list
            if feedIds is not None and feed['id'] not in feedIds:
                continue

            # Refresh RSS feed
            async with aiohttp.ClientSession() as session:
                async with session.get(feed['url']) as response:
                    print(
                        "[%s] Refreshing RSS feed for %s from %s"
                        % (self.getName(), feed['name'], feed['url'])
                    )
                    if response.status == 200:
                        self.__rss[feed['id']] = \
                            feedparser.parse(await response.text())
                    else:
                        print(
                            "[%s] Error downloading RSS feed. HTTP status: %d"
                            % (self.getName(), response.status)
                        )

        # Announce new entries after updating RSS feed
        if announce:
            await self.__announce(feedIds=feedIds)

    def __formatOutput(self, feed: dict, entry: dict,
                       summarize: bool = False) -> str:
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

        if summarize:
            return \
                "%s" % (
                    message
                )
        else:
            return \
                "%s | %s\n%s" % (
                    feed['name'].upper(),
                    message,
                    message2
                )
