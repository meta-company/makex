from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import (
    Protocol,
    Union,
)

from makex.colors import ColorsNames
from makex.python_script import FileLocation


class MakexError(Exception):
    pass


class SomeKindOfTarget(Protocol):
    name: str
    path: str


class ExecutionError(MakexError):
    def __init__(
        self,
        error: Union[str, Exception],
        target: Union[SomeKindOfTarget],
        location: FileLocation = None
    ):
        super().__init__(error)
        self.error = error
        self.target = target
        self.location = location


@dataclass(frozen=True)
class GenericFileLocation:
    path: Path
    line: int = None
    column: int = None


class GenericSyntaxError(MakexError):
    def __init__(
        self, error: Union[str, Exception], location: GenericFileLocation, type, context=(1, 2)
    ):
        super().__init__(error)
        self.error = error
        self.location = location
        self.context = context
        self.type = type

    def pretty(self, colors: ColorsNames):
        location = self.location
        exception = self.error

        buf = StringIO()
        buf.write(
            f"{colors.ERROR}Error{colors.RESET} inside the {self.type} file '{colors.BOLD}{location.path}{colors.RESET}:{location.line}'\n\n"
        )

        buf.write(f"{colors.ERROR}{exception}{colors.RESET}'\n\n")

        context_before, context_after = self.context
        with Path(location.path).open("r") as f:
            for i, line in enumerate(f):
                li = i + 1

                if li >= location.line - context_before and li < location.line:
                    buf.write(f"  {li}: " + line)
                elif li <= location.line + context_after and li > location.line:
                    buf.write(f"  {li}: " + line)
                elif li == location.line:
                    buf.write(f">>{li}: " + line)

        return buf.getvalue()


class CacheError(MakexError):
    pass


class Error(MakexError):
    pass


class MissingInputFileError(MakexError):
    location: FileLocation

    def __init__(self, message, location):
        pass


class MissingOutputFileError(MakexError):
    location: FileLocation

    def __init__(self, message, location):
        pass


class MultipleErrors(MakexError):
    def __init__(self, erorrs: list[Exception]):
        pass
