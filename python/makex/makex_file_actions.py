import logging
import os
import shlex
import shutil
import tarfile
import typing
import zipfile
from abc import (
    ABC,
    abstractmethod,
)
from dataclasses import dataclass
from itertools import chain
from os import remove as os_remove
from os.path import join
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Literal,
    Optional,
    Pattern,
    TypedDict,
    Union,
)

from makex._logging import (
    debug,
    error,
    trace,
)
from makex.constants import IGNORE_NONE_VALUES_IN_LISTS
from makex.context import Context
from makex.errors import ExecutionError
from makex.flags import (
    ABSOLUTE_PATHS_ENABLED,
    GLOBS_IN_ACTIONS_ENABLED,
    SHELL_USES_RETURN_CODE_OF_LINE,
)
from makex.makex_file_paths import (
    _resolve_task_self_path,
    join_string,
    parse_possible_task_reference,
    resolve_find_files,
    resolve_glob,
    resolve_path_element_workspace,
    resolve_pathlike,
    resolve_pathlike_list,
    resolve_string_path_workspace,
    resolve_task_path,
)
from makex.makex_file_types import (
    AllPathLike,
    Expansion,
    FindFiles,
    Glob,
    ListTypes,
    MultiplePathLike,
    PathElement,
    PathLikeTypes,
    TaskPath,
    TaskReferenceElement,
    TaskSelfInput,
    TaskSelfName,
    TaskSelfOutput,
    TaskSelfPath,
)
from makex.patterns import (
    combine_patterns,
    make_glob_pattern,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
    WorkspaceProtocol,
)
from makex.python_script import (
    FILE_LOCATION_ARGUMENT_NAME,
    FileLocation,
    JoinedString,
    ListValue,
    PythonScriptError,
    StringValue,
    get_location,
)
from makex.run import run
from makex.target import (
    ArgumentData,
    EvaluatedTask,
)

MISSING = object()


class InternalActionBase(ABC):
    location: FileLocation = None

    implicit_requirements: Optional[list[Union[StringValue, TaskReferenceElement]]] = None

    # TODO: add/collect requirements as we go
    def add_requirement(self, requirement: "TaskReferenceElement"):
        raise NotImplementedError

    def get_implicit_requirements(self, ctx: Context) -> Optional[Iterable[TaskReferenceElement]]:
        """
        Return a list of any target requirements in the action/arguments. Done before argument transformation.

        Any TargetReference or Path used by the target should be returned (except one for the Target itself).

        Used to detect implicit target requirements.
        
        We want to add any targets referenced in steps/task properties, so we can handle/parse them early.
        :return:
        """
        return None

    @abstractmethod
    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        # transform the input arguments (stored in instances), to a dictionary of actual values
        # keys must match argument keyword names
        raise NotImplementedError

    #implement this with transform_arguments() to get new functionality
    @abstractmethod
    def run_with_arguments(
        self, ctx: Context, target: EvaluatedTask, arguments: ArgumentData
    ) -> CommandOutput:
        raise NotImplementedError

    @abstractmethod
    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # produce a hash of the Action with the given arguments and functions
        raise NotImplementedError

    def __str__(self):
        return PythonScriptError("Converting Action to string not allowed.", self.location)


def _string_value_maybe_expand_user(ctx, base, value: StringValue) -> str:
    val = value.value

    if False:
        if val.startswith("~"):
            # TODO: use environment HOME to expand the user
            return Path(val).expanduser().as_posix()
        else:
            return value
    return val


def _resolve_string_argument(
    ctx: Context,
    target: EvaluatedTask,
    base: Path,
    value: PathLikeTypes,
) -> Optional[str]:
    if isinstance(value, StringValue):
        # XXX: we're not using our function here because we may not want to expand ~ arguments the way bash does
        # bash will replace a ~ wherever it is on the command line
        # TODO: remove this, we don't expand arguments implicitly anymore
        return _string_value_maybe_expand_user(ctx, base, value)
    elif isinstance(value, JoinedString):
        return join_string(ctx, target, base, value)
    elif isinstance(value, TaskPath):
        return resolve_task_path(ctx, value).as_posix()
    elif isinstance(value, TaskSelfPath):
        return _resolve_task_self_path(ctx, target, value).as_posix()
        #return target.path.as_posix()
    elif isinstance(value, PathElement):
        source = resolve_path_element_workspace(ctx, target.workspace, value, base)
        # source = _path_element_to_path(base, value)
        return source.as_posix()
    elif isinstance(value, Expansion):
        return str(value)
    #elif isinstance(value, (tuple, ListValue, list)):  #
    #    yield from resolve_string_argument_list(ctx, target, base, name, value)
    elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
        return None
    else:
        raise PythonScriptError(
            message=f"Invalid value. Expected String-like. Got {type(value)}.",
            location=get_location(value, target.location)
        )


