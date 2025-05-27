from abc import (
    ABC,
    abstractmethod,
)
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Optional,
    Union,
)

from makex.constants import IGNORE_NONE_VALUES_IN_LISTS
from makex.context import Context
from makex.makex_file_paths import (
    _resolve_task_self_path,
    join_string,
    resolve_path_element_workspace,
    resolve_task_path,
)
from makex.makex_file_types import (
    Expansion,
    PathElement,
    PathLikeTypes,
    TaskPath,
    TaskReferenceElement,
    TaskSelfPath,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
    FileLocation,
    JoinedString,
    PythonScriptError,
    StringValue,
    get_location,
)
from makex.target import (
    ArgumentData,
    Task,
)


class InternalAction(ABC):
    location: FileLocation = None

    implicit_requirements: Optional[list[Union[StringValue, TaskReferenceElement]]] = None

    # TODO: add/collect requirements as we go
    def add_requirement(self, requirement: "TaskReferenceElement"):
        raise NotImplementedError

    def get_implicit_requirements(self, ctx: Context) -> Optional[Iterable[TaskReferenceElement]]:
        """
        Return a list of any task requirements in the action/arguments. Done before argument transformation.

        Any TargetReference or Path used by the task should be returned (except one for the Target itself).

        Used to detect implicit task requirements.
        
        We want to add any targets referenced in steps/task properties, so we can handle/parse them early.
        :return:
        """
        return None

    @abstractmethod
    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
        # transform the input arguments (stored in instances), to a dictionary of actual values
        # keys must match argument keyword names
        raise NotImplementedError

    #implement this with transform_arguments() to get new functionality
    @abstractmethod
    def run_with_arguments(
        self, ctx: Context, target: Task, arguments: ArgumentData
    ) -> CommandOutput:
        raise NotImplementedError

    @abstractmethod
    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # produce a hash of the Action with the given arguments and functions
        raise NotImplementedError

    def __str__(self):
        return PythonScriptError("Converting Action to string not allowed.", self.location)


def string_value_maybe_expand_user(ctx, base, value: StringValue) -> str:
    val = value.value

    if False:
        if val.startswith("~"):
            # TODO: use environment HOME to expand the user
            return Path(val).expanduser().as_posix()
        else:
            return value
    return val


def resolve_string_argument(
    ctx: Context,
    target: Task,
    base: Path,
    value: PathLikeTypes,
) -> Optional[str]:
    if isinstance(value, StringValue):
        # XXX: we're not using our function here because we may not want to expand ~ arguments the way bash does
        # bash will replace a ~ wherever it is on the command line
        # TODO: remove this, we don't expand arguments implicitly anymore
        return string_value_maybe_expand_user(ctx, base, value)
    elif isinstance(value, JoinedString):
        return join_string(ctx, target, base, value)
    elif isinstance(value, TaskPath):
        return resolve_task_path(ctx, value).as_posix()
    elif isinstance(value, TaskSelfPath):
        return _resolve_task_self_path(ctx, target, value).as_posix()
        #return task.path.as_posix()
    elif isinstance(value, PathElement):
        source = resolve_path_element_workspace(ctx, target.workspace, value, base)
        # source = _path_element_to_path(base, value)
        return source.as_posix()
    elif isinstance(value, Expansion):
        return str(value)
    #elif isinstance(value, (tuple, ListValue, list)):  #
    #    yield from resolve_string_argument_list(ctx, task, base, name, value)
    elif IGNORE_NONE_VALUES_IN_LISTS and value is None:
        return None
    else:
        raise PythonScriptError(
            message=f"Invalid value. Expected String-like. Got {type(value)}.",
            location=get_location(value, target.location)
        )


@dataclass
class Print(InternalAction):
    NAME = "print"
    messages: list[Union[StringValue, JoinedString]]

    def __init__(self, messages, location):
        self.messages = messages
        self.location = location

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
        for message in arguments.get("strings", []):
            print(message)

        return CommandOutput(0)

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:

        strings = []
        for string in self.messages:
            value = resolve_string_argument(ctx, target, target.input_path, string)
            if value is None:
                continue
            strings.append(value)

        return ArgumentData({
            "strings": strings,
        })

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # this hash doesn't matter; doesn't affect output
        return ""
