---
status: Accepted
---
# Archive Action

This proposal specifies an `archive()` action in makex to archive files.

Files may be archived from arbitrary locations, or from a Tasks output path.

## Specification

```python
from typing import Literal,Union
from makex.typing import MultiplePathLike, PathLike, String, Path

def archive(
    path: String,
    type: Literal["tar.gz","zip","tar"]=None,
    items: list[MultiplePathLike]=None,
    prefix: Union[String,Path]=None,
):
    """
    :param path: File name/path of the archive. If just a name, it will be stored in the task's output folder.
    :param type: Optional type. Inferred from name.
    :param items: List of files/folders to add to the archive. May use find/glob to find files to include. If left empty, it will archive all the files inside the task's folder.
    :param prefix: Name/path to prefix items in the archive with.
    """
    pass
```

### Prefix Argument

The prefix parameter is defined, as prefixing is common (e.g. for source archives, a folder `name-version`).

The prefix accepts a relative path which will be used to prefix all items in the archive.

## Path Argument

The name `path` was chosen over `name` as one may want to immediately create/store the archive outside a task path.

## Items Argument

The name `items` was chosen over `files` as one may want to archive files and folders.

Items is a list of files (absolute, or relative to the task's output).

## Rejected Ideas

### Root Argument

- The root argument is confusing. 
- We can create roots explicitly, as we choose, with actions.

The root defaults to the Tasks output path. 
Any files referenced outside the task's output folder will be added to the archive root folder.
