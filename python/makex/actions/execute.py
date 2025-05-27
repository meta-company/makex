import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Optional,
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
    GLOBS_IN_ACTIONS_ENABLED,
    MAKEX_SYNTAX_VERSION,
)
from makex.locators import format_locator
from makex.makex_file_actions import (
    InternalAction,
    string_value_maybe_expand_user,
)
from makex.makex_file_paths import (
    _resolve_task_outputs_reference,
    _resolve_task_self_path,
    join_string,
    parse_possible_task_reference,
    resolve_glob,
    resolve_path_element_workspace,
    resolve_pathlike,
    resolve_string_path_workspace,
    resolve_task_path,
)
from makex.makex_file_types import (
    AllPathLike,
    Expansion,
    Glob,
    ListTypes,
    PathElement,
    PathLikeTypes,
    TaskOutputsReference,
    TaskPath,
    TaskReferenceElement,
    TaskSelfInput,
    TaskSelfName,
    TaskSelfOutput,
    TaskSelfPath,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
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
    Task,
)


def resolve_string_argument_list(
    ctx: Context,
    target: Task,
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
            yield string_value_maybe_expand_user(ctx, base, value)
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


def _resolve_executable_name(
    ctx: Context,
    task: Task,
    base: Path,
    value: StringValue,
) -> Path:
    if isinstance(value, StringValue):
        return _resolve_executable(ctx, task, value, base)
    elif isinstance(value, JoinedString):
        string = join_string(ctx, task, base, value)
        return _resolve_executable(ctx, task, string, base)
    elif isinstance(value, TaskReferenceElement):

        _path = value.path

        if _path is None:
            # Handle Executables in same file
            _path = task.makex_file_path
        else:
            _path = resolve_string_path_workspace(
                ctx, task.workspace, StringValue(value.path, value.location), base
            )

        trace("Resolve path %s -> %s", value, _path)

        # if implicit is disabled, and the requirement missing from the task warn the user about missing from the task requirements list.
        if ctx.implicit_requirements is False:
            if task.has_requirement(value.name, _path) is False:
                locator = format_locator(value.name, _path, syntax=ctx.makex_syntax_version)
                raise PythonScriptError(
                    f'Requirement for executable `{locator}` is missing from the task\'s requirements list.\nHint: task(..., requires=["{locator}"], ...). {task.requires_original}',
                    value.location
                )

        # TODO: we're using the wrong graph here for this, but it can work.
        #_ref_task = ctx.graph.get_task_for_path(_path, value.name)
        _ref_task = ctx.graph_2.get_task2(value.name, _path)

        if not _ref_task:

            raise PythonScriptError(
                f"Error resolving executable to task output. Can't find task {value} in graph. May be missing from task requirements list. {list(ctx.graph.targets.keys())}",
                value.location
            )

        # TODO: improve the validation here
        trace("Resolved executable to task output %r -> %r", _ref_task, _ref_task.outputs[0])

        return _ref_task.outputs[0].path
    elif isinstance(value, (PathElement, TaskPath, TaskSelfPath)):
        return resolve_pathlike(ctx, task, base, value)
    else:
        raise PythonScriptError(
            message=f"Invalid executable name. Got {type(value)}.",
            location=get_location(value, task.location)
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
class Execute(InternalAction):
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
        syntax=MAKEX_SYNTAX_VERSION,
    ):

        if isinstance(executable, StringValue):
            executable = parse_possible_task_reference(executable, syntax=syntax)

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

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
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
            elif isinstance(argument, TaskOutputsReference):
                for item in _resolve_task_outputs_reference(ctx, target, argument):
                    arguments.append(item.as_posix())
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

        # Resolve the executable name. May use the graph to get a task by path
        executable = _resolve_executable_name(ctx, target, target_input, self.executable)
        args["executable"] = executable.as_posix()
        return ArgumentData(arguments=args)

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
        executable = arguments.get("executable")
        arguments = arguments.get("arguments")
        #executable = _resolve_executable(task, executable.as_posix())

        # verify the executable is executable
        # TODO: use a stat cache to reduce all the stats
        if os.access(executable, os.X_OK) is False:
            if not os.path.exists(executable):
                raise ExecutionError(
                    f"Executable '{executable}' does not exist",
                    target,
                    get_location(self.executable, self.location),
                )
            debug("Making file executable: %s", executable)
            _stat = os.stat(executable)
            os.chmod(executable, _stat.st_mode | stat.S_IEXEC)

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


MISSING = object()
