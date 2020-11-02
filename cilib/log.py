""" log module
"""

import sys

import click
from loguru import logger

logger.remove()
logger.add(
    "ci.log", rotation="5 MB", level="DEBUG"
)  # Automatically rotate too big file
logger.add(
    sys.stderr,
    colorize=True,
    format="{time:HH:mm:ss} | <level>{level}</level> <green><b>{message}</b></green>",
    level="INFO",
)
logger.add(
    sys.stderr,
    colorize=True,
    format="{time:HH:mm:ss} | <level>{level}</level> <red><b>{message}</b></red>",
    level="ERROR",
)


def debug(ctx):
    logger.debug(ctx)


def error(ctx):
    click.secho(ctx, fg="red", bold=True)
    logger.debug(ctx)


def info(ctx):
    logger.info(ctx)


class DebugMixin:
    def debug(self, msg):
        name = self.__class__.__name__
        if hasattr(self, "name"):
            name = self.name
        debug(f"[{name}] {msg}")

    def log(self, msg):
        name = self.__class__.__name__
        if hasattr(self, "name"):
            name = self.name
        info(f"[{name}] {msg}")
