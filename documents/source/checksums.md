# Hashes and Checksums

Makex uses a number of hashes (or checksums) as part of the execution process to reduce the number of Targets requiring re-execution.

## Hashing Files

Makex will create and store hashes of a Target's input and output files and the hashes of the Makex file in which the target was defined.

Each file has a `hash`, which is a digest; and a `fingerprint`, which is its modification time concatenated with its size. 
A hash is not valid by itself without a fingerprint.

Hashes will be regenerated if no hash for the file has been generated before;
or if the fingerprint of the file doesn't match an existing/stored fingerprint for the corresponding file.

## Target Hashing

Makex uses a strategy to hash Targets. Hashing a Target involves making a unique and stable identifier based on:

- The Target's name.
- The Target's path.
- The Target's required input files.
- The unique and stable identifier of any of the Target's requirements which may be Targets themselves.
- The Target's Runnables, and their arguments.
- The Makex file in which the target was defined. Note: Any changes to this file will cause a target to become stale.
- Any "used" Environment variables. Environment variables which are used in a Makex file are recorded.

If any of these change, the Target will be rebuilt.

## Where hashes are stored

Typically, Makex stores hashes and fingerprints in the extended attributes of a file.

The filesystem of both the cache and workspace SHOULD have extended attributes support.

The following is a non-exhaustive list of filesystems which support extended attributes:

- Linux (Most of them): ext2/3/4, XFS, ZFS, Btrfs...
- Mac: HFS+...
- Windows: FAT, HPFS, NTFS...

The attribute in which the hash and fingerprint is stored is named `user.checksum.{type}`; where `{type}` is one of `sha256` or `md5`.

If Makex detects filesystems without extended attribute support, Makex will fall back to storing checksums in a database.

```{note}
Currently, this detection will fail if the filesystem is read-only.
```
