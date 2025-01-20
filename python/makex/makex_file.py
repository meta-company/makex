import ast
import logging
import re
import types
import typing
from dataclasses import dataclass
from io import StringIO
from itertools import chain
from os.path import expanduser
from pathlib import Path
from typing import (
    Any,
    Callable,
    Iterable,
    Optional,
    Protocol,
    TypedDict,
    Union,
)

from makex._logging import (
    debug,
    trace,
)
from makex.build_path import get_build_path
from makex.constants import (
    ENVIRONMENT_VARIABLES_IN_GLOBALS_ENABLED,
    HASH_USED_ENVIRONMENT_VARIABLES,
    OUTPUT_DIRECTLY_TO_CACHE,
)
from makex.context import Context
from makex.errors import (
    ErrorCategory,
    ErrorLevel,
    MakexError,
)
from makex.file_checksum import FileChecksum
from makex.flags import (
    ARCHIVE_FUNCTION_ENABLED,
    ERASE_FUNCTION_ENABLED,
    EXPAND_FUNCTION_ENABLED,
    FIND_FUNCTION_ENABLED,
    FIND_IN_INPUTS_ENABLED,
    GLOB_FUNCTION_ENABLED,
    GLOBS_IN_INPUTS_ENABLED,
    HOME_FUNCTION_ENABLED,
    IMPORT_ENABLED,
    INCLUDE_ENABLED,
    LATE_JOINED_STRINGS,
    NAMED_OUTPUTS_ENABLED,
    OPTIONAL_REQUIREMENTS_ENABLED,
    TARGET_PATH_ENABLED,
    TASK_SELF_ENABLED,
)
from makex.makex_file_actions import (
    Archive,
    Copy,
    Erase,
    Execute,
    InternalActionBase,
    Mirror,
    Print,
    SetEnvironment,
    Shell,
    Write,
)
from makex.makex_file_ast import (
    InsertAST,
    ProcessIncludes,
    TransformGetItem,
    TransformSelfReferences,
)
from makex.makex_file_paths import (
    create_build_path_object,
    join_string_nopath,
    parse_task_reference,
    resolve_path_element_workspace,
    resolve_path_parts_workspace,
    resolve_string_path_workspace,
)
from makex.makex_file_syntax import (
    _MACRO_DECORATOR_NAME,
    _TARGET_REFERENCE_NAME,
    MAKEX_FUNCTION_ARCHIVE,
    MAKEX_FUNCTION_COPY,
    MAKEX_FUNCTION_ENVIRONMENT,
    MAKEX_FUNCTION_ERASE,
    MAKEX_FUNCTION_EXECUTE,
    MAKEX_FUNCTION_EXPAND,
    MAKEX_FUNCTION_FIND,
    MAKEX_FUNCTION_GLOB,
    MAKEX_FUNCTION_HOME,
    MAKEX_FUNCTION_INCLUDE,
    MAKEX_FUNCTION_MIRROR,
    MAKEX_FUNCTION_PATH,
    MAKEX_FUNCTION_PRINT,
    MAKEX_FUNCTION_SHELL,
    MAKEX_FUNCTION_SOURCE,
    MAKEX_FUNCTION_TASK,
    MAKEX_FUNCTION_TASK_PATH,
    MAKEX_FUNCTION_TASK_SELF_INPUTS,
    MAKEX_FUNCTION_TASK_SELF_NAME,
    MAKEX_FUNCTION_TASK_SELF_OUTPUTS,
    MAKEX_FUNCTION_TASK_SELF_PATH,
    MAKEX_FUNCTION_WRITE,
)
from makex.makex_file_types import (
    AllPathLike,
    EnvironmentVariableProxy,
    Expansion,
    FindFiles,
    Glob,
    ListTypes,
    PathElement,
    PathLikeTypes,
    RegularExpression,
    ResolvedTaskReference,
    TaskPath,
    TaskReferenceElement,
    TaskSelfInput,
    TaskSelfName,
    TaskSelfOutput,
    TaskSelfPath,
)
from makex.protocols import (
    CommandOutput,
    MakexFileProtocol,
    TargetProtocol,
    WorkspaceProtocol,
)
from makex.python_script import (
    FILE_LOCATION_ARGUMENT_NAME,
    FileLocation,
    JoinedString,
    ListValue,
    PythonScriptError,
    PythonScriptFile,
    ScriptEnvironment,
    StringValue,
    get_location,
    wrap_script_function,
)
from makex.target import (
    ArgumentData,
    EvaluatedTask,
    format_hash_key,
    target_hash,
)
from makex.ui import pretty_file
from makex.version import VERSION

MAKEX_GLOBAL_TARGETS = "_TARGETS_"
MAKEX_GLOBAL_MACROS = "__macros__"
MAKEX_GLOBAL_MACRO_NAMES = "__macro_names__"

