import logging
from typing import Protocol

from makex._logging import (
    BOLD_SEQ,
    COLOR_SEQUENCS,
    RESET_SEQ,
)


class ColorsNames(Protocol):
    ERROR: str
    INFO: str
    WARNING: str
    CRITICAL: str
    RESET: str
    BOLD: str
    MAKEX: str


class Colors:
    MAKEX = COLOR_SEQUENCS[logging.DEBUG] + BOLD_SEQ
    ERROR = COLOR_SEQUENCS[logging.ERROR] + BOLD_SEQ
    INFO = COLOR_SEQUENCS[logging.INFO] + BOLD_SEQ
    WARNING = COLOR_SEQUENCS[logging.WARNING] + BOLD_SEQ
    CRITICAL = COLOR_SEQUENCS[logging.CRITICAL] + BOLD_SEQ

    RESET = RESET_SEQ
    BOLD = BOLD_SEQ


class NoColors:
    ERROR = ""
    INFO = ""
    WARNING = ""
    CRITICAL = ""
    RESET = ""
    BOLD = ""
    MAKEX = ""
