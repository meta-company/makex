from pathlib import Path

from makex.context import Context
from makex.errors import ExecutionError
from makex.make_file import (
    MakexFileCycleError,
    ResolvedTargetReference,
    TargetGraph,
    parse_makefile_into_graph,
)
from makex.python_script import PythonScriptError
from makex.workspace import Workspace


def test_parse(tmp_path: Path):
    """
    Test parsing of targets.
    """
    a = tmp_path / "Makexfile"
    a.write_text("""target(name="a")""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()
    result = parse_makefile_into_graph(ctx, a, graph)
    assert not result.errors
    assert ResolvedTargetReference("a", a) in graph


def test_parse_graph(tmp_path: Path):
    """
    Test the parsing of a target requiring a target in another path.
    """
    a = tmp_path / "Makexfile"
    b = tmp_path / "sub" / "Makexfile"

    b.parent.mkdir(parents=True)

    a.write_text("""target(name="a",requires=[Target("b", "sub")])""")

    b.write_text("""target(name="b")""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()
    result = parse_makefile_into_graph(ctx, a, graph)

    assert not result.errors

    assert ResolvedTargetReference("b", b) in graph
    assert ResolvedTargetReference("a", a) in graph


def test_cycle_error_external_targets(tmp_path: Path):
    """
    Test cycles between targets of different files.
    """
    makefile_path_a = tmp_path / "Makexfile-a"
    makefile_path_a.write_text("""target(name="a",requires=["Makexfile-b:b"])\n""")

    makefile_path_b = tmp_path / "Makexfile-b"
    makefile_path_b.write_text("""target(name="b",requires=["Makexfile-a:a"])\n""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path_a, graph, allow_makex_files=True)

    assert isinstance(result.errors[0], MakexFileCycleError)


def test_cycle_error_internal_targets(tmp_path: Path):
    """
    Test cycles between targets inside the same file.
    """
    makefile_path = tmp_path / "Makexfile"
    makefile_path.write_text(
        """target(name="a",requires=[":b"])\ntarget(name="b",requires=[":a"])\n"""
    )

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path, graph)

    assert isinstance(result.errors[0], MakexFileCycleError)


def test_missing_environment_variable(tmp_path: Path):
    """
    Test cycles between targets inside the same file.
    """
    makefile_path = tmp_path / "Makexfile"
    makefile_path.write_text("""E = Enviroment.get("DOES_NOT_EXIST")""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path, graph)

    assert isinstance(result.errors[0], PythonScriptError)


def test_nested_workspaces_error(tmp_path: Path):
    """
    Test cycles between targets inside the same file.
    """
    workspace_a = tmp_path
    workspace_b = tmp_path / "nested"
    workspace_b.mkdir(parents=True)

    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text("""target("a", requires=[])""")

    workspace_file_b = workspace_b / "WORKSPACE"
    workspace_file_b.touch()

    makefile_path_b = workspace_b / "Makexfile"
    makefile_path_b.write_text("""target("b", requires=["//..:b"])""")


    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path_b, graph)

    assert isinstance(result.errors[0], PythonScriptError)


def test_nested_workspaces(tmp_path: Path):
    workspace_a = tmp_path
    workspace_b = tmp_path / "nested"
    workspace_b.mkdir(parents=True)

    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text("""target("a", requires=["//nested:b"])""")

    workspace_file_b = workspace_b / "WORKSPACE"
    workspace_file_b.touch()

    makefile_path_b = workspace_b / "Makexfile"
    makefile_path_b.write_text("""target("b", requires=[])""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path_a, graph)
    ref_a = ResolvedTargetReference("a", makefile_path_a)

    a = graph.get_target(ref_a)

    assert a
    assert a.requires
    assert len(a.requires)
    assert not result.errors
    #assert a.requires == [ResolvedTargetReference("b", "//nested")]


