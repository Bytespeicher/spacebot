import aiocron
import aiohttp
import asyncio
import datetime
import icalendar
import recurring_ical_events
import locale
import pytz

import app.plugin
from app.config import config


class dates(app.plugin.plugin):
    """
    Plugin to post current dates from ical
    """

    # Keyword
    _keywords = {
        'dates': 'Show current dates',
    }

    # Default config
    _configDefault = {
        'locale': None
    }

    # Required configuration values
    _configRequired = [
        'announce_interval',
        'calendar',
        'list_days',
        'format.datetime',
    ]

    # Calendar objects
    __calendar = {}

    # Parsed events
    __events = {}

    def __init__(self, matrixApi):
        """Start base class constructor"""
        try:
            super().__init__(matrixApi)
        except LookupError as e:
            print(e)
            raise e

        # Ensure announce interval is a list
        if not type(self._config['announce_interval']) is list:
            self._config['announce_interval'] = \
                [self._config['announce_interval']]

        # set locale for time
        try:
            locale.setlocale(locale.LC_TIME, self._config['locale'])
        except locale.Error:
            print(
                "[%s] Locale %s is not valid. Setting system default."
                % (self.getName(), self._config['locale'])
            )
            locale.setlocale(locale.LC_TIME, None)

        # Get ical once and refresh bycron
        asyncio.get_event_loop().run_until_complete(self.__getIcals())
        asyncio.get_event_loop().run_until_complete(self.__announce())
        aiocron.crontab('*/60 * * * *', func=self.__getIcals)
        aiocron.crontab('* * * * *', func=self.__announce)

    async def __getIcals(self):
        """Get icals for all calendars"""
        for calendar in self._config['calendar']:
            await self.__getIcal(calendar)

    async def __getIcal(self, calendarConfig: dict):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(calendarConfig['url']) as response:
                    print(
                        "[%s] Refreshing calendar '%s' from URL %s"
                        % (
                            self.getName(),
                            calendarConfig['name'],
                            calendarConfig['url']
                        )
                    )
                    self.__calendar[calendarConfig['id']] = \
                        icalendar.Calendar.from_ical(await response.text())
                    self.__parseEvents(calendarConfig['id'])

        except Exception as e:
            # Something went wrong, remove parsed calender
            print(
                "[%s] Refreshing calendar '%s' failed: %s"
                % (
                    self.getName(),
                    calendarConfig['name'],
                    e
                )
            )
            self.__calendar[calendarConfig['id']] = None

    def __parseEvents(self, calendarId):

        # Calculate start and end date
        start_date = datetime.datetime.now()
        end_date = \
            start_date + datetime.timedelta(days=self._config['list_days'])

        # Get events in interval
        eventsFromIcal = \
            recurring_ical_events.of(
                self.__calendar[calendarId], components=["VEVENT"]
            ).between(start_date, end_date)

        # Parse events
        eventsParsed = []
        for event in eventsFromIcal:

            # Get start and end date/time
            dtstart = event.get('DTSTART').dt
            dtend = event.get('DTEND').dt

            # Convert date to datetime to handle whole day events
            if type(dtstart) is datetime.date:
                dtstart = pytz.timezone('Europe/Berlin').localize(
                    datetime.datetime(
                        year=dtstart.year,
                        month=dtstart.month,
                        day=dtstart.day,
                        hour=0,
                        minute=0,
                        second=0
                    )
                )
            if type(dtend) is datetime.date:
                dtend = pytz.timezone('Europe/Berlin').localize(
                    datetime.datetime(
                        year=dtend.year,
                        month=dtend.month,
                        day=dtend.day,
                        hour=0,
                        minute=0,
                        second=0
                    )
                )

            # Add event to parsed events
            eventsParsed.append({
                'start': dtstart,
                'end': dtend,
                'summary': event.get('SUMMARY'),
                'location': event.get('LOCATION'),
                'description': event.get('DESCRIPTION'),
            })

        eventsParsed = sorted(
            eventsParsed,
            key=lambda c: c['start'],
            reverse=False
        )

        self.__events[calendarId] = eventsParsed
        return

    def __getCalendarIdsByRoomId(self, roomId: str) -> list:
        """Get list of calender id with roomId
           in room filter or no room filter"""
        return [
            d['id']
            for d in self._config['calendar']
            if 'rooms' not in d or roomId in d['rooms']
        ]

    def __getCalendarIds(self) -> list:
        """Get list of all calender id"""
        return [d['id'] for d in self._config['calendar']]

    def dates(self, parameter: str, roomId: str):
        """Return answer

        Return
        ----------
        string
            Dates during the next days
        """

        if parameter is None:
            calendarIds = self.__getCalendarIdsByRoomId(roomId)
        elif parameter == "all":
            calendarIds = self.__getCalendarIds()
        elif parameter in self.__getCalendarIds():
            calendarIds = [parameter]
        else:
            return "Invalid parameter for !dates"

        # Get all events for calendar ids
        eventsMerged = self.__mergeAndSortEvents(
            calendarIds
        )

        if len(eventsMerged) >= 1:
            # Events found
            output = "Please notice the next following event(s):"
            for event in eventsMerged:
                output += "\n"
                output += \
                    "  %s - %s" % (
                        event['start'].strftime(
                            self._config['format']['datetime']
                        ),
                        event['summary']
                    )
                if event['end'].date() > event['start'].date():
                    output += \
                        " (until %s)" % (
                            event['end'].strftime(
                                self._config['format']['datetime']
                            )
                        )
        else:
            # No event found
            output = \
                "No dates during the next %d days" % self._config['list_days']

        del eventsMerged
        return output

    def help(self, controlsign: str, roomId: str):

        # Get sorted list of calendar configuration
        calendarConfig = sorted(
            self._config['calendar'],
            key=lambda c: c['id'],
            reverse=False
        )

        # Get calendars used in this room
        calendarIdsRoom = self.__getCalendarIdsByRoomId(roomId)

        # Generate output
        output = \
            "You can query a single calendar using " \
            "\"%sdates [calender id]\".\n" % controlsign
        output += \
            "To get a combination from all calendars " \
            "use \"%sdates all\".\n" % controlsign
        output += "Available calenders:\n"
        for calendar in calendarConfig:
            output += '\n'
            output += '[%s] %s' % (calendar['id'], calendar['name'])
            if calendar['id'] in calendarIdsRoom:
                output += " (*)"

        output += "\n\n"
        output += \
            "Calendars with (*) will be used on command \"%sdates\"" \
            "and auto announcements." % controlsign

        return output

    async def __announce(self):
        """Announce upcoming evens"""

        # Get current date and time without (micro)seconds
        now = pytz.timezone('Europe/Berlin').localize(
            datetime.datetime.now().replace(second=0, microsecond=0)
        )

        # Announce dates by joined rooms
        for roomId in (await self._getJoinedRoomIds()):
            # Get events for room id
            events = self.__mergeAndSortEvents(
                self.__getCalendarIdsByRoomId(roomId)
            )

            # Loop announce intervals
            for announceInterval in self._config['announce_interval']:

                # Loop events to find starting exactly after interval
                for event in events:
                    # Calculate datetime from now and interval
                    then = now + datetime.timedelta(minutes=announceInterval)
                    if event['start'] == then:
                        # Event found starting exactly after announce interval
                        await self._sendMessage(
                            "Upcoming event: %s - %s" % (
                                event['start'].strftime(
                                    self._config['format']['datetime']
                                ),
                                event['summary']
                            ),
                            roomId
                        )
                    if event['start'] > then:
                        # Ignore sorted events if start is after interval
                        break

    def __mergeAndSortEvents(self, calendarIds: list) -> list:
        """ Merge and sort events based on a list of calendar Ids"""
        eventsMerged = []
        for calendarId in calendarIds:
            eventsMerged += self.__events[calendarId]

        # Resort by datetime
        eventsMerged = sorted(
            eventsMerged,
            key=lambda c: c['start'],
            reverse=False
        )

        return eventsMerged
