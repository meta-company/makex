from makex.file_system import find_files
from makex.makex_file_paths import _make_glob_pattern


def test_find_files(tmp_path):

    (tmp_path / "test").mkdir(parents=True, exist_ok=True)

    test_file = (tmp_path / "test" / "test.ini")
    test_file.touch()

    pattern = _make_glob_pattern("test/*.ini")

    files = list(
        find_files(
            tmp_path,
            pattern=pattern, #ignore_pattern=ctx.ignore_pattern,
            #ignore_names=ignore_names,
        )
    )
    assert files[0] == test_file
