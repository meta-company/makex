import ast
import logging
import os
import re
import shlex
import shutil
import types
from abc import (
    ABC,
    abstractmethod,
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
from typing import (
    Any,
    Callable,
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
    ENVIRONMENT_VARIABLES_IN_GLOBALS_ENABLED,
    HASH_USED_ENVIRONMENT_VARIABLES,
    IGNORE_NONE_VALUES_IN_LISTS,
    OUTPUT_DIRECTLY_TO_CACHE,
    WORKSPACES_IN_PATHS_ENABLED,
)
from makex.context import Context
from makex.errors import (
    ExecutionError,
    MakexError,
)
from makex.file_checksum import FileChecksum
from makex.file_system import find_files
from makex.flags import (
    ABSOLUTE_PATHS_ENABLED,
    ARCHIVE_FUNCTION_ENABLED,
    EXPAND_FUNCTION_ENABLED,
    FIND_FUNCTION_ENABLED,
    FIND_IN_INPUTS_ENABLED,
    GLOB_FUNCTION_ENABLED,
    GLOBS_IN_ACTIONS_ENABLED,
    GLOBS_IN_INPUTS_ENABLED,
    HOME_FUNCTION_ENABLED,
    IMPORT_ENABLED,
    INCLUDE_ENABLED,
    NAMED_OUTPUTS_ENABLED,
    SHELL_USES_RETURN_CODE_OF_LINE,
    TARGET_PATH_ENABLED,
)
from makex.makex_file_types import (
    AllPathLike,
    EnvironmentVariableProxy,
    Expansion,
    FindFiles,
    Glob,
    ListTypes,
    MultiplePathLike,
    PathElement,
    PathLikeTypes,
    PathObject,
    RegularExpression,
    ResolvedTargetReference,
    TargetReferenceElement,
)
from makex.patterns import (
    combine_patterns,
    make_glob_pattern,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
    GLOBALS_NAME,
    FileLocation,
    ListValue,
    PythonScriptError,
    PythonScriptFile,
    ScriptEnvironment,
    StringValue,
    _create_file_location_call,
    call_function,
    is_function_call,
    wrap_script_function,
)
from makex.run import run
from makex.target import (
    ArgumentData,
    EvaluatedTarget,
    format_hash_key,
    target_hash,
)
from makex.ui import pretty_file
from makex.version import VERSION
from makex.workspace import Workspace
from typing_extensions import (
    NotRequired,
    Required,
    Unpack,
)

_TARGET_REFERENCE_NAME = "Reference"
_MACRO_DECORATOR_NAME = "macro"

TARGETS_MODULE_VARIABLE = "_TARGETS_"
MACROS_MODULE_VARIABLE = "__macros__"
MACRO_NAMES_MODULE_VARIABLE = "__macro_names__"

DISABLE_ASSIGNMENT_NAMES = {
    MACROS_MODULE_VARIABLE,
    MACRO_NAMES_MODULE_VARIABLE,
    MACRO_NAMES_MODULE_VARIABLE,
    "target",
    "Target",
    _MACRO_DECORATOR_NAME,
    _TARGET_REFERENCE_NAME,
    "task",
    "Task",
    "path",
    "execute",
    "shell",
    "copy",
    "print",
    "E",
    "ENVIRONMENT",
    "Environment",
    "environment",
    "glob",
    "pattern",
    "input",
    "inputs",
    "output",
    "outputs",
    "find",
    "Path",
    "source",
    "home",
    "archive",
    "mirror",
    "sync",
    "include",
}

# TODO: move these to makex_file_types


def _validate_path(
    parts: Union[list[StringValue], tuple[StringValue]],
    location: FileLocation,
    absolute=ABSOLUTE_PATHS_ENABLED,
):
    if ".." in parts:
        raise PythonScriptError("Relative path references not allowed in makex.", location)
    if parts[0] == "/" and absolute is False:
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
        #trace("Workspace path: %s %s", workspace, element)
        if WORKSPACES_IN_PATHS_ENABLED:
            _path = workspace.path / Path(*path.parts[1:])
        else:
            raise PythonScriptError("Workspaces markers // in paths not enabled.", element.location)
    elif not path.is_absolute():
        _path = base / path

    #trace("Resolve string path %s: %s", element, _path)

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
        elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
            continue

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
            # bash will replace a ~ wherever it is on the command line
            yield _string_value_maybe_expand_user(ctx, base, value)
        elif isinstance(value, PathObject):
            yield value.path.as_posix()
        elif isinstance(value, PathElement):
            source = resolve_path_element_workspace(ctx, target.workspace, value, base)
            #source = _path_element_to_path(base, value)
            yield source.as_posix()
        elif isinstance(value, Glob):
            if not GLOBS_IN_ACTIONS_ENABLED:
                raise ExecutionError("glob() can't be used in actions.", target, value.location)

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
        elif isinstance(value, tuple):
            yield from resolve_string_argument_list(ctx, target, base, name, value)
        elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
            continue
        else:
            raise NotImplementedError(f"{type(value)} {value!r}")


def _resolve_executable_name(ctx: Context, target, base: Path, name, value: StringValue) -> Path:
    if isinstance(value, StringValue):
        return _resolve_executable(ctx, target, value, base)
    elif isinstance(value, PathElement):
        _path = resolve_path_element_workspace(ctx, target.workspace, value, base)
        return _path
    elif isinstance(value, PathObject):
        return value.path
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
    pattern: Glob,
    ignore_names,
) -> Iterable[Path]:
    # TODO: check if glob is absolute here?
    glob_pattern = pattern.pattern
    _pattern = re.compile(make_glob_pattern(str(glob_pattern)))

    yield from find_files(
        path,
        pattern=_pattern,
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

    #TODO: support matching stringvalues to paths
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
    ctx,
    target,
    name: StringValue,
    base: Path,
    path_string: Optional[str] = None,
) -> Path:
    if name.find("/") >= 0:
        # path has a slash. resolve using a different algo.
        _path = resolve_string_path_workspace(ctx, target.workspace, name, base)
        if _path.exists() is False:
            raise ExecutionError(
                f"Could not find the executable for {name}. Please install whatever it "
                f"is that provides the command {name!r}.",
                target
            )
        return _path

    path_string = ctx.environment.get("PATH", "")
    if not path_string:
        path_string = str(base)
    else:
        path_string = f"{base}:{path_string}"

    # XXX: prepend the current folder to the path so executables are found next to the makex file.
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
    # TODO: remove this function. replace with late evaluation.
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


