import asyncio
import inspect
import os
import pkgutil

import app.plugin
from app.config import config


class pluginCollection:
    """
    plugin collection to scan for plugins and realise hooks

    Implentation based on
    https://www.guidodiepen.nl/2019/02/implementing-a-simple-plugin-framework-in-python/
    """

    # Singleton instance
    __instance = None

    # Plugins package module identifier
    __pluginsPackage = 'app.plugins'

    # Plugin object cache
    __plugins = {}

    # Registered keywords
    __keywords = {}

    # Scanned paths
    __scannedPaths = []

    def __new__(singletonClass, matrixApi=None):
        """Instantiate singleton class"""
        if singletonClass.__instance is None:
            print('Initialize plugins...')
            singletonClass.__instance = \
                super(pluginCollection, singletonClass).__new__(singletonClass)
            singletonClass.__instance.__reloadPlugins(matrixApi)
        return singletonClass.__instance

    def __reloadPlugins(self, matrixApi):
        """Reset the list of all plugins and initiate all available plugins"""
        self.__plugins = {}
        self.__scannedPaths = []
        print('Looking for plugins under package %s' % self.__pluginsPackage)
        self.__scanPlugins(self.__pluginsPackage, matrixApi)

    def __scanPlugins(self, package, matrixApi):
        """Recursively walk the supplied package to retrieve all plugins"""

        # Ignore __pycache__ folders
        if package.split('.')[-1] == '__pycache__':
            return

        # Import package from parameters
        importedPackage = __import__(package, fromlist=['test'])

        # Scan all plugins in package
        for _, pluginname, ispkg in \
                pkgutil.iter_modules(
                    importedPackage.__path__,
                    importedPackage.__name__ + '.'
                ):
            if not ispkg:
                plugin_module = __import__(pluginname, fromlist=['test'])
                classmembers = \
                    inspect.getmembers(plugin_module, inspect.isclass)
                for (_, c) in classmembers:
                    # Only add classes that are a sub class
                    # of plugin, but NOT plugin itself
                    if (
                        issubclass(c, app.plugin.plugin)
                        and c is not app.plugin.plugin
                        and config().isPluginEnabled(c.__name__)
                            ):
                        # Add plugin
                        self.__plugins[c.__name__] = c(matrixApi)
                        print(
                            '  Found plugin %s with keyword(s) %s...'
                            % (
                                c.__name__,
                                c.getKeywords(self.__plugins[c.__name__])
                            )
                        )
                        # Register keywords and help
                        self.__keywords = {
                            **self.__keywords,
                            **c.registerKeywords(self.__plugins[c.__name__])
                        }

        # Scan all modules in current package recursively
        if isinstance(importedPackage.__path__, str):
            allCurrentPaths = [importedPackage.__path__]
        else:
            allCurrentPaths = [x for x in importedPackage.__path__]

        # Scan all paths for packages
        for packagePath in allCurrentPaths:
            if packagePath not in self.__scannedPaths:
                self.__scannedPaths.append(packagePath)

                # Get all subdirectory of the current package path directory
                childPackages = \
                    [p for p in os.listdir(packagePath)
                     if os.path.isdir(os.path.join(packagePath, p))]

                # For each subdirectory, apply the
                # __scanPlugins method recursively
                for childPackage in childPackages:
                    self.__scanPlugins(package + '.' + childPackage, matrixApi)

    async def help(self, controlsign: str, roomId: str) -> str:
        maxLengthKeywords = len(max(self.__keywords.keys(), key=len))
        output = "%s%s\n  %s" \
            % (
                controlsign,
                'help [command]',
                'Show extended help for command if available. '
                'Example: %shelp dates' % controlsign
            )

        for keyword, value in self.__keywords.items():

            # Room ID not in rooms list
            if len(value['rooms']) > 0 and roomId not in value['rooms']:
                continue

            output += \
                "\n%s%s\n  %s" \
                % (controlsign, keyword, value['description'])

        return output

    async def keyword(self, keyword: str, parameter: str, roomId) -> str:
        """
        Run plugin method for keyword
        """

        # Keyword is not valid
        if keyword not in self.__keywords.keys():
            return None

        # Get plugin name
        pluginName = self.__keywords[keyword]['plugin']

        # Room ID not in rooms list
        if len(self.__keywords[pluginName]['rooms']) > 0 \
                and roomId not in self.__keywords[pluginName]['rooms']:
            return None

        # Run plugin method
        try:
            keywordMethod = getattr(
                self.__plugins[pluginName],
                keyword
            )

            # Call (a)synchronous function
            if inspect.iscoroutinefunction(keywordMethod):
                result = await keywordMethod(parameter, roomId)
            else:
                result = keywordMethod(parameter, roomId)

        except AttributeError:
            result = "Plugin method for keyword not implemented."

        return result

    async def keywordHelp(self, keyword: str, controlsign: str, roomId) -> str:
        """
        Run plugin help function for keyword if implemented
        """
        try:
            keywordMethod = getattr(
                self.__plugins[self.__keywords[keyword]['plugin']],
                'help'
            )
            result = keywordMethod(controlsign, roomId)
        except (KeyError, AttributeError):
            result = "Plugin method has no extended help."

        return result
