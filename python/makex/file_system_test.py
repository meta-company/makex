from makex.file_system import (
    copy_tree,
    find_files,
)
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


def test_copy_tree_symlinks_as_is(tmp_path):
    (tmp_path / "source").mkdir(parents=True, exist_ok=True)
    (tmp_path / "source" / "test1").mkdir(parents=True, exist_ok=True)

    test_file1 = (tmp_path / "source" / "test1" / "test.ini")
    test_file1.touch()

    test_file2 = (tmp_path / "source" / "test1" / "test.ini.link")
    test_file2.symlink_to(test_file1)

    copy_tree(tmp_path / "source", tmp_path / "destination", symlinks="copy-link")

    assert (tmp_path / "destination" / "test1" / "test.ini").exists()
    assert (tmp_path / "destination" / "test1" / "test.ini.link").exists()
    assert (tmp_path / "destination" / "test1" / "test.ini.link").is_symlink()


def test_copy_tree_symlinks_copy(tmp_path):
    (tmp_path / "source").mkdir(parents=True, exist_ok=True)
    (tmp_path / "source" / "test1").mkdir(parents=True, exist_ok=True)

    test_file1 = (tmp_path / "source" / "test1" / "test.ini")
    test_file1.touch()

    test_file2 = (tmp_path / "source" / "test1" / "test.ini.link")
    test_file2.symlink_to(test_file1)

    copy_tree(tmp_path / "source", tmp_path / "destination", symlinks="copy-data")

    assert (tmp_path / "destination" / "test1" / "test.ini").exists()
    assert (tmp_path / "destination" / "test1" / "test.ini.link").exists()
    assert (tmp_path / "destination" / "test1" / "test.ini.link").is_file()


def test_copy_tree_ignore(tmp_path):
    (tmp_path / "source").mkdir(parents=True, exist_ok=True)
    (tmp_path / "source" / "test1").mkdir(parents=True, exist_ok=True)

    test_file1 = (tmp_path / "source" / "test1" / "test.ini")
    test_file1.touch()

    test_file2 = (tmp_path / "source" / "test1" / "test.ini.link")
    test_file2.symlink_to(test_file1)

    def f(path, name):
        if name.endswith(".link"):
            return True

    copy_tree(tmp_path / "source", tmp_path / "destination", ignore=f)

    assert (tmp_path / "destination" / "test1" / "test.ini").exists()
    assert (tmp_path / "destination" / "test1" / "test.ini.link").exists() is False
