import re
from pathlib import Path
from typing import (
    Iterable,
    Optional,
    Pattern,
    Union,
)

from makex._logging import debug
from makex.constants import (
    IGNORE_NONE_VALUES_IN_LISTS,
    TASK_PATH_NAME_SEPARATOR,
    WORKSPACES_IN_PATHS_ENABLED,
)
from makex.context import Context
from makex.errors import ExecutionError
from makex.file_system import find_files
from makex.flags import ABSOLUTE_PATHS_ENABLED
from makex.makex_file_types import (
    FindFiles,
    Glob,
    MultiplePathLike,
    PathElement,
    PathLikeTypes,
    RegularExpression,
    TaskPath,
    TaskReferenceElement,
)
from makex.patterns import make_glob_pattern
from makex.protocols import (
    TargetProtocol,
    WorkspaceProtocol,
)
from makex.python_script import (
    FileLocation,
    PythonScriptError,
    StringValue,
)


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
    target: TargetProtocol, # EvaluatedTask
    base: Path,
    name: str,
    values: Iterable[Union[PathLikeTypes, MultiplePathLike]],
    glob=True,
    references=True,
) -> Iterable[Path]:
    for value in values:
        if isinstance(value, StringValue):
            yield resolve_string_path_workspace(ctx, target.workspace, value, base)
        elif isinstance(value, PathElement):
            source = resolve_path_element_workspace(ctx, target.workspace, value, base)
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

            if isinstance(value.path, TaskPath):
                path = resolve_task_path(ctx, value.path)
            elif isinstance(value.path, PathElement):
                path = resolve_path_element_workspace(ctx, target.workspace, value.path, base)
            else:
                path = base
            debug("Searching for files %s: %s", path, value.pattern)
            yield from resolve_find_files(ctx, target, path, value.pattern)
        elif isinstance(value, TaskPath):
            yield resolve_task_path(ctx, value)
        elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
            continue
        elif references and isinstance(value, TaskReferenceElement):
            # get the outputs of the specified task
            _path = value.path

            if _path is None:
                # TODO: Handle tasks in same file
                _path = target.makex_file_path
            else:
                _path = resolve_string_path_workspace(
                    ctx, target.workspace, StringValue(value.path, value.location), base
                )

            #trace("Resolve path %s -> %s", value, _path)
            # DONE: we're using the wrong graph here for this, but it can work.
            #_ref_task = ctx.graph.get_task_for_path(_path, value.name)
            _ref_task = ctx.graph_2.get_task2(value.name, _path)
            if not _ref_task:
                # TODO: if implicit and missing from the task warn the user about missing from the task requirements list.
                raise PythonScriptError(
                    f"Error resolving to task output. Can't find task {_path}:{value.name} in graph. "
                    f"May be missing from task requirements list. {list(ctx.graph.targets.keys())}",
                    value.location
                )
            # TODO: improve the validation here
            #trace("Resolved to task output %r -> %r", _ref_task, _ref_task.outputs[0])
            for output in _ref_task.outputs:
                #if isinstance(output, StringValue):
                #yield _resolve_pathlike(
                #    ctx, target=target, base=_ref_task.build_path, name=name, value=output
                #)
                yield output.path
            #return _ref_task.outputs[0].path
            #pass
        else:
            #raise ExecutionError(f"{type(value)} {value!r}", target, getattr(value, "location", target))
            raise NotImplementedError(f"Invalid argument in pathlike list: {type(value)} {value!r}")


def _resolve_pathlike(
    ctx: Context,
    target: TargetProtocol, # EvaluatedTask
    base: Path,
    value: PathLikeTypes,
) -> Path:
    if isinstance(value, StringValue):
        return resolve_string_path_workspace(ctx, target.workspace, value, base)
    elif isinstance(value, TaskPath):
        return resolve_task_path(ctx, value)
    elif isinstance(value, PathElement):
        return resolve_path_element_workspace(ctx, target.workspace, value, base)
    else:
        raise PythonScriptError(f"Invalid path type {type(value)} {value!r}", target.location)


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
    target: TargetProtocol,
    path,
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
    target: TargetProtocol,
    path,
    pattern: Optional[Union[Glob, StringValue, RegularExpression]],
    ignore_names=None,
) -> Iterable[Path]:
    # TODO: pass the find node

    # TODO: Handle extra ignores specified on the Find object
    ignore_names = ignore_names or ctx.ignore_names

    #TODO: support matching stringvalues to paths
    if isinstance(pattern, str):
        _pattern = _make_glob_pattern(pattern)
    elif isinstance(pattern, Glob):
        _pattern = _make_glob_pattern(pattern.pattern)
    elif isinstance(pattern, RegularExpression):
        _pattern = re.compile(pattern.pattern, re.U | re.X)
    elif pattern is None:
        _pattern = None
    else:
        raise ExecutionError(
            f"Invalid pattern argument for find(). Got: {type(pattern)}.",
            target,
            getattr(pattern, "location", target.location),
        )

    yield from find_files(
        path=path,
        pattern=_pattern,
        ignore_pattern=ctx.ignore_pattern,
        ignore_names=ignore_names,
    )


def parse_task_reference(string: StringValue) -> Optional[tuple[StringValue, StringValue]]:
    # Parse a task reference; path is optional

    #if not isinstance(string, StringValue):
    #    return None
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
