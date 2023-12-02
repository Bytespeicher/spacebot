import errno
import sys

from app.bot import bot
from app.pluginCollection import pluginCollection


def initApp() -> bot:
    """
    Initialize Matrix bot
    """

    # Initialize bot
    try:
        matrixBot = bot()
    except LookupError:
        sys.exit(errno.EINTR)

    # Initialize plugins
    try:
        pluginCollection(matrixBot.getMatrixApi())
    except LookupError:
        sys.exit(errno.EINTR)

    matrixBot.run()


if __name__ == '__main__':
    initApp()
