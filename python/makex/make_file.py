import logging
import os
import re
import shlex
import shutil
import sys
import time
from abc import (
    ABC,
    abstractmethod,
)
from collections import deque
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from dataclasses import dataclass
from io import StringIO
from itertools import chain
from os import PathLike
from os.path import (
    expanduser,
    join,
)
from pathlib import Path
from threading import (
    Event,
    current_thread,
)
from typing import (
    Any,
    Iterable,
    Optional,
    Pattern,
    Protocol,
    TypedDict,
    Union,
)

from makex._logging import (
    debug,
    error,
    trace,
)
from makex.build_path import get_build_path
from makex.constants import (
    DIRECT_REFERENCES_TO_MAKEX_FILES,
    ENVIRONMENT_VARIABLES_IN_GLOBALS_ENABLED,
    HASH_USED_ENVIRONMENT_VARIABLES,
    OUTPUT_DIRECTLY_TO_CACHE,
    WORKSPACES_IN_PATHS_ENABLED,
)
from makex.context import Context
from makex.errors import ExecutionError
from makex.file_checksum import FileChecksum
from makex.file_system import find_files
from makex.flags import (
    ABSOLUTE_PATHS_ENABLED,
    ARCHIVE_FUNCTION_ENABLED,
    EXPAND_FUNCTION_ENABLED,
    FIND_FUNCTION_ENABLED,
    FIND_IN_INPUTS_ENABLED,
    GLOB_FUNCTION_ENABLED,
    GLOBS_IN_INPUTS_ENABLED,
    GLOBS_IN_RUNNABLES_ENABLED,
    HOME_FUNCTION_ENABLED,
    NAMED_OUTPUTS_ENABLED,
    NESTED_WORKSPACES_ENABLED,
    SHELL_USES_RETURN_CODE_OF_LINE,
)
from makex.patterns import (
    combine_patterns,
    make_glob_pattern,
)
from makex.protocols import (
    CommandOutput,
    FileProtocol,
    StringHashFunction,
    TargetProtocol,
)
from makex.python_script import (
    FileLocation,
    ListValue,
    PythonScriptError,
    PythonScriptFile,
    ScriptEnvironment,
    StringValue,
    wrap_script_function,
)
from makex.run import run
from makex.target import (
    ArgumentData,
    EvaluatedTarget,
    TargetKey,
    format_hash_key,
    target_hash,
)
from makex.ui import pretty_file
from makex.workspace import Workspace

