import locale
import datetime

import app.plugin
from app.config import config


class time(app.plugin.plugin):
    """
    Plugin to post current time
    """

    # Keyword
    _keywords = {
        'now': 'Return current date and time',
    }

    # Default config
    _configDefault = {
        'locale': None
    }

    # Required configuration values
    _configRequired = []

    def __init__(self, matrixApi):
        """Start base class constructor"""
        try:
            super().__init__(matrixApi)
        except LookupError as e:
            print(e)
            raise e

        # set locale for time
        try:
            locale.setlocale(locale.LC_TIME, self._config['locale'])
        except locale.Error:
            print(
                "[%s] Locale %s is not valid. Setting system default."
                % (self.getName(), self._config['locale'])
            )
            locale.setlocale(locale.LC_TIME, None)

    def now(self, parameter: str, roomId):
        """Return answer

        Return
        ----------
        string
            Current localized date and time
        """
        return datetime.datetime.now().strftime('%A, %-d. %B %Y %H:%M:%S')