# TODO: move these to makex_file_actions.py


class ActionElementProtocol(Protocol):
    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> dict[str, Any]:
        ...

    def __call__(self, ctx: Context, target: EvaluatedTarget) -> CommandOutput:
        ...


class InternalActionBase(ABC):
    location: FileLocation = None

    # TODO: add/collect requirements as we go
    def add_requirement(self, requirement: "TargetReferenceElement"):
        raise NotImplementedError

    # TODO: make abstract and wire in.
    def get_requirements(self, ctx: Context) -> list["TargetReferenceElement"]:
        """
        Return a list of any target requirements in the action/arguments. Done before argument transformation.

        Any TargetReference or Path used by the target should be returned (except one for the Target itself).

        Used to detect implicit target requirements.
        :return:
        """
        return []

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
        # produce a hash of the Action with the given arguments and functions
        # TODO: make abstract once we migrate everything over to the new argument functionality
        raise NotImplementedError

    # old stuff below
    def __call__(self, ctx: Context, target: EvaluatedTarget) -> CommandOutput:
        raise NotImplementedError

    def __str__(self):
        return PythonScriptError("Converting Action to string not allowed.", self.location)


@dataclass
class Execute(InternalActionBase):
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
                #arguments.append(_string_value_maybe_expand_user(ctx, target_input, argument))
                arguments.append(argument)
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
            elif argument is None:
                # XXX: Ignore None arguments as they may be the result of a condition.
                continue
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


class Shell(InternalActionBase):
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
        # TODO: validate string type
        args["string"] = self.string
        args["preamble"] = self.preamble

        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        string = arguments.get("string")
        preamble = arguments.get("preamble")

        if not string:
            return CommandOutput(0)

        s_print = "\n".join([f"# {s}" for s in chain(preamble.split("\n"), self.string)])

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

        cwd = target.input_path
        ctx.ui.print(f"Running shell from {cwd}:\n{s_print}\n")
        if ctx.dry_run is True:
            return CommandOutput(0)
        try:
            #stdin = BytesIO()
            #stdin.write(script.encode("utf-8"))

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
            # XXX: set the location so we see what fails
            # TODO: Set the FileLocation of the specific shell line that fails
            output.location = self.location
            return output
        except Exception as e:
            raise ExecutionError(e, target, location=self.location) from e

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        return hash_function("\n".join(arguments.get("string", [])))


def file_ignore_function(output_folder_name):
    def f(src, names):
        return {output_folder_name}

    return f


