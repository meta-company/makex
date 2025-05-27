import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Literal,
    TypedDict,
    Union,
)

from makex._logging import (
    debug,
    trace,
)
from makex.context import Context
from makex.errors import ExecutionError
from makex.file_system import copy_tree
from makex.flags import (
    COPY_LIBRARY,
    GLOBS_IN_ACTIONS_ENABLED,
)
from makex.makex_file_actions import InternalAction
from makex.makex_file_paths import (
    resolve_pathlike,
    resolve_pathlike_list,
)
from makex.makex_file_types import (
    AllPathLike,
    MultiplePathLike,
    PathLikeTypes,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
    FileLocation,
    ListValue,
    PythonScriptError,
)
from makex.target import (
    ArgumentData,
    Task,
)


def file_ignore_function(output_folder_name):
    def f(src, names):
        return {output_folder_name}

    return f


@dataclass
class Mirror(InternalAction):
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
    symlinks: Literal["copy", "link", "ignore"] = "copy"

    class Arguments(TypedDict):
        sources: list[Path]
        destination: Path

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
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

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
        sources: list[Path] = arguments.get("sources")
        destination: Path = arguments.get("destination")
        symlinks: Path = arguments.get("symlinks")

        ignore = file_ignore_function(ctx.output_folder_name)

        def _ignore_function2(path: str, name: str, pattern=ctx.ignore_pattern):
            if pattern.match(path):
                trace("Copy/ignore: %s", path)
                return True

            #if excludes and excludes.match(path):
            #    trace("Copy/exclude: %s", path)
            #    return True
            return False

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
                    if COPY_LIBRARY == "shutil":
                        shutil.copytree(
                            source,
                            _destination,
                            copy_function=copy_file,
                            dirs_exist_ok=True,
                            ignore=ignore,
                            symlinks=True,
                        )
                    else:
                        copy_tree(
                            source,
                            _destination,
                            ignore=_ignore_function2,
                            symlinks="copy-link" if symlinks else "ignore",
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
