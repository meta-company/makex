from pathlib import Path

from makex.makex_file_types import TaskReference


def main_clean(args, extra):
    """
    - Clean the specified targets in the makex file in the current working directory
    - (support recursive target specifier ... or //...)
    - or, clean all of them
    """
    targets = args.targets

    to_clean: list[tuple[TaskReference, Path]] = []

    if targets:
        for target in targets:
            pass
    else:
        # simply remove the contents of the children of _output_ directory, and all of its children.
        pass