@dataclass
class Copy(InternalActionBase):
    source: Union[list[AllPathLike], PathLikeTypes]
    destination: PathLikeTypes
    exclude: list[AllPathLike]
    location: FileLocation
    destination_is_subdirectory: bool = False

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function):
        # checksum all the sources
        sources = arguments.get("sources")

        # hash the destination name
        destination = arguments.get("destination")

        exclusions = arguments.get("exclude", [])

        parts = []
        for source in sources:
            parts.append(hash_function(source.as_posix()))

        if destination is not None:
            parts.append(hash_function(destination.as_posix()))

        if exclusions:
            parts.append(hash_function(exclusions.pattern))

        return hash_function("|".join(parts))

    def get_requirements(self, ctx: Context) -> Iterable["TargetReferenceElement"]:
        if isinstance(self.source, ListTypes):
            for source in self.source:
                if isinstance(source, PathObject):
                    yield source.reference
        else:
            if isinstance(self.source, PathObject):
                yield self.source.reference

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

            if not isinstance(self.destination, (str, PathObject, PathElement)):
                raise PythonScriptError("Destination must be a string or path.", self.location)

            if isinstance(self.destination, str):
                if "/" in self.destination:
                    self.destination_is_subdirectory = True

            destination = _resolve_pathlike(
                ctx=ctx,
                target=target,
                name="destination",
                base=target.path,
                value=self.destination
            )

        else:
            destination = None

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

        destination_specified = destination is not None
        if destination_specified:
            destination_is_folder = destination.is_dir()
        else:
            destination = target.path
            destination_is_folder = True

        copy_file = ctx.copy_file_function

        if destination.exists() is False:
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

        # XXX: keep n sources so we can determine which form of copy() we have (8 forms).
        #  copy(items) will always use the file/folder name in the items list
        #  copy(files)
        #  copy(file)
        #  copy(folders)
        #  copy(folder)
        # with destination:
        #  copy(file, file) copy a file to specified file path. TODO: this doesn't work. remove this. suggest install()
        #  copy(file, folder) copy a file to specified folder.
        #  copy(folder, folder) allows renaming or mirroring a folder.
        #  copy(folders, folder) copies a set of folders to the specified folder..
        #  copy(files, folder) copies a set of files to the specified folder.

        #  copy(file, "folder" / file) allows renaming a file and prefixing it into a folder. TODO: remove this. suggest install()
        n_sources = len(sources)

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
            if destination_specified:
                # destination was specified, one of:
                # copy(folder, folder)
                # copy(folders, folder)
                # copy(file, file)
                # copy(files, destination)
                if n_sources == 1:
                    _destination = destination
                else:
                    _destination = destination / source.name
            else:
                # destination not specified, one of:
                # copy(folder)
                # copy(folders)
                # copy(file)
                # copy(files)
                _destination = destination / source.name

            if source.is_dir():
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
                        raise ExecutionError("\n".join(string), target, target.location) from e
                    except OSError as e:
                        string = [
                            f"Error copying tree {source} to {destination}:\n  Error to {e.filename} from {e.filename2}: {type(e)}: {e.args[0]} {e} "
                        ]

                        raise ExecutionError("\n".join(string), target, target.location) from e
            else:
                trace("Copy file %s <- %s", _destination, source)
                if ctx.dry_run is False:
                    try:
                        copy_file(source.as_posix(), _destination.as_posix())
                    except (OSError, shutil.Error) as e:
                        raise ExecutionError(
                            f"Error copying file {source} to {_destination}: {e}",
                            target,
                            target.location
                        ) from e
        return CommandOutput(0)


@dataclass
class Synchronize(InternalActionBase):
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

        if isinstance(self.source, (list, ListValue)):
            _source_list = self.source
        else:
            _source_list = [self.source]

        args["sources"] = sources = list(
            resolve_pathlike_list(
                ctx=ctx,
                target=target,
                name="source",
                base=target.input_path,
                values=_source_list,
                glob=GLOBS_IN_ACTIONS_ENABLED,
            )
        )
        #trace("Synchronize sources %s", sources)

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

        args["destination"] = destination
        args["symlinks"] = self.symlinks

        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        sources: list[Path] = arguments.get("sources")
        destination: Path = arguments.get("destination")
        symlinks: Path = arguments.get("symlinks")

        ignore = file_ignore_function(ctx.output_folder_name)

        if ctx.dry_run is False:
            destination.mkdir(parents=True, exist_ok=True)

        debug("Synchronize to destination: %s", destination)

        length = len(sources)

        if length > 1:
            ctx.ui.print(f"Synchronizing to {destination} ({length} items)")
        else:
            ctx.ui.print(f"Synchronizing to {destination} ({sources[0]})")

        for source in sources:
            #trace("Synchronize source to destination: %s: %s", source, destination)
            if not source.exists():
                raise ExecutionError(
                    f"Missing source/input file {source} in sync()", target, location=self.location
                )

            # Fix up destination; source relative should match destination relative.
            if source.parent.is_relative_to(target.input_path):
                _destination = destination / source.parent.relative_to(target.input_path)

                if ctx.dry_run is False:
                    _destination.mkdir(parents=True, exist_ok=True)
            else:
                _destination = destination

            if source.is_dir():
                # copy recursive
                trace("Copy tree %s <- %s", _destination, source)
                if ctx.dry_run:
                    continue
                shutil.copytree(source, _destination, dirs_exist_ok=True, ignore=ignore)
            else:
                trace("Copy file %s <- %s", _destination / source.name, source)
                if ctx.dry_run:
                    continue
                shutil.copy(source, _destination / source.name)

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [self.__class__.__name__, arguments.get("destination").as_posix()]
        parts.extend([a.as_posix() for a in arguments.get("sources")])

        return hash_function("|".join(parts))


@dataclass
class Print(InternalActionBase):
    messages: list[str]

    def __init__(self, messages, location):
        self.messages = messages
        self.location = location

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        for message in self.messages:
            print(message)

        return CommandOutput(0)

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget) -> ArgumentData:
        pass

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # this hash doesn't matter; doesn't affect output
        return ""


