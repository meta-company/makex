from typing import (
    Any,
    Union,
)

from makex.context import Context
from makex.makex_file_actions import (
    InternalAction,
    resolve_string_argument,
)
from makex.makex_file_paths import (
    resolve_path_element_workspace,
    resolve_task_path,
)
from makex.makex_file_types import (
    PathElement,
    PathLikeTypes,
    TaskPath,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
    FileLocation,
    PythonScriptError,
    StringValue,
)
from makex.target import (
    ArgumentData,
    Task,
)


class SetEnvironment(InternalAction):
    NAME = "set_environment"
    environment: dict[StringValue, Union[StringValue, PathLikeTypes]]

    def __init__(self, environment: dict, location: FileLocation):
        self.environment = environment
        self.location = location

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
        env = {}

        # transform all values to strings.
        for k, v in self.environment.items():
            value = resolve_string_argument(ctx, target, target.input_path, v)

            if False:
                if isinstance(v, StringValue):
                    value = v.value
                elif isinstance(v, PathElement):
                    value = resolve_path_element_workspace(
                        ctx, target.workspace, v, target.input_path
                    )
                    value = value.as_posix()
                elif isinstance(v, TaskPath):
                    value = resolve_task_path(ctx, v).as_posix()
                elif isinstance(v, (int)):
                    value = str(v)
                else:
                    raise PythonScriptError(
                        f"Invalid type of value in environment key {k}: {v!r} {type(v)}",
                        location=self.location
                    )

            env[str(k)] = value

        # TODO: input any paths/files referenced here as inputs
        return ArgumentData({"environment": env})

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
        env = arguments.get("environment", {})
        ctx.environment.update(env)
        return CommandOutput(0)

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        environment = arguments.get("environment")
        environment_string = ";".join(f"{k}={v}" for k, v in environment.items())
        return hash_function(environment_string)
