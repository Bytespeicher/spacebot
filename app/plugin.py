import pydeepmerge
import sys

from abc import ABC, abstractmethod
from app.config import config


class plugin(ABC):
    """Abstract base class for each plugin

    All methods that all plugins must implement should be defined here

    Implentation based on
    https://www.guidodiepen.nl/2019/02/implementing-a-simple-plugin-framework-in-python/
    """

    # Configuration
    _config = {}

    # Matrix Asyncclient
    __matrixApi = None

    def getName(self) -> str:
        return self.__class__.__name__

    def __init__(self, matrixApi):
        self._loadConfig()
        self.__matrixApi = matrixApi
        try:
            self._checkConfig()
        except LookupError as e:
            raise e

    def _loadConfig(self) -> dict:
        self._config = config().getPluginConfig(self.getName())

        if hasattr(self, '_configDefault'):
            self._config = pydeepmerge.deep_merge(
                self._configDefault,
                self._config
            )

        return self._config

    def _checkConfig(self):

        configErrors = False

        # No configuration check required
        if not hasattr(self, '_configRequired'):
            return

        # Check configuration by required values
        for configKey in self._configRequired:

            try:
                configKey = configKey.split('.')
                if len(configKey) == 1:
                    x = self._config[configKey[0]]
                if len(configKey) == 2:
                    x = self._config[configKey[0]][configKey[1]]
            except KeyError:
                print(
                    "Configcheck: [%s] Key %s missing." %
                    (self.getName(), configKey),
                    file=sys.stderr
                )
                configErrors = True

        # Configuration error occured
        if configErrors:
            raise LookupError(
                    'Configuration for plugin %s not valid.' % self.getName()
            )

    def _setConfig(self) -> dict:
        config().setPluginConfig(self.getName(), self._config)

    def _getConfigList(self, configName: str) -> dict:
        """ Return configuration sub list as dictionary """
        return {v['id']: v for k, v in enumerate(self._config[configName])}

    def registerKeywords(self) -> dict:
        return {
            keyword: {
                'plugin': self.getName(),
                'description':
                    config.get('description', "No description available."),
                'rooms': config.get('rooms', []),
                'help': config.get('help', False),
                'outputHtml': config.get('outputHtml', False),
            } for keyword, config in self._keywords.items()}

    def getKeywords(self) -> str:
        return ','.join(self._keywords.keys())

    async def _getJoinedRoomIds(self) -> list:
        """Return list of joined room ids"""
        try:
            return (await self.__matrixApi.joined_rooms()).rooms
        except Exception as e:
            print("Error getting joined rooms: %s" % e)
            return []

    async def _sendMessage(
            self, message, roomId: str = None, messageType: str = "text"):

        # Get rooms by plugin, global rooms or given parameter
        if roomId is None:
            try:
                rooms = self._config['rooms']
            except KeyError:
                rooms = config().getMatrixRooms()
        else:
            rooms = [roomId]

        if messageType not in ['text', 'notice']:
            raise ValueError("Wrong value for messageType")

        for room in rooms:
            print(
                "[%s] Send message in room %s:\n%s"
                % (self.getName(), room, message)
            )
            messageResponse = await self.__matrixApi.room_send(
                room,
                message_type="m.room.message",
                content={
                    "msgtype": "m.%s" % messageType,
                    "body": "%s" % message
                }
            )

    def _getIdsByRoomId(self, configName: str, roomId: str) -> list:
        """Get list of item id with roomId
           in room filter or no room filter"""
        return [
            d['id']
            for d in self._config[configName]
            if 'rooms' in d and roomId in d['rooms']
        ]

    def _getIds(self, configName: str) -> list:
        """Get list of all items id"""
        return [d['id'] for d in self._config[configName]]

    def _getRooms(self, configName: str) -> list:
        """Get list of all configured rooms for the plugin"""
        return [
            item for row in
            self._config[configName] for item in row['rooms']
        ]
