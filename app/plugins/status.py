import aiocron
import aiohttp
import asyncio
import datetime
import json

import app.plugin
from app.config import config


class status(app.plugin.plugin):
    """
    Plugin to post current status
    """

    # Keyword
    _keywords = {
        'status': {
            'description': 'Current room status',
            'rooms': [],
        }
    }

    # Default config
    _configDefault = {
        'cache_interval': 60,
        'show_people': False
    }

    # Required configuration values
    _configRequired = [
        'cache_interval',
        'show_people',
    ]

    # Status objects
    __status = {}

    # Last status update
    __statusUpdate = {}

    def __init__(self, matrixApi):
        """Start base class constructor"""
        try:
            super().__init__(matrixApi)
        except LookupError as e:
            print(e)
            raise e

        # Set available rooms from config
        self._keywords['status']['rooms'] = self._getRooms('status')

        # Get status once
        for statusConfig in self._config['status']:
            asyncio.get_event_loop().run_until_complete(
                self.__getStatus(statusConfig)
            )

    async def __getStatus(self, statusConfig: dict):
        """Refresh status if older than cache time"""

        try:
            # Ignore refresh if cache interval is not reached
            if (
                self.__statusUpdate[statusConfig['id']]
                + datetime.timedelta(seconds=self._config['cache_interval'])
            ) > datetime.datetime.now():
                return
        except KeyError:
            pass

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(statusConfig['url']) as response:
                    print(
                        "[%s] Refreshing status for %s from %s"
                        % (
                            self.getName(),
                            statusConfig['id'],
                            statusConfig['url']
                        )
                    )
                    if response.status == 200:
                        self.__status[statusConfig['id']] = \
                            json.loads(await response.text())
                        self.__statusUpdate[statusConfig['id']] = \
                            datetime.datetime.now()
                    else:
                        print(
                            "[%s] Error downloading status. HTTP status: %d"
                            % (self.getName(), response.status)
                        )

        except Exception as e:
            # Something went wrong, remove saved status
            print(
                "[%s] Refreshing status '%s' failed: %s"
                % (
                    self.getName(),
                    statusConfig['id'],
                    e
                )
            )
            self.__status[statusConfig['id']] = None

    async def status(self, parameter: str, roomId: str):
        """Return answer

        Return
        ----------
        string
            Status
        """
        if parameter is not None:
            return "Invalid parameter for !status"

        if len(self._getIdsByRoomId('status', roomId)) == 0:
            return "No status configured for this room."

        # Get required configs
        statusConfigs = list(
            filter(
                lambda c: c['id'] in self._getIdsByRoomId('status', roomId),
                self._config['status']
            )
        )

        # Refresh and output status
        output = ''
        for i, statusConfig in enumerate(statusConfigs):
            await self.__getStatus(statusConfig)
            output += self.__formatOutput(statusConfig['id'])
            # Allow multiple status outputs per room
            if i < len(statusConfig)-1:
                output += "\n"

        return output

    def __formatOutput(self, statusId: str) -> str:
        """ Output space status"""
        try:
            output = "%s is %s." % (
                self.__status[statusId]['space'],
                ("CLOSED", "OPEN")[self.__status[statusId]['state']['open']]
            )
        except (KeyError, TypeError):
            return "No valid space status found."

        try:
            if self._config['show_people'] \
                and int(self.__status[statusId]['sensors']
                        ['people_now_present'][0]['value']) > 0:
                output += " %d people present: %s" % (
                    int(self.__status[statusId]['sensors']
                        ['people_now_present'][0]['value']),
                    ', '.join(
                        self.__status[statusId]['sensors']
                        ['people_now_present'][0]['names']
                    )
                )
        except (KeyError, TypeError):
            pass

        return output
