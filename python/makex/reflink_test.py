from makex.reflink import (
    reflink,
    supported_at,
)


def test_reflink(tmp_path):

    a = tmp_path / "a"
    a.write_text("a")

    if supported_at(tmp_path):
        reflink(tmp_path / "a", tmp_path / "b")
