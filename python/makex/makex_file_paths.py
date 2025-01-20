import logging
import re
from os import PathLike
from os.path import join as os_path_join
from pathlib import Path
from typing import (
    Iterable,
    Optional,
    Pattern,
    Union,
)

from makex._logging import debug
from makex.build_path import get_build_path
from makex.constants import (
    IGNORE_NONE_VALUES_IN_LISTS,
    TASK_PATH_NAME_SEPARATOR,
    WORKSPACES_IN_PATHS_ENABLED,
)
from makex.context import Context
from makex.errors import ExecutionError
from makex.file_system import find_files
from makex.flags import (
    ABSOLUTE_PATHS_ENABLED,
    PATH_IN_GLOB_ENABLED,
)
from makex.makex_file_types import (
    Expansion,
    FindFiles,
    Glob,
    ListTypes,
    MultiplePathLike,
    PathElement,
    PathLikeTypes,
    RegularExpression,
    TaskPath,
    TaskReferenceElement,
    TaskSelfInput,
    TaskSelfName,
    TaskSelfOutput,
    TaskSelfPath,
    UnresolvedTaskPath,
    ValidJoinedStringPart,
)
from makex.patterns import make_glob_pattern
from makex.protocols import WorkspaceProtocol
from makex.python_script import (
    FileLocation,
    JoinedString,
    PythonScriptError,
    StringValue,
    get_location,
)
from makex.target import EvaluatedTask

MISSING = object()


class ResolvedPath:
    """
    We resolve unresolved paths to this object.
    
    :var location: The location the path was constructed or last location of a join() operation.
    
    """
    __slots__ = ("_path", "location")

    def __init__(self, path: str, location: FileLocation = None):
        self._path = path
        self.location = location

    def __fspath__(self):
        return self._path


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


def join_string(ctx: Context, task: EvaluatedTask, base: Path, string: JoinedString):
    """
    Joins the string using the information from ctx/task.
    
    :param ctx: 
    :param task: 
    :param string: 
    :return: 
    """
    _list = []
    try:
        return StringValue(
            "".join(_join_string_iterable(ctx, task, base, string)),
            location=string.location,
        )
    except Exception as e:
        logging.exception(e)
        raise PythonScriptError(
            f"Invalid string: {e}", location=get_location(string, task.location)
        )


def _join_string_iterable(ctx, task: EvaluatedTask, base: Path, string: JoinedString):
    for part in string.parts:
        if isinstance(part, StringValue):
            yield part.value
        elif isinstance(part, str):
            yield part
        elif isinstance(part, TaskPath):
            yield str(part)
        elif isinstance(part, PathElement):
            yield str(part)
        elif isinstance(part, TaskSelfPath):
            yield _resolve_task_self_path(ctx, task, part).as_posix()
        elif isinstance(part, TaskSelfInput):
            for value in task.inputs_mapping.get(part.name_or_index, []):
                yield value.as_posix()
        elif isinstance(part, TaskSelfOutput):
            for value in task.output_dict.get(part.name_or_index, []):
                yield value.path.as_posix()
        elif isinstance(part, TaskSelfName):
            yield task.name
        else:
            raise PythonScriptError(
                f"Invalid value type in joined string {type(part)}. Expected {ValidJoinedStringPart})",
                location=string.location,
            )


def join_string_nopath(ctx: Context, string: JoinedString):
    """
    Joins the string using the information from ctx/task.
    
    TODO: remove ctx argument.
    :param ctx: 
    :param string: 
    :return: 
    """
    _list = []
    return StringValue(
        "".join(_join_string_iterable_nopath(ctx, string)),
        location=string.location,
    )


def _join_string_iterable_nopath(ctx, string: JoinedString):
    for part in string.parts:
        if isinstance(part, StringValue):
            yield part.value
        elif isinstance(part, str):
            yield part
        else:
            raise PythonScriptError(
                f"Invalid value type in joined string {type(part)}. Expected {ValidJoinedStringPart})",
                location=string.location,
            )


def resolve_task_path(ctx: Context, path: TaskPath, absolute=False) -> Path:
    """ Given a TaskPath object return the actual filesystem path.

        If absolute is True return the absolute path to cache instead of the symbolic link to it.
    """
    # TODO: actually do the path resolution here
    return path.path


