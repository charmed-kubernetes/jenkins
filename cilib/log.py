""" log module
"""

import sys

from loguru import logger

logger.remove()
logger.add(
    "ci.log", rotation="5 MB", level="DEBUG"
)  # Automatically rotate too big file
logger.level("INFO", color="<green><bold>")
logger.add(
    sys.stderr,
    colorize=True,
    format="{time:HH:mm:ss} | <level>{level: <8} | {message}</level>",
)


debug = logger.debug
error = logger.error
info = logger.info
exception = logger.exception


class DebugMixin:
    def _prep_args(self, args):
        name = self.__class__.__name__
        if hasattr(self, "name"):
            name = self.name
        msg, *tail = args
        return f"[{name}] {msg}", *tail

    def log(self, *args, **kwargs):
        self.info(*args, **kwargs)

    def debug(self, *args, **kwargs):
        debug(*self._prep_args(args), **kwargs)

    def info(self, *args, **kwargs):
        info(*self._prep_args(args), **kwargs)

    def exception(self, *args, **kwargs):
        exception(*self._prep_args(args), **kwargs)

    def error(self, *args, **kwargs):
        error(*self._prep_args(args), **kwargs)
