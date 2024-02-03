from pathlib import Path

from makex.workspace import (
    Workspace,
    WorkspaceCache,
)


def test_nesting(tmp_path):
    """ Test that the workspace cache detects workspace boundaries correctly.
    """

    root = tmp_path / "WORKSPACE"
    sub1 = tmp_path / "sub" / "WORKSPACE"
    sub2 = tmp_path / "sub" / "sub" / "sub" / "sub" / "WORKSPACE"

    root.touch()

    sub1.parent.mkdir(parents=True)
    sub1.touch()

    sub2.parent.mkdir(parents=True)
    sub2.touch()

    cache = WorkspaceCache()

    # immediate should get sub1
    assert cache.get_workspace_of(tmp_path / "sub") == Workspace(sub1.parent)

    # intermediate directory should get sub1
    assert cache.get_workspace_of(tmp_path / "sub" / "sub") == Workspace(sub1.parent)

    # parent of tmp_path should return the root/anchor
    assert cache.get_workspace_of(tmp_path.parent) == Workspace(Path(*tmp_path.anchor))

    # immediate directory should get sub2
    assert cache.get_workspace_of(tmp_path / "sub" / "sub" / "sub" / "sub") == Workspace(
        sub2.parent
    )