@dataclass
class Write(InternalActionBase):
    path: PathLikeTypes
    data: StringValue
    executable: bool = False

    def __init__(
        self, path: PathLikeTypes, data: StringValue = None, executable=False, location=None
    ):
        self.path = path
        self.data = data
        self.location = location
        self.executable = False

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
        args["executable"] = self.executable
        return ArgumentData(args, inputs=[path])

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
        path: Path = arguments.get("path")
        data = arguments.get("data")

        ctx.ui.print(f"Writing {path}")

        if ctx.dry_run is False:
            if not path.parent.exists():
                path.parent.mkdir(mode=0o755, parents=True)

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
                "Invalid argument data argument to write()", target, location=target.location
            )

        if self.executable:
            path.chmod(0o755)

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [
            arguments.get("path").as_posix(),
            arguments.get("data"),
        ]
        return hash_function("|".join(parts))


class SetEnvironment(InternalActionBase):
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


class InsertAST(ast.NodeTransformer):
    def __init__(self, path, asts: list[ast.AST]):
        self.path = path
        self.asts = asts

    def visit_Module(self, node: ast.Module) -> Any:
        node.body = self.asts + node.body


class ProcessIncludes(ast.NodeTransformer):
    """
        Adds a globals() argument to include() calls so that the environment can modify its own globals.


        TODO: includes should be at the top of the file; enforcing this is tricky.
        we need to scan the body for any include() calls.
        if any include() is found after any other statement, raise an error
    """
    def __init__(self, path: str):
        self.path = path
        self.includes_seen: list[tuple[str, FileLocation]] = []

    def visit_Call(self, node: ast.Call) -> Any:
        if is_function_call(node, "include") is False:
            return node

        line = node.lineno
        col = node.col_offset

        #location = FileLocation(line, col, self.path)
        #if other_nodes_seen:
        #    raise PythonScriptError("Includes must be at the top of a file.", location)
        #else:
        #self.includes_seen.append((node.args[0].value, location))

        node.keywords.append(
            ast.keyword(
                arg='_globals',
                value=call_function(GLOBALS_NAME, line, col),
                lineno=line,
                col_offset=col,
            )
        )
        #debug("Transform include %s", ast.dump(node))
        return node


class TransformGetItem(ast.NodeTransformer):
    """
        Transforms Target Reference Slice Syntax: Target[path:name] into a TargetReference(name, path)


    >>> print(ast.dump(ast.parse('target["test":"test":"test"]', mode='single'), indent=4))

        Subscript(
            value=Name(id='target', ctx=Load()),
            slice=Slice(
                lower=Constant(value='test'),
                upper=Constant(value='test'),
                step=Constant(value='test')),
            ctx=Load()
            )
        )
    """
    NAME = "Target"

    def __init__(self, path):
        super().__init__()
        self.path = str(path)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        if isinstance(node.value, ast.Name) is False:
            self.generic_visit(node)
            return node
        if node.value.id != self.NAME:
            self.generic_visit(node)
            return node

        line = node.lineno
        offset = node.col_offset
        slice: ast.Slice = node.slice

        lower = slice.lower or ast.Constant(None, lineno=line, col_offset=offset)
        upper = slice.upper or ast.Constant(None, lineno=line, col_offset=offset)
        step = slice.step or ast.Constant(None, lineno=line, col_offset=offset)

        file_location = _create_file_location_call(self.path, line, offset)

        reference_call = ast.Call(
            func=ast.Name(
                id=_TARGET_REFERENCE_NAME,
                ctx=ast.Load(),
                lineno=line,
                col_offset=offset,
            ),
            args=[],
            keywords=[
                ast.keyword(
                    arg='name',
                    value=upper,
                    lineno=line,
                    col_offset=offset,
                ),
                ast.keyword(
                    arg='path',
                    value=lower,
                    lineno=line,
                    col_offset=offset,
                ),
                ast.keyword(
                    arg='location',
                    value=file_location,
                    lineno=line,
                    col_offset=offset,
                ),
            ],
            lineno=line,
            col_offset=offset,
        )
        return reference_call


class TargetObject:
    name: StringValue
    path: PathElement
    requires: list[Union[PathElement, PathObject, "TargetObject"]]
    commands: list[ActionElementProtocol]

    # TODO: inputs dictionary, "" or None is for unnamed inputs
    inputs: dict[None, AllPathLike]

    # outputs as a list. fast checks if has any outputs
    outputs: list[PathElement]

    # named outputs dict
    # None key is unnamed outputs
    outputs_dict: dict[Union[None, str], list[Union[PathElement, PathObject]]]

    # location to build. can be overridden by users.
    build_path: Path

    # The location in which this task was actually defined (i.e. where the task() function was called).
    location: FileLocation

    resolved_requires: list[ResolvedTargetReference]

    workspace: Workspace

    #makex_file_checksum: str

    # The makex file in which this target was registered
    makex_file: "MakexFile"

    endless: bool = False

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
        # TODO: pass the includer file so we can distinguish between where a target was defined and where it was finally included
        #   we need to use the includer to generate target.keys()
        includer=None,
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

        # cache the requirement references we've obtained so we don't have to search for makex file later
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
            return None

        yield from d.get(None)

        for k, v in d.items():
            if isinstance(v, list):
                yield from v
            else:
                yield v

    def add_resolved_requirement(self, requirement: ResolvedTargetReference):
        self.resolved_requires.append(requirement)

    @property
    def makex_file_path(self) -> str:
        return self.makex_file.path.as_posix()

    def path_input(self):
        """ Return the directory where this target is declared/applicable. """
        return self.makex_file.directory

    def __eq__(self, other):
        if not isinstance(other, (TargetObject, ResolvedTargetReference)):
            return False

        return self.key() == other.key()

    def key(self):
        return format_hash_key(self.name, self.makex_file.path)

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        if self.path:
            return f"TargetObject(\"{self.name}\", {self.makex_file.path})"
        return f"TargetObject(\"{self.name}\")"

    def for_include(self, file: "MakexFile"):
        # return a target transformed for inclusion
        raise NotImplementedError