# Any official/private function names added to globals are here

# NOTE: Some of these names are names we have used or will use.
DISABLE_ASSIGNMENT_NAMES = {
    "action",
    "cache",
    "call",
    "decode",
    "default",
    "DEFAULT",
    "E",
    "encode",
    "ENVIRONMENT",
    "Environment",
    "environment",
    "executable",
    "FILE",
    "file",
    "FOLDER",
    "folder",
    "generate",
    "help",
    "input",
    "inputs",
    "label",
    "labels",
    "link",
    "load",
    "named",
    "optional",
    "output",
    "outputs",
    "overlay",
    "Path",
    "pattern",
    "reference",
    "Reference",
    "run",
    "self",
    "serialize",
    "source",
    "sync",
    "target",
    "Target",
    "Task",
    "task_self",
    "tool",
    "variable",
    "variables",
    "variant",
    "vary",
    "varys",
    "workspace",
    _MACRO_DECORATOR_NAME,
    _TARGET_REFERENCE_NAME,
    MAKEX_GLOBAL_MACRO_NAMES,
    MAKEX_GLOBAL_MACRO_NAMES,
    MAKEX_GLOBAL_MACROS,
    MAKEX_FUNCTION_ARCHIVE,
    MAKEX_FUNCTION_COPY,
    MAKEX_FUNCTION_ERASE,
    MAKEX_FUNCTION_ENVIRONMENT,
    MAKEX_FUNCTION_EXECUTE,
    MAKEX_FUNCTION_EXPAND,
    MAKEX_FUNCTION_FIND,
    MAKEX_FUNCTION_GLOB,
    MAKEX_FUNCTION_HOME,
    MAKEX_FUNCTION_INCLUDE,
    MAKEX_FUNCTION_MIRROR,
    MAKEX_FUNCTION_PATH,
    MAKEX_FUNCTION_PRINT,
    MAKEX_FUNCTION_SHELL,
    MAKEX_FUNCTION_SOURCE,
    MAKEX_FUNCTION_TASK,
    MAKEX_FUNCTION_TASK_PATH,
    MAKEX_FUNCTION_TASK_SELF_INPUTS,
    MAKEX_FUNCTION_TASK_SELF_NAME,
    MAKEX_FUNCTION_TASK_SELF_OUTPUTS,
    MAKEX_FUNCTION_TASK_SELF_PATH,
    MAKEX_FUNCTION_WRITE,
}

VALID_NAME_RE = r"^[a-zA-Z][a-zA-Z0-9\-_@\.]*"
VALID_NAME_PATTERN = re.compile(VALID_NAME_RE, re.U)


def _validate_task_name(name: StringValue, location: FileLocation):
    if not VALID_NAME_PATTERN.match(name):
        raise PythonScriptError(
            f"Task has an invalid name {name!r}. Must be {VALID_NAME_RE!r} (regular expression).",
            location
        )
    return True


def make_hash_from_dictionary(d: dict[str, str]):
    flatten = []
    for k, v in d.items():
        flatten.append(k)
        if isinstance(v, list):
            flatten.extend(v)
        else:
            flatten.append(v)

    return target_hash("|".join(flatten))


class ActionElementProtocol(Protocol):
    def transform_arguments(self, ctx: Context, target: EvaluatedTask) -> ArgumentData:
        ...

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        raise NotImplementedError