def resolve_string_argument_list(
    ctx: Context,
    target: EvaluatedTask,
    base: Path,
    name: str,
    values: Iterable[AllPathLike],
) -> Iterable[str]:
    # Used to resolve arguments for an execute command, which must all be strings.
    for value in values:
        if isinstance(value, StringValue):
            # XXX: we're not using our function here because we may not want to expand ~ arguments the way bash does
            # bash will replace a ~ wherever it is on the command line
            # TODO: remove this, we don't expand arguments implicitly anymore
            yield _string_value_maybe_expand_user(ctx, base, value)
        elif isinstance(value, JoinedString):
            yield join_string(ctx, target, base, value)
        elif isinstance(value, TaskPath):
            yield resolve_task_path(ctx, value).as_posix()
        elif isinstance(value, TaskSelfPath):
            yield _resolve_task_self_path(ctx, target, value).as_posix()
        elif isinstance(value, TaskSelfOutput):
            output = target.output_dict.get(value.name_or_index, MISSING)
            if output is MISSING:
                raise PythonScriptError(
                    f"Undefined output name: {value.name_or_index}", value.location
                )

            output = [file.path for file in output]
        elif isinstance(value, TaskSelfInput):
            input = target.inputs_mapping.get(value.name_or_index, MISSING)
            if input is MISSING:
                raise PythonScriptError(
                    f"Undefined input name: {value.name_or_index}", value.location
                )

            yield from [path.as_posix() for path in input]
        elif isinstance(value, PathElement):
            source = resolve_path_element_workspace(ctx, target.workspace, value, base)
            #source = _path_element_to_path(base, value)
            yield source.as_posix()
        elif isinstance(value, Glob):
            if not GLOBS_IN_ACTIONS_ENABLED:
                raise ExecutionError("glob() can't be used in actions.", target, value.location)

            # todo: use glob cache from ctx for multiples of the same glob during a run
            #ignore = {ctx.output_folder_name}
            yield from (
                v.as_posix() for v in resolve_glob(ctx, target, base, value) #, ignore_names=ignore)
            )
        elif isinstance(value, Expansion):
            yield str(value)
        elif isinstance(value, (tuple, ListValue, list)): #
            yield from resolve_string_argument_list(ctx, target, base, name, value)
        elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
            continue
        else:
            raise PythonScriptError(
                message=f"Invalid value. Expected String-like. Got {type(value)}.",
                location=get_location(value, target.location)
            )


def _resolve_executable_name(ctx: Context, target, base: Path, value: StringValue) -> Path:
    if isinstance(value, StringValue):
        return _resolve_executable(ctx, target, value, base)
    elif isinstance(value, TaskReferenceElement):
        _path = value.path

        if _path is None:
            # Handle Executables in same file
            _path = target.makex_file_path
        else:
            _path = resolve_string_path_workspace(
                ctx, target.workspace, StringValue(value.path, value.location), base
            )

        trace("Resolve path %s -> %s", value, _path)

        # TODO: we're using the wrong graph here for this, but it can work.
        _ref_task = ctx.graph.get_task_for_path(_path, value.name)
        if not _ref_task:
            # TODO: if implicit and missing from the task warn the user about missing from the task requirements list.
            raise PythonScriptError(
                f"Error resolving executable to task output. Can't find task {value} in graph. May be missing from task requirements list. {list(ctx.graph.targets.keys())}",
                value.location
            )

        # TODO: improve the validation here
        trace("Resolved executable to task output %r -> %r", _ref_task, _ref_task.outputs[0])
        return _ref_task.outputs[0].path
    elif isinstance(value, PathElement):
        _path = resolve_path_element_workspace(ctx, target.workspace, value, base)
        return _path
    elif isinstance(value, TaskPath):
        return resolve_task_path(ctx, value)
    else:
        raise PythonScriptError(
            message=f"Invalid executable name. Got {type(value)}.",
            location=get_location(value, target.location)
        )


def _resolve_executable(
    ctx: Context,
    target,
    name: StringValue,
    base: Path,
    path_string: Optional[str] = None,
) -> Path:
    if name.find("/") >= 0:
        # path has a slash. resolve using a different algo. search within the workspace if necessary.
        _path = resolve_string_path_workspace(ctx, target.workspace, name, base)
        if _path.exists() is False:
            raise ExecutionError(
                f"Could not find the executable for {name}. Please install whatever it "
                f"is that provides the command {name!r}.",
                target
            )
        return _path

    # XXX: prepend the current folder to the path so executables are found next to the makex file.
    path_string = ctx.environment.get("PATH", "")
    if not path_string:
        path_string = str(base)
    else:
        path_string = f"{base}:{path_string}"

    _path = shutil.which(name, path=path_string)

    if _path is None:
        error("Which could not find the executable for %r: PATH=%s", name, path_string)
        raise ExecutionError(
            f"Could not find the executable for {name}. Please install whatever it "
            f"is that provides the command {name!r}, or modify your PATH environment variable "
            f"to include the path to the {name!r} executable.",
            target
        )

    return Path(_path)


