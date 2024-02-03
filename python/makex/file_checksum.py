import hashlib
import logging
import os
import shutil
import stat
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import (
    BinaryIO,
    Optional,
    Tuple,
)

import xattr

INODE_IN_FINGERPRINT = False

# must be prefixed with user. otherwise we will get OSError, Operation not supported
#from xattr import getxattr

TEST_KEY = b"user.test"
TEST_VALUE = b"test"


def get_digest_data(data: BinaryIO, hash_func=hashlib.sha256):
    h = hash_func()
    while True:
        # Reading is buffered, so we can read smaller chunks.
        chunk = data.read(h.block_size)
        if not chunk:
            break
        h.update(chunk)

    return h.hexdigest()


def get_digest(file_path, hash_func=hashlib.sha256):
    with open(file_path, 'rb') as file:
        return get_digest_data(file, hash_func=hash_func).upper()


LOGGER = logging.getLogger("file_checksum")


class FileChecksum:
    """
    Calculates the digest/checksum of a file, and stores it in extended attributes.

    In order to maintain stability, if any of the following change, the checksum is recomputed.

    mtime
    size
    inode number
    file mode
    owner uid and gid
    (targets only) the sequence number of the last time it was built

    We use mtime because ctime is too sensitive/false positive.

    """
    class Type(Enum):
        SHA256 = "sha256"
        MD5 = "md5"

    def __init__(self, type:Type, value, fingerprint: str = None):
        self.type = type
        self.value = value
        self.fingerprint = fingerprint

    def __repr__(self):
        return f"FileChecksum({self.type.value}:{self.value})"

    def __str__(self):
        if self.fingerprint is not None:
            return f"{self.type.value}:{self.value}:{self.fingerprint}"

        return f"{self.type.value}:{self.value}"

    def __hash__(self):
        return hash(f"{self.type.value}:{self.value}")

    @classmethod
    def parse(cls, string, fingerprint=None) -> "FileChecksum":
        assert isinstance(string, str)
        parts = string.split(":")
        if len(parts) == 2:
            type, value = parts
            return cls(FileChecksum.Type(type), value, fingerprint)
        elif len(parts) == 3:
            type, value, fingerprint = parts
            return cls(FileChecksum.Type(type), value, fingerprint)
        else:
            raise ValueError("Invalid number of parts.")

    @classmethod
    def from_data(cls, data: BinaryIO, type=Type.SHA256, fingerprint=None) -> "FileChecksum":
        d = get_digest_data(data)
        return cls(FileChecksum.Type(type), d, fingerprint)

    def __eq__(self, other: "FileChecksum"):
        assert isinstance(other, FileChecksum), f"got {other} {type(other)}"
        return self.type == other.type and self.value == other.value and self.fingerprint == other.fingerprint

    @classmethod
    def create(cls, path: Path, type: Type = Type.SHA256) -> "FileChecksum":
        """
        Creates a checksum if not already created.
        :param path:
        :param type:
        :return:
        """
        csum, csum_fingerprint, fingerprint = get_attributes(path, type)
        x = xattr.xattr(path.as_posix())

        #csum = None
        #csum_fingerprint = None

        #csum, csum_fingerprint = get_xattr(path, type)

        #try:
        #    csum = x.get(f"user.checksum.{type.value}").decode("ascii")
        #    csum_fingerprint = x.get(f"user.checksum.{type.value}.fingerprint").decode("ascii")
        #except IOError:
        #    # xattr raises exceptions if the file doesn't have the properties
        #    pass

        if csum and csum_fingerprint:
            if fingerprint == csum_fingerprint:
                return cls(type, csum, fingerprint)

        # recalc hash
        #t = datetime.now().timestamp()
        LOGGER.debug(
            "Creating new checksum of file %s %s != %s", path, fingerprint, csum_fingerprint
        )
        d = get_digest(path)

        # XXX: We should do this outside this function.
        if not os.access(path, os.W_OK):
            st = os.stat(path)
            new_mode = st.st_mode | stat.S_IXUSR | stat.S_IWGRP | stat.S_IWGRP | stat.S_IWRITE
            LOGGER.debug(f"Updating file mode {new_mode}: %s", path)
            os.chmod(path, new_mode)

        x.set(f"user.checksum.{type.value}", bytes(f"{d}:{fingerprint}", "ascii"))
        #x.set(f"user.checksum.{type}.time", str(t).encode("ascii"))
        #x.set(f"user.checksum.{type.value}.fingerprint", fingerprint.encode("ascii"))
        return cls(type, d, fingerprint)

    @classmethod
    def make(cls, path: Path, fingerprint:str, type: Type = Type.SHA256) -> "FileChecksum":
        d = get_digest(path)
        return cls(type, d, fingerprint)

    @staticmethod
    def verify(path: Path, type: Type = Type.SHA256) -> bool:
        """
        Compare the stored checksum with file data and return True if they match.

        Does not store a checksum.

        Returns True if:
        - there is no valid checksum/time extended attributes
        - stored checksum matches with new checksum

        Returns False if:
        - the fingerprint != stored fingerprint
        - the stored checksum doesn't match

        :param path:
        :param type:
        :return:
        """
        fingerprint = get_fingerprint(path)

        assert path.exists(), f"Missing path {path}"

        csum, csum_fingerprint = get_xattr(path, type)

        if not csum or not csum_fingerprint or not fingerprint:
            # can't verify files with no stored checksum/time.
            logging.debug("Cant verify %s", path)
            return False

        if fingerprint != csum_fingerprint:
            logging.debug(
                "differeing fingerprint %s: %s != %s", path, fingerprint, csum_fingerprint
            )
            # file was modified since its checksum time
            #modtime = path.stat().st_mtime
            #if modtime > csumtime:
            return False

        d = get_digest(path)
        logging.debug("CSUM %s == %s", csum, d)
        if csum == d:
            return True

        logging.debug("Difering csum %s: %s != %s", path, csum, d)
        return False

    @staticmethod
    def is_fingerprint_valid(path: Path, type: Type = Type.SHA256) -> bool:
        """
        Return true if the file attached checksum is still valid.

        if the file doesn't have a checksum, we don't presume any staleness
        :param path:
        :param type:
        :return:
        """
        fingerprint = get_fingerprint(path)
        if fingerprint is None:
            return False

        csum, csum_fingerprint = get_xattr(path, type)

        if csum_fingerprint is None:
            return False

        #logging.debug("Filechecksum %s == %s == %s", csum_fingerprint, fingerprint, csum_fingerprint == fingerprint)
        return csum_fingerprint == fingerprint

    @staticmethod
    def refresh_fingerprint(path: Path, type: Type = Type.SHA256) -> bool:
        # Force the refresh of a stored fingerprint of path.
        # when INODE_IN_FINGERPRINT is enabled, Must be used when copying otherwise checksums of copied files will be invalid.
        # inodes (may/likely) change when files are copied, no matter copy on write.
        csum, csum_fingerprint = get_xattr(path, type)

        if csum is None:
            return False

        fingerprint = get_fingerprint(path)
        x = xattr.xattr(path.as_posix())
        x.set(f"user.checksum.{type.value}", bytes(f"{csum}:{fingerprint}", "ascii"))
        return True

    @classmethod
    def compare(cls, a, b):
        """
        Compare the xattrs of a and b and

        :param a:
        :param b:
        :return:
        """
        # Return true if one checksum is equal to another
        asum = get_attributes(a)
        bsum = get_attributes(b)
        return asum == bsum

    @staticmethod
    def check(path: Path, value: str, type: Type = Type.SHA256) -> bool:
        d = get_digest(path)
        return value == d

    @staticmethod
    def check_supported(path: Path):
        """
        Return True if the path/directory supports extended attributes required for file attached checksums.
        :param path:
        :return:
        """
        if not path.is_dir():
            raise ValueError(f"{path} is not a directory. Directory Expected.")

        result = False

        with NamedTemporaryFile("w+b", dir=path) as f:
            try:
                fname = f.name.encode("utf-8")
                xattr.setxattr(fname, TEST_KEY, TEST_VALUE)

                if xattr.getxattr(fname, TEST_KEY) == TEST_VALUE:
                    xattr.removexattr(fname, TEST_KEY)
                    result = True
            except IOError as e:

                logging.error("IOERROR {}")
                logging.exception(e)
                result = False

        logging.debug("Check extended attributes supported at %s = %s.", path, result)
        # we shouldn't be here. faulty xattr implementation (can set, but not get).
        return result

    @staticmethod
    def copy(source: Path, destination: Path, type: Type = Type.SHA256):
        try:
            csum, fingerprint = get_xattr(source, type)
        except IOError as e:
            return False

        x = xattr.xattr(destination.as_posix())

        if INODE_IN_FINGERPRINT:
            # regenerate a fingerprint when copying with inodes in the fingerprint
            # inodes (may/likely) change when files are copied, no matter copy on write.
            fingerprint = get_fingerprint(destination).encode("ascii")

        x.set(f"user.checksum.{type.value}", bytes(f"{csum}:{fingerprint}", "ascii"))

    @staticmethod
    def fingerprint(path: Path, type: Type = Type.SHA256):
        return get_fingerprint(path)


