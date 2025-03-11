import shutil
from dataclasses import dataclass
from os import remove as os_remove
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Union,
)

from makex._logging import debug
from makex.constants import IGNORE_NONE_VALUES_IN_LISTS
from makex.context import Context
from makex.errors import ExecutionError
from makex.flags import ABSOLUTE_PATHS_ENABLED
from makex.makex_file_actions import InternalAction
from makex.makex_file_paths import (
    resolve_find_files,
    resolve_glob,
    resolve_task_path,
)
from makex.makex_file_types import (
    AllPathLike,
    FindFiles,
    Glob,
    MultiplePathLike,
    PathElement,
    PathLikeTypes,
    TaskPath,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
    WorkspaceProtocol,
)
from makex.python_script import (
    FileLocation,
    PythonScriptError,
    StringValue,
)
from makex.target import (
    ArgumentData,
    Task,
)


@dataclass
class Erase(InternalAction):
    """
    Erases files in a task's output (and within a task's output only).
    """
    NAME = "erase"

    files: tuple[AllPathLike]
    location: FileLocation

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
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
                "Workspaces markers // in paths may not be used for the erase action.",
                element.location
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
            raise PythonScriptError(
                "Workspaces markers // in paths may not be used for the erase action.",
                element.location
            )
        #elif not path.is_absolute():
        # always prefix path with the output/base
        _path = base / path

        #trace("Resolve string path %s: %s", element, _path)

        return _path

    def _resolve_pathlike_list(
        self,
        ctx: Context,
        target: Task,
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
                #raise ExecutionError(f"{type(value)} {value!r}", task, get_location(value, task))
                raise NotImplementedError(
                    f"Invalid argument in pathlike list: {type(value)} {value!r}"
                )

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
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
