from typing import Protocol

# These are the sequences need to get colored output
RESET = "\033[0m"
_COLOR_TEMPLATE = "\033[1;%dm"
BOLD = "\033[1m"

_BLACK, _RED, _GREEN, _YELLOW, _BLUE, _MAGENTA, _CYAN, _WHITE = [30 + r for r in range(8)]

BLACK = _COLOR_TEMPLATE % _BLACK
RED = _COLOR_TEMPLATE % _RED
YELLOW = _COLOR_TEMPLATE % _YELLOW
GREEN = _COLOR_TEMPLATE % _GREEN
CYAN = _COLOR_TEMPLATE % _CYAN
BLUE = _COLOR_TEMPLATE % _BLUE
MAGENTA = _COLOR_TEMPLATE % _MAGENTA
WHITE = _COLOR_TEMPLATE % _WHITE


class ColorsNames(Protocol):
    ERROR: str
    INFO: str
    WARNING: str
    CRITICAL: str
    RESET: str
    BOLD: str
    MAKEX: str


class Colors:
    MAKEX = GREEN + BOLD
    ERROR = RED + BOLD
    INFO = WHITE + BOLD
    WARNING = YELLOW + BOLD
    CRITICAL = RED + BOLD

    RESET = RESET
    BOLD = BOLD


class NoColors:
    ERROR = ""
    INFO = ""
    WARNING = ""
    CRITICAL = ""
    RESET = ""
    BOLD = ""
    MAKEX = ""
