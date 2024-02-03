from makex.patterns import (
    combine_patterns,
    make_glob_pattern,
)


def test():
    pattern = combine_patterns(
        [
            r"\.hgignore",
            r"\.p4ignore",
            make_glob_pattern("**/*.py"),
            make_glob_pattern("*.py"),
        ]
    )

    print(pattern.match(".hgignore"))
    assert not pattern.match("1hgignore")
    assert pattern.match(".hgignore")
    assert pattern.match(".p4ignore")
    assert not pattern.match("hgignore")
    assert pattern.match("test/test.py")
    assert pattern.match("/test/test.py")
    assert pattern.match("test.py")