@dataclass
class Execute(InternalActionBase):
    NAME = "execute"

    executable: Union[PathLikeTypes, "TaskReferenceElement"]

    arguments: tuple[Union[AllPathLike, list[AllPathLike]]]
    environment: dict[str, str]

    location: FileLocation

    #_redirect_output: PathLikeTypes = None

    @classmethod
    def build(
        cls,
        executable: Union[PathLikeTypes, "TaskReferenceElement"],
        arguments: tuple[Union[AllPathLike, list[AllPathLike]]],
        environment: dict[str, Any],
        location: FileLocation,
    ):

        if isinstance(executable, StringValue):
            executable = parse_possible_task_reference(executable)

        return cls(
            executable=executable,
            arguments=arguments,
            environment=environment,
            location=location,
        )

    def get_implicit_requirements(
        self,
        ctx: Context,
    ) -> Optional[Iterable[TaskReferenceElement]]:
        if isinstance(self.executable, TaskReferenceElement):
            yield self.executable

        for argument in self.arguments:
            if isinstance(argument, TaskPath) and argument.reference:
                yield argument.reference
            # TODO: handle joined string

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        args: dict[str, Any] = {}
        args["arguments"] = arguments = []
        target_input = target.input_path

        # TODO: replace with resolve_string_argument_list
        for argument in self.arguments:
            if isinstance(argument, StringValue):
                arguments.append(argument)
            elif isinstance(argument, JoinedString):
                arguments.append(join_string(ctx, task=target, base=target_input, string=argument))
            elif isinstance(argument, PathElement):
                arguments.append(resolve_pathlike(ctx, target, target_input, argument).as_posix())
            elif isinstance(argument, Expansion):
                arguments.append(str(argument.expand(ctx)))
            elif isinstance(argument, TaskPath):
                arguments.append(resolve_task_path(ctx, argument).as_posix())
            elif isinstance(argument, TaskSelfInput):
                input = target.inputs_mapping.get(argument.name_or_index, MISSING)
                if input is MISSING:
                    raise PythonScriptError(
                        f"Undefined input name: {argument.name_or_index}", argument.location
                    )

                input = [path.as_posix() for path in input]
                arguments.extend(input)
            elif isinstance(argument, TaskSelfOutput):
                output = target.output_dict.get(argument.name_or_index, MISSING)
                if output is MISSING:
                    raise PythonScriptError(
                        f"Undefined output name: {argument.name_or_index}", argument.location
                    )

                output = [file.path.as_posix() for file in output]
                arguments.extend(output)
            elif isinstance(argument, TaskSelfName):
                arguments.append(target.name)
            elif isinstance(argument, TaskSelfPath):
                arguments.append(_resolve_task_self_path(ctx, target, argument).as_posix())
            elif isinstance(argument, tuple):
                arguments.extend(
                    resolve_string_argument_list(ctx, target, target_input, target.name, argument)
                )
            elif isinstance(argument, ListTypes):
                arguments.extend(
                    resolve_string_argument_list(ctx, target, target_input, target.name, argument)
                )
            elif argument is None:
                # XXX: Ignore None arguments as they may be the result of a condition.
                continue
            else:
                raise PythonScriptError(
                    f"Invalid argument type: {type(argument)}: {argument!r}", target.location
                )

        # Resolve the executable name. May use the graph to get a target by path
        executable = _resolve_executable_name(ctx, target, target_input, self.executable)
        args["executable"] = executable.as_posix()
        return ArgumentData(arguments=args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
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
            output.name = executable
            return output
        except Exception as e:
            raise ExecutionError(e, target, location=self.location) from e

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        _arguments = arguments.get("arguments")
        _executable = arguments.get("executable")

        return hash_function("|".join([_executable] + _arguments))


class Shell(InternalActionBase):
    NAME = "shell"

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

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        args = {}
        target_input = target.input_path

        _list = []
        for part in self.string:
            if isinstance(part, StringValue):
                _list.append(part)
            elif isinstance(part, JoinedString):
                _list.append(join_string(ctx, task=target, base=target_input, string=part))
            else:
                raise PythonScriptError(
                    f"Invalid argument to shell. Expected String. Got {type(part)}", self.location
                )

        # TODO: validate string type
        args["string"] = _list
        args["preamble"] = self.preamble

        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        string = arguments.get("string")
        preamble = arguments.get("preamble")

        if not string:
            return CommandOutput(0)

        s_print = "\n".join([f"# {s}" for s in chain(preamble.split("\n"), string)])

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
    """
    Copies files/folders.

    #  copy(items) will always use the file/folder name in the items list
    #  copy(file)
    #  copy(files)
    #  copy(folder)
    #  copy(folders)
    # with destination:
    #  copy(file, folder) copy a file to specified folder.
    #  copy(files, folder) copies a set of files to the specified folder.
    #  copy(folder, folder) copy a folder to the inside of specified folder.
    #  copy(folders, folder) copies a set of folders to the specified folder..

    file or files may be one or more task locators (or references); in which all the output files from
    those tasks will be copied.

    TODO: handle copying specific named outputs of a task.

    # TODO: rename argument?
    """
    NAME = "copy"
    source: list[AllPathLike]
    destination: PathLikeTypes
    exclude: list[AllPathLike]
    name: StringValue
    location: FileLocation
    destination_is_subdirectory: bool = False

    @classmethod
    def build(cls, source, destination, exclude=None, name=None, location=None):
        # find/parse any target references early
        _source = list(cls._process_source(source))

        return cls(
            source=_source,
            destination=destination,
            exclude=exclude,
            name=name,
            location=location,
        )

    @classmethod
    def _process_source(cls, source: Union[PathLikeTypes]):
        # find/parse any target references early
        if isinstance(source, StringValue):
            yield parse_possible_task_reference(source)
        elif isinstance(source, ListTypes):
            for item in source:
                yield from cls._process_source(item)
        else:
            # TODO: check if actually one of the other pathlike types
            yield source

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function):
        # checksum all the sources
        sources = arguments.get("sources")

        # hash the destination name
        destination = arguments.get("destination")

        exclusions: Optional[Pattern] = arguments.get("exclude", None)

        parts = []
        for source in sources:
            parts.append(hash_function(source.as_posix()))

        if destination is not None:
            parts.append(hash_function(destination.as_posix()))

        if exclusions:
            parts.append(hash_function(exclusions.pattern))

        return hash_function("|".join(parts))

    def get_implicit_requirements(self, ctx: Context) -> Optional[Iterable[TaskReferenceElement]]:
        if isinstance(self.source, ListTypes):
            for source in self.source:
                if isinstance(source, TaskPath):
                    yield source.reference
        else:
            if isinstance(self.source, TaskPath):
                yield self.source.reference

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        sources = list(
            resolve_pathlike_list(
                ctx=ctx, task=target, base=target.input_path, name="source", values=self.source
            )
        )

        if self.name and len(sources) > 1:
            raise PythonScriptError(
                "Can't use name argument with more than one source.", self.location
            )

        if self.destination:
            if not isinstance(self.destination, (str, TaskPath, PathElement, TaskSelfOutput)):
                raise PythonScriptError(
                    message=f"Destination must be a string or path. Got a {type(self.destination)}.",
                    location=getattr(self.destination, FILE_LOCATION_ARGUMENT_NAME, self.location),
                )

            if isinstance(self.destination, str):
                if "/" in self.destination:
                    self.destination_is_subdirectory = True

            destination = resolve_pathlike(
                ctx=ctx, target=target, base=target.path, value=self.destination
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
                        "Expected list or glob for ignores.", get_location(string, target.location)
                    )
                excludes.append(make_glob_pattern(string.pattern))

            excludes = combine_patterns(excludes)

        return ArgumentData(
            {
                "sources": sources,
                "destination": destination,
                "excludes": excludes,
                "name": self.name
            }
        )

    def run_with_arguments(
        self, ctx: Context, target: EvaluatedTask, arguments: ArgumentData
    ) -> CommandOutput:
        sources = arguments.get("sources")
        destination: Path = arguments.get("destination")
        excludes: Pattern = arguments.get("excludes")

        destination_specified = destination is not None
        if destination_specified is False:
            destination = target.path

        copy_file = ctx.copy_file_function

        if destination.exists() is False:
            debug("Create destination %s", destination)
            if ctx.dry_run is False:
                destination.mkdir(parents=True)

        length = len(sources)
        if length == 0:
            ctx.ui.print(f"No files to copy.")

            trace(f"Not copying any files because none were evaluated.")
            return CommandOutput(0)

        elif length == 1:

            ctx.ui.print(f"Copying to {destination} ({sources[0]})")
            trace(f"Copying to {destination} ({sources[0]})")
        else:
            ctx.ui.print(f"Copying to {destination} ({length} items)")
            trace(f"Copying to {destination} ({length} items)")

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

        name = arguments.get("name", None)

        for source in sources:
            if not source.exists():
                raise ExecutionError(
                    f"Missing source file {source} in copy list",
                    target,
                    get_location(source, target.location)
                )

            if ignore_pattern.match(source.as_posix()):
                trace("File copy ignored %s", source)
                continue

            source_is_dir = source.is_dir()
            _destination = destination / source.name if name is None else destination / name

            if source_is_dir:
                # copy(folder)
                # copy(folders)
                # copy(folder, folder)
                # copy(folders, folder)

                debug("Copy tree %s <- %s", _destination, source)

                if ctx.dry_run is False:
                    try:
                        # copy recursive
                        shutil.copytree(
                            source,
                            _destination,
                            dirs_exist_ok=True,
                            copy_function=copy_file,
                            ignore=_ignore_function,
                            symlinks=True,
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
                # copy(file)
                # copy(files)
                # copy(file, folder)
                # copy(files, folder)
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
class Mirror(InternalActionBase):
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

        mirror(file, file): mirror a file into output with a new name
        mirror(folder, folder): mirror a folder into output with a new name

        mirror(file): mirror a file into output (redundant with copy)
        mirror(folder): mirror a folder into output (redundant with copy)

        mirror(files, folder): mirror files into folder (redundant with copy)
        mirror(folders, folder): mirror folders into folder (redundant with copy)
    """
    NAME = "mirror"
    source: Union[list[AllPathLike], AllPathLike]
    destination: PathLikeTypes
    exclude: list[MultiplePathLike]
    location: FileLocation

    # change how symbolic links are handled.
    # copy to copy the files pointed to by the symlink
    # link to link to the files pointed by the symlink
    symlinks: Literal["copy", "link"] = "copy"

    class Arguments(TypedDict):
        sources: list[Path]
        destination: Path

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
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
                task=target,
                base=target.input_path,
                name="source",
                values=_source_list,
                glob=GLOBS_IN_ACTIONS_ENABLED
            )
        )
        #trace("Mirror sources %s", sources)

        if self.destination:
            destination = resolve_pathlike(
                ctx=ctx, target=target, base=target.path, value=self.destination
            )
        else:
            destination = target.path

        args["destination"] = destination
        args["symlinks"] = self.symlinks

        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        sources: list[Path] = arguments.get("sources")
        destination: Path = arguments.get("destination")
        symlinks: Path = arguments.get("symlinks")

        ignore = file_ignore_function(ctx.output_folder_name)

        if ctx.dry_run is False:
            destination.mkdir(parents=True, exist_ok=True)

        copy_file = ctx.copy_file_function

        debug("Mirror to destination: %s", destination)

        length = len(sources)

        if length > 1:
            ctx.ui.print(f"Synchronizing to {destination} ({length} items)")
        else:
            ctx.ui.print(f"Synchronizing to {destination} ({sources[0]})")

        for source in sources:
            #trace("Mirror source to destination: %s: %s", source, destination)
            if not source.exists():
                raise ExecutionError(
                    f"Missing source/input file {source} in sync()", target, location=self.location
                )

            if source.is_dir():
                source_base = source
            else:
                source_base = source.parent

            # Fix up destination; source relative should match destination relative.
            if source_base.is_relative_to(target.input_path):
                _destination = destination / source_base.relative_to(target.input_path)

                if ctx.dry_run is False:
                    _destination.mkdir(parents=True, exist_ok=True)
            else:
                _destination = destination

            if source.is_dir():
                # copy recursive
                trace("Copy tree %s <- %s", _destination, source)
                if ctx.dry_run:
                    continue

                try:
                    shutil.copytree(
                        source,
                        _destination,
                        copy_function=copy_file,
                        dirs_exist_ok=True,
                        ignore=ignore,
                        symlinks=True,
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
                trace("Copy file %s <- %s", _destination / source.name, source)
                if ctx.dry_run:
                    continue

                #shutil.copy(source, _destination / source.name)
                try:
                    copy_file(source.as_posix(), _destination.as_posix())
                except (OSError, shutil.Error) as e:
                    raise ExecutionError(
                        f"Error copying file {source} to {_destination}: {e}",
                        target,
                        target.location
                    ) from e

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [self.__class__.__name__, arguments.get("destination").as_posix()]
        parts.extend([a.as_posix() for a in arguments.get("sources")])

        return hash_function("|".join(parts))


@dataclass
class Print(InternalActionBase):
    NAME = "print"
    messages: list[Union[StringValue, JoinedString]]

    def __init__(self, messages, location):
        self.messages = messages
        self.location = location

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        for message in arguments.get("strings", []):
            print(message)

        return CommandOutput(0)

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:

        strings = []
        for string in self.messages:
            value = _resolve_string_argument(ctx, target, target.input_path, string)
            if value is None:
                continue
            strings.append(value)

        return ArgumentData({
            "strings": strings,
        })

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # this hash doesn't matter; doesn't affect output
        return ""


@dataclass
class Write(InternalActionBase):
    """
        Writes data to a file.

        write(file, *data)

        Data may be a string, path or other encodable object, or a list of them. None values are skipped.

        Amalgamations can be made by passing a path to a file:

        write("file.cpp", "\n// begin file\n", path(), "\n// end file\n")

        TODO: support file paths and variable argument lists of items.
    """
    NAME = "write"
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

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        args = {}
        args["path"] = path = resolve_pathlike(ctx, target, base=target.path, value=self.path)

        data = self.data
        if isinstance(data, StringValue):
            data = data.value
        elif isinstance(data, JoinedString):
            data = join_string(ctx, task=target, base=target.path, string=data).value
        elif data is None:
            data = ""
        else:
            raise ExecutionError(
                f"Invalid argument text argument to write(). Got {data!r} {type(data)}. Expected string.",
                target,
                location=get_location(data, target.location)
            )

        args["data"] = data
        args["executable"] = self.executable
        return ArgumentData(args, inputs=[path])

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
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
                try:
                    path.write_text(data)
                except IsADirectoryError as e:
                    raise ExecutionError(
                        f"Invalid argument path argument to write(): Is a folder: {path}",
                        target,
                        location=target.location,
                    )
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
    NAME = "environment"
    environment: dict[StringValue, Union[StringValue, PathLikeTypes]]

    def __init__(self, environment: dict, location: FileLocation):
        self.environment = environment
        self.location = location

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        env = {}

        # transform all values to strings.
        for k, v in self.environment.items():
            if isinstance(v, StringValue):
                value = v.value
            elif isinstance(v, PathElement):
                value = resolve_path_element_workspace(ctx, target.workspace, v, target.input_path)
                value = value.as_posix()
            elif isinstance(v, TaskPath):
                value = resolve_task_path(ctx, v).as_posix()
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

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        env = arguments.get("environment", {})
        ctx.environment.update(env)
        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        environment = arguments.get("environment")
        environment_string = ";".join(f"{k}={v}" for k, v in environment.items())
        return hash_function(environment_string)


_SUFFIX_ZIP = (".zip", )
_SUFFIX_TAR_GZ = (".tar", ".gz")
_SUFFIX_TAR = (".tar", )
_ARCHIVE_TYPES: dict[tuple[str, ...], str] = {
    _SUFFIX_TAR: "tar",
    _SUFFIX_TAR_GZ: "tar.gz",
    _SUFFIX_ZIP: "zip",
}


class Archive(InternalActionBase):
    """
    archive(
        path=task_path("rpm") / "SOURCES/makex-source.zip",
        path="makex.tar",
        type=None, # automatically inferred from extension

        # TODO: can we resolve these roots automatically?
        root=".",

        # list of files to add to the archive.
        files=[
            find()
        ]
    ),
    """
    NAME = "archive"

    # Destination where to store the archive. can be anywhere, but typically a task's output folder
    path: PathLikeTypes

    # automatically inferred from path.
    type: typing.Literal["zip", "tar.gz", "tar"]

    # Base/root path which all items should be relative to. Defaults to the containing tasks output path.
    # If archiving the outputs from a referenced tasks outputs, the root should be that tasks cache/output path (one must use `task_path()`).
    # This path prefix will be stripped from all files added to the archive.
    root: PathLikeTypes

    # unused. intended to prefix the items in the archive.
    prefix: PathLikeTypes

    # unused
    options: dict

    # the list of files to archive
    # one may use the find function to find files somewhere else.
    # one may use the glob function to find files within the tasks output.
    files: list[AllPathLike]

    location: FileLocation

    def __init__(
        self,
        path: PathLikeTypes,
        root,
        type,
        options,
        files,
        prefix=None,
        location: FileLocation = None
    ):
        self.path = path
        self.root = root
        self.type = type
        self.options = options
        self.files = files
        self.prefix = prefix
        self.location = location

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        # TODO: resolve a list of files AND which task "roots" they came from.
        #  if a file came from a specific task root, use that to make the file relative in the archive.
        #  otherwise, use self.root to rename archive files.
        files = list(
            resolve_pathlike_list(
                ctx=ctx, task=target, base=target.cache_path, name="files", values=self.files or []
            )
        )

        if not self.path:
            raise PythonScriptError(
                "Path argument to archive() missing. Must be the name/path of the archive file.",
                location=self.location
            )
        #try:
        path = resolve_pathlike(ctx, target, target.cache_path, self.path, location=self.location)
        #except PythonScriptError as e:
        #    raise PythonScriptError(
        #        f"Invalid argument to archive.path. Should be a path, got a {type(self.path)}",
        #        location=target.location or self.location,
        #    )
        logging.debug("Resolve path: %s", path)
        if self.root:
            root = resolve_pathlike(
                ctx, target, target.cache_path, self.root, location=self.location
            )
        else:
            root = target.cache_path

        logging.debug("Resolve root %s", root)
        options = self.options
        _type = self.type

        logging.debug("Detect archive type %s %s", path.suffixes, path.suffixes == [".tar", ".gz"])
        if self.type is None:
            suffixes = tuple(path.suffixes)
            _type = _ARCHIVE_TYPES.get(suffixes, None)
            if _type is None:
                raise PythonScriptError(
                    f"Could not detect archive type from filename {suffixes!r}. Specify type=zip|tar.gz|tar",
                    self.path.location or self.location
                )

        return ArgumentData(
            {
                "path": path,
                "type": _type,
                "prefix": self.prefix,
                "root": root,
                "options": options,
                "files": files,
            }
        )

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        type = arguments.get("type")

        logging.debug("Creating archive...")
        if type == "zip":
            return self._run_zip(ctx, target, arguments=arguments)
        elif type == "tar.gz":
            return self._run_tar_compress(
                ctx,
                target,
                compression="gz",
                arguments=arguments,
            )
        elif type == "tar":
            return self._run_tar(ctx, target, arguments=arguments)
        else:
            raise NotImplementedError(type)

    def scantree(self, path):
        for entry in os.scandir(path):
            if entry.is_dir(follow_symlinks=False):
                yield from self.scantree(entry.path)
            else:
                yield entry

    def _run_zip(self, ctx, target, arguments) -> CommandOutput:
        path = arguments.get("path")
        root = arguments.get("root")
        prefix = arguments.get("prefix")
        if prefix:
            prefix = Path(prefix)

        zipobj = zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED)
        files: list[Path] = arguments.get("files")

        for file in files:

            if file.is_relative_to(root):
                is_relative = True
                file_relative = file.relative_to(root)
            else:
                is_relative = False
                file_relative = file

            if file.is_dir():
                for direntry in self.scantree(file):
                    if is_relative:
                        arcpath = Path(direntry.path).relative_to(root)
                    else:
                        arcpath = direntry.path

                    if prefix:
                        arcpath = prefix / arcpath

                    zipobj.write(direntry.path, arcpath)
            else:

                zipobj.write(file, file_relative)

        return CommandOutput(0)

    def _run_tar_compress(self, ctx, target, compression: Literal["gz", "bz2", "xz"], arguments):
        files: list[Path] = arguments.get("files")
        root = arguments.get("root")

        def reset(tarinfo):
            tarinfo.uid = tarinfo.gid = 0
            tarinfo.uname = tarinfo.gname = "root"
            return tarinfo

        path = arguments.get("path")
        debug("Writing tar file to %s", path)
        with tarfile.open(path, f"w:{compression}", format=tarfile.PAX_FORMAT) as tar:
            for file in files:
                # the name in the archive should always be relative so it may be extracted anywhere
                # ./{path}
                arcname = None
                if file.is_relative_to(root):
                    arcname = file.relative_to(root).as_posix()

                    trace("Make relative path %s to %s", arcname, file)
                    arcname = f"./{arcname}"

                trace("Adding file %s", file)
                tar.add(file, arcname=arcname, filter=reset) # , arcname=f"./{arcname}"

        return CommandOutput(0)

    def _run_tar(self, ctx, target, arguments):
        files: list[Path] = arguments.get("files")
        root = arguments.get("root")

        def reset(tarinfo):
            tarinfo.uid = tarinfo.gid = 0
            tarinfo.uname = tarinfo.gname = "root"
            return tarinfo

        path = arguments.get("path")
        debug("Writing tar file to %s", path)
        with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as tar:
            for file in files:
                # the name in the archive should always be relative so it may be extracted anywhere
                # ./{path}
                arcname = None
                if file.is_relative_to(root):

                    arcname = file.relative_to(root).as_posix()

                    trace("Make relative path %s to %s", arcname, file)
                    arcname = f"./{arcname}"

                trace("Adding file %s", file)
                tar.add(file, arcname=arcname, filter=reset) # , arcname=f"./{arcname}"

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [
            str(arguments.get("path")),
            arguments.get("type"),
            str(arguments.get("options")),
            str(arguments.get("root")),
            str(arguments.get("files"))
        ]
        string = "".join(parts)
        return hash_function(string)


@dataclass
class Erase(InternalActionBase):
    """
    Erases files in a task's output (and within a task's output only).
    """
    NAME = "erase"
    files: tuple[AllPathLike]
    location: FileLocation

    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        # XXX: we can't transform any globs here because other steps/actions/tasks may have not produced them yet.
        return ArgumentData({
            "files": self.files,
        })

    def _validate_path(
        self,
        parts: Union[list[StringValue], tuple[StringValue]],
        location: FileLocation,
        absolute=ABSOLUTE_PATHS_ENABLED,
    ):
        if ".." in parts:
            raise PythonScriptError("Relative path references not allowed in makex.", location)
        #if parts[0] == "/" and absolute is False:
        #    raise PythonScriptError("Absolute path references not allowed in makex.", location)
        return True

    def _resolve_path_element_workspace(
        self,
        ctx: Context,
        workspace: WorkspaceProtocol,
        element: PathElement,
        base: Path,
    ) -> Path:
        if element.resolved:
            path = element.resolved
        else:
            path = Path(*element.parts)

        self._validate_path(path.parts, element.location)

        if path.parts[0] == "//":
            #trace("Workspace path: %s %s", workspace, element)
            #if WORKSPACES_IN_PATHS_ENABLED:
            #    path = workspace.path / Path(*path.parts[1:])
            #else:
            raise PythonScriptError(
                "Workspaces markers // in paths not enabled here.", element.location
            )
        #elif not path.is_absolute():

        # always prefix path with the output/base
        path = base / path

        #trace("Resolve path element path %r:  %r (%r)", element, path, element.parts)

        return path

    def _resolve_string_path_workspace(
        self,
        ctx: Context,
        workspace: WorkspaceProtocol,
        element: StringValue,
        base: Path,
    ) -> Path:

        if element.value == ".":
            return base

        _path = path = Path(element.value)

        self._validate_path(path.parts, element.location)

        if path.parts[0] == "//":
            #trace("Resolve workspace path: %s %s", workspace, element)
            #if WORKSPACES_IN_PATHS_ENABLED:
            #    _path = workspace.path / Path(*path.parts[1:])
            #else:
            raise PythonScriptError("Workspaces markers // in paths not enabled.", element.location)
        #elif not path.is_absolute():
        # always prefix path with the output/base
        _path = base / path

        #trace("Resolve string path %s: %s", element, _path)

        return _path

    def _resolve_pathlike_list(
        self,
        ctx: Context,
        target: EvaluatedTask,
        base: Path,
        name: str,
        values: Iterable[Union[PathLikeTypes, MultiplePathLike]],
        glob=True,
    ) -> Iterable[Path]:
        # XXX: tweak resolve pathlike_list to always return paths prefixed with base
        for value in values:
            if isinstance(value, StringValue):
                yield self._resolve_string_path_workspace(ctx, target.workspace, value, base)
            elif isinstance(value, PathElement):
                source = self._resolve_path_element_workspace(ctx, target.workspace, value, base)
                yield source
            elif isinstance(value, Glob):
                if glob is False:
                    raise ExecutionError(
                        f"Globs are not allowed in the {name} property.", target, value.location
                    )
                # todo: use glob cache from ctx for multiples of the same glob during a run
                yield from resolve_glob(ctx, target, base, value)
            elif isinstance(value, FindFiles):
                # find(path, pattern, type=file|symlink)
                # TODO: clarify how find will be used here.
                if True:
                    raise NotImplementedError(
                        f"Invalid argument in pathlike list: {type(value)} {value!r}"
                    )
                else:
                    if value.path:
                        path = self._resolve_path_element_workspace(
                            ctx, target.workspace, value.path, base
                        )
                    else:
                        path = base
                    debug("Searching for files %s: %s", path, value.pattern)
                    yield from resolve_find_files(ctx, target, path, value.pattern)
            elif isinstance(value, TaskPath):
                # yield task paths as is
                yield resolve_task_path(ctx, value)
            elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
                continue
            else:
                #raise ExecutionError(f"{type(value)} {value!r}", target, get_location(value, target))
                raise NotImplementedError(
                    f"Invalid argument in pathlike list: {type(value)} {value!r}"
                )

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        # XXX: note: we're doing transformation of the erase list here because erase might have to work with files from previous actions.
        files = list(
            self._resolve_pathlike_list(
                ctx=ctx,
                target=target,
                name="files",
                base=target.cache_path,
                values=self.files or [],
            )
        )

        for file in files:
            if not file.is_relative_to(target.cache_path):
                debug("Skipping file not in task output: %s", file)
                continue

            debug("Erasing file %s", file)
            if file.is_dir():
                shutil.rmtree(file, ignore_errors=True)
            else:
                os_remove(file)

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [
            str(arguments.get("files")),
        ]
        string = "".join(parts)
        return hash_function(string)
