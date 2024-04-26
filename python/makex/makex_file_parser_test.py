from pathlib import Path

import pytest
from makex.context import Context
from makex.errors import ExecutionError
from makex.makex_file import MakexFileCycleError
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)
from makex.makex_file_types import ResolvedTargetReference
from makex.python_script import PythonScriptError
from makex.workspace import Workspace


def test_parse(tmp_path: Path):
    """
    Test parsing of targets.
    """
    a = tmp_path / "Makexfile"
    a.write_text("""task(name="a")""")

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

    a.write_text("""task(name="a",requires=[Reference("b", "sub")])""")

    b.write_text("""task(name="b")""")

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
    makefile_path_a.write_text("""task(name="a",requires=["Makexfile-b:b"])\n""")

    makefile_path_b = tmp_path / "Makexfile-b"
    makefile_path_b.write_text("""task(name="b",requires=["Makexfile-a:a"])\n""")

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
    makefile_path.write_text("""task(name="a",requires=[":b"])\ntask(name="b",requires=[":a"])\n""")

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
    makefile_path_a.write_text("""task("a", requires=[])""")

    workspace_file_b = workspace_b / "WORKSPACE"
    workspace_file_b.touch()

    makefile_path_b = workspace_b / "Makexfile"
    makefile_path_b.write_text("""task("b", requires=["//..:b"])""")

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
    makefile_path_a.write_text("""task(name="a", requires=["//nested:b"])""")

    workspace_file_b = workspace_b / "WORKSPACE"
    workspace_file_b.touch()

    makefile_path_b = workspace_b / "Makexfile"
    makefile_path_b.write_text("""task(name="b", requires=[])""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path_a, graph)
    ref_a = ResolvedTargetReference("a", makefile_path_a)

    a = graph.get_target(ref_a)

    assert not result.errors

    assert a
    assert a.requires
    assert len(a.requires)

    #assert a.requires == [ResolvedTargetReference("b", "//nested")]


def test_include_macros(tmp_path: Path):
    workspace_a = tmp_path
    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text("""include("include.mx"); test()""")

    makefile_path_b = workspace_a / "include.mx"
    makefile_path_b.write_text("""@macro
def test():
  task(name="test")
""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path_a, graph)
    ref_a = ResolvedTargetReference("test", makefile_path_a)

    a = graph.get_target(ref_a)
    assert a


def test_include_targets(tmp_path: Path):
    workspace_a = tmp_path
    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text("""include("include.mx", tasks=True); task(name="a")""")

    makefile_path_b = workspace_a / "include.mx"
    makefile_path_b.write_text("""task(name="b")""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path_a, graph)
    ref_a = ResolvedTargetReference("b", makefile_path_a)

    a = graph.get_target(ref_a)
    assert a

    ref_a = ResolvedTargetReference("a", makefile_path_a)
    a = graph.get_target(ref_a)

    assert a


@pytest.mark.skip
def test_import_macros(tmp_path: Path):
    # TODO: enable flag or weave a variable into ctx so that this can work
    workspace_a = tmp_path
    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text("""from include import test; test()""")

    makefile_path_b = workspace_a / "include.mx"
    makefile_path_b.write_text("""@macro
def test():
  task(name="test")
""")

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    graph = TargetGraph()

    result = parse_makefile_into_graph(ctx, makefile_path_a, graph)
    ref_a = ResolvedTargetReference("test", makefile_path_a)

    a = graph.get_target(ref_a)
    assert a