def resolve_string_path_workspace(
    ctx: Context,
    workspace: WorkspaceProtocol,
    element: StringValue,
    base: Path,
) -> Path:

    if element.value == ".":
        return base

    _path = path = Path(element.value)

    _validate_path(path.parts, element.location)

    if path.parts[0] == "//":
        #trace("Resolve workspace path: %s %s", workspace, element)
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
    workspace: WorkspaceProtocol,
    element: PathElement,
    base: Path,
) -> Path:
    if element.resolved:
        path = element.resolved
    else:
        path = Path(*element.parts)

    _validate_path(path.parts, element.location)

    if path.parts[0] == "//":

        #trace("Workspace path: %s %s", workspace, element)
        if WORKSPACES_IN_PATHS_ENABLED:
            path = workspace.path / Path(*path.parts[1:])
        else:
            raise PythonScriptError("Workspaces markers // in paths not enabled.", element.location)
    elif not path.is_absolute():
        path = base / path

    #trace("Resolve path element path %r:  %r (%r)", element, path, element.parts)

    return path


def resolve_path_parts_workspace(
    ctx: Context,
    workspace: WorkspaceProtocol,
    parts: Union[tuple[StringValue], list[StringValue]],
    base: Path,
    location: FileLocation,
) -> Path:
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


def resolve_pathlike_list(
    ctx: Context,
    task: EvaluatedTask,
    base: Path,
    name: str,
    values: Iterable[Union[PathLikeTypes, MultiplePathLike]],
    glob=True,
    references=True,
) -> Iterable[Path]:

    for i, value in enumerate(values):
        if isinstance(value, StringValue):
            yield resolve_string_path_workspace(ctx, task.workspace, value, base)
        elif isinstance(value, JoinedString):
            yield resolve_string_path_workspace(
                ctx, task.workspace, join_string(ctx, task, base, value), base
            )
        elif isinstance(value, PathElement):
            source = resolve_path_element_workspace(ctx, task.workspace, value, base)
            yield source
        elif isinstance(value, Glob):
            if glob is False:
                raise ExecutionError(
                    error=f"Globs are not allowed in the {name} property.",
                    target=task,
                    location=value.location,
                )
            # todo: use glob cache from ctx for multiples of the same glob during a run
            yield from resolve_glob(ctx, task, base, value)
        elif isinstance(value, FindFiles):
            # find(path, pattern, type=file|symlink)

            if isinstance(value.path, TaskPath):
                path = resolve_task_path(ctx, value.path)
            elif isinstance(value.path, PathElement):
                path = resolve_path_element_workspace(ctx, task.workspace, value.path, base)
            else:
                path = base
            debug("Searching for files %s: %s", path, value.pattern)
            yield from resolve_find_files(ctx, task, path, value.pattern)
        elif isinstance(value, TaskPath):
            yield resolve_task_path(ctx, value)
        elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
            continue
        elif isinstance(value, TaskSelfInput):
            yield from task.inputs_mapping.get(value.name_or_index, [])
        elif isinstance(value, TaskSelfOutput):
            yield from task.output_dict.get(value.name_or_index, []).path
        elif references and isinstance(value, TaskReferenceElement):
            # get the outputs of the specified task
            _path = value.path

            if _path is None:
                # TODO: Handle tasks in same file
                _path = task.makex_file_path
            else:
                _path = resolve_string_path_workspace(
                    ctx, task.workspace, StringValue(value.path, value.location), base
                )

            #trace("Resolve path %s -> %s", value, _path)
            # DONE: we're using the wrong graph here for this, but it can work.
            #_ref_task = ctx.graph.get_task_for_path(_path, value.name)
            _ref_task = ctx.graph_2.get_task2(value.name, _path)
            if not _ref_task:
                # TODO: if implicit and missing from the task warn the user about missing from the task requirements list.
                raise PythonScriptError(
                    f"Error resolving to the output of '{value.name}'. Can't find task {_path}:{value.name} in graph. "
                    f"The task may be missing from this task's requirements list. {list(ctx.graph_2.get_keys())}",
                    value.location
                )
            # TODO: improve the validation here
            #trace("Resolved to task output %r -> %r", _ref_task, _ref_task.outputs[0])
            for output in _ref_task.outputs:
                #if isinstance(output, StringValue):
                #yield _resolve_pathlike(
                #    ctx, task=task, base=_ref_task.build_path, name=name, value=output
                #)
                yield output.path
            #return _ref_task.outputs[0].path
            #pass
        else:

            #raise ExecutionError(f"{type(value)} {value!r}", task, get_location(value, task))
            raise PythonScriptError(
                f"Invalid value (index={i}) in pathlike list: {type(value)}",
                get_location(value, task.location)
            )


