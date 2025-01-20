import os
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from types import CodeType
from typing import (
    Callable,
    Iterable,
    Optional,
    Protocol,
    Union,
)

from makex.context import Context
from makex.file_checksum import FileChecksum
from makex.python_script import FileLocation


def _trim_output(output: str):
    # prevent executable output from swamping out stdout/log
    if output is None:
        return ""

    if len(output) > 20:
        return output[:20] + "..."
    return output


class CommandOutput:
    __match_args__ = ('status', 'output', 'error', 'hash', 'location')

    def __init__(
        self,
        status: int,
        output: str = None,
        error: str = None,
        hash: str = None,
        name: str = None,
        location: FileLocation = None
    ) -> None:
        self.status = status
        self.output = output
        self.error = error
        self.hash = hash
        self.location = location
        self.name = name

    def __repr__(self):
        cls = type(self).__name__
        return f'{cls}(status={self.status!r}, output={_trim_output(self.output)!r}, error={_trim_output(self.error)!r}, hash={self.hash!r}, location={self.location!r})'

    def __eq__(self, other):
        if not isinstance(other, CommandOutput):
            return NotImplemented
        return (
            self.status,
            self.output,
            self.error,
            self.hash,
            self.location,
        ) == (
            other.status,
            other.output,
            other.error,
            other.hash,
            other.location,
        )


class CommandProtocol(Protocol):
    def __call__(self, ctx: Context, target: "TargetProtocol") -> CommandOutput:
        pass


class FileLocationProtocol:
    line: int
    column: int
    path: PathLike


class StringProtocol(Protocol):
    location: FileLocationProtocol

    def __str__(self):
        ...

    def __fspath__(self):
        ...


class PathProtocol(Protocol):
    location: FileLocationProtocol

    def __fspath__(self):
        ...


class TargetRequirementProtocol:
    name: str
    path: os.PathLike = None

    def key(self) -> str:
        ...


class WorkspaceProtocol(Protocol):
    # Path of the workspace, a directory.
    path: Path

    # File which this workspace was defined
    file: Path

    # short readable name [a-zA-Z_][a-zA-Z0-9\-._@]+
    # used in workspace prefixes
    name: str


class TargetProtocol(Protocol):
    id: StringProtocol

    name: str

    workspace: WorkspaceProtocol
    # path of the target. a directory.
    path: PathProtocol

    requires: list[TargetRequirementProtocol]
    commands: list[CommandProtocol]

    # TODO; these names/types are wrong
    inputs: dict[Union[str, None], PathProtocol]
    outputs: dict[Union[str, None], "FileStatus"]

    # which file it was defined in
    # duplicate of location?
    build_file: Path

    location: FileLocationProtocol

    def key(self) -> str:
        ...

    def path_input(self) -> PathLike:
        ...


class FileProtocol(Protocol):
    path: PathLike
    location: FileLocation


def hash_target(obj: TargetRequirementProtocol) -> str:
    return ":" + obj.name + ":" + str(obj.path)


@dataclass(frozen=True)
class FileStatus:
    path: Path
    error: Exception = None
    checksum: FileChecksum = None
    location: FileLocation = None

    def __hash__(self):
        return hash(self.key())

    def key(self):
        return self.path.as_posix() + str(self.checksum)


class FileChecksumFunction(Protocol):
    def __call__(self, file: Path) -> str:
        ...


class StringHashFunction(Protocol):
    def __call__(self, file: str) -> str:
        ...


class HashFunctions:
    file: FileChecksumFunction
    string: StringHashFunction


class MakexFileProtocol(Protocol):

    # absolute path to the makex file
    path: PathLike

    # absolute path to the folder where the makex file is defined.
    # TODO: rename to folder
    directory: PathLike

    targets: dict[str, TargetProtocol]

    macros: dict[str, Callable]

    code: Optional[CodeType] = None

    includes: list["MakexFileProtocol"]

    # TODO: rename to hash
    checksum: str

    environment_hash: str

    def hash_components(self) -> Iterable[str]:
        pass
