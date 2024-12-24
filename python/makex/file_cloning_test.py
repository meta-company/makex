from makex.file_cloning import (
    clone_file,
    supported_at,
)


def test_reflink(tmp_path):

    a = tmp_path / "a"
    a.write_text("a")

    b = tmp_path / "b"
    if supported_at(tmp_path):
        clone_file(a, b)
        assert a.read_text() == b.read_text()
