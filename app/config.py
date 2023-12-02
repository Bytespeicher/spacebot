import os
import pydeepmerge
import sys
import yaml


class config:
    """Data ORM for config"""

    # Singleton instance
    __instance = None

    # Data in memory
    __config = {}

    # Filename from loaded config
    __filename = None

    def __new__(singletonClass):
        """Instantiate singleton class"""
        if singletonClass.__instance is None:
            print('Initialize config orm object...')
            singletonClass.__instance = \
                super(config, singletonClass).__new__(singletonClass)
            singletonClass.__load(
                    singletonClass.__instance,
                    'config/config.yaml'
            )
        return singletonClass.__instance

    def __load(self, filename: str):
        """Load and check configuration from yaml file

        Parameters
        ----------
        filename : str
            Filename of the yaml configuration file
        """

        configErrors = False
        self.__filename = filename

        # Read configuration from yaml file
        with open(self.__filename, 'r') as configfile:
            self.__config = yaml.load(configfile, Loader=yaml.FullLoader)

        # Test if matrix connection config is defined
        if 'matrix' not in self.__config or self.__config['matrix'] is None:
            print(
                "Configcheck: No matrix connection configuration defined",
                file=sys.stderr
            )
            configErrors = True

        # Stop if any error occured
        if configErrors:
            sys.exit(1)

    def __save(self):
        """Write configuration to yaml file"""
        with open(self.__filename, 'w') as configfile:
            yaml.dump(self.__config, configfile)

    def getConfig(self) -> dict:
        return self.__config

    def getMatrixConfig(self) -> dict:
        return self.__config['matrix']

    def getMatrixRooms(self) -> list:
        return self.__config['matrix']['rooms']

    def getPluginConfig(self, plugin: str) -> dict:
        """ Get plugin configuration """
        try:
            pluginConfig = self.__config['plugins'][plugin]
        except KeyError:
            pluginConfig = {}

        return pluginConfig

    def setPluginConfig(self, plugin: str, data: dict):
        """ Set plugin configuration """
        self.__config['plugins'][plugin] = data
        self.__save()
        return self.__config['plugins'][plugin]
