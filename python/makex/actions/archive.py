import logging
import os
import tarfile
import typing
import zipfile
from pathlib import Path
from typing import (
    Any,
    Literal,
)

from makex._logging import (
    debug,
    trace,
)
from makex.context import Context
from makex.makex_file_actions import InternalAction
from makex.makex_file_paths import (
    resolve_pathlike,
    resolve_pathlike_list,
)
from makex.makex_file_types import (
    AllPathLike,
    PathLikeTypes,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
    FileLocation,
    PythonScriptError,
)
from makex.target import (
    ArgumentData,
    Task,
)

_SUFFIX_ZIP = (".zip", )
_SUFFIX_TAR_GZ = (".tar", ".gz")
_SUFFIX_TAR = (".tar", )
_ARCHIVE_TYPES: dict[tuple[str, ...], str] = {
    _SUFFIX_TAR: "tar",
    _SUFFIX_TAR_GZ: "tar.gz",
    _SUFFIX_ZIP: "zip",
}


class Archive(InternalAction):
    """
    
    archive(
        path=task_path("rpm") / "SOURCES/makex-source.zip",
        path="makex.tar",
        type=None, # automatically inferred from extension

        # list of files to add to the archive.
        items=[
            "file",
            find(),
        ],
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

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
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
        #        location=task.location or self.location,
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

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
        type = arguments.get("type")

        logging.debug("Creating archive...")
        if type == "zip":
            return self._run_zip(ctx, target, arguments=arguments)
        elif type == "tar.gz":
            return self._run_tar(
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

    def _run_tar(self, ctx, target, arguments, compression: Literal["gz", "bz2", "xz"] = None):
        files: list[Path] = arguments.get("files")
        root = arguments.get("root")
        _compression = f":{compression}" if compression else ""

        # TODO: exclude globally ignored files
        def reset(tarinfo):
            tarinfo.uid = tarinfo.gid = 0
            tarinfo.uname = tarinfo.gname = "root"
            return tarinfo

        path = arguments.get("path")
        debug("Writing tar file to %s", path)

        _prefix = ""
        if prefix := arguments.get("prefix", ""):
            _prefix = f"{prefix}/"

        with tarfile.open(path, f"w{_compression}", format=tarfile.PAX_FORMAT) as tar:
            for file in files:
                # the name in the archive should always be relative so it may be extracted anywhere
                # ./{path}
                #if file.is_relative_to(root):
                #    arcname = file.relative_to(root).as_posix()
                #    trace("Make relative path %s to %s", arcname, file)
                #    arcname = f"./{arcname}"
                #else:
                arcname = f"./{_prefix}{file.name}"
                if file.is_dir():
                    pass

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
