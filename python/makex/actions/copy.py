import logging
import shutil
from dataclasses import dataclass
from os.path import join
from pathlib import Path
from re import Pattern
from typing import (
    Any,
    Iterable,
    Optional,
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
    MAKEX_SYNTAX_VERSION,
)
from makex.makex_file_actions import InternalAction
from makex.makex_file_paths import (
    parse_possible_task_reference,
    resolve_pathlike,
    resolve_pathlike_list,
)
from makex.makex_file_types import (
    AllPathLike,
    Glob,
    ListTypes,
    PathElement,
    PathLikeTypes,
    TaskPath,
    TaskReferenceElement,
    TaskSelfOutput,
)
from makex.patterns import (
    combine_patterns,
    make_glob_pattern,
)
from makex.protocols import CommandOutput
from makex.python_script import (
    FILE_LOCATION_ARGUMENT_NAME,
    FileLocation,
    ListValue,
    PythonScriptError,
    StringValue,
    get_location,
)
from makex.target import (
    ArgumentData,
    Task,
)


@dataclass
class Copy(InternalAction):
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
    def build(
        cls,
        source,
        destination,
        exclude=None,
        name=None,
        location=None,
        syntax=MAKEX_SYNTAX_VERSION
    ):
        # find/parse any task references early
        _source = list(cls._process_source(source, syntax=syntax))

        return cls(
            source=_source,
            destination=destination,
            exclude=exclude,
            name=name,
            location=location,
        )

    @classmethod
    def _process_source(cls, source: Union[PathLikeTypes], syntax=MAKEX_SYNTAX_VERSION):
        # find/parse any task references early
        if isinstance(source, StringValue):
            yield parse_possible_task_reference(source, syntax=syntax)
        elif isinstance(source, ListTypes):
            for item in source:
                yield from cls._process_source(item, syntax=syntax)
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

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
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
        self, ctx: Context, target: Task, arguments: ArgumentData
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

        def _ignore_function2(path: str, name: str, pattern=ignore_pattern):
            if pattern.match(path):
                trace("Copy/ignore: %s", path)
                return True

            if excludes and excludes.match(path):
                trace("Copy/exclude: %s", path)
                return True
            return False

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
                        if COPY_LIBRARY == "shutil":

                            shutil.copytree(
                                source,
                                _destination,
                                dirs_exist_ok=True,
                                copy_function=copy_file,
                                ignore=_ignore_function,
                                symlinks=True,
                            )
                        else:
                            copy_tree(
                                source,
                                _destination,
                                ignore=_ignore_function2,
                                symlinks="copy-link",
                            )

                    except (shutil.Error) as e:
                        # XXX: capture OSErrors from shutil with file exists. these are spurious (i think).
                        real_error = False
                        # XXX: Must be above OSError since it is a subclass.
                        # XXX: shutil returns multiple errors inside an error
                        string = [f"Error copying tree {source} to {destination}:"]
                        for tup in e.args:
                            for error in tup:
                                e_source, e_destination, exc = error

                                # XXX: hardcoded error string because that's what shutil does.
                                # TODO: fix this. replace shutil.
                                if "[Errno 17]" in exc:
                                    ctx.ui.warn(
                                        f"There may have been a problem copying files that already exist: {e_source}"
                                    )
                                    continue

                                string.append(
                                    f"\tError copying to  {e_destination} from {e_source} {e.errno}\n\t\t{exc} {copy_file}"
                                )
                                real_error = True
                        if ctx.debug:
                            logging.exception(e)

                        if real_error:
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
