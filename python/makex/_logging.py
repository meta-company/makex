import logging
import sys
from functools import (
    partial,
    partialmethod,
)
from logging import StreamHandler

from makex.colors import (
    BOLD,
    RESET,
    BLUE,
    RED,
    WHITE,
    YELLOW,
)

debug = logging.debug
error = logging.error
info = logging.info
warn = logging.warning
warning = logging.warning

# hack in a new trace level https://stackoverflow.com/a/55276759
logging.TRACE = 5
logging.addLevelName(logging.TRACE, 'TRACE')
logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
logging.trace = partial(logging.log, logging.TRACE)

trace = logging.trace

LOGGER = logging.getLogger("makex")

COLOR_SEQUENCES = {
    logging.WARNING: YELLOW,
    logging.INFO: WHITE,
    logging.DEBUG: BLUE,
    logging.CRITICAL: RED,
    logging.ERROR: RED,
    logging.TRACE: WHITE,
}


class ColoredStream(logging.StreamHandler):
    def __init__(
        self,
        fmt="%(COLOR)s[makex][%(levelname)s]%(RESET)s[%(BOLD)s%(name)s%(RESET)s] (%(BOLD)s%(filename)s%(RESET)s:%(lineno)d) %(message)s",
        colors=COLOR_SEQUENCES,
    ):
        super().__init__()
        self.colors = colors
        self.formatter = logging.Formatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        level_color = self.colors.get(record.levelno, "")
        #level_color = COLOR_SEQ % level_color if level_color else "

        record.__dict__["COLOR"] = level_color
        record.__dict__["BOLD"] = BOLD
        record.__dict__["RESET"] = RESET

        print(self.formatter.format(record))


def initialize_logging(color=False, level=logging.NOTSET):
    logger = logging.getLogger()

    for handler in logger.handlers:
        logger.removeHandler(handler)

    if level:
        if color:
            logger.addHandler(ColoredStream())
        else:
            fmt = logging.Formatter(
                fmt="[%(levelname)s][%(name)s] (%(filename)s:%(lineno)d) %(message)s "
            )
            handler = StreamHandler(sys.stdout)
            handler.setLevel(level)
            handler.setFormatter(fmt)
            logger.addHandler(handler)
        logger.setLevel(level)
