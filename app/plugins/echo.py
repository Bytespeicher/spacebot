import app.plugin

from app.config import config


class echo(app.plugin.plugin):
    """
    Plugin to echo given parameters
    """

    # Keyword
    _keywords = {
        'echo': 'Bot returns text after keyword echo',
    }

    # Default config
    _configDefault = {}

    # Required configuration values
    _configRequired = []

    def __init__(self, matrixApi):
        """Start base class constructor"""
        try:
            super().__init__(matrixApi)
        except LookupError as e:
            print(e)
            raise e

    def echo(self, parameter: str, roomId):
        """Return parameter after keyword echo

        Return
        ----------
        string
            Current parameter
        """
        if parameter is not None:
            return parameter
        else:
            return "Nothing to echo here."
