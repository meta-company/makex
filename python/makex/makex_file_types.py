import os
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import (
    Optional,
    Union,
)

from makex.context import Context
from makex.protocols import FileProtocol
from makex.python_script import (
    FileLocation,
    ListValue,
    PythonScriptError,
    StringValue,
)
from makex.target import format_hash_key

ListTypes = (list, ListValue)

# TODO: handle bytes

PathLikeTypes = Union[StringValue, "PathElement", "PathObject"]
MultiplePathLike = Union["Glob", "FindFiles"]
AllPathLike = Union["Glob", "FindFiles", StringValue, "PathElement"]

SENTINEL = object()


class VariableValue:
    pass


class Variable:
    name: str
    value: VariableValue
    location: FileLocation


@dataclass(frozen=True)
class Variant:
    name: str
    value: str


class RegularExpression:
    pattern: str
    location: FileLocation

    def __init__(self, pattern, location):
        self.pattern = pattern
        self.location = location

    def __str__(self):
        return self.pattern


class Glob:
    pattern: StringValue
    location: FileLocation

    def __init__(self, pattern, location):
        self.pattern = pattern
        self.location = location

    def __str__(self):
        return self.pattern


@dataclass()
class Expansion:
    """
    Define a string that will expand according to the shells rules.

    expand("~/.config/path") will expand a  user path.

    expand("$VARIABLE") will expand a variable.

    On Unix and Windows, a string that starts with ~ or ~user replaced by that user’s home directory.

    On Unix, an initial ~ is replaced by the environment variable HOME if it is set;
    otherwise the current user’s home directory is looked up in the password directory through the built-in module pwd.
    An initial ~user is looked up directly in the password directory.

    On Windows, USERPROFILE will be used if set, otherwise a combination of HOMEPATH and HOMEDRIVE will be used.
     An initial ~user is handled by checking that the last directory component of the current user’s home directory
     matches USERNAME, and replacing it if so.

    If the expansion fails or if the path does not begin with a tilde, the path is returned unchanged.

    Substrings of the form $name or ${name} are replaced by the value of environment variable name.
     Malformed variable names and references to non-existing variables are left unchanged.

    """
    context: Context
    string: StringValue
    location: FileLocation

    # XXX: cache the expanded state
    _expanded: str = None

    def expand(self, ctx):
        string = self.string
        return os.path.expandvars(os.path.expanduser(string))

    def __str__(self):
        if self._expanded is not None:
            return self._expanded

        self._expanded = self.expand(self.context)
        return self._expanded

    def __repr__(self):
        return f"Expansion({self.string!r})"


class PathObject:
    """
    The [output] path() object in makex files.

    TODO: Rename to TaskPath.
    TODO: use str instead of path for late evaluation.

    """
    def __init__(
        self,
        path: Path,
        reference: Optional["TargetReferenceElement"] = None,
        location: FileLocation = None
    ):
        self.path: Path = path
        self.location = location
        self.reference = reference

    def __str__(self):
        return self.path.as_posix()

    def __repr__(self):
        return f"PathObject(path={self.path.as_posix()!r})"

    def __truediv__(self, other):
        if isinstance(other, StringValue):
            return PathObject(self.path.joinpath(other.value), location=other.location)
        elif isinstance(other, PathObject):
            return PathObject(self.path / other.path, location=other.location)
        else:
            top = self
            bottom = other
            raise TypeError(f"Unsupported operation: {top} / {bottom!r}")


class BuildPathVariable:
    location: FileLocation

    def __init__(self, location=None):
        self.location = location

    def __str__(self):
        return "$$$$$$BUILD$$$$$$$"


class TargetOutput:
    def __str__(self):
        return "$$$$$TARGET-OUTPUT$$$$$"