def resolve_pathlike(
    ctx: Context,
    target: EvaluatedTask,
    base: Path,
    value: PathLikeTypes,
    location=None,
) -> Path:
    if isinstance(value, StringValue):
        return resolve_string_path_workspace(ctx, target.workspace, value, base)
    elif isinstance(value, TaskPath):
        return resolve_task_path(ctx, value)
    elif isinstance(value, TaskSelfPath):
        return _resolve_task_self_path(ctx, target, value)

    elif isinstance(value, TaskSelfOutput):
        task_path = target.path

        return_value = target.output_dict.get(value.name_or_index, MISSING)
        if return_value is MISSING:
            raise PythonScriptError(
                f"Invalid output name reference self.outputs.{value.name_or_index}",
                location or target.location
            )

        # XXX: Will always be a list if we access output_dict.
        # TODO: we need a copy of the original user dict
        if isinstance(return_value, ListTypes):
            if len(return_value) > 1:
                raise PythonScriptError(
                    f"Invalid output reference/definition self.outputs.{value.name_or_index}. Expected single path, or list with single item, got list.",
                    location or target.location
                )
            return return_value[0].path

            #raise PythonScriptError(
            #    f"Invalid output reference/definition self.outputs.{value.name_or_index}. Expected single path, got list.",
            #    location or target.location
            #)

        #return_value = Path(task_path, *return_value..parts)
        return return_value.path

    elif isinstance(value, PathElement):
        return resolve_path_element_workspace(ctx, target.workspace, value, base)
    else:
        raise PythonScriptError(
            f"Invalid path type {type(value)} {value!r}", location or target.location
        )


def _resolve_task_self_path(ctx, task: EvaluatedTask, value: TaskSelfPath) -> Path:
    task_path = task.path
    value = Path(task_path, *value.parts)
    return value


def _make_glob_pattern(glob_pattern: str) -> Pattern:
    prefix = ""
    if glob_pattern.startswith("/") is False:
        # XXX: make sure non-absolute globs match with find_files
        #  we need to prefix with .* because find files matches against the full path
        prefix = ".*"

    # TODO: check if glob is absolute here?
    #glob_pattern = pattern.pattern
    _pattern = re.compile(prefix + make_glob_pattern(glob_pattern))
    return _pattern


def resolve_glob(
    ctx: Context,
    target: EvaluatedTask,
    path: PathLike,
    pattern: Glob,
    ignore_names=None,
) -> Iterable[Path]:

    ignore_names = ignore_names or ctx.ignore_names

    _pattern = _make_glob_pattern(pattern.pattern)
    yield from find_files(
        path,
        pattern=_pattern,
        ignore_pattern=ctx.ignore_pattern,
        ignore_names=ignore_names,
    )


def resolve_find_files(
    ctx: Context,
    target: EvaluatedTask,
    path,
    pattern: Optional[Union[Glob, StringValue, RegularExpression]],
    ignore_names=None,
) -> Iterable[Path]:
    # TODO: pass the find node

    # TODO: Handle extra ignores specified on the Find object
    ignore_names = ignore_names or ctx.ignore_names

    #TODO: support matching stringvalues to paths
    if isinstance(pattern, (str, StringValue)):
        _pattern = _make_glob_pattern(pattern)
    elif isinstance(pattern, Glob):
        if isinstance(pattern.pattern, (TaskPath, PathElement)):
            if PATH_IN_GLOB_ENABLED:
                # TODO: handle unresolved paths here.
                pattern = os_path_join(pattern.pattern.parts[0], *pattern.pattern.parts[1:])
            else:
                raise ExecutionError(
                    f"Invalid pattern argument for find(). Got: {type(pattern)}.",
                    target,
                    get_location(pattern, target.location),
                )
        else:
            pattern = pattern.pattern
        _pattern = _make_glob_pattern(pattern)
    elif isinstance(pattern, RegularExpression):
        _pattern = re.compile(pattern.pattern, re.U | re.X)
    elif pattern is None:
        _pattern = None
    else:
        raise ExecutionError(
            f"Invalid pattern argument for find(). Got: {type(pattern)}.",
            target,
            get_location(pattern, target.location),
        )

    yield from find_files(
        path=path,
        pattern=_pattern,
        ignore_pattern=ctx.ignore_pattern,
        ignore_names=ignore_names,
    )


def parse_task_reference(string: StringValue) -> Optional[tuple[StringValue, StringValue]]:
    """
    Parse a simple task reference:
    
    //{path}:{task_name}
    
    :param string: 
    :return: 
    """
    # Parse a task reference; path is optional
    _string = string.value

    if (index := _string.find(TASK_PATH_NAME_SEPARATOR)) >= 0:
        if index == 0:
            path = None
        else:
            path = StringValue(_string[0:index], string.location)

        name = StringValue(_string[index + 1:], string.location)
        return (path, name)
    else:
        return None


def parse_possible_task_reference(
    reference: StringValue
) -> Union[StringValue, TaskReferenceElement]:
    # TODO: handle references to the task namespace //{path}:{task_name}:{namespace}:{name} where namespace is one of inputs/outputs
    if task_reference := parse_task_reference(reference):
        task_path, task_name = task_reference

        if not task_path:
            task_path = None

        return TaskReferenceElement(task_name, task_path, reference.location)
    return reference


