# Hashes and Checksums

Makex uses hashes (or checksums) as part of the execution process to reduce the Tasks requiring re-execution.

## Hashing Files

Makex will create and store hashes of a Task's input and output files, 
and the hashes of the Makex file in which the task was defined.

Each file has a `hash`, which is a digest; and a `fingerprint`, 
which is its modification time concatenated with its size. 
A hash is not valid by itself without a fingerprint.

Hashes will be regenerated if no hash for the file has been generated before;
or if the fingerprint of the file doesn't match an existing/stored fingerprint for the corresponding file.

## Task Hashing

Makex uses a strategy to hash Tasks. Hashing a Task involves making a unique and stable identifier based on:

- The Task's name.
- The Task's output path.
- The Task's required input files.
- The unique and stable identifier of any of the Task's requirements which may be Tasks themselves.
- The Task's Actions, and their arguments.
- The Makex file in which the task was defined. Note: Any changes to this file will cause a task to become stale.
- Any Environment variables _used_ in the Makex File. Environment variables which are used in a Makex file are recorded.

If any of these change, the Task will be re-executed.

## Where hashes are stored

Typically, Makex stores hashes and fingerprints in the extended attributes of a file.

The filesystem of both the cache and workspace SHOULD have extended attributes support.

The following is a non-exhaustive list of filesystems which support extended attributes:

- Linux (Most of them): ext2/3/4, XFS, ZFS, Btrfs...
- Mac: HFS+...
- Windows: FAT, HPFS, NTFS...

The attribute in which the hash and fingerprint is stored is named `user.checksum.{type}`; 
where `{type}` is one of `sha256` or `md5`.

If a filesystem without extended attribute support is detected, Makex will fall back to storing hashes in a database.

```{note}
Currently, this detection will fail if the filesystem is read-only.
```