ListTypes = (list, ListValue)


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

    expand("~/.config/path") will exapnd a  user path.

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

    """
    def __init__(self, path: Path, location: FileLocation = None):
        self.path: Path = path
        self.location = location

    def __str__(self):
        return self.path.as_posix()

    def __repr__(self):
        return f"PathObject(path={self.path.as_posix()!r})"

    def __truediv__(self, other):
        if isinstance(other, StringValue):
            return PathObject(self.path.joinpath(other.value), other.location)
        elif isinstance(other, PathObject):
            return PathObject(self.path / other.path, other.location)
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
                f"Can't combine two fully absolute resolved Paths. The first path must be absolute, and the other path must be relative \n. Unsupported operation {self} / {other}"
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


def _validate_path(parts: Union[list[str], tuple[str]], location: FileLocation):
    if ".." in parts:
        raise PythonScriptError("Relative path references not allowed in makex.", location)
    if ABSOLUTE_PATHS_ENABLED is False and parts[0] == "/":
        raise PythonScriptError("Absolute path references not allowed in makex.", location)
    return True


VALID_NAME_RE = r"^[a-zA-Z][a-zA-Z0-9\-._@]*"
VALID_NAME_PATTERN = re.compile(VALID_NAME_RE, re.U)


def _validate_target_name(name: StringValue, location: FileLocation):
    if not VALID_NAME_PATTERN.match(name):
        raise PythonScriptError(
            f"Target has an invalid name {name!r}. Must be {VALID_NAME_RE!r} (regular expression).",
            location
        )
    return True


def resolve_string_path_workspace(
    ctx: Context,
    workspace: Workspace,
    element: StringValue,
    base: Path,
) -> Path:
    _path = path = Path(element.value)

    _validate_path(path.parts, element.location)

    if path.parts[0] == "//":
        trace("Workspace path: %s %s", workspace, element)
        if WORKSPACES_IN_PATHS_ENABLED:
            _path = workspace.path / Path(*path.parts[1:])
        else:
            raise PythonScriptError("Workspaces markers // in paths not enabled.", element.location)
    elif not path.is_absolute():
        _path = base / path

    trace("Resolve string path %s: %s", element, _path)

    return _path


def resolve_path_element_workspace(
    ctx: Context,
    workspace: Workspace,
    element: PathElement,
    base: Path,
) -> Path:
    if element.resolved:
        path = element.resolved
    else:
        path = Path(*element.parts)

    _validate_path(path.parts, element.location)

    if path.parts[0] == "//":

        trace("Workspace path: %s %s", workspace, element)
        if WORKSPACES_IN_PATHS_ENABLED:
            path = workspace.path / Path(*path.parts[1:])
        else:
            raise PythonScriptError("Workspaces markers // in paths not enabled.", element.location)
    elif not path.is_absolute():
        path = base / path

    #trace("Resolve path element path %s:  %s", element, path)

    return path


def resolve_path_parts_workspace(
    ctx: Context,
    workspace: Workspace,
    parts: Union[tuple[StringValue], list[StringValue]],
    base: Path,
    location: FileLocation,
):
    path = Path(*parts)

    _validate_path(path.parts, location)

    if path.parts[0] == "//":
        if WORKSPACES_IN_PATHS_ENABLED:
            path = Path(workspace.path, *path.parts[1:])
        else:
            raise PythonScriptError("Workspaces markers // in paths not enabled.", location)
    elif not path.is_absolute():
        path = base / path

    return path


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


# TODO: handle bytes
PathLikeTypes = Union[StringValue, PathElement]
MultiplePathLike = Union[Glob, FindFiles]
AllPathLike = Union[Glob, FindFiles, StringValue, PathElement]


def _string_value_maybe_expand_user(ctx, base, value: StringValue) -> str:
    val = value.value

    if False:
        if val.startswith("~"):
            # TODO: use environment HOME to expand the user
            return Path(val).expanduser().as_posix()
        else:
            return value
    return val


def resolve_pathlike_list(
    ctx: Context,
    target: EvaluatedTarget,
    base: Path,
    name: str,
    values: Iterable[Union[PathLikeTypes, MultiplePathLike]],
    glob=True,
) -> Iterable[Path]:
    for value in values:
        if isinstance(value, StringValue):
            yield resolve_string_path_workspace(ctx, target.workspace, value, base)
        elif isinstance(value, PathElement):
            source = resolve_path_element_workspace(ctx, target.workspace, value, base)
            #source = _path_element_to_path(base, value)
            yield source
        elif isinstance(value, Glob):
            if glob is False:
                raise ExecutionError(
                    f"Globs are not allowed in the {name} property.", target, value.location
                )
            # TODO: handle find() here as well
            # todo: use glob cache from ctx for multiples of the same glob during a run
            #pattern = make_glob_pattern(value.pattern)
            #pattern = re.compile(pattern)
            ignore = {ctx.output_folder_name}
            #yield from find_files(base, pattern, ignore_names=ignore)

            yield from resolve_glob(ctx, target, base, value, ignore_names=ignore)
        elif isinstance(value, PathObject):
            yield value.path
        else:
            #raise ExecutionError(f"{type(value)} {value!r}", target, getattr(value, "location", target))
            raise NotImplementedError(f"Invalid argument in pathlike list: {type(value)} {value!r}")


def resolve_string_argument_list(
    ctx: Context,
    target: EvaluatedTarget,
    base: Path,
    name: str,
    values: Iterable[Union[PathLikeTypes, MultiplePathLike]],
) -> Iterable[str]:
    # Used to resolve arguments for an execute command, which must all be strings.
    for value in values:
        if isinstance(value, StringValue):
            # XXX: we're not using our function here because we may not want to expand ~ arguments the way bash does
            # bash will replace a ~ whereever it is on the command line
            yield _string_value_maybe_expand_user(ctx, base, value)
        elif isinstance(value, PathObject):
            yield value.path.as_posix()
        elif isinstance(value, PathElement):
            source = resolve_path_element_workspace(ctx, target.workspace, value, base)
            #source = _path_element_to_path(base, value)
            yield source.as_posix()
        elif isinstance(value, Glob):
            if not GLOBS_IN_RUNNABLES_ENABLED:
                raise ExecutionError("glob() can't be used in runnables.", target, value.location)

            # todo: use glob cache from ctx for multiples of the same glob during a run
            #pattern = make_glob_pattern(value.pattern)
            #pattern = re.compile(pattern)
            ignore = {ctx.output_folder_name}
            #yield from (v.as_posix() for v in find_files(base, pattern, ignore_names=ignore))
            yield from (
                v.as_posix() for v in resolve_glob(ctx, target, base, value, ignore_names=ignore)
            )
        elif isinstance(value, Expansion):
            yield str(value)
        else:
            raise NotImplementedError(f"{type(value)} {value!r}")


def _resolve_executable_name(ctx: Context, target, base: Path, name, value: StringValue) -> Path:
    if isinstance(value, StringValue):
        return _resolve_executable(ctx, target, value, base)
    elif isinstance(value, PathElement):
        _path = resolve_path_element_workspace(ctx, target.workspace, value, base)
        return _path
    else:
        raise NotImplementedError(f"{type(value)} {value!r}")


def _resolve_pathlike(
    ctx: Context,
    target: EvaluatedTarget,
    base: Path,
    name: str,
    value: PathLikeTypes,
    error_string: str = "{type(value)} {value!r}"
) -> Path:
    if isinstance(value, StringValue):
        return resolve_string_path_workspace(ctx, target.workspace, value, base)
    elif isinstance(value, PathObject):
        return value.path
    elif isinstance(value, PathElement):
        return resolve_path_element_workspace(ctx, target.workspace, value, base)
    else:
        raise NotImplementedError(error_string.format(value=value, target=target))


def resolve_glob(
    ctx: Context,
    target: "TargetObject",
    path,
    pattern: Optional[Union[Glob]],
    ignore_names,
) -> Iterable[Path]:
    # TODO: check if glob is absolute here?
    glob_pattern = pattern.pattern
    pattern = re.compile(make_glob_pattern(str(glob_pattern)))

    yield from find_files(
        path,
        pattern=pattern,
        ignore_pattern=ctx.ignore_pattern,
        ignore_names=ignore_names,
    )


def resolve_find_files(
    ctx: Context,
    target: "TargetObject",
    path,
    pattern: Optional[Union[Glob, StringValue, RegularExpression]],
    ignore_names,
) -> Iterable[Path]:

    #TODO: support matchin stringvalues to paths
    if isinstance(pattern, (Glob, str)):
        pattern = re.compile(make_glob_pattern(str(pattern)))
    elif isinstance(pattern, RegularExpression):
        pattern = re.compile(pattern.pattern, re.U | re.X)
    elif pattern is None:
        pass
    else:
        raise ExecutionError(
            f"Invalid pattern argument for find(). Got: {type(pattern)}.",
            target,
            getattr(pattern, "location", target.location),
        )
    yield from find_files(
        path=path,
        pattern=pattern,
        ignore_pattern=ctx.ignore_pattern,
        ignore_names=ignore_names,
    )


def _resolve_executable(
    ctx, target, name: StringValue, base: Path, path_string: str = None
) -> Path:
    if name.find("/") >= 0:

        _path = resolve_string_path_workspace(ctx, target.workspace, name, base)
        return _path

    _path = shutil.which(name, path=path_string)

    if _path is None:
        error(
            "Which could not find the executable for %r: PATH=%s", name, os.environ.get("PATH", "")
        )
        raise ExecutionError(
            f"Could not find the executable for {name}. Please install whatever it "
            f"is that provides the command {name!r}, or modify your PATH environment variable "
            f"to include the path to the {name!r} executable.",
            target
        )

    return Path(_path)


def create_build_path_object(ctx: Context, target, path, variants, location: FileLocation):
    workspace = ctx.workspace_path

    path, link_path = get_build_path(
        objective_name=target,
        variants=variants or [],
        input_directory=path,
        build_root=ctx.cache,
        workspace=ctx.workspace_path,
        workspace_id=ctx.workspace_object.id,
        output_folder=ctx.output_folder_name,
    )
    return PathObject(link_path, location=location)


def make_hash_from_dictionary(d: dict[str, str]):
    flatten = []
    for k, v in d.items():
        flatten.append(k)
        if isinstance(v, list):
            flatten.extend(v)
        else:
            flatten.append(v)

    return target_hash("|".join(flatten))


class RunnableElementProtocol(Protocol):
    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> dict[str, Any]:
        ...

    def __call__(self, ctx: Context, target: EvaluatedTarget) -> CommandOutput:
        ...


class InternalRunnableBase(ABC):
    location: FileLocation

    @abstractmethod
    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        # transform the input arguments (stored in instances), to a dictionary of actual values
        # keys must match argument keyword names
        raise NotImplementedError

    #implement this with transform_arguments() to get new functionality
    @abstractmethod
    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        raise NotImplementedError

    @abstractmethod
    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # produce a hash of the runnable with the given arguments and functions
        # TODO: make abstract once we migrate everything over to the new argument functionality
        raise NotImplementedError

    # old stuff below
    def __call__(self, ctx: Context, target: EvaluatedTarget) -> CommandOutput:
        raise NotImplementedError

    def __str__(self):
        return PythonScriptError("Converting Runnable to string not allowed.", self.location)


@dataclass
class Execute(InternalRunnableBase):
    executable: PathLikeTypes
    arguments: Union[tuple[AllPathLike], tuple[AllPathLike, ...]]
    environment: dict[str, str]
    location: FileLocation

    _redirect_output: PathLikeTypes = None

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        args = {}
        args["arguments"] = arguments = []
        target_input = target.input_path

        for argument in self.arguments:
            if isinstance(argument, StringValue):
                arguments.append(_string_value_maybe_expand_user(ctx, target_input, argument))
            elif isinstance(argument, PathElement):
                arguments.append(
                    _resolve_pathlike(ctx, target, target_input, target.name, argument).as_posix()
                )
            elif isinstance(argument, Expansion):
                arguments.append(str(argument.expand(ctx)))
            elif isinstance(argument, PathObject):
                arguments.append(argument.path.as_posix())
            elif isinstance(argument, ListTypes):
                arguments.extend(
                    resolve_string_argument_list(ctx, target, target_input, target.name, argument)
                )
            else:
                raise PythonScriptError(
                    f"Invalid argument type: {type(argument)}: {argument}", target.location
                )

        executable = _resolve_executable_name(
            ctx, target, target_input, target.name, self.executable
        )
        args["executable"] = executable.as_posix()
        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        executable = arguments.get("executable")
        arguments = arguments.get("arguments")
        #executable = _resolve_executable(target, executable.as_posix())

        cwd = target.input_path

        PS1 = ctx.environment.get("PS1", "")
        argstring = " ".join(arguments)
        #ctx.ui.print(f"Running executable from {cwd}")#\n# {executable} {argstring}")
        ctx.ui.print(f"{ctx.colors.BOLD}{cwd} {PS1}${ctx.colors.RESET} {executable} {argstring}")
        if ctx.dry_run is True:
            return CommandOutput(0)

        try:
            # create a real pipe to pass to the specified shell
            #read, write = os.pipe()
            #os.write(write, script.encode("utf-8"))
            #os.close(write)

            output = run(
                [executable] + arguments,
                ctx.environment,
                capture=True,
                shell=False,
                cwd=cwd,
                #stdin=read,
                color_error=ctx.colors.ERROR,
                color_escape=ctx.colors.RESET,
            )
            return output
        except Exception as e:
            raise ExecutionError(e, target, location=self.location) from e

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        _arguments = arguments.get("arguments")
        _executable = arguments.get("executable")

        return hash_function("|".join([_executable] + _arguments))


class ShellCommand(InternalRunnableBase):
    string: list[StringValue]
    location: FileLocation

    # https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_25

    # -e: Error on any error.
    # -u When the shell tries to expand an unset parameter other than the '@' and '*' special parameters,
    # it shall write a message to standard error and the expansion shall fail with the consequences specified in Consequences of Shell Errors.

    # strict options:
    # -C  Prevent existing files from being overwritten by the shell's '>' redirection operator (see Redirecting Output);
    # the ">|" redirection operator shall override this noclobber option for an individual file.

    # -f: The shell shall disable pathname expansion.

    # -o: Write the current settings of the options to standard output in an unspecified format.
    preamble: str = "set -Eeuo pipefail"

    def __init__(self, string, location):
        self.string = string
        self.location = location

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        args = {}
        args["string"] = self.string
        args["preamble"] = self.preamble

        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        string = arguments.get("string")
        preamble = arguments.get("preamble")

        #def __call__(self, ctx: Context, target: EvaluatedTarget):
        if not string:
            return CommandOutput(0)

        s_print = "\n".join([f"# {s}" for s in chain(preamble.split("\n"), self.string)])

        # TODO: we may want to change this to &&
        #s = " && ".join(self.string)

        _script = ["\n"]
        _script.append(preamble)
        # XXX: this line is required to prevent "unbound variable" errors (on account of the -u switch)
        _script.append("__error=0")
        #script.append(r"IFS=$'\n'")
        for i, line in enumerate(string):
            #script.append(f"({line}) || (exit $?)")
            if ctx.verbose > 0 or ctx.debug:
                _script.append(
                    f"echo \"{ctx.colors.MAKEX}[makex]{ctx.colors.RESET} {ctx.colors.BOLD}${{PS1:-}}\${ctx.colors.RESET} {line}\""
                )

            # bash: https://www.gnu.org/software/bash/manual/html_node/Command-Grouping.html
            # Placing a list of commands between curly braces causes the list to be executed in the current shell context.
            # No subshell is created. The semicolon (or newline) following list is required.
            if SHELL_USES_RETURN_CODE_OF_LINE:
                _script.append(
                    f"{{ {line}; }} || {{ __error=$?; echo -e \"{ctx.colors.ERROR}Error (exit=$?) on on shell script line {i+1}:{ctx.colors.RESET} {shlex.quote(line)!r}\"; exit $__error; }}"
                )
            else:
                _script.append(f"{{ {line}; }}")

            #script.append(f"( {line} ) || (exit $?)")

        script = "\n".join(_script)
        trace("Real script:\n%s", script)
        #stdin = BytesIO()
        #stdin.write(script.encode("utf-8"))
        cwd = target.input_path
        ctx.ui.print(f"Running shell from {cwd}:\n{s_print}\n")
        if ctx.dry_run is True:
            return CommandOutput(0)
        try:
            # create a real pipe to pass to the specified shell
            read, write = os.pipe()
            os.write(write, script.encode("utf-8"))
            os.close(write)

            output = run(
                [ctx.shell],
                ctx.environment,
                capture=True,
                shell=False,
                cwd=cwd,
                stdin=read, #stdin_data=script.encode("utf-8"),
                color_error=ctx.colors.WARNING,
                color_escape=ctx.colors.RESET,
            )
            return output
        except Exception as e:
            raise ExecutionError(e, target, location=self.location) from e
        #finally:
        #    ctx.ui.print("Script finished")

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        return hash_function("\n".join(arguments.get("string", [])))


def file_ignore_function(output_folder_name):
    def f(src, names):
        return {output_folder_name}

    return f


@dataclass
class Copy(InternalRunnableBase):
    source: Union[list[AllPathLike], PathLikeTypes]
    destination: PathLikeTypes
    exclude: list[AllPathLike]
    location: FileLocation

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function):
        # checksum all the sources
        sources = arguments.get("sources")

        # hash the destination name
        destination = arguments.get("destination")

        exclusions = arguments.get("exclude", [])

        parts = []
        for source in sources:
            parts.append(hash_function(source.as_posix()))

        parts.append(hash_function(destination.as_posix()))

        if exclusions:
            parts.append(hash_function(exclusions.pattern))

        return hash_function("|".join(parts))

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        if isinstance(self.source, ListTypes):
            sources = list(
                resolve_pathlike_list(
                    ctx=ctx,
                    target=target,
                    name="source",
                    base=target.input_path,
                    values=self.source
                )
            )
        else:
            sources = [
                _resolve_pathlike(
                    ctx=ctx,
                    target=target,
                    name="source",
                    base=target.input_path,
                    value=self.source
                )
            ]

        if self.destination:
            destination = _resolve_pathlike(
                ctx=ctx,
                target=target,
                name="destination",
                base=target.path,
                value=self.destination
            )
        else:
            destination = target.path

        excludes = None
        if self.exclude:
            excludes = []
            pattern_strings = []
            if isinstance(self.exclude, ListValue):
                pattern_strings = self.exclude
            elif isinstance(self.exclude, Glob):
                pattern_strings.append(self.exclude)
            else:
                raise PythonScriptError(
                    f"Expected list or glob for ignores. Got {self.exclude} ({type(self.exclude)})",
                    getattr(self.exclude, "location", target.location)
                )

            for string in pattern_strings:
                if not isinstance(string, Glob):
                    raise PythonScriptError(
                        "Expected list or glob for ignores.",
                        getattr(string, "location", target.location)
                    )
                excludes.append(make_glob_pattern(string.pattern))

            excludes = combine_patterns(excludes)

        return ArgumentData({"sources": sources, "destination": destination, "excludes": excludes})

    def run_with_arguments(
        self, ctx: Context, target: EvaluatedTarget, arguments: ArgumentData
    ) -> CommandOutput:
        sources = arguments.get("sources")
        destination: Path = arguments.get("destination")
        excludes: Pattern = arguments.get("excludes")

        copy_file = ctx.copy_file_function

        if not destination.exists():
            debug("Create destination %s", destination)
            if ctx.dry_run is False:
                destination.mkdir(parents=True)

        length = len(sources)
        if length == 1:
            ctx.ui.print(f"Copying to {destination} ({sources[0]})")
        else:
            ctx.ui.print(f"Copying to {destination} ({length} items)")

        ignore_pattern = ctx.ignore_pattern

        if excludes:
            trace("Using custom exclusion pattern: %s", excludes.pattern)

        #trace("Using global ignore pattern: %s", ignore_pattern.pattern)
        def _ignore_function(src, names, pattern=ignore_pattern) -> set[str]:
            # XXX: Must yield a set.
            _names = set()
            for name in names:
                path = join(src, name)
                if pattern.match(path):
                    trace("Copy/ignore: %s", path)
                    _names.add(name)
                elif excludes and excludes.match(path):
                    trace("Copy/exclude: %s", path)
                    _names.add(name)
            return _names

        # sometimes
        for source in sources:

            if not source.exists():
                raise ExecutionError(
                    f"Missing source file {source} in copy list",
                    target,
                    getattr(source, "location", target.location)
                )

            if ignore_pattern.match(source.as_posix()):
                trace("File copy ignored %s", source)
                continue

            #trace("Copy source %s", source)
            if source.is_dir():
                _destination = destination / source.name
                debug("Copy tree %s <- %s", _destination, source)

                if ctx.dry_run is False:
                    try:
                        # copy recursive
                        shutil.copytree(
                            source,
                            _destination,
                            dirs_exist_ok=True,
                            copy_function=copy_file,
                            ignore=_ignore_function
                        )

                    except (shutil.Error) as e:
                        # XXX: Must be above OSError since it is a subclass.
                        # XXX: shutil returns multiple errors inside an error
                        string = [f"Error copying tree {source} to {destination}:"]
                        for tup in e.args:
                            for error in tup:
                                e_source, e_destination, exc = error
                                string.append(
                                    f"\tError copying to  {e_destination} from {e_source}\n\t\t{exc} {copy_file}"
                                )
                        if ctx.debug:
                            logging.exception(e)
                        string = "\n".join(string)
                        raise ExecutionError(string, target, target.location) from e
                    except OSError as e:
                        string = [
                            f"Error copying tree {source} to {destination}:\n  Error to {e.filename} from {e.filename2}: {type(e)}: {e.args[0]} {e} "
                        ]

                        string = "\n".join(string)
                        raise ExecutionError(string, target, target.location) from e
            else:
                trace("Copy file %s <- %s", destination / source.name, source)
                if ctx.dry_run is False:
                    try:
                        copy_file(source.as_posix(), (destination / source.name).as_posix())

                    except (OSError, shutil.Error) as e:
                        raise ExecutionError(
                            f"Error copying file {source} to {destination/source.name}: {e}",
                            target,
                            target.location
                        ) from e
        return CommandOutput(0)


@dataclass
class Synchronize(InternalRunnableBase):
    """
        synchronize/mirror files much like rsync.

        list of input paths are mirrored to Target.path
        e.g.
        sync(["directory1", "file1", "sub/directory"])

        will replicate the paths in the source:

        - directory1
        - file1
        - sub/directory

        destination argument (e.g. "source" or "source/") will prefix the paths with the destination:

        - source/directory1
        - source/file1
        - source/sub/directory
    """
    source: Union[list[AllPathLike], AllPathLike]
    destination: PathLikeTypes
    exclude: list[MultiplePathLike]
    location: FileLocation
    symlinks = False

    class Arguments(TypedDict):
        sources: list[Path]
        destination: Path

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        args = {}

        if not self.source:
            raise PythonScriptError(
                f"Source argument is empty.",
                self.location,
            )

        _source_list = self.source

        try:
            _source_list = iter(_source_list)
        except TypeError:
            # make it iterable and try.
            _source_list = [_source_list]
            if False:
                # not iterable
                raise PythonScriptError(
                    f"Expected variable number of sources, got {type(_source_list)}: {_source_list!r}",
                    getattr(_source_list, "location", self.location)
                )
        else:
            # iterable
            pass

        #if not isinstance(self.source, ListTypes):
        #    raise PythonScriptError(
        #        f"Expected variable number of sources, got {type(self.source)}: {self.source!r}", getattr(self.source, "location", self.location)
        #    )

        args["sources"] = sources = list(
            resolve_pathlike_list(
                ctx=ctx,
                target=target,
                name="source",
                base=target.input_path,
                values=_source_list,
                glob=GLOBS_IN_RUNNABLES_ENABLED,
            )
        )
        trace("Synchronize sources %s", sources)

        if self.destination:
            destination = _resolve_pathlike(
                ctx=ctx,
                target=target,
                name="destination",
                base=target.path,
                value=self.destination
            )
            if ctx.dry_run is False:
                destination.mkdir(parents=True, exist_ok=True)
        else:
            destination = target.path
            if ctx.dry_run is False:
                destination.mkdir(parents=True, exist_ok=True)

        args["destination"] = destination
        args["symlinks"] = self.symlinks

        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        sources: list[Path] = arguments.get("sources")
        destination: Path = arguments.get("destination")
        symlinks: Path = arguments.get("symlinks")

        ignore = file_ignore_function(ctx.output_folder_name)

        debug("Synchronize to destination: %s", destination)

        length = len(sources)

        if length > 1:
            ctx.ui.print(f"Synchonizing to {destination} ({length} items)")
        else:
            ctx.ui.print(f"Synchonizing to {destination} ({sources[0]})")

        for source in sources:
            #trace("Synchronize source to destination: %s: %s", source, destination)
            if not source.exists():
                raise ExecutionError(
                    f"Missing source/input file {source} in sync()", target, location=self.location
                )
            if source.is_dir():
                # fix up destination to have relat
                #rel_path = source.relative_to(target.input_path)
                if source.is_relative_to(target.input_path):
                    _destination = destination / source.relative_to(target.input_path)
                    if ctx.dry_run is False:
                        _destination.mkdir(parents=True, exist_ok=True)
                else:
                    _destination = destination

                trace("Copy tree %s <- %s", _destination, source)
                if ctx.dry_run is False:
                    # copy recursive
                    shutil.copytree(source, _destination, dirs_exist_ok=True, ignore=ignore)
            else:
                if source.parent.is_relative_to(target.input_path):
                    _destination = destination / source.parent.relative_to(target.input_path)

                    if ctx.dry_run is False:
                        _destination.mkdir(parents=True, exist_ok=True)

                trace("Copy file %s <- %s", _destination / source.name, source)
                if ctx.dry_run is False:
                    shutil.copy(source, _destination / source.name)

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [self.__class__.__name__, arguments.get("destination").as_posix()]
        parts.extend([a.as_posix() for a in arguments.get("sources")])

        return hash_function("|".join(parts))


@dataclass
class Print(InternalRunnableBase):
    messages: list[str]

    def __init__(self, messages, location):
        self.messages = messages
        self.location = location

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        pass

        #def __call__(self, ctx: Context, target: EvaluatedTarget) -> CommandOutput:
        for message in self.messages:
            print(message)

        return CommandOutput(0)

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        pass

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # this hash doesn't matter; doesn't affect output
        return ""


@dataclass
class Write(InternalRunnableBase):
    path: PathLikeTypes
    data: StringValue

    def __init__(self, path: PathLikeTypes, data: StringValue = None, location=None):
        self.path = path
        self.data = data
        self.location = location

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        args = {}
        args["path"] = path = _resolve_pathlike(ctx, target, target.path, "path", self.path)

        data = self.data
        if isinstance(data, StringValue):
            data = data.value
        elif data is None:
            data = ""
        else:
            raise ExecutionError(
                f"Invalid argument text argument to write(). Got {data!r} {type(data)}. Expected string.",
                target,
                location=getattr(data, "location", target.location)
            )

        args["data"] = data
        return ArgumentData(args, inputs=[path])

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        path = arguments.get("path")
        data = arguments.get("data")
        if data is None:
            debug("Touching file at %s", path)
            if ctx.dry_run is False:
                path.touch(exist_ok=True)
        elif isinstance(data, str):
            debug("Writing file at %s", path)
            if ctx.dry_run is False:
                path.write_text(data)
        else:
            raise ExecutionError(
                "Invalid argument text argument to write()", target, location=target.location
            )

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [
            arguments.get("path").as_posix(),
            arguments.get("data"),
        ]
        return hash_function("|".join(parts))


class SetEnvironment(InternalRunnableBase):
    environment: dict[StringValue, Union[StringValue, PathLikeTypes]]

    def __init__(self, environment: dict, location: FileLocation):
        self.environment = environment
        self.location = location

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        env = {}
        for k, v in self.environment.items():
            if isinstance(v, StringValue):
                value = v.value
            elif isinstance(v, PathElement):
                value = resolve_path_element_workspace(ctx, target.workspace, v, target.input_path)
                value = value.as_posix()
            elif isinstance(v, PathObject):
                value = str(v)
            elif isinstance(v, (int)):
                value = str(v)
            else:
                raise PythonScriptError(
                    f"Invalid type of value in environment key {k}: {v} {type(v)}",
                    location=self.location
                )

            env[str(k)] = value

        # TODO: input any paths/files referenced here as inputs
        return ArgumentData({"environment": env})

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        env = arguments.get("environment", {})
        ctx.environment.update(env)
        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        environment = arguments.get("environment")
        environment_string = ";".join(f"{k}={v}" for k, v in environment.items())
        return hash_function(environment_string)


@dataclass
class TargetReferenceElement:
    """
    A reference to a target in a makex file: Target(name, path).

    Also produced synthetically when : is called.
    """
    name: StringValue
    path: Union[PathElement, StringValue] = None
    location: FileLocation = None

    def __repr__(self):
        path = self.path
        if path is not None:
            return f"TargetReferenceElement({self.name.value!r}, {path!r})"

        return f"TargetReferenceElement({self.name.value!r})"


@dataclass
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


CommandTypes = Union[Execute, ShellCommand, InternalRunnableBase]


class TargetObject:
    name: StringValue
    path: PathElement
    requires: list[Union[PathElement, PathObject, "TargetObject"]]
    commands: list[RunnableElementProtocol]

    # outputs as a list. fast checks if has any outputs
    outputs: list[PathElement]

    # named outputs dict
    # None key is unnamed outputs
    outputs_dict: dict[Union[None, str], list[Union[PathElement, PathObject]]]

    # location to build. can be overidden by users.
    build_path: Path

    location: FileLocation

    resolved_requires: list[ResolvedTargetReference]

    workspace: Workspace

    #makex_file_checksum: str

    makex_file: "MakexFile"

    def __init__(
        self,
        name,
        path: Union[StringValue, PathElement] = None,
        requires=None,
        run=None,
        outputs=None,
        build_path=None,
        outputs_dict=None,
        workspace=None,
        #makex_file_checksum=None,
        makex_file=None,
        location=None,
    ):
        #if not path is None:
        #    assert isinstance(path, (PathElement)), f"Got: {path!r}"

        self.name = name
        self.path = path
        self.requires = requires or []
        self.commands = run or []
        self.outputs = outputs or []
        self.build_path = build_path
        self.workspace = workspace

        # cache the requirement references weve obtained so we don't have to search for makex file later
        self.resolved_requires = []
        self.outputs_dict = outputs_dict or {}

        if outputs and outputs_dict is None:
            # TEST ONLY
            for output in outputs:
                self.outputs_dict.setdefault(None, []).append(output)

        self.makex_file = makex_file

        self.location = location

    def all_outputs(self) -> Iterable[Union[PathElement, PathObject]]:
        d = self.outputs_dict
        if not d:
            return
        yield from d.get(None)

        for k, v in d.items():
            yield from v

    def add_resolved_requirement(self, requirement: ResolvedTargetReference):
        self.resolved_requires.append(requirement)

    @property
    def makex_file_path(self) -> str:
        return self.location.path

    def path_input(self):
        return Path(self.location.path).parent

    def __eq__(self, other):
        if not isinstance(other, (TargetObject, ResolvedTargetReference)):
            return False

        return self.key() == other.key()
        #return other.path == self.path and self.name == other.name

    def key(self):
        #if self.path is None or self.path.resolved:
        #    raise Exception(f"Can't hash key of unresovled {self!r}")

        return format_hash_key(self.name, self.location.path)

        #return hash_target(self)

    def __hash__(self):

        #if self.path is None:
        #    return hash(f":{self.name}:")

        #if not self.path.as_path():
        #    raise Exception(f"Can't hash unresolved path {self.path}")

        return hash(self.key())

    def __repr__(self):
        if self.path:
            return f"TargetObject(\"{self.name}\", {self.location.path})"
        return f"TargetObject(\"{self.name}\")"


def resolve_target_output_path(ctx, target: TargetObject, create=False):
    # return link (or direct) and cache path.
    target_input_path = target.path_input()

    if target.path is None:
        build_path, linkpath = get_build_path(
            objective_name=target.name,
            variants=[],
            input_directory=target_input_path,
            build_root=ctx.cache,
            workspace=ctx.workspace_path,
            workspace_id=ctx.workspace_object.id,
            output_folder=ctx.output_folder_name,
        )

        real_path = build_path
        #if create:
        #    # create the output directory in the cache.
        #    # link it in if we have SYMLINK_PER_TARGET_ENABLED
        #    create_output_path(
        #        build_path, linkpath=linkpath if SYMLINK_PER_TARGET_ENABLED else None
        #    )

        # DONE: allow a flag to switch whether we build to link or directly to output
        if OUTPUT_DIRECTLY_TO_CACHE:
            # we shouldn't really use this branch
            target_output_path = build_path
        else:
            target_output_path = linkpath
    elif isinstance(target.path, PathElement):
        #trace("Current path is %r: %s", target.path, target.path.resolved)
        target_output_path = resolve_path_element_workspace(
            ctx, target.workspace, target.path, target_input_path
        )
        #if target.path.resolved:
        #    target_output_path = target.path.resolved
        #else:
        #    target_output_path = target.path._as_path()
        #    if not target_output_path.is_absolute():
        #        target_output_path = target.path_input() / target_output_path

        real_path = target_output_path
    elif isinstance(target.path, StringValue):
        # path to a simple file within the output.

        #target_output_path = Path(target.path.value)
        #if not target_output_path.is_absolute():
        #    target_output_path = target_input_path / target_output_path
        #raise ExecutionError(f"STRING VALUE: {type(target.path)} {target}", target, location=target.location)
        raise NotImplementedError(
            f"STRING VALUE: {target.path.value} {type(target.path)} {target} {target.location}"
        )
    else:
        raise NotImplementedError(f"{type(target)} {target!r}")

    return target_output_path, real_path


class MakexFileCycleError(Exception):
    detection: TargetObject
    cycles: list[TargetObject]

    def __init__(self, message, detection: TargetObject, cycles: list[TargetObject]):
        super().__init__(message)
        self.message = message
        self.detection = detection
        self.cycles = cycles

    def pretty(self, ctx: Context) -> str:
        string = StringIO()
        string.write(
            f"{ctx.colors.ERROR}ERROR:{ctx.colors.RESET} Cycles detected between targets:\n"
        )
        string.write(f" - {self.detection.key()} {self.detection}\n")

        if self.detection.location:
            string.write(pretty_file(self.detection.location, ctx.colors))

        first_cycle = self.cycles[0]
        string.write(f" - {first_cycle.key()}\n")

        if first_cycle.location:
            string.write(pretty_file(first_cycle.location, ctx.colors))

        stack = self.cycles[1:]
        if stack:
            string.write("Stack:\n")
            for r in stack:
                string.write(f" - {r}\n")

        return string.getvalue()


class TargetGraph:
    # NOTE: We use TargetObject here because we use isinstance checks

    targets: list[TargetObject]

    def __init__(self):
        # TODO: we could probably merge TargetKey and file keys and all of these dictionaries.

        # TargetKey -> object
        self.targets: dict[TargetKey, TargetObject] = {}

        # map of TargetKey to all of it's requirements
        self._requires: dict[TargetKey, list[TargetObject]] = {}

        # map of TargetKey to all the Files/paths it provides
        self._provides: dict[TargetKey, list[PathLike]] = {}

        # map from all the files inputting into TargetObject
        self._files_to_target: dict[PathLike, set[TargetObject]] = {}

        # map from Target to all the things it provides to
        self._provides_to: dict[TargetKey, set[TargetObject]] = {}

    def __contains__(self, item: ResolvedTargetReference):
        return item.key() in self.targets

    def get_target(self, t) -> Optional[TargetObject]:
        #debug("Find %s in %s. key=%s", t, self.targets, t.key())
        return self.targets.get(t.key(), None)

    def in_degree(self) -> Iterable[tuple[TargetObject, int]]:
        for key, target in self.targets.items():
            yield (target, len(self._provides_to.get(key, [])))

    def add_targets(self, ctx: Context, *targets: TargetObject):
        assert isinstance(ctx, Context)
        assert ctx.workspace_object

        for target in targets:
            self.add_target(ctx, target)

    def _process_target_requirements(
        self,
        ctx: Context,
        target: TargetObject,
    ) -> Iterable[TargetObject]:

        target_input_path = target.path_input()
        makex_file_path = Path(target.location.path)

        for require in target.requires:
            if isinstance(require, PathElement):
                # a simple path to a file.. declared as Path() or automatically parsed
                # resolve the input file path
                if False:
                    path = require._as_path()

                    if not path.is_absolute():
                        # make path relative to target
                        path = target_input_path / path

                path = resolve_path_element_workspace(
                    ctx, target.workspace, require, target_input_path
                )

                # point file -> current target
                self._files_to_target.setdefault(path, set()).add(target)
                continue
            elif isinstance(require, TargetObject):
                # add to rdeps map
                self._provides_to.setdefault(require.key(), set()).add(target)
                # add to requires map
                #requirements.append(require)

                # TODO: this is for tests only. should yield a ResolvedTargetReference

                yield require
            elif isinstance(require, TargetReferenceElement):
                # reference to a target, either internal or outside the makex file
                name = require.name.value
                path = require.path

                trace("reference input is %r: %r", require, path)

                location = require.location
                if isinstance(path, StringValue):
                    # Target(name, "some/path")
                    location = path.location
                    #_path = Path(path.value)
                    _path = resolve_string_path_workspace(
                        ctx, target.workspace, path, target_input_path
                    )
                elif isinstance(path, PathElement):
                    # Target(name, Path())
                    location = path.location

                    _path = resolve_path_element_workspace(
                        ctx, target.workspace, path, target_input_path
                    )
                elif path is None:
                    # Target(name)
                    _path = makex_file_path
                elif isinstance(path, str):
                    # XXX: this is used for testing only. we should not be dealing with str (instead we should a StringValues)
                    location = FileLocation(None, None, target.location)
                    _path = Path(path)
                else:
                    raise ExecutionError(
                        f"Invalid target reference path: Type: {type(path)} {path}",
                        target,
                        getattr(path, "location", None)
                    )

                if not _path.is_absolute():
                    _path = target_input_path / _path

                if _path.is_dir():
                    # find the makexfile it's referring to
                    file = find_makex_files(_path, ctx.makex_file_names)
                    if file is None:
                        raise ExecutionError(
                            f"No makex file found at {_path}. Invalid target reference.",
                            target,
                            path.location
                        )
                else:
                    file = _path

                trace("Got reference %r %r", name, file)
                #requirements.append(ResolvedTargetReference(name, path))
                yield ResolvedTargetReference(name, file, location=location)
            elif isinstance(require, (FindFiles, Glob)):
                # These things will be resolved in a later pass.
                # TODO: we may want to resolve these early and keep a cache.
                pass
            else:
                raise NotImplementedError(f"Type: {type(require)}")

    def add_target(self, ctx: Context, target: TargetObject):
        # add targetobjects during parsing

        # add all the targets we encountered during evaluation
        self.targets[target.key()] = target

        key = target.key()
        self._requires[key] = requirements = []

        if target.requires:
            #### process the requirements, a list of PathElement(input file) | StringValue | Target
            for requirement in self._process_target_requirements(ctx, target):
                requirements.append(requirement)

        self._provides[key] = provides = []

        #trace("Add target to graph: %r", target)
        output_path, real_path = resolve_target_output_path(ctx, target)

        if output_path:
            pass

        if target.outputs:
            for output in target.all_outputs():
                if isinstance(output, PathElement):
                    output = resolve_path_element_workspace(
                        ctx, target.workspace, output, output_path
                    )
                    #output = output._as_path()

                    #if not output.is_absolute():
                    # make path relative to target
                    #    output = output_path / output
                elif isinstance(output, PathObject):
                    output = output.path
                elif isinstance(output, StringValue):
                    output = Path(output.value)

                    if not output.is_absolute():
                        # make path relative to target
                        output = output_path / output

                elif isinstance(output, (FindFiles, Glob)):
                    pass
                else:
                    raise NotImplementedError(f"Invalid output type {type(output)} {output}")

                provides.append(output)

    def get_requires(
        self,
        target: TargetProtocol,
        recursive=False,
        _seen: set = None,
    ) -> Iterable[TargetObject]:
        # XXX: faster version of get_requires without cycle detection. used by the executor/downstream
        # query the graph for requirements in reverse order (farthest to closest)
        # TODO: we should be able to remove _seen entirely.
        _seen = set() if _seen is None else _seen

        if target in _seen:
            return

        _seen.add(target)

        for requirement in self._requires.get(target.key(), []):
            if requirement in _seen:
                continue

            if recursive:
                yield from self.get_requires(requirement, recursive=recursive, _seen=_seen)

            yield requirement

    def get_requires_detect_cycles(
        self,
        target: TargetProtocol,
        recursive=False,
        _stack: list = None,
        _seen: set = None
    ) -> Iterable[TargetObject]:
        # query the graph for requirements in reverse order (farthest to closest)
        _stack = list() if _stack is None else _stack
        _seen = set() if _seen is None else _seen

        #trace("Get requires and detect cycles %r", target)
        if target in _stack:
            return

        _stack.append(target)

        _seen.add(target)

        for requirement in self._requires.get(target.key(), []):
            requirement: TargetObject = requirement

            if requirement in _seen:
                continue

            if requirement in _stack:
                #error("CYCLES %r: %r", requirement, _seen)
                target = self.targets.get(requirement.key())
                # reverse so we see the most recent file depended on.
                reverse = [self.targets.get(s.key()) for s in reversed(_stack)]
                raise MakexFileCycleError(
                    f"Internal cycle detected: {requirement!r}", target, reverse
                )

            if recursive:
                yield from self.get_requires_detect_cycles(
                    requirement, recursive=recursive, _stack=_stack, _seen=_seen
                )

            yield requirement

        _stack.pop()

    def get_outputs(self, *targets, recursive=False) -> Iterable[FileProtocol]:
        # reverse dependencies of targets
        # targets outputs + outputs for each of targets.requires
        for target in targets:
            yield from self._provides.get(target, [])

            if recursive:
                yield from self.get_outputs(target.requires)

    def topological_sort_grouped(self: "TargetGraph", start: list[TargetObject]):
        indegree_map = {v: d for v, d in self.in_degree() if d > 0}
        zero_indegree = [v for v, d in self.in_degree() if d == 0]

        while zero_indegree:
            yield zero_indegree
            new_zero_indegree = []
            for v in zero_indegree:
                for child in self.get_requires_detect_cycles(v):
                    indegree_map[child] -= 1
                    if not indegree_map[child]:
                        new_zero_indegree.append(child)
            zero_indegree = new_zero_indegree


def find_makex_files(path, names):
    for name in names:
        check = path / name
        if check.exists():
            return check
    return None


@dataclass
class ArchiveCommand:
    path: PathLike
    prefix: PathLike
    location: FileLocation


class FileObject(FileProtocol):
    path: PathLike
    location: FileLocation


SENTINEL = object()


class EnvironmentProxy:
    def __init__(self, env):
        self.__env = env
        # record usages of environment variables so we can include it as part of the hashing of targets/makex files.
        self.__usages: dict[str, str] = {}

    def get(self, key, default=SENTINEL, _location_: FileLocation = None):
        item = self.__env.get(key, default)
        if item is None or item is SENTINEL:
            raise PythonScriptError(f"Enviroment variable {key} not defined.", _location_)

        self.__usages[key] = item

        return StringValue(item, location=_location_)

    def _usages(self):
        return self.__usages


class MakefileScriptEnv(ScriptEnvironment):
    def __init__(
        self,
        ctx,
        directory: Path,
        path: Path,
        workspace: Workspace = None,
        checksum: str = None,
        targets: dict[str, TargetObject] = None,
        makex_file: "MakexFile" = None,
    ):
        self.directory = directory

        # path to the actual makex file
        self.path = path

        self.ctx = ctx
        # TODO: wrap environment dict so it can't be modified
        self.environment = EnvironmentProxy(ctx.environment)
        self.targets = {} if targets is None else targets
        #self.variables = []
        self.build_paths = []
        self.workspace = workspace
        self.makex_file_checksum = checksum
        self.makex_file = makex_file or None

    def globals(self):
        g = {
            "Environment": self.environment, #"pattern": wrap_script_function(self._pattern),
            "target": wrap_script_function(self._function_target),
            "Target": wrap_script_function(self._function_Target),
        }
        # path utilities
        g.update(
            {
                "path": wrap_script_function(self._function_path),
                # TODO: path() is a common variable (e.g. in a loop), and as an argument (to target) and Path() object. confusing.
                #  alias to cache(), or output()
                #"cache": wrap_script_function(self.build_path),
                #"output": wrap_script_function(self.build_path),
                "Path": wrap_script_function(self._function_Path),
                "source": wrap_script_function(self._function_source),
            }
        )

        if GLOB_FUNCTION_ENABLED:
            g["glob"] = wrap_script_function(self._function_glob)

        if FIND_FUNCTION_ENABLED:
            g["find"] = wrap_script_function(self._function_find)

        # runnables
        g.update(
            {
                "print": wrap_script_function(self._function_print),
                "shell": wrap_script_function(self._function_shell),
                "sync": wrap_script_function(self._function_sync),
                "execute": wrap_script_function(self._function_execute),
                "copy": wrap_script_function(self._function_copy),
                "write": wrap_script_function(self._function_write),
                "environment": wrap_script_function(self._function_environment),
            }
        )

        if ARCHIVE_FUNCTION_ENABLED:
            g["archive"] = wrap_script_function(self._function_archive)

        if EXPAND_FUNCTION_ENABLED:
            g["expand"] = wrap_script_function(self._function_expand)

        if HOME_FUNCTION_ENABLED:
            g["home"] = wrap_script_function(self._function_home)
        return g

    def _function_expand(self, string: StringValue, location: FileLocation):
        return Expansion(context=self.ctx, string=string, location=location)

    def _function_home(self, user=None, location=None):
        if user:
            arg = f"~{user}"
        else:
            arg = "~"
        home = expanduser(arg)

        return PathElement(arg, resolved=Path(home), location=location)

    def _function_find(
        self, path: PathLikeTypes, expr: Union[Glob, RegularExpression] = None, location=None
    ):

        if isinstance(path, StringValue):
            _path = resolve_string_path_workspace(self.ctx, self.workspace, path, self.directory)

            path = PathElement(path.value, resolved=_path, location=path.location)
        elif path is None or isinstance(path, PathElement):
            pass
        else:
            raise PythonScriptError(
                f"Invalid path type in find() function: {type(path)} ({path}). Path or string expected."
            )
        return FindFiles(expr, path, location=location)

    def _function_environment(
        self,
        dict: [StringValue, Union[PathLikeTypes, StringValue]],
        location: FileLocation = None
    ):
        return SetEnvironment(dict, location=location)

    def _function_Target(self, name, path: PathLikeTypes = None, location=None, **kwargs):
        # absorb kwargs so we can error between Target and target
        return TargetReferenceElement(name=name, path=path, location=location)

    def _function_path(
        self,
        name,
        path: PathLikeTypes = None,
        variants: list[str] = None,
        location=None,
    ):
        if isinstance(path, PathElement):
            _path = resolve_path_element_workspace(self.ctx, self.workspace, path, self.directory)
        elif isinstance(path, StringValue):
            _path = resolve_string_path_workspace(self.ctx, self.workspace, path, self.directory)
        elif path is None:
            _path = self.directory
        else:
            raise PythonScriptError(f"Invalid path value:{type(path)}")

        return create_build_path_object(
            self.ctx, target=name, path=_path, variants=variants, location=location
        )

    def _function_source(self, *path: StringValue, location=None):
        if not path:
            # XXX: No path. Return the source directory.
            return PathElement(*self.directory.parts, resolved=self.directory, location=location)

        #parts = []
        for part in path:
            if not isinstance(part, StringValue):
                raise PythonScriptError(
                    f"Invalid path part type in source() function. Expected string. Got {type(part)}: {part!r}",
                    getattr(part, "location", location)
                )

        #_path = resolve_path_parts(parts, self.directory, location)
        _path = resolve_path_parts_workspace(
            self.ctx, self.workspace, path, self.directory, location
        )

        # XXX: all of _path.parts is used, so it's fully absolute
        return PathElement(*path, resolved=_path, location=location)

    def _function_Path(self, *path: PathLikeTypes, location=None):
        #parts = []
        for part in path:
            if not isinstance(part, StringValue):
                raise PythonScriptError(
                    f"Invalid path part type in Path() function. Expected string. Got {type(part)}: {part!r}",
                    getattr(part, "location", location)
                )

        trace("Creating path: %s", path)
        #_path = resolve_path_parts(parts, self.directory, location)
        _path = resolve_path_parts_workspace(
            self.ctx, self.workspace, path, self.directory, location
        )

        return PathElement(*path, resolved=_path, location=location)

    def _function_archive(self, path: PathLikeTypes = None, *, prefix=None, location=None):
        return ArchiveCommand(path, prefix=prefix, location=location)

    def _function_shell(self, *script: tuple[StringValue, ...], location=None):
        for part in script:
            if not isinstance(part, StringValue):
                raise PythonScriptError(
                    f"Invalid script in shell function. Expected string. Got {type(part)}: {part!r}",
                    getattr(part, "location", location)
                )

        return ShellCommand(script, location)

    def _function_execute(
        self,
        file: PathLikeTypes,
        /,
        *args: Union[tuple[PathLikeTypes], tuple[PathLikeTypes, ...]],
        **kwargs, #environment: dict[str, str] = None,
        #location=None,
    ):
        environment = kwargs.get("environment", None)

        if isinstance(file, ListTypes):
            file = file[0]
            args = file[1:]
        return Execute(
            file,
            args,
            environment=environment,
            location=kwargs.get("location", None),
        )

    def _function_glob(self, glob: str, location=None):
        return Glob(glob, location)

    def _function_print(self, *messages, location=None):
        return Print(messages, location)

    def _function_write(self, destination: PathLikeTypes, data: StringValue = None, location=None):
        # contents=None for touch
        return Write(destination, data=data, location=location)

    def _function_sync(
        self, source: list[AllPathLike], destination: PathLikeTypes = None, /, **kwargs
    ):
        location: FileLocation = kwargs.pop("location", None)
        exclude: list[Union[StringValue, Glob]] = kwargs.pop("exclude", None)
        destination: PathLikeTypes = destination
        return Synchronize(
            source=source,
            destination=destination,
            exclude=exclude,
            location=location,
        )

    def _function_copy(
        self,
        source: list[Union[StringValue, Glob]],
        path=None,
        /,
        exclude: list[Union[StringValue, Glob]] = None,
        location=None,
    ):
        return Copy(
            source=source,
            destination=path,
            exclude=exclude,
            location=location,
        )

    def _target_requires(
        self,
        requirements: list[Union[PathElement, StringValue, Glob, TargetReferenceElement]],
        location,
    ) -> Iterable[Union[TargetReferenceElement, PathElement, Glob]]:
        # process the requires= list of the target() function.
        # convert to targetreferences where approriate
        for require in requirements:
            if isinstance(require, StringValue):
                if require.value.find(":") >= 0:
                    # abbreviated target reference as a string
                    rpath, target = require.value.split(":")

                    # construct the same ast
                    # TODO: handle location properly by splitting and relocating
                    target = StringValue(target, location=require.location)
                    if not rpath:
                        rpath = None
                        #rpath = StringValue(rpath, location=require.location)
                    else:
                        # TODO: pass resolved= here
                        resolved = resolve_string_path_workspace(
                            ctx=self.ctx,
                            workspace=self.workspace,
                            element=StringValue(rpath, location=require.location),
                            base=self.directory
                        )
                        rpath = PathElement(rpath, resolved=resolved, location=require.location)
                        #_validate_path(rpath._as_path().parts, require.location)

                    yield TargetReferenceElement(target, rpath, location=require.location)
                else:
                    # convert strings to paths
                    p = resolve_string_path_workspace(
                        self.ctx, self.workspace, require, self.directory
                    )
                    yield PathElement(require, resolved=p, location=require.location)

            elif isinstance(require, TargetReferenceElement):
                # append internal objects referring to files such as is find(), glob() and Target(); these will be expanded later
                yield require
            elif isinstance(require, FindFiles):
                # append internal objects referring to files such as is find(), glob() and Target(); these will be expanded later
                if FIND_IN_INPUTS_ENABLED is False:
                    raise PythonScriptError(
                        "The find function (find()) is not allowed in the target's requires list.",
                        require.location
                    )

                yield require
            elif isinstance(require, Glob):
                if GLOBS_IN_INPUTS_ENABLED is False:
                    raise PythonScriptError(
                        "The glob function (glob) is not allowed in the target's requires list.",
                        require.location
                    )
                # append internal objects referring to files such as is find(), glob() and Target(); these will be expanded later
                yield require
            elif isinstance(require, PathElement):
                yield require
            elif isinstance(require, TargetObject):
                raise PythonScriptError("Invalid use of target() for the requires args. ", location)
            elif isinstance(require, ListTypes):
                # TODO: wrap lists so we can get a precise location.
                # TODO: limit list depth.
                yield from self._target_requires(require, location)
            else:
                raise PythonScriptError(
                    f"Invalid type {type(require)} in requires list. Got {require!r}.", location
                )

    def _function_target(
        self,
        name,
        *,
        path=None,
        requires=None,
        runs=None,
        outputs=None,
        location: FileLocation = None,
    ):

        if name is None or name == "":
            raise PythonScriptError(f"Invalid target name {name!r}.", location)

        _validate_target_name(name, getattr(name, "location", location))

        existing: TargetObject = self.targets.get(name, None)
        if existing:
            raise PythonScriptError(
                f"Duplicate target name {name!r}. Already defined at {existing.location.path}:{existing.location.line}.",
                location
            )

        if requires:
            _requires = list(self._target_requires(requires, location))
        else:
            _requires = []

        _outputs = []

        # unnamed outputs go in None
        outputs_dict = {None: []}
        unnamed_outputs = outputs_dict.get(None)

        if outputs:

            def process_output(
                output: Union[StringValue, Glob],
                location,
            ) -> Union[PathElement, PathObject, Glob]:
                # Mostly return the outputs, as is, for later evaluation. Check for invalid arguments early.
                if isinstance(output, StringValue):
                    return PathElement(output, location=output.location)
                elif isinstance(output, Glob):
                    # append glob as is. we'll resolve later.
                    return output
                elif isinstance(output, PathObject):
                    return output
                elif isinstance(output, PathElement):
                    return output
                else:
                    raise PythonScriptError(
                        f"Invalid output type {type(output)} in output list for target {name}: {output}",
                        location
                    )

            if isinstance(outputs, ListTypes):
                for out in outputs:
                    output = process_output(out, location)
                    _outputs.append(output)
                    unnamed_outputs.append(output)

            elif NAMED_OUTPUTS_ENABLED and isinstance(outputs, dict):
                # named outputs
                for k, v in outputs.items():
                    output = process_output(v, location)
                    _outputs.append(output)
                    outputs_dict[k] = output
            else:
                raise PythonScriptError(
                    f"Invalid outputs type {type(outputs)}. Should be a list.", location
                )

        target = TargetObject(
            name=name,
            path=path,
            requires=_requires,
            run=runs or [], # commands will be evaluated later
            outputs=_outputs,
            outputs_dict=outputs_dict,
            workspace=self.workspace,
            makex_file=self.makex_file,
            location=location,
        )
        self.targets[name] = target
        return None


class MakexFile:
    # to the makefile
    path: Path

    targets: dict[str, TargetObject]

    def __init__(self, ctx, path: Path, targets=None, variables=None, checksum: str = None):
        self.ctx = ctx
        self.path = path
        self.directory = path.parent
        self.targets = targets or {}
        self.variables = variables or []
        self.checksum = checksum
        self.enviroment_hash = None

    def key(self):
        return str(self.path)

    @classmethod
    def parse(cls, ctx: Context, path: Path, workspace: Workspace) -> "MakexFile":
        debug("Started parsing makefile %s ...", path)

        checksum = FileChecksum.create(path)
        checksum_str = str(checksum)

        makefile = cls(ctx, path, checksum=checksum_str)

        env = MakefileScriptEnv(
            ctx,
            directory=path.parent,
            path=path,
            makex_file=makefile,
            targets=makefile.targets,
            workspace=workspace,
            checksum=checksum_str,
        )

        _globals = {}

        # add environment variables to makefiles as variables
        if ENVIRONMENT_VARIABLES_IN_GLOBALS_ENABLED:
            _globals.update(ctx.environment)

        script = PythonScriptFile(path, env, _globals)

        with path.open("rb") as f:
            script.execute(f)

        if HASH_USED_ENVIRONMENT_VARIABLES:
            # hash the enviroment variable usages so targets change when they change.
            usages = env.environment._usages()
            if usages:
                makefile.enviroment_hash = target_hash(
                    "".join(f"{k}={v}" for k, v in sorted(usages.items()))
                )

        debug("Finished parsing makefile %s.", path)
        return makefile


class ParseResult:
    makex_file: MakexFile = None
    errors: deque[PythonScriptError]

    def __init__(self, makex_file=None, errors=None):
        self.errors = errors
        self.makex_file = makex_file


def parse_makefile_into_graph(
    ctx: Context,
    path: Path,
    graph: TargetGraph,
    threads=2,
    allow_makex_files=DIRECT_REFERENCES_TO_MAKEX_FILES,
) -> ParseResult:
    assert ctx.workspace_object

    # link from path -> path so we can detect cycles
    linkages: dict[ResolvedTargetReference, list[ResolvedTargetReference]] = {}

    # set this event to stop the parsing loop
    stop = Event()

    # any errors collected during parsing
    errors = deque()

    # any makefiles completed (either success or error)
    completed: deque[Path] = deque()

    # paths added to thread pool ready to parse
    executing: deque[Path] = deque()

    # waiting to be queued for work; requirements added from other files
    input_queue: deque[Path] = deque([path])

    _initial = path
    _finished: dict[Path, MakexFile] = {}

    def stop_and_error(error):
        stop.set()
        errors.append(error)

    def _iterate_target_requires(
        makefile_path: Path,
        makefile: MakexFile,
        target: TargetObject,
    ) -> Iterable[ResolvedTargetReference]:
        # yields a list of Paths the specified makefile requires
        #debug("Check requires %s -> %s", target, target.requires)
        #target_input = makefile.directory
        target_input = target.path_input()
        workspace = target.workspace

        assert isinstance(workspace, Workspace)

        for require in target.requires:
            trace("Process requirement %s", require)
            if isinstance(require, TargetObject):
                # we have a Target object.
                # TODO: This is used in testing. Not really important.
                # Manually constructed target objects.
                trace("Yield target", require)
                makex_file = require.makex_file_path
                yield ResolvedTargetReference(
                    require.name, Path(makex_file), location=require.location
                )

            elif isinstance(require, TargetReferenceElement):
                name = require.name
                path = require.path

                if isinstance(path, StringValue):
                    # Target(name, "path/to/target")
                    #trace("Path is string value: %r", path)
                    search_path = resolve_string_path_workspace(
                        ctx, target.workspace, path, target_input
                    )

                    trace("Resolve search path from string %r: %s", path, search_path)
                    # we could have a directory, or we could have a file
                    if search_path.is_file():
                        if allow_makex_files:
                            yield ResolvedTargetReference(name, search_path, path.location)
                            continue
                        else:
                            error = ExecutionError(
                                "References directly to makex files are not allowed."
                                " Strip the makex file name.",
                                target,
                                path.location
                            )
                            stop_and_error(error)
                            raise error
                    #trace("Searching path for makex files: %s", search_path)
                    makex_file = find_makex_files(search_path, ctx.makex_file_names)

                    trace("Resolved makex file from string %s: %s", path, makex_file)
                    if makex_file is None:
                        error = ExecutionError(
                            f"No makex files found in path {search_path} {path!r} for the target's requirements."
                            f" Tried: {ctx.makex_file_names!r} {target}",
                            target,
                            path.location
                        )
                        stop_and_error(error)
                        raise error
                    yield ResolvedTargetReference(name, makex_file, path.location)
                elif isinstance(path, PathElement):
                    # allow users to specify an absolute path to
                    # Target(name, Path("path/to/something")))
                    search_path = resolve_path_element_workspace(
                        ctx, target.workspace, path, target_input
                    )
                    trace("Resolve search path from %r: %s", path, search_path)

                    # we could have a directory, or we could have a file
                    if search_path.is_file():

                        if allow_makex_files:
                            yield ResolvedTargetReference(name, search_path, path.location)
                            continue
                        else:
                            error = ExecutionError(
                                "References directly to makex files are not allowed. Strip the makex file name.",
                                target,
                                path.location
                            )
                            stop_and_error(error)
                            raise error
                            break

                    makex_file = find_makex_files(search_path, ctx.makex_file_names)

                    trace("Resolved makex file from pathelement %s: %s", path, makex_file)
                    if makex_file is None:
                        error = ExecutionError(
                            f"No makex files found in path {search_path} for the target's requirements.",
                            target,
                            path.location
                        )
                        stop_and_error(error)
                        raise error

                    yield ResolvedTargetReference(name, makex_file, path.location)
                elif path is None:
                    # Target(name)
                    # we're referring to this file. we don't need to parse anything.
                    yield ResolvedTargetReference(name, makefile_path, require.location)
                else:
                    debug("Invalid ref type %s: %r", type(path), path)
                    exc = Exception(f"Invalid reference path type {type(path)}: {path!r}")
                    stop_and_error(exc)
                    raise exc
                #debug("Got reference %s %s", name, path)
                #l.append(ResolvedTargetReference(name, path))

    def finished(makefile_path: Path, makefile: Future[MakexFile]):
        makefile_path = Path(makefile_path)
        trace("Makefile parsing finished in thread %s: %s", current_thread().ident, makefile_path)

        e = makefile.exception()
        if e:
            logging.error("Makefile had an error %s %r", e, e)
            logging.exception(e)
            errors.append(e)

            mark_path_finished(makefile_path)
            return

        makefile = makefile.result()

        _finished[makefile_path] = makefile

        if makefile.targets:
            trace(
                "Adding %d targets from makefile...",
                len(makefile.targets), #makefile.targets[:min(3, len(makefile.targets))]
            )

            # we're done. add the target references to the parsing input queue
            for target_name, target in makefile.targets.items():
                trace("Add target to graph %s %s ", target, target.key())
                try:
                    graph.add_target(ctx, target)
                except ExecutionError as e:
                    errors.append(e)
                    mark_path_finished(makefile_path)
                    return

                t_as_ref = ResolvedTargetReference(
                    target.name, Path(target.makex_file_path), target.location
                )

                trace("Check requires %s -> %r", target.key(), target.requires)

                # TODO: store this iteration for later (target evaluation in Executor)
                #  we're duplicating code there.
                iterable = _iterate_target_requires(
                    makefile=makefile,
                    makefile_path=makefile_path,
                    target=target,
                )
                for reference in iterable:
                    # Check for any cycles BETWEEN files and targets.
                    cycles = linkages.get(reference, None)
                    #trace("Linkages of %s: %s", reference, cycles)
                    linkages.setdefault(t_as_ref, list()).append(reference)
                    if cycles and (t_as_ref in cycles):
                        mark_path_finished(makefile_path)
                        error = MakexFileCycleError(
                            f"Cycle detected from {reference.key()} to {cycles[-1].key()}",
                            target,
                            cycles,
                        )
                        errors.append(error)
                        raise error

                    #trace("Got required path %s", reference)
                    if reference.path in completed:
                        trace("Path already completed %s. Possible cycle.", reference)
                        continue

                    trace("Add to parsing input queue %s", reference)
                    input_queue.append(reference.path)
                    target.add_resolved_requirement(reference)

        #if path in queued:
        trace("Remove from deque %s", makefile_path)
        mark_path_finished(makefile_path)

    def mark_path_finished(makefile_path: Path):
        completed.append(makefile_path)

        if makefile_path in executing:
            executing.remove(makefile_path)

    pool = ThreadPoolExecutor(threads)

    try:
        while stop.is_set() is False:

            if len(input_queue) == 0:
                debug("Stopped. Empty queue.")
                stop.set()
                continue

            while len(executing) == threads:
                debug("queue wait. %s", executing)
                time.sleep(1)

            path = input_queue.pop()

            if path in executing:
                input_queue.append(path)
            else:
                if path not in completed:
                    if NESTED_WORKSPACES_ENABLED:
                        workspace_of_makefile: Workspace = ctx.workspace_cache.get_workspace_of(
                            path
                        )
                        trace(
                            "Detected workspace of makefile at path %s: %s",
                            path,
                            workspace_of_makefile
                        )
                    else:
                        # Use the root/initial workspace if no nesting.
                        workspace_of_makefile = ctx.workspace_object

                    debug(
                        "Queue MakeFile for parsing %s (workspace=%s) ...",
                        path,
                        workspace_of_makefile
                    )

                    f = pool.submit(
                        MakexFile.parse,
                        ctx=ctx,
                        path=Path(path),
                        workspace=workspace_of_makefile,
                    )
                    # We must use a lambda passing the path because if we have
                    # an Exception we won't know which file caused it.
                    f.add_done_callback(lambda future, p=path: finished(p, future))

                    executing.append(path)
                    input_queue.append(path)
                    # XXX: this sleep is required so that is_set isn't called repeatedly (thousands of times+) when running.
                    time.sleep(0.1)

    finally:
        debug("Wait for pool to shutdown...")
        pool.shutdown()

    return ParseResult(makex_file=_finished.get(_initial), errors=errors)


def parse_target_string_reference(
    ctx: Context,
    base,
    string,
    check=True,
) -> Optional[ResolvedTargetReference]:
    # resolve the path/makefile?:target_or_build_path name
    # return name/Path
    parts = string.split(":", 1)
    if len(parts) == 2:
        path, target = parts
        path = Path(path)
        if not path.is_absolute():
            path = base / path

        if path.is_symlink():
            path = path.readlink()
    else:
        target = parts[0]
        path = base

    if path.is_dir():
        if check:
            # check for Build/Makexfile in path
            path, checked = find_makex_files(path, ctx.makex_file_names)
            if path is None:
                ctx.ui.print(
                    f"Makex file does not exist for target specified: {target}", error=True
                )
                for check in checked:
                    ctx.ui.print(f"- Checked in {check}")
                sys.exit(-1)

    return ResolvedTargetReference(target, path=path)


#def _string_value_to_path(ctx, base, value: StringValue) -> Path:
#    val = value.value
#
#    if False and val.startswith("~"):
#        # TODO: use environment HOME to expand the user
#        return Path(val).expanduser()
#    else:
#        path = Path(val)
#
#        if not path.is_absolute():
#            path = base / path
#
#        return path

#def _path_element_to_path(base, value: PathElement) -> Path:
#    return resolve_path_element(value, base)
#    if value.resolved:
#        source = value.resolved
#        if not source.is_absolute():
#            source = base / source
#    else:
#        source = value._as_path()
#        #source = source.expanduser()
#        if not source.is_absolute():
#            source = base / source
#
#    return source
#def resolve_path_element(element: PathElement, base: Path) -> Path:
#    """
#    Resolve an unresolved relative PathObject.
#
#    :param element:
#    :param base:
#    :return:
#    """
#
#    #if search_path.parts[0] == "//":
#    #    error = NotImplementedError("Workspace paths not supported yet.")
#    #    stop_and_error(error)
#    #    break
#
#    if element.resolved:
#        return element.resolved
#
#    path = Path(*element.parts)
#
#    if not path.is_absolute():
#        path = base / path
#    return path

#def resolve_path_parts(parts: list[StringValue], base: Path, location) -> Path:
#    path = Path(*parts)
#
#    _validate_path(path.parts, location)
#
#    if not path.is_absolute():
#        path = base / path
#
#    return path

#def resolve_string_path(element: StringValue, base: Path) -> Path:
#    path = Path(element.value)
#
#    _validate_path(path.parts, element.location)
#
#    if not path.is_absolute():
#        path = base / path
#
#    return path