class TaskObject:
    name: StringValue
    path: PathElement
    requires: list[Union[PathElement, TaskPath, "TaskObject"]]

    # TODO: rename to .steps
    commands: list[ActionElementProtocol]

    # inputs dictionary, "" or None is for unnamed inputs
    inputs: dict[Union[None, str], AllPathLike]

    # All outputs as a list. For fast checks if a task has any outputs
    outputs: list[Union[PathElement, TaskPath]]

    # named outputs dict
    # None key is unnamed outputs
    outputs_dict: dict[Union[None, str], list[Union[PathElement, TaskPath]]]

    OutputKey = tuple[Union[None, int], int]
    """
    TODO: declared outputs replacing outputs_dict. key is a tuple (name, index); where name can be None. 
    """
    outputs_mapping: dict[OutputKey, Union[PathElement, TaskPath]]

    # location to build. can be overridden by users.
    build_path: Path

    # The location in which this task was actually defined (i.e. where the task() function was called).
    location: FileLocation

    # A list of required tasks we've actually resolved to a defined task.
    resolved_requires: list[ResolvedTaskReference]

    # Any requirements keys that are missing (and optional).
    # we keep all requirements as defined, and this set allows us to know which ones haven't been found so we may skip them
    missing_requirements: set[str]

    workspace: WorkspaceProtocol

    # The makex file in which this target was registered
    makex_file: "MakexFile"

    endless: bool = False

    environment: dict[str, PathLikeTypes]

    labels: set[Union[StringValue, JoinedString]]

    def __init__(
        self,
        name,
        path: Union[StringValue, PathElement] = None,
        requires=None,
        run=None,
        inputs=None,
        outputs=None,
        build_path=None,
        outputs_dict=None,
        workspace=None,
        makex_file=None,
        # TODO: pass the includer file so we can distinguish between where a target was defined and where it was finally included
        #   we need to use the includer to generate target.keys()
        includer=None,
        location=None,
        environment=None,
        labels=None,
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
        self.missing_requirements = set()
        self.outputs_dict = outputs_dict or {}

        self.inputs = inputs or {}

        if outputs and outputs_dict is None:
            # TEST ONLY
            for output in outputs:
                self.outputs_dict.setdefault(None, []).append(output)

        self.makex_file = makex_file

        self.location = location
        self.environment = environment or {}
        self.labels = labels

    def all_outputs(self) -> Iterable[Union[PathElement, TaskPath]]:
        d = self.outputs_dict
        if not d:
            return None

        yield from d.get(None)

        for k, v in d.items():
            if isinstance(v, list):
                yield from v
            else:
                yield v

    def add_resolved_requirement(self, requirement: ResolvedTaskReference):
        self.resolved_requires.append(requirement)

    @property
    def makex_file_path(self) -> str:
        return self.makex_file.path.as_posix()

    def path_input(self):
        """ Return the directory where this target is declared/applicable. """
        return self.makex_file.directory

    def __eq__(self, other):
        if not isinstance(other, (TaskObject, ResolvedTaskReference)):
            return False

        return self.key() == other.key()

    def key(self):
        return format_hash_key(self.name, self.makex_file.path)

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        if self.path:
            return f"TaskObject(\"{self.name}\", {self.makex_file.path})"
        return f"TaskObject(\"{self.name}\")"

    def for_include(self, file: "MakexFile"):
        # return a target transformed for inclusion
        raise NotImplementedError


def resolve_task_output_path(ctx, target: TargetProtocol) -> tuple[Path, Path]:
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
    detection: TaskObject
    cycles: list[TaskObject]

    def __init__(self, message, detection: TaskObject, cycles: list[TaskObject]):
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


class IncludeFunction(Protocol):
    def __call__(
        self,
        ctx: Context,
        workspace: WorkspaceProtocol,
        base: Path,
        search_path: str,
        makex_file: "MakexFileProtocol",
        location: FileLocation,
        search=False,
        globals=None,
        stack=None,
        targets=False,
        required=True,
    ) -> tuple[types.ModuleType, "MakexFileProtocol"]:
        pass


def _process_output(
    output: Union[StringValue, Glob],
    target_name,
    location,
) -> Union[PathElement, TaskPath, Glob]:
    # Mostly return the outputs, as is, for later evaluation. Check for invalid arguments early.
    if isinstance(output, StringValue):
        return PathElement(output, location=output.location)
    elif isinstance(output, Glob):
        # append glob as is. we'll resolve later.
        return output
    elif isinstance(output, TaskPath):
        return output
    elif isinstance(output, PathElement):
        return output
    else:
        raise PythonScriptError(
            f"Invalid output type {type(output)} in output list for task {target_name}: {output}",
            location
        )


if typing.TYPE_CHECKING:

    from typing_extensions import (
        NotRequired,
        Required,
    )

    # TODO: remove this in the future when >=3.12 is expected
    class TargetArguments(TypedDict):
        name: str
        label: str
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
else:

    class TargetArguments(TypedDict):
        name: str
        label: str
        path: Path
        requires: list[str]
        runs: list
        actions: list
        outputs: list
        inputs: dict
        location: FileLocation


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
        ctx: Context,
        directory: Path,
        path: Path,
        workspace: WorkspaceProtocol = None,
        targets: Optional[dict[str, TargetProtocol]] = None,
        macros: Optional[dict[str, Callable]] = None,
        makex_file: Optional["MakexFileProtocol"] = None,
        stack: Optional[list[str]] = None, # stack of paths reaching the file
        include_function: Optional[IncludeFunction] = None,
        globals=None,
    ):
        self.stack = stack or [path.as_posix()]

        self.directory = directory

        # path to the actual makex file
        self.path = path

        self.ctx: Context = ctx
        # wrap environment dict so it can't be modified
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
        self.includes: set[MakexFileProtocol] = set()

        self.errors = []
        self.warnings = []

        implicit_error_level = self.ctx.error_levels[ErrorCategory.IMPLICIT_REQUIREMENT_ADDED]

        if implicit_error_level == ErrorLevel.ERROR:

            def implicit_error(message, location):
                self.errors.append(PythonScriptError(message, location))
        elif implicit_error_level == ErrorLevel.WARNING:

            def implicit_error(message, location):
                self.warnings.append(PythonScriptError(message, location))
        elif implicit_error_level == ErrorLevel.OFF:

            def implicit_error(message, location):
                pass

        self._implicit_error = implicit_error

    def globals(self):
        parent = super().globals()

        g = {
            **parent,
            MAKEX_GLOBAL_TARGETS: self.targets,
            MAKEX_GLOBAL_MACROS: self.macros,
            "Environment": self.environment, #"pattern": wrap_script_function(self._pattern),
            "ENVIRONMENT": self.environment, # TODO: deprecate this:
            "E": self.environment,
            "Task": wrap_script_function(self._function_task),
            MAKEX_FUNCTION_TASK: wrap_script_function(self._function_task),
            _TARGET_REFERENCE_NAME: wrap_script_function(self._function_Reference),
            _MACRO_DECORATOR_NAME: self._decorator_macro, #"macro": Decorator,
        }

        if INCLUDE_ENABLED:
            g[MAKEX_FUNCTION_INCLUDE] = self._function_include

        # path utilities
        g.update(
            {
                # DONE: path() is a common variable (e.g. in a loop), and as an argument (to target) and Path() object. confusing.
                #  alias to cache(), or output()
                #"path": wrap_script_function(self._function_path),
                MAKEX_FUNCTION_TASK_PATH: wrap_script_function(self._function_task_path),
                # cache is a bit shorter than task_path
                "cache": wrap_script_function(self._function_task_path),
                #"output": wrap_script_function(self.build_path),
                "Path": wrap_script_function(self._function_Path, _deprecate=True),
                MAKEX_FUNCTION_PATH: wrap_script_function(self._function_Path),
                MAKEX_FUNCTION_SOURCE: wrap_script_function(self._function_source),
            }
        )

        if GLOB_FUNCTION_ENABLED:
            g[MAKEX_FUNCTION_GLOB] = wrap_script_function(self._function_glob)

        if FIND_FUNCTION_ENABLED:
            g[MAKEX_FUNCTION_FIND] = wrap_script_function(self._function_find)

        # Actions
        _actions = {
            MAKEX_FUNCTION_PRINT: wrap_script_function(self._function_print),
            MAKEX_FUNCTION_SHELL: wrap_script_function(self._function_shell),
            MAKEX_FUNCTION_MIRROR: wrap_script_function(self._function_mirror),
            MAKEX_FUNCTION_EXECUTE: wrap_script_function(self._function_execute),
            MAKEX_FUNCTION_COPY: wrap_script_function(self._function_copy),
            MAKEX_FUNCTION_WRITE: wrap_script_function(self._function_write),
            MAKEX_FUNCTION_ENVIRONMENT: wrap_script_function(self._function_environment),
        }

        if ARCHIVE_FUNCTION_ENABLED:
            _actions[MAKEX_FUNCTION_ARCHIVE] = wrap_script_function(self._function_archive)

        if EXPAND_FUNCTION_ENABLED:
            _actions[MAKEX_FUNCTION_EXPAND] = wrap_script_function(self._function_expand)

        if HOME_FUNCTION_ENABLED:
            _actions[MAKEX_FUNCTION_HOME] = wrap_script_function(self._function_home)

        if ERASE_FUNCTION_ENABLED:
            _actions[MAKEX_FUNCTION_ERASE] = wrap_script_function(self._function_erase)

        if OPTIONAL_REQUIREMENTS_ENABLED:
            _actions["optional"] = wrap_script_function(self._function_optional)

        if TASK_SELF_ENABLED:
            g.update(
                {
                    MAKEX_FUNCTION_TASK_SELF_NAME: wrap_script_function(
                        self._function_task_self_name
                    ),
                    MAKEX_FUNCTION_TASK_SELF_PATH: wrap_script_function(
                        self._function_task_self_path
                    ),
                    MAKEX_FUNCTION_TASK_SELF_INPUTS: wrap_script_function(
                        self._function_task_self_inputs
                    ),
                    MAKEX_FUNCTION_TASK_SELF_OUTPUTS: wrap_script_function(
                        self._function_task_self_outputs
                    )
                }
            )

        g.update(_actions)

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
            # TODO: map _location1_ to the returned object
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
        # Call the parsers include function.
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
            if required is False:
                debug("Skipping missing optional makex file.")
                return None
            else:
                raise PythonScriptError(
                    f"Missing file to include {path} in {self.path}", location=_location_
                )

        del module.__builtins__
        _macros = getattr(module, MAKEX_GLOBAL_MACROS)
        debug("Importing macros from %s: %s", path, _macros.keys())

        _globals.update(_macros)

        self.includes.add(file)

        if tasks:
            trace("Adding tasks from included file: %s", module._TARGETS_.keys())
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
            _path = _path.joinpath(*path)

        return PathElement(arg, resolved=_path, location=location)

    def _function_find(
        self, path: PathLikeTypes, expr: Union[Glob, RegularExpression] = None, location=None
    ):

        if isinstance(path, StringValue):
            _path = resolve_string_path_workspace(self.ctx, self.workspace, path, self.directory)

            path = PathElement(path.value, resolved=_path, location=path.location)
        elif path is None or isinstance(path, (PathElement, TaskPath)):
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

    def _function_Reference(self, name, path: PathLikeTypes = None, location=None, **kwargs):
        # absorb kwargs so we can error between Target and target
        if path is None:
            path = self.makex_file.directory
        return TaskReferenceElement(
            name=name,
            path=StringValue(path, location=location),
            location=location,
        )

    def _function_optional(
        self, reference: Union[StringValue, TaskReferenceElement], location, **kwargs
    ):
        if isinstance(reference, StringValue):
            if task_reference := parse_task_reference(reference):
                path, name = task_reference
                return TaskReferenceElement(name=name, path=path, location=location, optional=True)
            raise PythonScriptError(
                "Invalid task reference. Expected {path}:{task}.",
                location=location,
            )
        elif isinstance(reference, JoinedString):
            _reference = join_string_nopath(self.ctx, string=reference)
            if task_reference := parse_task_reference(_reference):
                path, name = task_reference
                return TaskReferenceElement(name=name, path=path, location=location, optional=True)
            raise PythonScriptError(
                "Invalid task reference. Expected {path}:{task}.",
                location=location,
            )

        elif isinstance(reference, TaskReferenceElement):
            reference.optional = True
            return reference
        else:
            raise PythonScriptError(
                "Invalid argument to optional(). Expected Task Reference or String.",
                location=location,
            )

    def _function_task_self_name(self, location=None, **kwargs):
        return TaskSelfName(location=location)

    def _function_task_self_path(self, location=None, **kwargs):
        return TaskSelfPath(location=location)

    def _function_task_self_inputs(self, name: StringValue = None, location=None, **kwargs):
        return TaskSelfInput(name, location=location)

    def _function_task_self_outputs(self, name: StringValue, location=None, **kwargs):
        return TaskSelfOutput(name, location=location)

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
    ) -> TaskPath:
        ref_path = path
        if isinstance(path, PathElement):
            # task_path(name:str, path("path/to/task"))
            _path = resolve_path_element_workspace(self.ctx, self.workspace, path, self.directory)
        elif isinstance(path, StringValue):
            # task_path(name:str, path:str)
            # TODO: check if name contains a : marker. use that as the path.
            _path = resolve_string_path_workspace(self.ctx, self.workspace, path, self.directory)
        elif path is None:
            # task_path(name:str)
            _path = self.directory
        else:
            raise PythonScriptError(f"Invalid path value: {type(path)}", location)
        return create_build_path_object(
            self.ctx,
            target=name,
            path=_path,
            variants=variants,
            location=location,
            ref_path=ref_path,
        )

    def _function_source(self, *path: StringValue, location=None):
        if not path:
            # XXX: No path. Return the source directory.
            return PathElement(*self.directory.parts, resolved=self.directory, location=location)

        # OPTIMIZATION: fast path for sources with a single Path() argument
        if len(path) == 1:
            path0 = path[0]
            if isinstance(path0, PathElement):
                _parts = self.directory.parts + path0.parts
                resolved = self.directory / path0._as_path()
                return PathElement(*_parts, resolved=resolved, location=location)
            elif isinstance(path0, StringValue):
                resolved = self.directory / path0
                return PathElement(path0, resolved=resolved, location=location)
            else:
                raise PythonScriptError(
                    f"Invalid path part type in source() function. Expected string. Got {type(path0)}: {path0!r}",
                    get_location(path0, location)
                )

        _parts = []
        for part in path:
            if isinstance(part, PathElement):
                _parts += part.parts

            elif isinstance(part, StringValue):
                _parts.append(part)
            else:
                raise PythonScriptError(
                    f"Invalid path part type in source() function. Expected string. Got {type(part)}: {part!r}",
                    get_location(part, location)
                )

        _path = resolve_path_parts_workspace(
            self.ctx, self.workspace, _parts, self.directory, location
        )

        # XXX: all of _path.parts is used, so it's fully absolute
        return PathElement(*path, resolved=_path, location=location)

    def _function_Path(self, *path: StringValue, location=None, **kwargs):
        for part in path:
            if not isinstance(part, StringValue):
                raise PythonScriptError(
                    f"Invalid path part type in Path() function. Expected string. Got {type(part)}: {part!r}",
                    get_location(part, location)
                )

        if kwargs.pop("_deprecated", False):
            self.ctx.ui.warn(
                f"The Path() function is deprecated. Please change to using path() instead.",
                location=location,
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

    def _function_archive(self, *args, **kwargs):
        location = kwargs.pop(FILE_LOCATION_ARGUMENT_NAME, None)
        if args:
            raise PythonScriptError(
                "archive() function must be called with keyword arguments only.", location
            )

        path = kwargs.pop("path", None)
        root = kwargs.pop("root", None)
        type = kwargs.pop("type", None)
        options = kwargs.pop("options", None)
        prefix = kwargs.pop("prefix", None)
        files = kwargs.pop("files", None)
        return Archive(
            path=path,
            root=root,
            type=type,
            options=options,
            files=files,
            prefix=prefix,
            location=location,
        )

    def _function_shell(self, *script: tuple[StringValue, ...], location=None):
        return Shell(script, location)

    def _function_execute(
        self,
        file: PathLikeTypes,
        /,
        *args: tuple[Union[PathLikeTypes, list[PathLikeTypes]]],
        **kwargs, #environment: dict[str, str] = None,
        #location=None,
    ):
        environment = kwargs.pop("environment", None)
        location = kwargs.pop("location", None)

        if isinstance(file, ListTypes):
            # allow passing a list to executable with the first argument being the executable.
            # TODO: we should probably deprecate/remove this.
            file = file[0]
            args = file[1:]

        return Execute.build(
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
        # data=None for touch
        return Write(destination, data=data, executable=executable, location=location)

    def _function_mirror(
        self, source: list[AllPathLike], destination: PathLikeTypes = None, /, **kwargs
    ):
        location: FileLocation = kwargs.pop("location", None)
        exclude: list[Union[StringValue, Glob]] = kwargs.pop("exclude", None)
        return Mirror(
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
        name=None,
        location=None,
    ):
        return Copy.build(
            source=source,
            destination=path,
            exclude=exclude,
            location=location,
            name=name,
        )

    def _function_erase(self, *paths: tuple[AllPathLike], **kwargs):
        location = kwargs.pop(FILE_LOCATION_ARGUMENT_NAME, None)

        return Erase(files=paths, location=location)

    def _target_requires(
        self,
        requirements: list[Union[PathElement, StringValue, Glob, TaskReferenceElement]],
        location,
        task_name,
    ) -> Iterable[Union[TaskReferenceElement, PathElement, Glob, FindFiles]]:
        # process the requires= list of the target() function.
        # convert to TargetReference where appropriate

        # keep a set to make sure we report/return unique items as some of them may be added implicitly
        _yielded = set()

        for implicit, require in requirements:
            if isinstance(require, StringValue):
                if task_reference := parse_task_reference(require):
                    # parse a requirement string with a task marker. e.g. `//path:task_name`
                    # if the path can be resolved, do it now.
                    rpath, target = task_reference

                    if not rpath:
                        # received :task_name
                        rpath = None
                        #rpath = StringValue(rpath, location=require.location)

                        if target == task_name:
                            # Don't create references to self (implicitly or explicitly)
                            continue
                    else:
                        # received //path:task_name or path:task_name
                        # TODO: pass resolved= here
                        resolved = resolve_string_path_workspace(
                            ctx=self.ctx,
                            workspace=self.workspace,
                            element=StringValue(rpath, location=require.location),
                            base=self.directory
                        )
                        rpath = PathElement(rpath, resolved=resolved, location=require.location)
                        #_validate_path(rpath._as_path().parts, require.location)

                    ref = TaskReferenceElement(target, rpath, location=require.location)

                    if ref in _yielded:
                        continue

                    if implicit:
                        self._implicit_error(
                            f"Implicit requirement added to: {ref}", require.location
                        )

                        # TODO: pass task path/name here so we can info the user.
                        debug(
                            "Adding implicit requirement: %s to task %s from %s",
                            ref,
                            task_name,
                            require.location
                        )

                    _yielded.add(ref)
                    yield ref
                else:
                    # convert strings to paths
                    p = resolve_string_path_workspace(
                        self.ctx, self.workspace, require, self.directory
                    )
                    yield PathElement(require, resolved=p, location=require.location)

            elif isinstance(require, TaskReferenceElement):
                # yield references which will be followed later

                if require.path is None and require.name == task_name:
                    # Don't create references to self (implicitly or explicitly)
                    continue

                if require in _yielded:
                    # skip anything we've already yielded
                    continue

                if implicit:
                    self._implicit_error(
                        f"Implicit requirement added to: {require}", require.location
                    )

                    # TODO: pass task path/name here so we can info the user.
                    debug(
                        "Adding implicit requirement: %s to task %s from %s",
                        require,
                        task_name,
                        require.location
                    )

                _yielded.add(require)
                yield require
            elif isinstance(require, FindFiles):
                # append internal objects referring to files such as is find(), glob() and Target(); these will be expanded later
                if FIND_IN_INPUTS_ENABLED is False:
                    raise PythonScriptError(
                        "The find function (find()) is not allowed in the task's requires list.",
                        require.location
                    )

                yield require
            elif isinstance(require, Glob):
                # append internal objects referring to files such as is find(), glob() and Target(); these will be expanded later
                if GLOBS_IN_INPUTS_ENABLED is False:
                    raise PythonScriptError(
                        "The glob function (glob) is not allowed in the task's requires list.",
                        require.location
                    )
                yield require
            elif isinstance(require, PathElement):
                yield require
            elif isinstance(require, TaskObject):
                raise PythonScriptError("Invalid use of task() for the requires args. ", location)
            elif isinstance(require, ListTypes):
                # TODO: limit list depth.
                yield from self._target_requires(
                    map(lambda r: (False, r), require), location=location, task_name=task_name
                )
            elif require is None:
                # skip None values
                # TODO: notify of none values.
                continue
            else:
                raise PythonScriptError(
                    f"Invalid type {type(require)} in requires list. Got {require!r}.", location
                )

    # Unpack[TargetArguments],
    def _function_task(
        self,
        *args,
        **kwargs: TargetArguments,
    ):
        location = kwargs.pop("location", None)

        if args:
            raise PythonScriptError(
                "task() function must be called with keyword arguments only.", location
            )

        #if False:
        #    arglen = len(args)
        #    if not arglen:
        #        pass
        #    elif arglen == 3:
        #        name, path, variants = args
        #        return TaskReferenceElement(name, path, variants, location=location)
        #    elif arglen == 2:
        #        name, path = args
        #        return TaskReferenceElement(name, path, location=location)
        #    elif arglen == 1:
        #        name = args[0]
        #        return TaskReferenceElement(name, location=location)
        #    else:
        #        raise PythonScriptError(
        #            "Invalid number of arguments to create Task Reference. Expected name and optional path.",
        #            location=location
        #        )

        if self.block_registration:
            trace("Registration of task blocked at %s", location)
            return

        #trace("Calling target() from %s", self.makex_file)
        name: Optional[StringValue] = kwargs.pop("name", None)
        path = kwargs.pop("path", None)
        requires = kwargs.pop("requires", None)
        steps: Optional[list[InternalActionBase]] = (
            kwargs.pop("actions", None) or kwargs.pop("steps", None)
        )
        outputs = kwargs.pop("outputs", None)
        environment = kwargs.pop("environment", None)
        labels = kwargs.pop("labels", None)

        # TODO: process the inputs dictionary/list
        inputs = kwargs.pop("inputs", None)

        if kwargs:
            raise PythonScriptError(f"Unknown arguments to task(): {list(kwargs.keys())}", location)

        if name is None or name == "":
            raise PythonScriptError(f"Invalid task name {name!r}.", location)

        _validate_task_name(name, get_location(name, location))

        existing: TaskObject = self.targets.get(name, None)
        if existing:
            raise PythonScriptError(
                f"Duplicate task name {name!r}. Already defined at {existing.location}.", location
            )

        # collect any implicit requirements from steps/actions.
        # TODO: we don't need to build a list here.
        _implicit_requirements = []

        if self.ctx.implicit_requirements and steps:
            if isinstance(steps, ListTypes) is False:
                raise PythonScriptError(
                    message=f"task.steps must be a list. Got a {type(steps)}.",
                    location=get_location(steps, location)
                )

            for action in steps:
                if implicit := action.get_implicit_requirements(ctx=self.ctx):
                    _implicit_requirements.extend(implicit)

        if requires:
            # produce two chains, both producing (implicit:bool, requirement:TaskReferenceElement)
            _iter = chain(
                map(lambda r: (False, r), requires),
                map(lambda r: (True, r), _implicit_requirements)
            )
            _requires = list(self._target_requires(_iter, location=location, task_name=name))
        else:
            _requires = []

        _outputs = []

        # unnamed outputs go in None
        outputs_dict: dict[Union[str, None], PathLikeTypes] = {None: []}
        unnamed_outputs = outputs_dict.get(None)
        inputs_mapping = {}

        #_outputs2: dict[tuple[Union[str, None], int], PathLikeTypes] = {}
        if inputs:
            if isinstance(inputs, ListTypes):
                raise PythonScriptError(
                    message=f"Invalid inputs type {type(outputs)}. Should be a dictionary/mapping.",
                    location=location
                )
            elif isinstance(inputs, dict):
                for k, value in inputs.items():
                    output = value #_process_output(value, name, location)
                    inputs_mapping[k] = output
            elif isinstance(inputs, (StringValue, JoinedString)):
                inputs_mapping[None] = [inputs]
            else:
                raise PythonScriptError(
                    message=f"Invalid inputs type {type(inputs)}. Should be a dictionary/mapping.",
                    location=location
                )
        if outputs:
            if isinstance(outputs, ListTypes):
                # outputs was declared as a list
                for i, out in enumerate(outputs):
                    output = _process_output(out, name, location)
                    _outputs.append(output)
                    unnamed_outputs.append(output)
                    outputs_dict[i] = output
                    #_outputs2[(None, i)] = outputs
            elif isinstance(outputs, (JoinedString, StringValue, PathElement, TaskPath)):
                # outputs=path or outputs=string
                _outputs.append(outputs)
                unnamed_outputs.append(outputs)

                #_outputs2[(None, 0)] = outputs
            elif NAMED_OUTPUTS_ENABLED and isinstance(outputs, dict):
                # named outputs. outputs was declared as a dictionary. may have single or list values.
                for k, v in outputs.items():
                    output = _process_output(v, name, location)
                    _outputs.append(output)
                    outputs_dict[k] = output
                    #for i, _o in enumerate(_out):
                    #    _outputs2[(k, 0)] = _o
            else:
                raise PythonScriptError(f"Invalid outputs type {type(outputs)}.", location)

        if TARGET_PATH_ENABLED is False and path is not None:
            raise PythonScriptError(
                "Setting path is not allowed (by flag). TARGET_PATH_ENABLED",
                get_location(path, location)
            )

        task = TaskObject(
            name=name,
            path=path,
            requires=_requires,
            run=steps or [], # commands will be evaluated later
            inputs=inputs_mapping,
            outputs=_outputs,
            outputs_dict=outputs_dict,
            workspace=self.workspace,
            makex_file=self.makex_file,
            location=location,
            environment=environment,
            labels=labels,
        )

        self.targets[name] = task
        trace("Registered task %s in makexfile %s. %s ", task.name, self.makex_file, location)
        return None


class MakexFile(MakexFileProtocol):
    # to the makefile
    #path: Path

    targets: dict[str, TaskObject]

    macros: dict[str, Callable]

    #code: Optional[types.CodeType] = None
    includes: list[MakexFileProtocol]

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
        # Included in hash.
        self.includes = []

    def hash_components(self):
        yield f"version:{VERSION}"
        yield f"environment:{self.environment_hash}"
        yield f"makex-file:{self.checksum}"
        for include in self.includes:
            yield f"environment:include:{include.environment_hash}"
            yield f"makex-file:include:{include.checksum}"
            # TODO: is a recursive hash necessary?

    def key(self):
        return str(self.path)

    @classmethod
    def execute(
        cls,
        ctx: Context,
        path: Path,
        workspace: WorkspaceProtocol,
        node: ast.AST,
        include_function,
        globals=None,
        importer=None
    ) -> "MakexFileProtocol":
        pass

    @classmethod
    def parse(
        cls,
        ctx: Context,
        path: Path,
        workspace: WorkspaceProtocol,
        include_function,
        globals=None,
        importer=None
    ) -> "MakexFileProtocol":
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
        debug("Started parsing makex file %s ...", path)

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

        pre_visitors = []
        post_visitors = [TransformGetItem(posix_path)]

        if INCLUDE_ENABLED:
            include_processor = ProcessIncludes(posix_path)
            pre_visitors.append(include_processor)
        else:
            include_processor = None

        if TASK_SELF_ENABLED:
            pre_visitors.append(TransformSelfReferences(posix_path))

        options = PythonScriptFile.Options(
            pre_visitors=pre_visitors,
            post_visitors=post_visitors,
            imports_enabled=IMPORT_ENABLED,
            import_function=importer,
            disable_assigment_names=DISABLE_ASSIGNMENT_NAMES,
            late_joined_string=LATE_JOINED_STRINGS,
        )
        script = PythonScriptFile(path, _globals, options=options)

        with path.open("rb") as f:
            tree = script.parse(f)

        if False and INCLUDE_ENABLED:
            # find any includes, parse those and insert their asts before we execute.
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
            "Finished parsing makex file %s: Macros: %s | Tasks: %s",
            path,
            makefile.macros.keys(),
            _globals[MAKEX_GLOBAL_TARGETS].keys()
        )
        makefile.targets = _globals[MAKEX_GLOBAL_TARGETS]
        return makefile

    def __repr__(self):
        return self.key()
