import sqlite3
from contextlib import contextmanager
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Optional

from makex._logging import debug, info
from makex.file_checksum import FileChecksum

DATABASE_VERSION = 3


@contextmanager
def transaction(conn):
    # From: https://charlesleifer.com/blog/going-fast-with-sqlite-and-python/
    # We must issue a "BEGIN" explicitly when running in auto-commit mode.
    conn.execute('BEGIN')
    try:
        # Yield control back to the caller.
        yield
    except Exception as e:
        conn.rollback() # Roll back all changes if an exception occurs.
        raise e
    else:
        conn.commit()


def upgrade_3(backend: "SqliteMetadataBackend"):
    result = backend._execute("DROP TABLE IF EXISTS files")
    result = backend._execute(
        "CREATE TABLE IF NOT EXISTS files (path TEXT, fingerprint TEXT, checksum_type TEXT, checksum TEXT,  date TEXT)"
    )
    backend._execute(f"PRAGMA user_version=3")

class SqliteMetadataBackend:
    def __init__(self, path: Path):
        debug("Connecting to sqlite database at %s", path)
        self.con = sqlite3.connect(path.as_posix())
        self.cur = self.con.cursor()
        # raise a database needs upgrade error.
        self.cur.execute("PRAGMA journal_mode=WAL")
        # increase cache from default 2MB to 16000KiB (note negatives are kilobytes)
        self.cur.execute("PRAGMA cache_size=-16000")
        # mmap size is zero by default (disabled). increase it to 20MB.
        # https://sqlite.org/mmap.html
        self.cur.execute("PRAGMA mmap_size=20000000")

        # TODO: check user_version pragma to check if our schema is still valid
        version = self._get_one("PRAGMA user_version")

        debug("Database version %s < %s", version, DATABASE_VERSION)

        if version is not None and version > 0:
            version = int(version)

            if version == 2:
                info("Upgrading database to version 3...")
                # move any old database file before initialization
                #if version == 2:
                upgrade_3(self)
                version = 3
        else:
            self.initialize()

        # TODO: use an LRU here to keep hot things
        self._target_cache = {}

    def _execute(self, query, *args):
        self.con.execute(query, args)

    def _get_one(self, query, *args):
        res = self.cur.execute(query, args)
        result = res.fetchone()
        if result is None:
            return None

        return result[0]

    def _get_row(self, query, *args):
        res = self.cur.execute(query, args)
        result = res.fetchone()
        if result is None:
            return None

        return result

    def has_target(self, target_key: str, target_hash: str) -> bool:
        # return true if the db has the target with a hash (it was executed).
        count = self._get_one(
            "SELECT count(*) FROM targets WHERE key = ? AND hash = ?", target_key, target_hash
        )
        if count:
            return True

        return False

    def put_target(self, key, target_hash):
        time = datetime.now(timezone.utc)
        time = time.strftime("%Y-%m-%d %H:%M:%S")
        with transaction(self.con):
            self._execute("INSERT INTO targets VALUES(?, ?, ?)", key, target_hash, time)

    def has_file(self, path, fingerprint):
        count = self._get_one(
            "SELECT count(*) FROM files WHERE path = ? AND fingerprint = ?", path, fingerprint
        )
        if count:
            return True

        return False

    def get_file_checksum(self, path: str, fingerprint: str) -> Optional[FileChecksum]:
        count = self._get_row(
            "SELECT checksum_type, checksum FROM files WHERE path = ? AND fingerprint = ?",
            path,
            fingerprint
        )
        if count is None:
            return None

        return FileChecksum(FileChecksum.Type(count[0]), count[1], fingerprint)

    def put_file(self, path: str, fingerprint: str, checksum_type: str, checksum: str):
        # store checksums for input/output files (out of band)
        # tombstone/delete any other records for file
        time = datetime.now(timezone.utc)
        time = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with transaction(self.con):
                self._execute(
                    "INSERT into files values (?, ?, ?, ?, ?)",
                    path,
                    fingerprint,
                    checksum_type,
                    checksum,
                    time
                )
        except sqlite3.IntegrityError as e:
            raise e

    def initialize(self):
        cur = self.cur
        with transaction(self.con):
            # drop and create tables
            # drop table if exists targets
            result = self._execute("DROP TABLE IF EXISTS targets")
            result = self._execute("DROP TABLE IF EXISTS files")
            result = self._execute(
                "CREATE TABLE IF NOT EXISTS targets (key TEXT, hash TEXT, date TEXT)"
            )
            result = self._execute(
                "CREATE TABLE IF NOT EXISTS files (path TEXT, fingerprint TEXT, checksum_type TEXT, checksum TEXT,  date TEXT)"
            )
            self._execute(f"PRAGMA user_version={DATABASE_VERSION}")

    def clear(self):

        with self.con:
            res = self._execute("delete from targets")
            res = self._execute("delete from files")
