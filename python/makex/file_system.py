import errno
import logging
import os
from enum import Enum
from os import (
    DirEntry,
    PathLike,
)
from os import makedirs as os_makedirs
from os import readlink as os_readlink
from os import scandir as os_scandir
from os import symlink as os_symlink
from os.path import join as path_join
from pathlib import Path
from shutil import copy2
from typing import (
    Iterable,
    Literal,
    Optional,
    Pattern,
    Protocol,
    Union,
)

from makex.constants import BUILT_IN_REFLINKS

REFLINKS_ENABLED = False

if BUILT_IN_REFLINKS:
    from makex.file_cloning import clone_file
    REFLINKS_ENABLED = True
else:
    try:
        from file_cloning import clone_file
        REFLINKS_ENABLED = True
    except ImportError:
        clone_file = None
        REFLINKS_ENABLED = False

# PERFORMANCE: Optimize these lookups out
_is_dir = DirEntry.is_dir
_is_symlink = DirEntry.is_symlink
_is_file = DirEntry.is_file


def same_fs(file1, file2):
    dev1 = os.stat(file1).st_dev
    dev2 = os.stat(file2).st_dev
    return dev1 == dev2


class ItemType(Enum):
    UNKNOWN = 0
    DIRECTORY = 1
    FILE = 2
    SYMLINK = 3


def find_files(
    path: Union[str, bytes, os.PathLike, DirEntry],
    pattern: Optional[Pattern] = None,
    ignore_pattern: Optional[Pattern] = None,
    ignore_names: Optional[set] = None,
    symlinks=False,
    folders=False,
) -> Iterable[Path]:
    """
    Find files. Use os.scandir for performance.

    :param path: The path to start the search from.
    :param pattern: A pattern of file names to include. Should match a full path.
    :param ignore_pattern: A pattern of file names to ignore. Should match a full path.
    :param ignore_names: Set of names to quickly check for ignores; faster than using the pattern.
    :param symlinks: Yield matching  symlink files.
    :param folders: Yield matching folders.
    :return:
    """
    #trace("Find files in %s: pattern=%s ignore=%s", path.path if isinstance(path, DirEntry) else path, pattern, ignore_names)
    ignore_names = ignore_names or set()

    # XXX: Performance optimization for many calls.
    _ignore_match = ignore_pattern.match if ignore_pattern else (lambda v: False)
    _pattern_match = pattern.match if pattern else lambda v: True

    # TODO: scandir may return bytes: https://docs.python.org/3/library/os.html#os.scandir
    for entry in os_scandir(path):
        name = entry.name
        _path = entry.path

        if name in ignore_names:
            continue

        if _ignore_match(_path):
            continue

        if _is_dir(entry, follow_symlinks=False):
            #XXX: must be the first branch because symlinks can be dirs
            if folders and _pattern_match(_path):
                yield Path(_path)

            yield from find_files(
                path=entry,
                pattern=pattern,
                ignore_pattern=ignore_pattern,
                ignore_names=ignore_names,
                symlinks=symlinks,
                folders=folders,
            )

        if not _pattern_match(_path):
            continue

        if _is_file(entry, follow_symlinks=False):
            yield Path(_path)
        elif symlinks and _is_symlink(entry):
            yield Path(_path)


def safe_reflink(src, dest):
    # EINVAL fd_in and fd_out refer to the same file and the source and target ranges overlap.
    # https://manpages.ubuntu.com/manpages/focal/en/man2/copy_file_range.2.html
    # EINVAL when handling ioctl: The filesystem does not support reflinking the ranges of the given files.

    # XXX: THIS DOESN'T WORK. Tried it. Inodes should be the same
    # Returns from this function when it should actually do a copy. Could be an fs error.
    # IOError: [Errno 2] No such file or directory
    #a = os.stat(src)
    #b = os.stat(dest)
    #if a.st_ino == b.st_ino:
    #    return

    try:
        clone_file(src, dest)
    except IOError as reflink_error:
        logging.error("Reflink error: %s", reflink_error)
        # Fall back to old [reliable] copy function if we get an EINVAL error.
        if reflink_error.errno == errno.EINVAL:
            logging.warning(
                "Error with reflinks. Falling back to using copy.", exc_info=reflink_error
            )
            try:
                copy2(src, dest)
            except OSError as copy_error:
                raise copy_error
        else:
            raise reflink_error
    except Exception as reflink_error:
        logging.error("Reflink implementation had an unknown error: %s", reflink_error)
        logging.exception(reflink_error)
        raise reflink_error


def shutil_compatible_copy_file(source, destination):
    #if path_exists(destination):
    #    # if a path exists, unlink it matching shutil.copy behavior (overwriting a file).
    #    # clone_file will fail if the destination exists.
    #    # TODO: remove this once we replace copytree for one less stat call.
    #    os_unlink(destination)
    safe_reflink(source, destination)


def shutil_copy_file(source, destination):
    #if path_exists(destination):
    #    # if a path exists, unlink it matching shutil.copy behavior (overwriting a file).
    #    # clone_file will fail if the destination exists.
    #    # TODO: remove this once we replace copytree for one less stat call.
    #    os_unlink(destination)
    copy2(source, destination)


class IgnoreFunction(Protocol):
    def __call__(self, folder: str, file_name: str) -> bool:
        """
        Return True if a file should be ignored by this function.
        
        :param folder: 
        :param file_name: 
        :return: 
        """
        ...


def copy_tree(
    source: Union[str, PathLike],
    destination: Union[str, PathLike],
    ignore: IgnoreFunction = None,
    copy=shutil_copy_file,
    symlinks: Literal["ignore", "copy-link", "copy-data"] = "copy-link",
):
    """
    Copies a folder tree using scandir.
    
    shutil is broken: the ignore function protocol has us creating huge sets in memory slowing down significantly.
    """
    _source = os.fspath(source)
    os_makedirs(destination, exist_ok=True)

    with os_scandir(_source) as entries:
        for entry in entries:
            if ignore and ignore(_source, entry.name) is True:
                continue

            source_path = path_join(_source, entry.name)
            destination_path = path_join(destination, entry.name)

            if _is_dir(entry, follow_symlinks=False):
                copy_tree(
                    source_path,
                    destination_path,
                    symlinks=symlinks,
                    ignore=ignore,
                    copy=copy,
                )
            elif _is_file(entry, follow_symlinks=False):

                #trace("Copy file data %s -> %s", source_path, destination_path)
                copy(source_path, destination_path)
            elif _is_symlink(entry):
                if symlinks == "copy-link":
                    linkto = os_readlink(source_path)
                    os_symlink(linkto, destination_path)
                    #trace("Copy symlink as is %s → %s", linkto, destination_path)
                elif symlinks == "copy-data":
                    linkto = os_readlink(source_path)
                    copy(linkto, destination_path)
                    #trace("Copy symlink data %s → %s", linkto, destination_path)
                elif symlinks == "ignore":
                    continue
