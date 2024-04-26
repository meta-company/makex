from makex.file_cloning import (
    clone_file,
    supported_at,
)


def test_reflink(tmp_path):

    a = tmp_path / "a"
    a.write_text("a")

    if supported_at(tmp_path):
        clone_file(tmp_path / "a", tmp_path / "b")
