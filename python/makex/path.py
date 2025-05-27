from pathlib import Path
from pathlib import Path as PathlibPath
from typing import (
    Optional,
    Protocol,
    Union,
)

from makex.python_script import (
    FileLocation,
    FileLocationProtocol,
    get_location,
)


class PathProtocol(Protocol):
    """ Path with the original location it came from.
    """
    location: FileLocationProtocol
    name: str
    parent: Optional["PathProtocol"]
    parts: list[str]
    anchor: str
    suffixes: list[str]

    def __init__(
        self, path: Union[str, PathlibPath], location: FileLocationProtocol = None, **kwargs
    ):
        ...

    def open(self, *args, **kwargs):
        ...

    def exists(self) -> bool:
        ...

    def is_absolute(self) -> bool:
        ...

    def is_file(self) -> bool:
        ...

    def is_symlink(self) -> bool:
        ...

    def write_text(self, *args, **kwargs):
        ...

    def is_dir(self) -> bool:
        ...

    def stat(self) -> tuple:
        ...

    def as_posix(self) -> str:
        ...

    def mkdir(self, **kwargs):
        ...

    def __fspath__(self):
        ...

    def __truediv__(self, other):
        ...

    def __repr__(self):
        ...

    def __hash__(self):
        ...

    def __eq__(self, other):
        ...

    def __str__(self):
        ...


class PathWithLocation:
    """ Path with the original location it came from.
    
        This has the same interface as pathlib.Path.
        
        TODO: have liberty to improve the performance here.
    """
    location: FileLocation

    def __init__(self, path: Union[Path, str], location: FileLocation = None, **kwargs):
        self._parts = path.parts
        self._path = path
        self.location = location
        self.name = path.name
        self.parent = path.parent

    def open(self, *args, **kwargs):
        return self._path.open(*args, **kwargs)

    @property
    def parts(self):
        return self._parts

    @property
    def suffixes(self):
        return self._path.suffixes

    @property
    def anchor(self):
        return self._path.anchor

    def is_relative_to(self, other: "PathWithLocation"):
        if isinstance(other, PathWithLocation):
            return self._path.is_relative_to(other._path)
        return self._path.is_relative_to(other)

    def relative_to(self, other: "PathWithLocation"):
        if isinstance(other, PathWithLocation):
            return self._path.relative_to(other._path)
        return self._path.relative_to(other)

    def is_absolute(self):
        return self._path.is_absolute()

    def is_file(self):
        return self._path.is_file()

    def is_symlink(self):
        return self._path.is_symlink()

    def write_text(self, *args, **kwargs):
        return self._path.write_text(*args, **kwargs)

    def is_dir(self):
        return self._path.is_dir()

    def stat(self):
        return self._path.stat()

    def as_posix(self):
        return self._path.as_posix()

    def mkdir(self, **kwargs):
        return self._path.mkdir(**kwargs)

    def __truediv__(self, other):
        new_path = self._path / other

        if isinstance(other, str):
            return PathWithLocation(new_path, self.location)
        else:
            return PathWithLocation(new_path, get_location(other, self.location))

    def exists(self):
        return self._path.exists()

    def __repr__(self):
        return f"Path({repr(self._path)})"

    def __fspath__(self):
        return self._path.as_posix()

    def __hash__(self):
        return self._path.__hash__()

    def __eq__(self, other):
        if isinstance(other, PathWithLocation):
            return self._path.__eq__(other._path)

        return self._path.__eq__(other)

    def __str__(self):
        return self.as_posix()
