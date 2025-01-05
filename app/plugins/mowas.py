import aiocron
# import aiohttp
import asyncio
import datetime
# import json
import pytz

from deutschland import nina
from deutschland.nina.api import warnings_api
from deutschland.nina.exceptions import ApiException, NotFoundException

import app.plugin
from app.config import config


class mowas(app.plugin.plugin):
    """
    Plugin to post current notifications from "Modulare Warnsystem" (MoWaS)
    """

    # Keyword
    _keywords = {
        'mowas': {
            'description':
                'Current entries from "Modulares Warnsystem" (MoWaS)',
            'rooms': [],
            'help': True,
            'outputHtml': True
        }
    }

    # Default config
    _configDefault = {}

    # Required configuration values
    _configRequired = [
        'format.datetime'
    ]

    # API Url for MoWaS
    __apiUrl = "https://nina.api.proxy.bund.dev/api31"
    # __apiUrl = "https://warnung.bund.de/api31"

    # Url for detailed web informations
    __warningDetailUrl = "https://warnung.bund.de/meldungen/"

    # Colors for severity
    __severityColor = {
        'Unknown':  '#FFFF00',
        'Minor':  '#FFFF00',
        'Moderate': '#FFA500',
        'Severe': '#FF0000',
        'Extreme': '#EE82EE',
        'Cancel': '#888888'
    }

    # Warning Type constants
    TYPE_OTHER = 0
    TYPE_HIGHWATER = 1
    TYPE_WEATHER = 2

    # Provider based informations
    # EXTREME: Extreme Gefahr (violett)
    # SEVERE: Gefahr (rot)
    # MINOR: Gefahreninformation (orange)
    # cancel -> Entwarnung (weiss)
    __provider = {
        '_all': {
            'type': TYPE_OTHER,
            # Extracted from NINA Warn App
            'severity': {
                'Unknown': 'Unbekannt',
                'Minor': 'Warnung',
                'Moderate': 'Gefahreninformationr',
                'Severe': 'Gefahr',
                'Extreme': 'Extreme Gefahr',
                'Cancel': 'Entwarnung'
            }
        },
        'LHP': {
            'sendername': 'Länderübergreifendes Hochwasserportal',
            'type': TYPE_HIGHWATER,
            # Extracted from NINA Warn App
            'severity': {
                'Unknown': 'Vorwarnung',
                'Minor': 'Hochwasserwarnung',
                'Moderate': 'Hochwasser',
                'Severe': 'Großes Hochwasser',
                'Extreme': 'Extremes Hochwasser'
            }
        },
        'DWD': {
            'sendername': 'Deutscher Wetterdienst',
            'type': TYPE_WEATHER,
            # https://www.dwd.de/DE/leistungen/opendata/help/warnungen/cap_dwd_profile_de_pdf_1_12.pdf
            'severity': {
                'Unknown': 'Unbekannt',
                'Minor': 'Wetterwarnung',
                'Moderate': 'Markante Wetterwarnung',
                'Severe': 'Unwetterwarnung',
                'Extreme': 'Extreme Unwetterwarnung'
            }
        }
    }

    # Mowas objects
    __mowasWarningsApi = None

    # Mowas messages
    __mowas = {}

    def __init__(self, matrixApi):
        """Start base class constructor"""
        try:
            super().__init__(matrixApi)
        except LookupError as e:
            print(e)
            raise e

        # Configuration check for feeds
        self.__configCheck()

        # Create MoWaS client instance
        mowasClient = \
            nina.ApiClient(
                nina.Configuration(host=self.__apiUrl)
            )
        self.__mowasWarningsApi = \
            nina.api.warnings_api.WarningsApi(mowasClient)

        # Get location configurations as dictionary
        self.__locationConfig = self._getConfigList('locations')

        # Get mowas messages once and refresh by cron
        asyncio.get_event_loop().run_until_complete(self.__getLocations())
        aiocron.crontab('* * * * *', func=self.__getLocations)

    def __configCheck(self):
        """ Check default configuration for locations """
        for location in self._config['locations']:
            # Set last published to current timestamp if empty
            try:
                location['published']
            except KeyError:
                location['published'] = \
                    int(datetime.datetime.now().timestamp())

    async def __getLocations(self):
        """ Get mowas messages for all locations """
        for location in self._config['locations']:
            await self.__getLocation(location)

        # Announce new entries after updating location informations
        await self.__announce()

    async def __getLocation(self, locationConfig: dict):

        try:
            print(
                "[%s] Refreshing messages for '%s'"
                % (
                    self.getName(),
                    locationConfig['name'],
                )
            )

            # Run async threads for update
            thread = \
                self.__mowasWarningsApi.get_dashboard(
                    str(locationConfig['ars']), async_req=True
                )
            self.__mowas[locationConfig['id']] = thread.get().get('value')

            # Sort warnings by sent date descendant
            self.__mowas[locationConfig['id']] = sorted(
                self.__mowas[locationConfig['id']],
                key=lambda c: c['sent'],
                reverse=True
            )
        except (
            nina.exceptions.NotFoundException, nina.exceptions.ApiException
        ) as e:
            # Something went wrong, remove parsed messages
            print(
                "[%s] Refreshing messages for '%s' failed: %s"
                % (
                    self.getName(),
                    locationConfig['name'],
                    e
                )
            )
            self.__mowas[locationConfig['id']] = None

    async def mowas(self, parameter: str, roomId: str, announce: bool = None):
        """Return answer

        Return
        ----------
        string
            MoWaS messages
        """

        if parameter is None:
            locationIds = self._getIdsByRoomId('locations', roomId)
        elif parameter == "all":
            locationIds = self._getIds('locations')
        elif parameter in self._getIds('locations'):
            locationIds = [parameter]
        else:
            return "Invalid parameter for !mowas"

        output = ""
        for locationId in locationIds:

            # Ignore empty mowas warning list
            if self.__mowas[locationId] is None:
                continue

            # Get last published datetime for location
            if announce is True:
                published = pytz.timezone('Europe/Berlin').localize(
                    datetime.datetime.fromtimestamp(
                        self.__locationConfig[locationId]['published']
                    )
                )

            warningIndex = 0
            for warning in self.__mowas[locationId]:

                # Ignore entries before timestamp
                if announce is True and warning['sent'] <= published:
                    continue

                # Set published to latest (first) warning on announcement
                if announce is True and warningIndex == 0:
                    self.__locationConfig[locationId]['published'] = \
                        int(warning['sent'].timestamp())

                # Ignore highwater or weather
                if (
                    not self.__getTypeConfigured(locationId, 'highwater') and
                    self.__getType(warning) == self.TYPE_HIGHWATER
                ) or (
                    not self.__getTypeConfigured(locationId, 'weather') and
                    self.__getType(warning) == self.TYPE_WEATHER
                ):
                    continue

                output += self.__formatOutput(
                    warning, locationId, len(locationIds)
                )
                output += "<br />"

                warningIndex += 1

        if len(output) == 0 and announce is False:
            # No warnings found
            output = \
                "No warnings available"

        if announce is True:
            self._setConfig()

        return output

    def help(self, controlsign: str, roomId: str):

        # Get sorted list of location configuration
        locationConfig = sorted(
            self._config['locations'],
            key=lambda c: c['id'],
            reverse=False
        )

        # Get locations used in this room
        locationIdsRoom = self._getIdsByRoomId('locations', roomId)

        # Get max length of location ids or "LOCATION-ID"
        idMaxLength = max(11, len(max(self.__locationConfig, key=len)))+1

        # Generate output
        output = \
            "You can query a single location using " \
            "\"%smowas LOCATION-ID\".\n" % controlsign
        output += \
            "To get a combination from all locations " \
            "use \"%smowas all\".\n\n" % controlsign
        output += "%s | NAME" % 'LOCATION-ID'.rjust(idMaxLength, ' ')
        for location in locationConfig:
            outputExtend = []
            output += '\n'
            output += '%s | %s' % (
                location['id'].rjust(idMaxLength, ' '), location['name']
            )
            if location['id'] in locationIdsRoom:
                outputExtend.append("*")
            if len(outputExtend) > 0:
                output += " (%s)" % ', '.join(outputExtend)

        output += "\n\n"
        output += \
            "Locations with (*) will be used on command \"%smowas\"" \
            " and auto announcements." % controlsign

        return output

    async def __announce(self):
        """ Announce warnings """

        # Get current date and time without (micro)seconds
        now = pytz.timezone('Europe/Berlin').localize(
            datetime.datetime.now().replace(second=0, microsecond=0)
        )

        # Announce warnings by joined roooms
        for roomId in (await self._getJoinedRoomIds()):

            output = \
                await self.mowas(parameter=None, roomId=roomId, announce=True)

            if len(output) > 0:
                await self._sendMessage(
                    output,
                    roomId=roomId,
                    messageType="html"
                )

    def __formatOutput(
            self, warning: dict, locationId: str, locationCount: int) -> str:
        """ Output warning"""

        # Resolve well-known provider names
        try:
            provider = \
                self.__provider[
                    warning['payload']['data']['provider']
                ]['sendername']
        except KeyError:
            provider = warning['payload']['data']['provider']

        # Get severity from warning
        severity = warning['payload']['data']['severity']

        # Handle cancelations as severity
        if warning['payload']['data']['msg_type'] == "Cancel":
            severity = "Cancel"

        # Resolve severity to well-known names
        try:
            severityName = \
                self.__provider[
                    warning['payload']['data']['provider']
                ]['severity'][severity]
        except KeyError:
            severityName = \
                self.__provider['_all']['severity'][severity]

        # Create output for warning
        output = ""
        try:
            # Prefix location name on multiple locations
            if locationCount > 1:
                output += "%s | " % (
                    self.__locationConfig[locationId]['name']
                )
            # Add colored message
            output += \
                "<font color=\"%s\"><strong>%s</strong></font> | "\
                "<a href=\"%s%s\">%s</a> | %s" % (
                    self.__severityColor[severity],
                    severityName,
                    self.__warningDetailUrl,
                    warning['id'],
                    warning['i18n_title']['de'],
                    provider
                )

            # Add update information
            if warning['payload']['data']['msg_type'].lower() == 'update':
                output += "<font color=\"#666666\"> | Aktualisierung</font>"

            # Add validity date
            if 'onset' in warning and 'expires' in warning:
                output += \
                    "<br /><font color=\"#aaaaaa\"><i> " \
                    "(gültig vom %s bis %s)</i></font>" % (
                        warning['onset'].strftime(
                            self._config['format']['datetime']
                        ),
                        warning['expires'].strftime(
                            self._config['format']['datetime']
                        )
                    )

        except (KeyError, TypeError) as e:
            # No valid warning found
            output = ""

        return output

    def __getType(self, warning: dict) -> str:
        """ Get type of warning """
        try:
            return \
                self.__provider[
                    warning['payload']['data']['provider']
                ]['type']
        except KeyError:
            return \
                self.__provider['_all']['type']

    def __getTypeConfigured(self, locationId: str, configKey: str) -> bool:
        """ Get configuration value for configured type """
        try:
            return self.__locationConfig[locationId][configKey]
        except KeyError:
            return True
