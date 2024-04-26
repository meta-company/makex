import errno
import logging
import os
from enum import Enum
from os import DirEntry
from pathlib import Path
from shutil import copy2
from typing import (
    Iterable,
    Pattern,
    Union,
    cast,
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
        REFLINKS_ENABLED = False


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
    pattern: Pattern = None,
    ignore_pattern: Pattern = None,
    ignore_names: set = None,
    symlinks=False,
) -> Iterable[Path]:
    """
    Find files. Use os.scandir for performance.

    :param path:
    :param pattern:
    :param ignore_pattern:
    :param ignore_names:
    :param symlinks:
    :return:
    """
    #trace("Find files in %s: pattern=%s ignore=%s", path.path if isinstance(path, DirEntry) else path, pattern, ignore_names)
    ignore_names = ignore_names or set()

    # XXX: Performance optimization for many calls.
    _ignore_match = ignore_pattern.match
    _pattern_match = pattern.match if pattern else None

    # TODO: scandir may return bytes: https://docs.python.org/3/library/os.html#os.scandir
    for entry in os.scandir(path):
        entry = cast(DirEntry, entry)
        name = entry.name
        path = entry.path

        if name in ignore_names:
            continue

        if entry.is_dir(): #XXX: must be first because symlinks can be dirs
            yield from find_files(
                path=entry,
                pattern=pattern,
                ignore_pattern=ignore_pattern,
                ignore_names=ignore_names,
            )
        elif entry.is_file():

            if ignore_pattern and _ignore_match(path):
                continue

            if pattern is None:
                yield Path(path)
            else:
                if _pattern_match(path):
                    yield Path(path)
        elif symlinks and entry.is_symlink():
            yield Path(path)


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
