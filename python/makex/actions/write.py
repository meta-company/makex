from dataclasses import dataclass
from pathlib import Path
from typing import Any

from makex._logging import debug
from makex.context import Context
from makex.errors import ExecutionError
from makex.makex_file_actions import InternalAction
from makex.makex_file_paths import (
    join_string,
    resolve_pathlike,
)
from makex.makex_file_types import PathLikeTypes
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
    JoinedString,
    StringValue,
    get_location,
)
from makex.target import (
    ArgumentData,
    Task,
)


@dataclass
class Write(InternalAction):
    """
        Writes data to a file.

        write(file, *data)

        Data may be a string, path or other encodable object, or a list of them. None values are skipped.

        Amalgamations can be made by passing a path to a file:

        write("file.cpp", "\n// begin file\n", path(), "\n// end file\n")

        TODO: support file paths and variable argument lists of items.
    """
    path: PathLikeTypes
    data: StringValue
    executable: bool = False

    def __init__(
        self, path: PathLikeTypes, data: StringValue = None, executable=False, location=None
    ):
        self.path = path
        self.data = data
        self.location = location
        self.executable = False

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
        args = {}
        args["path"] = path = resolve_pathlike(ctx, target, base=target.path, value=self.path)

        data = self.data
        if isinstance(data, StringValue):
            data = data.value
        elif isinstance(data, JoinedString):
            data = join_string(ctx, task=target, base=target.path, string=data).value
        elif data is None:
            data = ""
        else:
            raise ExecutionError(
                f"Invalid argument text argument to write(). Got {data!r} {type(data)}. Expected string.",
                target,
                location=get_location(data, target.location)
            )

        args["data"] = data
        args["executable"] = self.executable
        return ArgumentData(args, inputs=[path])

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
        path: Path = arguments.get("path")
        data = arguments.get("data")

        ctx.ui.print(f"Writing {path}")

        if ctx.dry_run is False:
            if not path.parent.exists():
                path.parent.mkdir(mode=0o755, parents=True)

        if data is None:
            debug("Touching file at %s", path)
            if ctx.dry_run is False:
                path.touch(exist_ok=True)
        elif isinstance(data, str):
            debug("Writing file at %s", path)
            if ctx.dry_run is False:
                try:
                    path.write_text(data)
                except IsADirectoryError as e:
                    raise ExecutionError(
                        f"Invalid argument path argument to write(): Is a folder: {path}",
                        target,
                        location=target.location,
                    )
        else:
            raise ExecutionError(
                "Invalid argument data argument to write()", target, location=target.location
            )

        if self.executable:
            path.chmod(0o755)

        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        parts = [
            arguments.get("path").as_posix(),
            arguments.get("data"),
        ]
        return hash_function("|".join(parts))