def resolve_target_output_path(ctx, target: TargetObject):
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


class MakexFileCycleError(MakexError):
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


def find_makex_files(path, names) -> Optional[Path]:
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


class IncludeFunction(Protocol):
    def __call__(
        self,
        ctx: Context,
        workspace: Workspace,
        base: Path,
        search_path: str,
        makex_file: "MakexFile",
        location: FileLocation,
        search=False,
        globals=None,
        stack=None,
        targets=False,
        required=True,
    ) -> tuple[types.ModuleType, "MakexFile"]:
        pass


def _process_output(
    output: Union[StringValue, Glob],
    target_name,
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
            f"Invalid output type {type(output)} in output list for target {target_name}: {output}",
            location
        )


class MakexFileScriptEnvironment(ScriptEnvironment):
    class Task:
        def __init__(self, env):
            self.env = env

        def __getitem__(self, item):
            if item not in {"path"}:
                raise AttributeError

            return self.env.path

        def __call__(self, *args, **kwargs):
            pass

    def __init__(
        self,
        ctx,
        directory: Path,
        path: Path,
        workspace: Workspace = None,
        targets: Optional[dict[str, TargetObject]] = None,
        macros: Optional[dict[str, Callable]] = None,
        makex_file: Optional["MakexFile"] = None,
        stack: Optional[list[str]] = None, # stack of paths reaching the file
        include_function: Optional[IncludeFunction] = None,
        globals=None,
    ):
        self.stack = stack or [path.as_posix()]

        self.directory = directory

        # path to the actual makex file
        self.path = path

        self.ctx = ctx
        # TODO: wrap environment dict so it can't be modified
        self.environment = EnvironmentVariableProxy(ctx.environment)
        self.targets = {} if targets is None else targets
        #self.variables = []
        self.build_paths: list[Path] = []
        self.workspace = workspace
        self.makex_file = makex_file or None

        self._include_function = include_function
        self._globals: dict[str, Any] = globals or {}
        self.macros: dict[str, Callable] = {} if macros is None else macros
        self.block_registration = False
        self.includes: set[MakexFile] = set()

    def globals(self):
        parent = super().globals()

        g = {
            #**self._globals,
            **parent,
            TARGETS_MODULE_VARIABLE: self.targets,
            MACROS_MODULE_VARIABLE: self.macros,
            "Environment": self.environment, #"pattern": wrap_script_function(self._pattern),
            "ENVIRONMENT": self.environment,
            "target": wrap_script_function(self._function_target),

 # TODO: declare new aliases:
            "Task": wrap_script_function(self._function_task),
            "task": wrap_script_function(self._function_task),
            _TARGET_REFERENCE_NAME: wrap_script_function(self._function_Target),
            #TODO: define a Target object for type references
            #"Target": wrap_script_function(self._function_Target),
            _MACRO_DECORATOR_NAME: self._decorator_macro, #"macro": Decorator,
        }

        if INCLUDE_ENABLED:
            g["include"] = self._function_include

        # path utilities
        g.update(
            {
                # DONE: path() is a common variable (e.g. in a loop), and as an argument (to target) and Path() object. confusing.
                #  alias to cache(), or output()
                "path": wrap_script_function(self._function_path),
                "task_path": wrap_script_function(self._function_task_path),
                # cache is a bit shorter than task_path
                "cache": wrap_script_function(self._function_task_path),
                #"output": wrap_script_function(self.build_path),
                "Path": wrap_script_function(self._function_Path),
                "source": wrap_script_function(self._function_source),
            }
        )

        if GLOB_FUNCTION_ENABLED:
            g["glob"] = wrap_script_function(self._function_glob)

        if FIND_FUNCTION_ENABLED:
            g["find"] = wrap_script_function(self._function_find)

        # Actions
        g.update(
            {
                "print": wrap_script_function(self._function_print),
                "shell": wrap_script_function(self._function_shell),
                # TODO: deprecate sync
                "sync": wrap_script_function(self._function_sync),
                "mirror": wrap_script_function(self._function_sync),
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

    @dataclass
    class MacroContext:
        target: Callable
        path: Callable
        source: Callable

    def _decorator_macro(self, fn, _location1_=None):
        # @macro decorator implementation
        # wrap functions to handle location argument
        # TODO: macros should be keyword only.
        def f(
            *args,
            _location_=None,
            **kwargs,
        ):
            if args:
                raise PythonScriptError("Macros must be called with keyword arguments.", _location_)

            debug("Calling macro %s %s %s %s", fn, args, kwargs, _location_)
            return fn(*args, **kwargs)

        trace(f"Declaring macro: %s: %s (%s)", self.path, fn.__name__, _location1_)
        self.macros[fn.__name__] = f
        f.__name__ = fn.__name__

        # slighly similar way to achieve the same goal:
        #self._globals[fn.__name__] = f
        #import inspect
        #inspect.stack()[1][0].f_globals.update()
        return f

    if False:

        def has_global(self, name):
            print("check has global", name)
            return name in self._globals

        def get_global(self, name):
            return self._globals.get(name)

    def _function_include(
        self,
        path: StringValue,
        search=False,
        tasks=False,
        _globals=None,
        required=True,
        _location_=None,
        **kwargs
    ):

        # _globals argument is passed in via ast modifications
        if self._include_function is None:
            raise PythonScriptError("Can't include from this file.", _location_)

        debug("Including %s ...", path)
        module, file = self._include_function(
            ctx=self.ctx,
            workspace=self.workspace,
            base=self.directory,
            makex_file=self.makex_file,
            search_path=path,
            search=search,
            globals=_globals,
            location=_location_,
            targets=tasks,
            required=required,
            extra=kwargs,
        )

        if module is None:
            debug("Skipping missing optional makex file.")
            return None

        del module.__builtins__
        _macros = getattr(module, MACROS_MODULE_VARIABLE)
        debug("Importing macros from %s: %s", path, _macros.keys())

        _globals.update(_macros)

        self.includes.add(file)

        if tasks:
            trace("Adding targets from included file: %s", module._TARGETS_.keys())
            self.targets.update(module._TARGETS_)

    def _function_expand(self, string: StringValue, location: FileLocation):
        return Expansion(context=self.ctx, string=string, location=location)

    def _function_home(self, *path, user=None, location=None):
        if user:
            arg = f"~{user}"
        else:
            arg = "~"
        home = expanduser(arg)

        _path = Path(home)
        if path:
            _path =  _path.joinpath(*path)

        return PathElement(arg, resolved=_path, location=location)

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
                f"Invalid path type in find() function: {type(path)} ({path}). Path or string expected.",
                location
            )
        return FindFiles(expr, path, location=location)

    def _function_environment(
        self,
        dictionary: Optional[dict[StringValue, Union[PathLikeTypes, StringValue]]] = None,
        location: FileLocation = None,
        **kwargs: Union[PathLikeTypes, StringValue],
    ):
        _dictionary = dictionary or {}
        _dictionary.update(**kwargs)
        return SetEnvironment(_dictionary, location=location)

    def _function_Target(self, name, path: PathLikeTypes = None, location=None, **kwargs):
        # absorb kwargs so we can error between Target and target
        return TargetReferenceElement(name=name, path=path, location=location)

    def _function_path(
        self,
        *args,
        **kwargs,
    ):
        location = kwargs.get("location", "")

        self.ctx.ui.warn(
            f"The path() function is deprecated. Please change to using task_path() instead. {location}"
        )
        return self._function_task_path(*args, **kwargs)

    def _function_task_path(
        self,
        name,
        path: PathLikeTypes = None,
        variants: Optional[list[str]] = None,
        location=None,
    ):
        if isinstance(path, PathElement):
            _path = resolve_path_element_workspace(self.ctx, self.workspace, path, self.directory)
        elif isinstance(path, StringValue):
            _path = resolve_string_path_workspace(self.ctx, self.workspace, path, self.directory)
        elif path is None:
            _path = self.directory
        else:
            raise PythonScriptError(f"Invalid path value:{type(path)}", location)
        return create_build_path_object(
            self.ctx, target=name, path=_path, variants=variants, location=location
        )

    def _function_source(self, *path: StringValue, location=None):
        if not path:
            # XXX: No path. Return the source directory.
            return PathElement(*self.directory.parts, resolved=self.directory, location=location)

        for part in path:
            if not isinstance(part, StringValue):
                raise PythonScriptError(
                    f"Invalid path part type in source() function. Expected string. Got {type(part)}: {part!r}",
                    getattr(part, "location", location)
                )

        _path = resolve_path_parts_workspace(
            self.ctx, self.workspace, path, self.directory, location
        )

        # XXX: all of _path.parts is used, so it's fully absolute
        return PathElement(*path, resolved=_path, location=location)

    def _function_Path(self, *path: StringValue, location=None):
        for part in path:
            if not isinstance(part, StringValue):
                raise PythonScriptError(
                    f"Invalid path part type in Path() function. Expected string. Got {type(part)}: {part!r}",
                    getattr(part, "location", location)
                )

        #trace("Creating path: %s", path)
        if True:
            _path = None
        else:
            # TODO: handle resolving workspace paths here
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

        return Shell(script, location)

    def _function_execute(
        self,
        file: PathLikeTypes,
        /,
        *args: Union[tuple[PathLikeTypes], tuple[PathLikeTypes, ...]],
        **kwargs, #environment: dict[str, str] = None,
        #location=None,
    ):
        environment = kwargs.pop("environment", None)
        location = kwargs.pop("location", None)

        if isinstance(file, ListTypes):
            file = file[0]
            args = file[1:]
        return Execute(
            file,
            args,
            environment=environment,
            location=location,
        )

    def _function_glob(self, glob: str, location=None):
        return Glob(glob, location)

    def _function_print(self, *messages, location=None):
        return Print(messages, location)

    def _function_write(
        self,
        destination: PathLikeTypes,
        data: StringValue = None,
        executable=False,
        location=None
    ):
        # contents=None for touch
        return Write(destination, data=data, executable=executable, location=location)

    def _function_sync(
        self, source: list[AllPathLike], destination: PathLikeTypes = None, /, **kwargs
    ):
        location: FileLocation = kwargs.pop("location", None)
        exclude: list[Union[StringValue, Glob]] = kwargs.pop("exclude", None)
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
    ) -> Iterable[Union[TargetReferenceElement, PathElement, Glob, FindFiles]]:
        # process the requires= list of the target() function.
        # convert to TargetReference where appropriate
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
                # append references which will be evaluated later
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
                # append internal objects referring to files such as is find(), glob() and Target(); these will be expanded later
                if GLOBS_IN_INPUTS_ENABLED is False:
                    raise PythonScriptError(
                        "The glob function (glob) is not allowed in the target's requires list.",
                        require.location
                    )
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

    class TargetArguments(TypedDict):
        name: str
        path: NotRequired[Path]
        requires: NotRequired[list[str]]
        runs: NotRequired[list]
        actions: NotRequired[list]
        outputs: NotRequired[list]
        inputs: NotRequired[dict]
        location: Required[FileLocation]
        #**kwargs: Unpack[TargetArguments]
        # NotRequired
        #

    def _function_target(
        self, #*args,
        **kwargs: Unpack[TargetArguments],
    ):
        location = kwargs.get("location", None)
        self.ctx.ui.warn(
            f"The target() function is deprecated. It will be removed by 2024-06. Please change to using task(steps=[]) instead. {location}"
        )
        steps = kwargs.pop("runs", None)
        return self._function_task(steps=steps, **kwargs)

    def _function_task(
        self, #*args,
        **kwargs: Unpack[TargetArguments],
    ):
        location = kwargs.pop("location", None)

        if False:
            arglen = len(args)
            if not arglen:
                pass
            elif arglen == 3:
                name, path, variants = args
                return TargetReferenceElement(name, path, variants, location=location)
            elif arglen == 2:
                name, path = args
                return TargetReferenceElement(name, path, location=location)
            elif arglen == 1:
                name = args[0]
                return TargetReferenceElement(name, location=location)
            else:
                raise PythonScriptError(
                    "Invalid number of arguments to create Target Reference. Expected name and optional path.",
                    location=location
                )

        if self.block_registration:
            trace("Registration of target blocked at %s", location)
            return

        #trace("Calling target() from %s", self.makex_file)
        name = kwargs.pop("name", None)
        path = kwargs.pop("path", None)
        requires = kwargs.pop("requires", None)
        runs = kwargs.pop("actions", None) or kwargs.pop("steps", None)
        outputs = kwargs.pop("outputs", None)

        if kwargs:
            raise PythonScriptError(f"Unknown arguments to task(): {kwargs}", location)

        if name is None or name == "":
            raise PythonScriptError(f"Invalid target name {name!r}.", location)

        _validate_target_name(name, getattr(name, "location", location))

        existing: TargetObject = self.targets.get(name, None)
        if existing:
            raise PythonScriptError(
                f"Duplicate target name {name!r}. Already defined at {existing.location}.",
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
            if isinstance(outputs, ListTypes):
                for i, out in enumerate(outputs):
                    output = _process_output(out, name, location)
                    _outputs.append(output)
                    unnamed_outputs.append(output)
                    outputs_dict[i] = output

            elif NAMED_OUTPUTS_ENABLED and isinstance(outputs, dict):
                # named outputs
                for k, v in outputs.items():
                    output = _process_output(v, name, location)
                    _outputs.append(output)
                    outputs_dict[k] = output
            else:
                raise PythonScriptError(
                    f"Invalid outputs type {type(outputs)}. Should be a list.", location
                )

        if TARGET_PATH_ENABLED is False and path is not None:
            raise PythonScriptError(
                "Setting path is not allowed (by flag). TARGET_PATH_ENABLED",
                getattr(path, "location", location)
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
        trace("Registered target %s in makexfile %s. %s ", target.name, self.makex_file, location)
        return None


class MakexFile:
    # to the makefile
    path: Path

    targets: dict[str, TargetObject]

    macros: dict[str, Callable]

    code: Optional[types.CodeType] = None

    def __init__(self, ctx, path: Path, targets=None, variables=None, checksum: str = None):
        self.ctx = ctx
        self.path = path
        self.directory = path.parent
        self.targets = targets or {}
        self.variables = variables or []
        self.checksum = checksum
        self.environment_hash = None
        self.macros = {}

        # list of paths this MakexFile imports or includes.
        # TODO: Must be included in hash.
        self.includes: list[MakexFile] = []

    def hash_components(self):
        yield f"version:{VERSION}"
        yield f"environment:{self.environment_hash}"
        yield f"makex-file:{self.checksum}"
        for include in self.includes:
            yield f"environment:include:{include.environment_hash}"
            yield f"makex-file:include:{include.checksum}"

    def key(self):
        return str(self.path)

    @classmethod
    def preparse(cls, ctx: Context, path: Path, workspace: Workspace, include_function) -> ast.AST:
        trace("PREPARSE %s", path)
        checksum = FileChecksum.create(path)
        checksum_str = str(checksum)
        makefile = cls(ctx, path, checksum=checksum_str)
        env = MakexFileScriptEnvironment(
            ctx,
            directory=path.parent,
            path=path,
            makex_file=makefile,
            targets=makefile.targets,
            macros=makefile.macros,
            workspace=workspace,
            include_function=include_function
        )

        _globals = {}

        # add environment variables to makefiles as variables
        if ENVIRONMENT_VARIABLES_IN_GLOBALS_ENABLED:
            _globals.update(ctx.environment)

        posix_path = path.as_posix()
        include_processor = ProcessIncludes(posix_path)

        script = PythonScriptFile(
            path, _globals, extra_visitors=[TransformGetItem(posix_path), include_processor]
        )
        script.set_disabled_assignment_names(DISABLE_ASSIGNMENT_NAMES)

        with path.open("rb") as f:
            return script.parse(f)

    @classmethod
    def execute(
        cls,
        ctx: Context,
        path: Path,
        workspace: Workspace,
        node: ast.AST,
        include_function,
        globals=None,
        importer=None
    ) -> "MakexFile":
        pass

    @classmethod
    def parse(
        cls,
        ctx: Context,
        path: Path,
        workspace: Workspace,
        include_function,
        globals=None,
        importer=None
    ) -> "MakexFile":
        """

        Globals may be passed in for uses such as include(). Globals dictionary shall contain task() and other defined functions.
        When task is called in an included file, the task should register the including file. It's hacky, but it works.

        :param ctx:
        :param path:
        :param workspace:
        :param include_function:
        :param globals:
        :param importer:
        :return:
        """
        debug("Started parsing makefile %s ...", path)

        checksum = FileChecksum.create(path)
        checksum_str = str(checksum)

        # TODO: this needs to be refactored. we should create the makefile last.
        makefile = cls(ctx, path, checksum=checksum_str)

        env = MakexFileScriptEnvironment(
            ctx,
            directory=path.parent,
            path=path,
            makex_file=makefile,
            targets=makefile.targets,
            macros=makefile.macros,
            workspace=workspace,
            include_function=include_function
        )

        # reuse the globals, except for the one that defines a macro
        # we want the target() and path() functions to work as they would in the includer.
        # path should resolve relative to includer
        # target() should be registered in includer

        if globals:
            _globals = {"FILE": path, **env.globals(), **globals}
        else:
            _globals = {"FILE": path, **env.globals()}

        # force the use of the local environments macro decorator, ignoring anything passed in
        _globals[_MACRO_DECORATOR_NAME] = env._decorator_macro

        #debug("Globals before parse %s %s", path, _globals)

        # add environment variables to makefiles as variables
        if ENVIRONMENT_VARIABLES_IN_GLOBALS_ENABLED:
            _globals.update(ctx.environment)

        posix_path = path.as_posix()
        if INCLUDE_ENABLED:
            include_processor = ProcessIncludes(posix_path)
        else:
            include_processor = None

        script = PythonScriptFile(
            path,
            _globals,
            importer=importer,
            pre_visitors=[include_processor] if INCLUDE_ENABLED else [],
            extra_visitors=[TransformGetItem(posix_path)],
            enable_imports=IMPORT_ENABLED,
        )
        script.set_disabled_assignment_names(DISABLE_ASSIGNMENT_NAMES)

        # TODO: parse the file, find any includes, parse those and insert their asts before we execute.
        with path.open("rb") as f:
            tree = script.parse(f)

        if False and INCLUDE_ENABLED:
            asts = []
            for search_path, location in include_processor.includes_seen:
                trace("AST INCLUDE: %s", search_path)
                asts += include_function(
                    ctx, workspace, path.parent, search_path, location, search=True
                )

            InsertAST(path, asts).visit(tree)

        makefile.macros = env.macros

        # store a code object so we can reuse it
        makefile.code = script.execute(tree)

        makefile.includes.extend(env.includes)

        if HASH_USED_ENVIRONMENT_VARIABLES:
            # hash the environment variable usages so targets change when they change.
            usages = env.environment._usages()
            if usages:
                makefile.environment_hash = target_hash(
                    "".join(f"{k}={v}" for k, v in sorted(usages.items()))
                )

        debug(
            "Finished parsing makefile %s: Macros: %s | Targets: %s",
            path,
            makefile.macros.keys(),
            _globals[TARGETS_MODULE_VARIABLE].keys()
        )
        makefile.targets = _globals[TARGETS_MODULE_VARIABLE]
        return makefile

    def __repr__(self):
        return self.key()
