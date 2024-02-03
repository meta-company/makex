import logging
import os
from enum import Enum
from os import DirEntry
from pathlib import Path
from shutil import copy2
from typing import (
    Iterable,
    Pattern,
    cast,
    Union,
)

REFLINK_PACKAGE_DETECTED = True

try:
    from reflink import reflink
except ImportError:
    REFLINK_PACKAGE_DETECTED = False


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
    # TODO: scandir may return bytes: https://docs.python.org/3/library/os.html#os.scandir
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
    #    # same file. don't reflink otherwise we'll get:
    #    return

    try:
        reflink(src, dest)
    except IOError as e:
        # Fall back to old [reliable] copy function if we get an EINVAL error.
        if str(e).startswith("EINVAL"):
            logging.warning("Error with reflinks. Falling back to using copy.", exc_info=e)
            try:
                copy2(src, dest)
            except OSError as copy_error:
                raise copy_error
        else:
            raise e
    except Exception as e:
        logging.error("Reflink implementation had an unknown error: %s", e)
        logging.exception(e)
        raise e

    #try:
    #    reflink(src, dest)
    #except OSError as e:
    #    raise Exception(f"Error making reflink to {dest} from {src}: {e}")
