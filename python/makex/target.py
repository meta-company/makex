import hashlib
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Optional,
    Protocol,
    Type,
    Union,
)

from makex._logging import trace
from makex.constants import HASHING_ALGORITHM
from makex.context import Context
from makex.protocols import (
    CommandOutput,
    FileStatus,
    MakexFileProtocol,
    StringHashFunction,
)
from makex.python_script import FileLocation
from makex.workspace import Workspace

TaskKey = str

HASH_FUNCTION = getattr(hashlib, HASHING_ALGORITHM, "sha1")


class Action(Protocol):
    location: FileLocation

    def __call__(self, ctx: Context, target: "EvaluatedTask") -> CommandOutput:
        # old Action function
        ...

    def run_with_arguments(
        self, ctx: Context, target: "EvaluatedTask", arguments: dict[str, Any]
    ) -> CommandOutput:
        ...

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        # allow Actions to produce a hash of their arguments
        # if anything about them changes (e.g. arguments/inputs/checksums) the hash should change
        return


class InternalAction:
    """
    Keep an Internal Action that records the arguments evaluated from a Action,
    so we can hash the Action before running it.

    Keep a pointer to the original Action as it's unnecessary to copy it.
    """
    def __init__(self, action: Action, arguments: dict[str, Any]):
        self.action = action
        self.arguments = arguments

    @property
    def location(self):
        return self.action.location

    def hash(self, ctx: Context, hash_function: StringHashFunction):
        assert hasattr(self.action, "hash")
        assert callable(self.action.hash)

        return self.action.hash(ctx=ctx, arguments=self.arguments, hash_function=hash_function)

    def __call__(self, ctx, target: "EvaluatedTask") -> CommandOutput:

        if getattr(self.action, "run_with_arguments", None):
            return self.action.run_with_arguments(ctx, target, self.arguments)
        else:
            return self.action(ctx, target)

    def __repr__(self):
        return f"InternalAction({self.action!r}, {self.arguments})"


class Hasher:
    def __init__(self, type=HASH_FUNCTION):
        self._hash = type()

    def update(self, string: str):
        self._hash.update(string.encode("ascii"))

    def hex_digest(self, length=20):
        return self._hash.hexdigest() # .hexdigest(length)


@dataclass
class EvaluatedTask:
    """
    An "evaluated" target.

    All the properties/attributes in this type have been evaluated or are resolved.

    Paths are resolved to absolute. TODO: They should retain their FileLocation for debug/ui.

    """
    name: str

    # absolute path to the output of the target
    path: Path

    input_path: Path

    workspace: Workspace = None

    # all inputs used (or to be used) for this target
    inputs: list[FileStatus] = None

    # all outputs produced (or to be produced) for this target
    outputs: list[FileStatus] = None

    output_dict: dict[Union[int, str, None], Union[FileStatus, list[FileStatus]]] = None

    # TODO: inputs dictionary, "" or None is for unnamed inputs.
    #  used for evaluation of actions/arguments/self-references
    inputs_mapping: dict[Union[str, None], list[Path]] = None

    # references to targets this target requires.
    requires: list["EvaluatedTask"] = None

    actions: list[InternalAction] = None

    # Contains the file path and location which the target was defined.
    location: FileLocation = None

    makex_file: MakexFileProtocol = None

    # actual path to cache; symlinks resolved
    cache_path: Path = None

    # any environment variables defined by the task
    environment: dict[str, str] = None

    @property
    def makex_file_path(self) -> str:
        # TODO: fix this.
        return str(self.location.path)

    def key(self) -> TaskKey:
        return format_hash_key(self.name, self.makex_file.path)

    def __eq__(self, other: "EvaluatedTask"):
        keyfunc = getattr(other, "key", None)
        assert keyfunc is not None
        assert callable(keyfunc)
        return self.key() == keyfunc()

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        return f"EvaluatedTask(\"{self.key()}\")" # , requires={self.requires!r})"

    def hash(
        self,
        ctx: Context,
        hash_function: StringHashFunction = None,
        hasher: Type[Hasher] = None,
        hash_cache: dict[str, "EvaluatedTask"] = None,
    ) -> str:
        hash_function = hash_function or target_hash
        hasher = hasher or Hasher

        data = [
            f"key:{hash_function(self.key())}",
            f"makex-file-path:{hash_function(self.makex_file_path)}",
            f"source:{hash_function(self.input_path.as_posix())}",
            f"path:{hash_function(self.path.as_posix())}",
        ]

        if self.makex_file:
            # Add the checksums of the makex file, included makex files and any used environment variables.
            data.extend(self.makex_file.hash_components())

        if self.actions:
            for command in self.actions:
                data.append(
                    f"command:{command.action.__class__.__name__}:{command.hash(ctx, hash_function=hash_function)}"
                )

        # XXX: Run recursively.
        # XXX: We can run require.hash because we've evaluated all targets up to this one.
        if self.requires:
            for require in self.requires:
                rehash = False
                if hash_cache is None:
                    rehash = True
                    trace("Rehashing. No cache. %s", require.key())
                else:
                    requirement_hash = hash_cache.get(require.key(), None)
                    if requirement_hash is None:
                        rehash = True
                        trace("Rehashing. Not in cache. %s", require.key())

                if rehash:
                    requirement_hash = require.hash(
                        ctx,
                        hash_function=hash_function,
                        hash_cache=hash_cache,
                    )
                    # XXX: not sure about this. we should have a HashCache class which does this internally.
                    hash_cache[require.key()] = require

                data.append(f"require:{requirement_hash}")

        if self.environment:
            environment_string = ";".join(f"{k}={v}" for k, v in self.environment.items())
            environment_hash = hash_function(environment_string)
            data.append(f"environment:{environment_hash}")

        if self.inputs:
            # XXX: Inputs lists can be large (find()/glob()); optimize by using Hasher.update into one value.
            _hasher = hasher()
            for input in self.inputs:
                # data.append(f"input-file:{str(input.checksum)}")
                _hasher.update(f"input-file:{str(input.checksum)}")
            data.append(f"input-files:{_hasher.hex_digest()}")

        trace("Target %s hash data: %s", self.key(), data)
        return hash_function("|".join(data))


