from datetime import (
    datetime,
    timezone,
)
from typing import (
    Optional,
    Protocol,
)

from makex.context import Context
from makex.protocols import StringHashFunction
from makex.python_script import FileLocation
from makex.target import EvaluatedTarget


class TargetWithValidKey:
    def key(self) -> str:
        ...


class File:
    path: str
    checksum: str

    def __init__(self, path, checksum):
        self.path = path
        self.checksum = checksum

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return self.path == other.path and self.checksum == other.checksum


class Output(File):
    pass


class Input(File):
    pass


class Requirement:
    name: str
    # path of the file which it was defined
    path: str
    #
    hash: str

    def __init__(self, name, path, hash):
        self.name = name
        self.path = path
        self.hash = hash

    def __hash__(self):
        return hash(self.hash)

    def __eq__(self, other):
        return self.hash == other.hash

    @classmethod
    def from_json(cls, d):
        return cls(
            name=d.get("name"),
            path=d.get("path"),
            hash=d.get("hash"),
        )


class Dirtyness:

    # paths to inputs/outputs
    inputs: list[str]
    outputs: list[str]

    # details about requirements that have failed
    requires: list[Requirement]

    def __init__(self, inputs: list[str], outputs: list[str], requires: list[Requirement]):
        self.inputs = inputs
        self.outputs = outputs
        self.requires = requires


#class FileLocation:
#    line:int
#    column:int
#    path:str


class TargetMetadata:
    # TODO: we should be able to serialize Actions/arguments
    name: str
    path: str
    key: str

    # where this target came from
    location: FileLocation

    # values of variants when building this target
    variants: dict[str, str]

    # hash of the target
    # hash(hash(key) + hash(actions) + hash(requires) + hash(outputs) + hash(inputs))
    hash: list[str]

    # map of path -> File
    inputs: dict[str, Input]
    outputs: dict[str, Output]

    # map from requirement hash to requirement
    requires: dict[str, Requirement]

    # time from unix epoch
    # the time the target started execution
    start_time: datetime = None

    # the time the target finished execution
    end_time: datetime = None

    # the time this metadata record was created
    time: datetime = None

    @classmethod
    def from_json(cls, d) -> "TargetMetadata":
        c = cls()
        c.name = d.get("name")
        c.path = d.get("path")
        c.hash = d.get("hash")
        c.outputs = {output.get("path"): output.get("checksum") for output in d.get("outputs")}
        c.inputs = {output.get("path"): output.get("checksum") for output in d.get("inputs")}
        c.requires = requires = {}

        for requirement in d.get("requires"):
            r = Requirement.from_json(requirement)
            requires[r.hash] = r
        return c

    @classmethod
    def from_evaluated_target(
        cls,
        ctx: Context,
        target: EvaluatedTarget,
        hash_function: StringHashFunction,
        timing=None
    ) -> "TargetMetadata":
        c = cls()
        c.name = target.name
        c.path = target.path.as_posix()
        c.key = target.key()

        c.hash = target.hash(ctx, hash_function=hash_function)

        c.outputs = {output.path: str(output.checksum) for output in target.outputs or []}
        c.inputs = {input.path: str(input.checksum) for input in target.inputs or []}
        c.requires = []

        c.location = target.location
        c.time = datetime.now(timezone.utc)

        if timing:
            c.start_time, c.end_time = timing
        for requirement in target.requires or []:
            requirement.key()
            requirement.hash(ctx, hash_function=hash_function)
        return c

    def dirty(self, ctx: Context, target: EvaluatedTarget) -> Dirtyness:
        # TODO: we don' really need this at the moment.
        # Manually evaluate the dirtyness of a target.

        # TargetMetadata.hash == target.hash()

        # assume we're dirty unless something tells us otherwise
        dirty = True

        # compare checksums of input files
        # if any inputs are missing, we're dirty.

        missing_inputs = []
        missing_outputs = []
        changed_requires = []
        missing_requires = []

        previous_inputs = set()
        checked_inputs = set()
        for input in target.inputs:
            input_metadata = self.inputs.get(input.path, None)
            checked_inputs.add(input)

        # manually check if a target is dirty
        # if any outputs are missing, we're dirty
        checked_outputs = set()
        for output in target.outputs:
            output_metadata = self.outputs.get(output.path, None)

        # compare requirement hashes
        for require in target.requires:
            new_hash = require.hash(ctx)

            require_metadata = self.requires.get(new_hash, None)
            if require_metadata is None:
                missing_requires.append(require)
            else:
                # n
                if require.hash(ctx) != require_metadata.hash:
                    changed_requires.append(require)

        return Dirtyness()


class MetadataProtocol(Protocol):
    """
    Metadata [backend] protocol. This should be fast and synchronous.
    """
    def get_target(self, target_hash: str) -> Optional[TargetMetadata]:
        pass

    def put_target(self, target: TargetMetadata) -> Optional[Exception]:
        pass
