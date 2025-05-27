import dataclasses
from enum import Enum
from pathlib import Path

from makex.constants import ABSOLUTE_WORKSPACE
from makex.workspace import get_workspace


class ScopePart(Enum):
    RECURSIVE = "..."


@dataclasses.dataclass
class ParsedScope:
    path: Path
    type: ScopePart = None


def parse_scope(scope):
    type = None
    if scope.startswith(ABSOLUTE_WORKSPACE):
        workspace = get_workspace()
        if workspace is None:
            raise Exception("Workspace prefix // used but no WORKSPACE defined.")
        path = workspace / Path(scope[2:])
        name = path.name

        if name == "...":
            type = ScopePart.RECURSIVE

        return ParsedScope(path, type)
    else:
        path = Path(scope)
        if not path.is_absolute():
            path = Path.cwd() / path

    if not path.exists():
        raise Exception(f"Path in scope {scope} does not exist (Expected: {path}).")

    return ParsedScope(path, type)