class PathElement:
    """

    Implements the Path() object as defined in spec.

    Arbitrary paths, relative or absolute.

    """
    # the original path as defined
    parts: Union[tuple[str], list[str]] = None

    # Resolved is the actual fully resolved absolute path if any.
    # XXX: This is an optimization for when we can resolve a path
    resolved: Path

    location: FileLocation

    # base path of relative paths
    base: str

    def __init__(self, *args: str, base: str = None, resolved=None, location=None):
        # TODO: change *args to parts.
        self.parts = args
        self.location = location
        self.resolved = resolved
        self._path = path = Path(*args)
        self.base = base
        if resolved is None:
            if path.is_absolute():
                self.resolved = path
        else:
            self.resolved = resolved

    @property
    def name(self):
        return StringValue(self._path.name, self.location)

    def _as_path(self):
        return self._path

    if False:

        def absolute(self, _location_: FileLocation = None) -> "PathElement":
            """
            Used in the script environment to make paths absolute.

            :param root:
            :return:
            """

            # TODO: we should get _line/column/path from the transform call
            path = Path(*self.parts)

            if not path.is_absolute():
                path = self.base / path

            return PathElement(*path.parts, resolved=path, location=_location_)

    def __truediv__(self, other):
        if isinstance(other, StringValue):
            if self.resolved:
                _path = Path(other)
                resolved = self.resolved.joinpath(*_path.parts)
            else:
                _path = Path(other)
                resolved = None

            parts = self.parts + _path.parts

            return PathElement(*parts, resolved=resolved, location=other.location)

        if not isinstance(other, PathElement):
            raise TypeError(f"Unsupported operation {self} / {other}")

        resolved = None
        if other.resolved and self.resolved:
            raise TypeError(
                f"Can't combine two fully absolute resolved Paths. "
                f"The first path must be absolute, and the other path must be relative \n. "
                f"Unsupported operation {self} / {other}"
            )
        else:
            if self.resolved:
                resolved = self.resolved.joinpath(*other.parts)
            elif other.resolved:
                raise TypeError("Can't combine unresolved path with resolved path.")

        parts = self.parts + other.parts
        return PathElement(*parts, resolved=resolved, location=other.location)

    def __repr__(self):
        return f'PathElement({self._as_path()})'

    def __str__(self):
        if self.resolved:
            return str(self.resolved)
        else:
            raise Exception("Can't use unresolved path here.")


class FindFiles:
    """
    find files. relative paths are based on the input.
    """
    pattern: Union[Glob, RegularExpression]
    path: Optional[PathElement] = None

    location: FileLocation

    def __init__(self, pattern, path, location):
        self.pattern = pattern
        self.path = path
        self.location = location


@dataclass(frozen=True)
class TargetOutputsReference:
    """
    Reference to an output.

    TargetReference(name, path).outputs[output_id]
    or
    Target[path:name].outputs[output_id]

    output_id is either an integer to access an item from a list, or a string to access items from a dictionary.

    If output_id is not specified, return all the outputs.
    """
    target: "TargetReferenceElement"
    output_name: Optional[StringValue] = None


@dataclass(frozen=True)
class TargetReferenceElement:
    """
    A reference to a target in a makex file: Target(name, path).

    Also synthesized when a string with : is passed to a target argument.
    """
    name: StringValue
    path: Union[PathElement, StringValue] = None
    location: FileLocation = None

    def __getattr__(self, item):
        if item in ["inputs", "outputs"]:
            return self.with_parameter

    def __repr__(self):
        path = self.path
        if path is not None:
            return f"TargetReferenceElement({self.name.value!r}, {path!r})"

        return f"TargetReferenceElement({self.name.value!r})"

    def outputs(self, name=None):
        return TargetOutputsReference(self, name)


@dataclass(frozen=True)
class ResolvedTargetReference:
    """
    Used in a target graph and for external matching.
    """
    name: StringValue

    # path the actual makex file containing the target
    path: Path

    # where this reference was defined
    location: FileLocation = None

    def key(self):
        return format_hash_key(self.name, self.path)

    def __eq__(self, other):
        #assert isinstance(other, ResolvedTargetReference), f"Got {type(other)} {other}. Expected ResolvedTarget"
        assert hasattr(other, "key"), f"{other!r} has no key() method."
        assert callable(getattr(other, "key"))
        return self.key() == other.key()

    def __hash__(self):
        return hash(self.key())


class TargetType:
    def _get_item(self, subscript, location: FileLocation):
        if isinstance(subscript, slice):
            # handle target[start:stop:step]
            # TODO: use step for variants.
            path, target, variants = subscript.start, subscript.stop, subscript.step
            if path is None and target:
                return TargetReferenceElement(target)
            elif path and target is None:
                raise PythonScriptError("Invalid target reference. Missing target name.", location)
            elif path and target:
                return TargetReferenceElement(target, path, location=location)
        else:
            # handle target[item]
            # TODO: handle locations
            if not isinstance(subscript, StringValue):
                raise PythonScriptError(
                    f"Subscript must be a string. Got {subscript!r} ({type(subscript)})",
                    location=location
                )
            return TargetReferenceElement(subscript, location=location)


class FileObject(FileProtocol):
    path: PathLike
    location: FileLocation


class EnvironmentVariableProxy:
    def __init__(self, env: dict[str, str]):
        self.__env = env
        # record usages of environment variables so we can include it as part of the hashing of targets/makex files.
        self.__usages: dict[str, str] = {}

    def get(self, key, default=SENTINEL, _location_: FileLocation = None) -> StringValue:
        item = self.__env.get(key, default)
        if item is None or item is SENTINEL:
            raise PythonScriptError(f"Environment variable {key} not defined.", _location_)

        self.__usages[key] = item

        return StringValue(item, location=_location_)

    def _usages(self):
        return self.__usages