def target_hash(data: str):
    return HASH_FUNCTION(data.encode()).hexdigest()


def format_hash_key(name: str, path: Union[PathLike, str]):
    return f"{path}:{name}"


class EvaluatedTaskGraph:
    _targets: dict[TaskKey, EvaluatedTask]
    _requires: dict[TaskKey, list[EvaluatedTask]]
    _provides: dict[TaskKey, set[EvaluatedTask]]
    _input_files: dict[Path, set[EvaluatedTask]]

    def __init__(self):
        self._targets = {}

        # list of requires for each target
        self._requires = {}

        # list of targets that each target directly provides to
        self._provides = {}

        # targets requiring files Path -> list of targets

        # targets for input files
        self._input_files = {}

    def add_target(self, target: EvaluatedTask):
        # NOTE: all requires MUST be added first
        assert isinstance(target, EvaluatedTask), f"Got {type(target)}: {target!r}"
        key = target.key()
        # TODO: only use altkey if the task comes from a default/main makexfile
        altkey = format_hash_key(target.name, target.input_path)
        self._targets[key] = target

        # store in an alternate key for the folder default tasks
        self._targets[altkey] = target

        # build edges from require -> target
        for require in target.requires:
            assert require, f"Got {type(require)}: {require!r}"
            self._provides.setdefault(require.key(), set()).add(target)

        for path in target.inputs:
            self._input_files.setdefault(path, set()).add(target)

    SimpleGraph = tuple[EvaluatedTask, Iterable["SimpleGraph"]]

    def get_affected_graph(self, paths: Iterable[Path], scopes: list[Path] = None) -> SimpleGraph:
        seen = set()

        # Performance optimization for possibly large numbers of paths
        scope_check = lambda target: True

        if scopes:

            def scope_check(target: EvaluatedTask):
                return self._scope_list_check(scopes, target.input_path)

        for path in paths:
            targets: set[EvaluatedTask] = self._input_files.get(path, None)

            if targets is None:
                continue

            for target in targets:
                key = target.key()

                if key in seen:
                    continue

                if not scope_check(target):
                    continue

                yield (target, self.get_requires_graph(target, scopes=scopes, recursive=True))

                seen.add(key)

    def get_affected(
        self,
        paths: Iterable[Path],
        scopes: list[Path] = None,
        depth=0,
    ) -> Iterable[EvaluatedTask]:
        """
        Return targets affected by the input files.

        Should return in topologically sorted order. t > requires > requires > requires.

        If you need to group them, e.g. for a run tree use group=True.

        depth: 0 is recursive, 1 is first level.

        optionally limit targets returned to those under the scope path.

        :param paths:
        :return:
        """
        seen = set()

        # Performance optimization for possibly large numbers of paths
        scope_check = lambda target: True

        if scopes:

            def scope_check(target: EvaluatedTask):
                return self._scope_list_check(scopes, target.input_path)

        for path in paths:
            targets: set[EvaluatedTask] = self._input_files.get(path, None)

            if targets is None:
                continue

            for target in targets:
                key = target.key()

                if key in seen:
                    continue

                if not scope_check(target):
                    continue

                yield target
                yield from self.get_requires(target, scopes=scopes, depth=depth)

                seen.add(key)

    def get_target(self, target: EvaluatedTask) -> Optional[EvaluatedTask]:
        return self._targets.get(target.key(), None)

    def get_task2(self, task_name: str, path: str) -> Optional[EvaluatedTask]:
        return self._targets.get(format_hash_key(task_name, path), None)

    def _scope_list_check(self, scopes, path):
        for scope in scopes:

            if path.is_relative_to(scope):
                return True

        return False

    def get_requires(
        self,
        target: EvaluatedTask,
        scopes: list[Path] = None,
        depth=0,
        _depth=None,
    ) -> Iterable[EvaluatedTask]:
        # return the requirements as an iterable
        _depth = -1 if _depth is None else _depth

        if depth > _depth:
            return iter([])

        for require in target.requires:
            if scopes is not None and self._scope_list_check(scopes, require.input_path) is False:
                continue

            yield from self.get_requires(require, scopes=scopes, depth=depth, _depth=_depth)
            yield require

    def get_requires_graph(self,
                           target: EvaluatedTask,
                           scopes: list[Path] = None,
                           recursive=True) -> Iterable[SimpleGraph]:
        # return the requirements as a graph
        for require in target.requires:
            # TODO: linux platforms can optimize this with a str.starts_with check
            if scopes is not None and self._scope_list_check(scopes, require.input_path) is False:
                continue

            graph = self.get_requires_graph(target, scopes, recursive=recursive)
            yield (target, graph)

    def get_inputs(self, target: EvaluatedTask, recursive=True) -> Iterable[Path]:
        """
        yields the inputs of target and required targets.

        yields target.require's inputs first, then yields those of target's dependendencies

        :param target:
        :param recursive:
        :return:
        """
        for require in target.requires:
            yield from self.get_inputs(require, recursive=recursive)

        for input in target.inputs:
            yield input

    def get_outputs(self, target: EvaluatedTask, recursive=True) -> Iterable[Path]:
        for require in target.requires:
            yield from self.get_outputs(require, recursive=recursive)

        for output in target.outputs:
            yield output

    def get_keys(self) -> Iterable[TaskKey]:
        return self._targets.keys()


def brief_task_name(ctx: Context, target: "EvaluatedTask", color=False):
    # path = target.input_path
    path = Path(target.location.path)
    # if path.name in ["Makefilex", "Makexfile"]:
    #    path = path.parent

    if color:
        if " " in path.as_posix():
            return f"'{ctx.colors.BOLD}{target.name}{ctx.colors.RESET}:{path}'"
        return f"{ctx.colors.BOLD}{target.name}{ctx.colors.RESET}:{path}"
    else:
        if " " in path.as_posix():
            return f"'{target.name}:{path}'"
        return f"{target.name}:{path}"


class ArgumentData(dict):
    # any input files we recorded from arguments
    inputs: list[Path]

    # the actual argument values passed to be cached and passed around
    arguments: dict[str, Any]

    # any requirements recovered from task action arguments
    # these will be added as implicit dependencies
    requirements: list[TaskKey]

    errors: list[Exception] = None

    def __init__(self, arguments=None, inputs=None, errors=None, requirements=None):
        super().__init__()
        self.arguments = arguments or {}
        self.inputs = inputs
        self.errors = errors or []
        self.requirements = requirements or []

    def get(self, key, default=None):
        return self.arguments.get(key, default)
