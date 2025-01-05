import aiocron
import aiohttp
import asyncio
import datetime
import icalendar
import recurring_ical_events
import locale
import pytz
import os
import xml.etree.ElementTree

import app.plugin
from app.config import config


class dates(app.plugin.plugin):
    """
    Plugin to post current dates from ical
    """

    # Keyword
    _keywords = {
        'dates': {
            'description': 'Next dates from calendar',
            'help': True,
        }
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

    # Calendar configurations
    __calendarConfig = {}

    # Calendar objects
    __calendar = {}

    # Parsed events
    __events = {}

    def __init__(self, matrixApi):
        """ Start base class constructor """
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

        # Get calendar configurations as dictionary
        self.__calendarConfig = self._getConfigList('calendar')

        # Get ical once and refresh bycron
        asyncio.get_event_loop().run_until_complete(self.__getIcals())
        asyncio.get_event_loop().run_until_complete(self.__announce())
        aiocron.crontab('*/60 * * * *', func=self.__getIcals)
        aiocron.crontab('* * * * *', func=self.__announce)

    async def __getIcals(self):
        """ Get iCals for all calendars """
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
                        self.__parseFile(
                            calendarConfig.get('type', 'ical'),
                            await response.text()
                        )
                    self.__parseEvents(calendarConfig)

        except Exception as e:
            # Something went wrong, remove parsed calendar
            print(
                "[%s] Refreshing calendar '%s' failed: %s"
                % (
                    self.getName(),
                    calendarConfig['name'],
                    e
                )
            )
            self.__calendar[calendarConfig['id']] = None

    def __parseFile(self, filetype, text):

        # Parse ical format
        if filetype == 'ical':
            return icalendar.Calendar.from_ical(text)

        # Parse xcal format
        if filetype == 'xcal':

            xmlFormat = xml.etree.ElementTree.fromstring(text)

            # Build ical from xcal
            icalFormat = "BEGIN:VCALENDAR" + os.linesep
            icalFormat += "PRODID;X-RICAL-TZSOURCE=TZINFO:-//com.denhaven2/"\
                          "NONSGML ri_cal gem//EN" + os.linesep
            icalFormat += "CALSCALE:GREGORIAN" + os.linesep
            icalFormat += "VERSION:2.0" + os.linesep

            # Parse event elements
            for vevent in xmlFormat.findall('vcalendar/vevent'):
                icalFormat += 'BEGIN:VEVENT' + os.linesep
                icalFormat += ('DTSTART;VALUE=DATE-TIME:%s' %
                               vevent.find('dtstart').text) + os.linesep
                icalFormat += ('DTEND;VALUE=DATE-TIME:%s' %
                               vevent.find('dtend').text) + os.linesep
                icalFormat += ('UID:%s' %
                               vevent.find('uid').text) + os.linesep
                icalFormat += ('DESCRIPTION:%s' %
                               vevent.find('description').text) + os.linesep
                icalFormat += ('URL:%s' %
                               vevent.find('url').text) + os.linesep
                icalFormat += ('SUMMARY:%s' %
                               vevent.find('summary').text) + os.linesep
                icalFormat += ('LOCATION:%s' %
                               vevent.find('location').text) + os.linesep
                icalFormat += 'END:VEVENT' + os.linesep

            # Close ical format
            icalFormat += "END:VCALENDAR"

            # Parse generated ical
            return icalendar.Calendar.from_ical(icalFormat)

    def __parseEvents(self, calendarConfig: dict):

        # Calculate start and end date
        start_date = datetime.datetime.now()
        end_date = \
            start_date + datetime.timedelta(days=self._config['list_days'])

        # Get events in interval
        eventsFromIcal = \
            recurring_ical_events.of(
                self.__calendar[calendarConfig['id']], components=["VEVENT"]
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

            # Localize start and end
            dtstart = dtstart.astimezone(pytz.timezone('Europe/Berlin'))
            dtend = dtend.astimezone(pytz.timezone('Europe/Berlin'))

            # Add event to parsed events
            eventsParsed.append({
                'calendar_id': calendarConfig['id'],
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

        self.__events[calendarConfig['id']] = eventsParsed
        return

    def __getAnnounceIntervalsByCalendarIds(self, calendarIds: list) -> list:
        """ Get individual or global announce intervals """

        # Create initial dict for interval summary
        announceIntervals = {
            "__all": []
        }

        for calendarId in calendarIds:
            try:
                announceIntervalsByCalendarId = \
                    self.__calendarConfig[calendarId]['announce_interval']
                # Ensure announce interval is a list
                if not type(announceIntervalsByCalendarId) is list:
                    announceIntervalsByCalendarId = \
                        [announceIntervalsByCalendarId]

                announceIntervals['__all'] += announceIntervalsByCalendarId
                announceIntervals[calendarId] = \
                    sorted(announceIntervalsByCalendarId)
            except KeyError:
                # Use global interval due to missing individual configuration
                announceIntervals['__all'] += self._config['announce_interval']
                announceIntervals[calendarId] = \
                    sorted(self._config['announce_interval'])

        # Consolidate announce interval summary
        announceIntervals['__all'] = \
            sorted(list(set(announceIntervals['__all'])))

        return announceIntervals

    def __isAnnounceLocation(self, calendarId: str) -> bool:
        """ Return if calendar should announce location """
        try:
            return self.__calendarConfig[calendarId]['announce_location']
        except KeyError:
            return False

    def dates(self, parameter: str, roomId: str):
        """
        Return answer

        Return
        ----------
        string
            Dates during the next days
        """

        if parameter is None:
            calendarIds = self._getIdsByRoomId('calendar', roomId)
        elif parameter == "all":
            calendarIds = self._getIds('calendar')
        elif parameter in self._getIds('calendar'):
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
                output += self.__formatOutput(event)
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
        calendarIdsRoom = self._getIdsByRoomId('calendar', roomId)

        # Get max length of calendar ids or "CALENDAR-ID"
        idMaxLength = max(11, len(max(self.__calendarConfig, key=len)))+1

        # Generate output
        output = \
            "You can query a single calendar using " \
            "\"%sdates CALENDAR-ID\".\n" % controlsign
        output += \
            "To get a combination from all calendars " \
            "use \"%sdates all\".\n\n" % controlsign
        output += "%s | NAME" % 'CALENDAR-ID'.rjust(idMaxLength, ' ')
        for calendar in calendarConfig:
            outputExtend = []
            output += '\n'
            output += '%s | %s' % (
                calendar['id'].rjust(idMaxLength, ' '), calendar['name']
            )
            if calendar['id'] in calendarIdsRoom:
                outputExtend.append("*")
            if 'limit_entries' in calendar:
                outputExtend.append(
                    "max. %d entries" % calendar['limit_entries']
                )
            if len(outputExtend) > 0:
                output += " (%s)" % ', '.join(outputExtend)

        output += "\n\n"
        output += \
            "Calendars with (*) will be used on command \"%sdates\"" \
            " and auto announcements." % controlsign

        return output

    async def __announce(self):
        """ Announce upcoming evens """

        # Get current date and time without (micro)seconds
        now = pytz.timezone('Europe/Berlin').localize(
            datetime.datetime.now().replace(second=0, microsecond=0)
        )

        # Announce dates by joined rooms
        for roomId in (await self._getJoinedRoomIds()):

            # Get events for room id
            events = self.__mergeAndSortEvents(
                calendarIds=self._getIdsByRoomId('calendar', roomId),
                ignoreLimit=True
            )

            # Get all announceIntervals
            announceIntervals = \
                self.__getAnnounceIntervalsByCalendarIds(
                    self._getIdsByRoomId('calendar', roomId)
                )

            # Generate output
            output = []
            for announceInterval in announceIntervals['__all']:

                # Loop events to find starting exactly after interval
                for event in events:

                    # Skip event if interval is not configured for calendar
                    if announceInterval not in \
                            announceIntervals[event['calendar_id']]:
                        continue

                    # Calculate datetime from now and interval
                    then = now + datetime.timedelta(minutes=announceInterval)

                    # Event found starting exactly after announce interval
                    if event['start'] == then:
                        output.append(self.__formatOutput(event))

                    # Ignore sorted events if start is after interval
                    if event['start'] > then:
                        break

            # Output single event
            if len(output) == 1:
                await self._sendMessage(
                    "Upcoming event: %s" % output[0],
                    roomId=roomId,
                    messageType="notice"
                )
            # Output multiple events
            elif len(output) > 1:
                await self._sendMessage(
                    "Upcoming events:\n%s" % "\n".join(output),
                    roomId=roomId,
                    messageType="notice"
                )

    def __mergeAndSortEvents(
            self, calendarIds: list, ignoreLimit: bool = False) -> list:
        """ Merge and sort events based on a list of calendar Ids """

        eventsMerged = []
        for calendarId in calendarIds:

            # Get events for calendar
            if ignoreLimit:
                # Ignore Limit
                eventsMerged += self.__events[calendarId]
            else:
                # Shorten event list (if limit_entries configured)
                try:
                    eventsMerged += \
                        self.__events[calendarId][
                            0:
                            self.__calendarConfig[calendarId]['limit_entries']
                        ]
                except KeyError:
                    eventsMerged += self.__events[calendarId]

        # Resort by datetime
        eventsMerged = sorted(
            eventsMerged,
            key=lambda c: c['start'],
            reverse=False
        )

        return eventsMerged

    def __formatOutput(self, event: dict) -> str:
        """ Format output """
        output = \
            "%s - %s" % (
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

        if self.__isAnnounceLocation(event['calendar_id']):
            output += " (%s)" % event['location']

        return output
