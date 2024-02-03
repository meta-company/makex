from makex.context import Context
from makex.metadata import TargetMetadata
from makex.python_script import FileLocation
from makex.target import EvaluatedTarget, target_hash


def test_metadata(tmp_path):
    makex_file = tmp_path/"Makexfile"
    target = EvaluatedTarget(
        name="test",
        path=tmp_path/"_output_"/"test",
        input_path=tmp_path,
        location=FileLocation(0,0,makex_file.as_posix())
    )

    ctx = Context()
    metadata = TargetMetadata.from_evaluated_target(ctx=ctx, target=target, hash_function=target_hash)

    pass