def parse_task_reference_extended(
    string: StringValue
) -> Optional[tuple[StringValue, StringValue, StringValue, StringValue]]:
    """
    Parse an extended task reference.
    
    //{path}:{task_name}:{namespace}:{name}
    
    :param string: 
    :return: 
    """
    _string = string.value

    if (index := _string.find(TASK_PATH_NAME_SEPARATOR)) >= 0:
        namespace = None
        namespace_name = None

        _name_part = _string[index + 1:]
        if index == 0:
            path = None
        else:
            _path_part = _string[0:index]
            if TASK_PATH_NAME_SEPARATOR in _path_part:
                # we have an extended reference with additional : markers
                parts = _path_part.split(":")

                _path_part = parts[0]
                namespace = StringValue(parts[1], string.location)
                namespace_name = StringValue(parts[2], string.location)

            path = StringValue(_path_part, string.location)

        name = StringValue(_name_part, string.location)
        return (path, name, namespace, namespace_name)
    else:
        return None


def create_build_path_object(
    ctx: Context, target: StringValue, path: Path, variants, location: FileLocation, ref_path=None
):
    # TODO: remove this function call. replace with late evaluation.
    _path, link_path = get_build_path(
        objective_name=target,
        variants=variants or [],
        input_directory=path,
        build_root=ctx.cache,
        workspace=ctx.workspace_path,
        workspace_id=ctx.workspace_object.id,
        output_folder=ctx.output_folder_name,
    )
    return TaskPath(
        link_path,
        reference=TaskReferenceElement(target, ref_path, location=location),
        location=location
    )


def resolve_path(
    context: Context,
    pathlike: Union[UnresolvedTaskPath, TaskSelfPath],
    task: EvaluatedTask,
) -> Optional[ResolvedPath]:
    """ 
    Turn an unresolved path into a resolved path.
    
    :param task: The task we are resolving for. 
    :return: 
    """
    # TODO: resolve an unresolved path path
    if isinstance(pathlike, UnresolvedTaskPath):
        task_path = pathlike.reference.path
        task_name = pathlike.reference.name
        real_path, link_path = get_build_path(
            objective_name=task_name,
            variants=[],
            input_directory=task_path,
            build_root=context.cache,
            workspace=context.workspace_path,
            workspace_id=context.workspace_object.id,
            output_folder=context.output_folder_name,
        )
        return ResolvedPath(link_path.as_posix(), location=pathlike.location)
    elif isinstance(pathlike, TaskSelfPath):
        return ResolvedPath(os_path_join(task.path, pathlike.parts), location=pathlike.location)

    return None


def resolve_to_string(
    ctx: Context,
    task: EvaluatedTask,
    value: PathLikeTypes,
) -> Optional[StringValue]:
    if isinstance(value, StringValue):
        # arguments.append(_string_value_maybe_expand_user(ctx, target_input, argument))
        return value
    elif isinstance(value, JoinedString):
        return join_string(ctx, task=task, base=task.input_path, string=value)
    elif isinstance(value, PathElement):
        return resolve_pathlike(ctx, task, task.input_path, value).as_posix()
    elif isinstance(value, Expansion):
        return str(value.expand(ctx))
    elif isinstance(value, TaskPath):
        return resolve_task_path(ctx, value).as_posix()


#elif isinstance(value, TaskSelfInput):
#    input = task.inputs_mapping.get(value.name_or_index, MISSING)
#    if input is MISSING:
#        raise PythonScriptError(f"Undefined input name: {value.name_or_index}", value.location)

#    input = [path.as_posix() for path in input]
#    return input
#elif isinstance(value, TaskSelfOutput):
#    output = task.output_dict.get(value.name_or_index, MISSING)
#    if output is MISSING:
#        raise PythonScriptError(f"Undefined output name: {value.name_or_index}", value.location)

#    output = [file.path for file in output]
#    return output
    elif isinstance(value, TaskSelfName):
        return task.name
    elif isinstance(value, TaskSelfPath):
        return _resolve_task_self_path(ctx, task, value).as_posix()
    #elif isinstance(value, tuple):
    #    arguments.extend(
    #        resolve_string_argument_list(ctx, target, target_input, target.name, argument)
    #    )
    #elif isinstance(value, ListTypes):
    #    arguments.extend(
    #        resolve_string_argument_list(ctx, target, target_input, target.name, argument)
    #    )
    elif value is None:
        # XXX: Ignore None arguments as they may be the result of a condition.
        return None
    else:
        raise PythonScriptError(
            message=f"Invalid argument type: {type(value)}. Expected String-like value.",
            location=get_location(value, task.location),
        )
