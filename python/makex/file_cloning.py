"""
Native python implementation of file cloning (aka reflinks).

- In linux, this is done with an ioctl (ioctl_ficlonerange, )
- Apple has a clonefile system call.
- Windows has DUPLICATE_EXTENTS_TO_FILE.

The following filesystems support file cloning: bcachefs, btrfs, XFS, ZFS (unstable, 2.2.0+), OCFS2, APFS and ReFSv2.

"""

import errno
import os
import sys
from typing import Union

# True if the Operating has some support for a reflink like feature.
SUPPORTED = False

if sys.platform in {"linux"}:
    # XXX: Assume there is some support.
    SUPPORTED = True

    import fcntl

    # TODO: Investigate FICLONERANGE.
    FICLONE = 0x40049409

    def _clone_file_platform(source, destination):
        result = -1
        try:
            with open(source) as s, open(destination, "w+") as d:
                result = fcntl.ioctl(d.fileno(), FICLONE, s.fileno())
        finally:
            if result != 0:
                os.unlink(destination)

        # TODO: handle errors from ioctl (man ioctl)

        # SEE: man ioctl_ficlone
        if result == 0:
            return None
        elif result == errno.EINVAL:
            # The filesystem does not support reflinking the ranges of the given files. This error can also appear if either
            # file descriptor represents a device, FIFO, or socket. Disk filesystems generally require the offset and length
            # arguments to be aligned to the fundamental block size.
            # XFS and Btrfs do not support overlapping reflink ranges in the same file.
            raise IOError(
                result,
                f"EINVAL: Error creating link from {source} to {destination}",
                source,
                None,
                destination
            )
        elif result == errno.EBADF:
            # source is not open for reading;
            # dest is no open for writing, or is open for append-only writes;
            # or the fs which source resides on doesn't support reflinks
            raise IOError(
                result,
                f"EBADF: Error creating link from {source} to {destination}: "
                f"Source/destionion can't be opened or fs doesn't support reflinks.",
                source,
                None,
                destination
            )
        elif result == errno.EISDIR:
            raise IOError(
                result,
                f"EISDIR: Error creating link from {source} to {destination}: "
                f"One of the files is a directory.",
                source,
                None,
                destination
            )
        elif result == errno.EOPNOTSUPP:
            raise IOError(
                result,
                f"EOPNOTSUPP: Error creating link from {source} to {destination}: "
                f"Filesystem doesn't support reflinking, or one of the files is a special node.",
                source,
                None,
                destination
            )
        elif result == errno.EPERM:
            raise IOError(
                result,
                f"EPERM: Error creating link from {source} to {destination}: "
                f"Destination is immutable.",
                source,
                None,
                destination
            )
        elif result == errno.ETXTBSY:
            raise IOError(
                result,
                f"ETXTBSY: Error creating link from {source} to {destination}: "
                f"One of the files is a swap file",
                source,
                None,
                destination
            )
        elif result == errno.EXDEV:
            raise IOError(
                result,
                f"EXDEV: Error creating link from {source} to {destination}: Source and destination are not on the same filesystem.",
                source,
                None,
                destination
            )
        elif result != 0:
            raise IOError(
                result,
                f"Unknown Error. Can't create reflink from {source} to {destination}",
                source,
                None,
                destination
            )

elif sys.platform in {"darwin"}:
    import ctypes

    LIBC = "libc.dylib"
    LIBC_FALLBACK = "/usr/lib/libSystem.dylib"

    try:
        _libc = ctypes.CDLL(LIBC)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise e
        try:
            # NOTE: trying to bypass System Integrity Protection (SIP)
            _libc = ctypes.CDLL(LIBC_FALLBACK)
        except OSError as e:
            _libc = object()

    if not hasattr(_libc, "clonefile"):
        SUPPORTED = False
    else:
        SUPPORTED = True

        _CHAR_P = ctypes.c_char_p
        _C_INT = ctypes.c_int
        _clonefile = _libc.clonefile
        _clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        _clonefile.restype = ctypes.c_int

        def _clone_file_platform(source, destination):
            result = _clonefile(
                _CHAR_P(os.fsencode(source)),
                _CHAR_P(os.fsencode(destination)),
                _C_INT(0),
            )

            if result != 0:
                raise IOError(
                    result,
                    f"Error creating reflink from {source} to {destination}. {result}",
                    source,
                    None,
                    destination
                )
            return None

elif sys.platform in {"win32"}:
    SUPPORTED = False


def clone_file(source: Union[str, os.PathLike], destination: Union[str, os.PathLike]):
    """
    :raises [IOError]:
    :param source:
    :param destination:
    :return: None
    """
    _clone_file_platform(os.fspath(source), os.fspath(destination))


def supported_at(path: Union[str, os.PathLike]) -> bool:
    """
    :returns: `True` when a path on the filesystem supports file cloning, `False` otherwise.
    """
    # XXX: There's no way to check reflink support aside from testing it.

    if SUPPORTED is False:
        return False

    a = os.path.join(path, "___a___")
    b = os.path.join(path, "___b___")

    with open(a, 'w+') as f:
        f.write("")
    try:
        _clone_file_platform(a, b)
        return True
    finally:
        os.unlink(a)
        if os.path.isfile(b):
            os.unlink(b)
        return False