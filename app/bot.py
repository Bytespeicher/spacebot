import asyncio
import json
import nio
import os
import safer
import sys

from app import VERSION
from app.config import config
from app.pluginCollection import pluginCollection


class bot:
    """
    Class to act as matrix bot to get and post message
    """

    # Required configuration values
    _configRequired = [
        'controlsign',
        'homeserver',
        'username',
        'password',
        'rooms',
    ]

    # Matrix API instances
    __matrixApi = None

    # Event loop
    __loop = None

    def __init__(self):
        """
        Constructor

        Start base class constructor and initiate connection
        """

        # Load config
        self._config = config().getMatrixConfig()
        try:
            self._checkConfig()
        except LookupError as e:
            raise e

        # Set default session cache file
        if 'sessioncache' not in self._config:
            self._config['sessioncache'] = 'config/cache/matrix-session'

        # Initialize matrix api instance and connect to server
        self.__loop = asyncio.get_event_loop()
        self.__loop.run_until_complete(self.__connect())

    def __del__(self):
        """
        Destructor to cleanup matrix api instances
        """
        if self.__matrixApi is not None:
            try:
                print("MATRIX: Close connection.")
                self.__loop.run_until_complete(self.__matrixApi.close())
            except KeyError:
                pass

    def _checkConfig(self):

        configErrors = False

        # Check configuration
        for configKey in self._configRequired:
            try:
                configKey = configKey.split('.')
                if len(configKey) == 1:
                    x = self._config[configKey[0]]
                if len(configKey) == 2:
                    x = self._config[configKey[0]][configKey[1]]
            except KeyError:
                print(
                    "Configcheck: Key %s in matrix connection missing." %
                    (configKey),
                    file=sys.stderr
                )
                configErrors = True

        # Configuration error occured
        if configErrors:
            raise LookupError(
                'Configuration for matrix connection is not valid.'
            )

    async def __connect(self):
        """Login to matrix using cached session information or credentials"""

        if os.path.exists(self._config['sessioncache']):

            # Use previus session tokens
            with open(self._config['sessioncache'], 'r') as f:
                sessionCache = json.load(f)

            # Reauthenticate if homeserver and username are equal
            if (sessionCache['homeserver'] == self._config['homeserver']
                    and sessionCache['user_id'] == self._config['username']):

                print(
                    'MATRIX: Try reauthentication to homeserver %s'
                    % sessionCache['homeserver']
                )

                client = nio.AsyncClient(sessionCache['homeserver'])
                client.restore_login(
                    user_id=sessionCache['user_id'],
                    device_id=sessionCache['device_id'],
                    access_token=sessionCache['access_token']
                )

                self.__matrixApi = client

                # Try to send welcome messages to verify cached credentials
                if await self.__sendWelcomeMessages():
                    return

        print(
            'MATRIX: Authenticate to homeserver %s'
            % self._config['homeserver']
        )

        # Try to login
        client = nio.AsyncClient(
                    self._config['homeserver'],
                    self._config['username']
                 )
        loginResponse = await client.login(
                            self._config['password'],
                            device_name='botserver'
                        )

        # check that we logged in succesfully
        if (isinstance(loginResponse, nio.LoginResponse)):
            print(
                'MATRIX: Successfully authenticated to ' +
                'homeserver with device id %s.' %
                (loginResponse.device_id)
            )
            self.__matrixApi = client

            with safer.open(self._config['sessioncache'], 'w') as f:
                f.write(
                    json.dumps(
                        {
                            "homeserver": self._config['homeserver'],
                            "user_id": loginResponse.user_id,
                            "device_id": loginResponse.device_id,
                            "access_token": loginResponse.access_token
                        },
                        indent=4
                    )
                )
            print(
                'MATRIX: Save cached session for homeserver %s.'
                % self._config['homeserver']
            )
        else:
            print(
                'ERROR: Login to homeserver failed: %' %
                (loginResponse),
                file=sys.stderr
            )
            await client.close()

        # Try to send welcome message to verify login
        if await self.__sendWelcomeMessages():
            return

    async def __sendWelcomeMessages(self) -> bool:
        """Send welcome messages to all rooms

        Returns
        -------
        bool
        """

        # Set welcome phrase to name and state
        try:
            welcomePhrase = self._config['welcomemessage']
        except KeyError:
            welcomePhrase = \
                "I'm here to assist you. Try !help to get more information."

        # Join all rooms
        for room in self._config['rooms']:
            # Try to join new room and haven't joined as that user, you can use
            # Joining if already joined will also be successfull
            joinResponse = await self.__matrixApi.join(room)
            if not isinstance(joinResponse, nio.JoinResponse):
                # Join to channel failed
                print(
                    'ERROR: Matrix join to room %s failed.' %
                    (room),
                    file=sys.stderr
                )
                return False

        # Post welcome message to all rooms
        for room in self._config['rooms']:
            # Push status message to matrix
            messageResponse = await self.__matrixApi.room_send(
                room,
                message_type="m.room.message",
                content={
                    "msgtype": "m.notice",
                    "body": welcomePhrase
                }
            )

            if isinstance(messageResponse, nio.RoomSendResponse):
                print(
                    'MATRIX: Welcome message for room %s send successfully.'
                    % room
                )
            else:
                # Cached session credetials invalid,
                # remove instance and output error message
                self.__matrixApi = None
                print(
                    'ERROR: Matrix welcome message for room' +
                    '%s cound not be send.' %
                    room,
                    file=sys.stderr
                )
                return False

        return True

    def __getMatrixApi(self) -> nio.AsyncClient:
        """Get Matrix api instance for current host of the request

        Returns
        -------
        bool
        """
        try:
            return self.__matrixApi
        except KeyError:
            return None

    def __getRoom(self) -> str:
        """Get room id for current host of the request

        Returns
        -------
        string
        """
        return self._getConfig()['room']

    def run(self):
        try:
            print('Bot instance started successfully')
            self.__loop.run_until_complete(self._run())
        except KeyboardInterrupt:
            print("Received exit, exiting")

    def getMatrixApi(self):
        return self.__matrixApi

    async def _receiveMessage(
        self, room: nio.MatrixRoom, event: nio.RoomMessageText
    ):

        # only accept messages
        # - from other users
        # - starting with control sign
        # - not older as 5000ms
        if (event.sender != room.own_user_id
                and event.body.startswith(self._config['controlsign'])
                and event.source['unsigned']['age'] <= 5000):

            # Log message
            print(
                "Message received in room %s from %s: %s"
                % (room.display_name, room.user_name(event.sender), event.body)
            )

            # Split keyword and parameters
            try:
                keyword, parameter = event.body[1:].split(' ', 1)
            except ValueError:
                keyword, parameter = event.body[1:], None

            # Version request
            if (keyword == "version"):

                messageResponse = await self.__matrixApi.room_send(
                    room.room_id,
                    message_type="m.room.message",
                    content={
                        "msgtype": "m.text",
                        "body": "Running version: %s" % VERSION
                    }
                )

            # Help request
            elif (keyword == "help"):

                if parameter is None:
                    # No parameter, output global help
                    result = \
                        await pluginCollection().help(
                            self._config['controlsign'],
                            room.room_id
                        )
                else:
                    # Parameter set, output plugin help if available
                    result = \
                        await pluginCollection().keywordHelp(
                            parameter,
                            self._config['controlsign'],
                            room.room_id
                        )

                # Output valid results
                if result is not None:
                    messageResponse = await self.__matrixApi.room_send(
                        room.room_id,
                        message_type="m.room.message",
                        content={
                            "msgtype": "m.notice",
                            "format": "org.matrix.custom.html",
                            "body": "message",
                            "formatted_body":
                                "<pre><code>%s</code></pre>"
                                % result
                        }
                    )

            # Any other request
            else:
                result = \
                    await pluginCollection().keyword(
                        keyword,
                        parameter,
                        room.room_id
                    )

                if result is not None:
                    if pluginCollection().isOutputHtml(keyword):
                        # Send valid result as html
                        messageResponse = await self.__matrixApi.room_send(
                            room.room_id,
                            message_type="m.room.message",
                            content={
                                "msgtype": "m.text",
                                "format": "org.matrix.custom.html",
                                "body": "message",
                                "formatted_body": "%s" % result
                            }
                        )
                    else:
                        # Send valid result as text
                        messageResponse = await self.__matrixApi.room_send(
                            room.room_id,
                            message_type="m.room.message",
                            content={
                                "msgtype": "m.text",
                                "body": "%s" % result
                            }
                        )

    async def _run(self):
        self.__matrixApi.add_event_callback(
            self._receiveMessage,
            nio.RoomMessageText
        )
        await self.__matrixApi.sync_forever(timeout=30000, full_state=True)
