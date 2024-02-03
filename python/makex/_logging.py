import logging
import sys
from logging import StreamHandler

LOGGER = logging.getLogger("makex")

#These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = [30 + r for r in range(8)]
COLORS = {
    logging.WARNING: YELLOW,
    logging.INFO: WHITE,
    logging.DEBUG: BLUE,
    logging.CRITICAL: YELLOW,
    logging.ERROR: RED
}

COLOR_SEQUENCS = {
    logging.WARNING: COLOR_SEQ % YELLOW,
    logging.INFO: COLOR_SEQ % WHITE,
    logging.DEBUG: COLOR_SEQ % BLUE,
    logging.CRITICAL: COLOR_SEQ % YELLOW,
    logging.ERROR: COLOR_SEQ % RED
}


class ColoredStream(logging.StreamHandler):
    def __init__(
        self,
        fmt="%(COLOR)s[%(levelname)s]%(RESET)s[%(BOLD)s%(name)s%(RESET)s] (%(BOLD)s%(filename)s%(RESET)s:%(lineno)d) %(message)s",
        colors=COLORS,
    ):
        super().__init__()
        self.colors = colors
        self.formatter = logging.Formatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        level_color = self.colors.get(record.levelno, False)
        level_color = COLOR_SEQ % level_color if level_color else ""
        record.__dict__["COLOR"] = level_color
        record.__dict__["BOLD"] = BOLD_SEQ
        record.__dict__["RESET"] = RESET_SEQ

        print(self.formatter.format(record))


def initialize_logging(color=False, level=logging.NOTSET):
    logger = logging.getLogger()

    #if level:
    #    logging.basicConfig(level=level)

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


debug = logging.debug
error = logging.error
info = logging.info
warn = logging.warning
warning = logging.warning
#addLoggingLevel("TRACE", logging.DEBUG -5)

import logging
from functools import (
    partial,
    partialmethod,
)

# hack in a new trace level https://stackoverflow.com/a/55276759
logging.TRACE = 5
logging.addLevelName(logging.TRACE, 'TRACE')
logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
logging.trace = partial(logging.log, logging.TRACE)

trace = logging.trace