def copy_with_checksum(source, destination):
    shutil.copy2(source, destination)
    #shutil.copystat(source, destination)
    FileChecksum.copy(source, destination)


def get_xattr(path: Path, type: FileChecksum.Type) -> tuple[str, str]:
    assert isinstance(type, FileChecksum.Type)
    #logging.debug("Chek sadad %s", type.value)

    x = xattr.xattr(path.as_posix())
    try:
        csum = x.get(f"user.checksum.{type.value}").decode("ascii")
        csum, csum_fingerprint = csum.split(":")

    except ValueError:
        return None, None
    except IOError as e:
        #logging.exception(e)
        return None, None

    return csum, csum_fingerprint


def get_fingerprint(path: Path) -> Optional[str]:
    # Return None
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None

    mtime = stat.st_mtime
    mtime_ns = stat.st_mtime_ns
    modified_time = mtime_ns or mtime
    if INODE_IN_FINGERPRINT:
        return f"{stat.st_ino}_{modified_time}_{stat.st_size}"

    return f"{modified_time}_{stat.st_size}"


def get_attributes(path,
                   type: FileChecksum.Type) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    # check if still valid

    fingerprint = get_fingerprint(path)
    x = xattr.xattr(path.as_posix())

    csum = None
    csum_fingerpint = None

    try:
        csum = x.get(f"user.checksum.{type.value}").decode("ascii")
        csum, csum_fingerpint = csum.split(":")#x.get(f"user.checksum.{type.value}.fingerprint").decode("ascii")
    except ValueError:
        return None, None, None
    except IOError:
        # xattr raises exceptions if the file doesn't have the properties
        pass

    #if fingerprint != csum_fingerpint:
    #    return None, None, fingerprint

    return csum, csum_fingerpint, fingerprint
