from pathlib import Path

import pytest
from makex.constants import SYNTAX_2025
from makex.context import Context
from makex.errors import MakexFileCycleError
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)
from makex.makex_file_types import TaskReference
from makex.python_script import PythonScriptError
from makex.workspace import Workspace


@pytest.fixture
def _makex_context(tmp_path):
    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    ctx.makex_syntax_version = SYNTAX_2025
    ctx.debug = True
    return ctx


def test_parse(tmp_path: Path, _makex_context):
    """
    Test parsing of targets.
    """
    a = tmp_path / "Makexfile"
    a.write_text("""task(name="a")""")

    ctx = _makex_context
    graph = TargetGraph()
    result = parse_makefile_into_graph(ctx, a, graph)
    assert not result.errors
    assert TaskReference("a", a) in graph


def test_parse_graph(tmp_path: Path, _makex_context):
    """
    Test the parsing of a target requiring a target in another path.
    """
    a = tmp_path / "Makexfile"
    b = tmp_path / "sub" / "Makexfile"

    b.parent.mkdir(parents=True)

    a.write_text("""task(name="a",requires=[Reference("b", "sub")])""")

    b.write_text("""task(name="b")""")

    ctx = _makex_context
    graph = TargetGraph()
    result = parse_makefile_into_graph(ctx, a, graph)

    assert not result.errors

    assert TaskReference("b", b) in graph
    assert TaskReference("a", a) in graph


def test_cycle_error_external_targets(tmp_path: Path, _makex_context):
    """
    Test cycles between targets of different files.
    """
    makefile_path_a = tmp_path / "Makexfile-a"
    makefile_path_a.write_text("""task(name="a",requires=["b:Makexfile-b"])\n""")

    makefile_path_b = tmp_path / "Makexfile-b"
    makefile_path_b.write_text("""task(name="b",requires=["a:Makexfile-a"])\n""")

    graph = TargetGraph()
    ctx = _makex_context
    result = parse_makefile_into_graph(ctx, makefile_path_a, graph, allow_makex_files=True)

    assert isinstance(result.errors[0], MakexFileCycleError)


def test_cycle_error_internal_targets(tmp_path: Path, _makex_context):
    """
    Test cycles between targets inside the same file.
    """
    makefile_path = tmp_path / "Makexfile"
    makefile_path.write_text("""task(name="a",requires=["b"])\ntask(name="b",requires=["a"])\n""")

    graph = TargetGraph()
    ctx = _makex_context
    result = parse_makefile_into_graph(ctx, makefile_path, graph)

    assert isinstance(result.errors[0], MakexFileCycleError)


def test_missing_environment_variable(tmp_path: Path, _makex_context):
    """
    Test cycles between targets inside the same file.
    """
    makefile_path = tmp_path / "Makexfile"
    makefile_path.write_text("""E = Enviroment.get("DOES_NOT_EXIST")""")

    graph = TargetGraph()

    result = parse_makefile_into_graph(_makex_context, makefile_path, graph)

    assert isinstance(result.errors[0], PythonScriptError)


def test_nested_workspaces_error(tmp_path: Path, _makex_context):
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
    makefile_path_b.write_text("""task("b", requires=["b://.."])""")

    graph = TargetGraph()

    result = parse_makefile_into_graph(_makex_context, makefile_path_b, graph)

    assert isinstance(result.errors[0], PythonScriptError)


def test_nested_workspaces(tmp_path: Path, _makex_context):
    workspace_a = tmp_path
    workspace_b = tmp_path / "nested"
    workspace_b.mkdir(parents=True)

    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text("""task(name="a", requires=["b://nested"])""")

    workspace_file_b = workspace_b / "WORKSPACE"
    workspace_file_b.touch()

    makefile_path_b = workspace_b / "Makexfile"
    makefile_path_b.write_text("""task(name="b", requires=[])""")

    graph = TargetGraph()

    result = parse_makefile_into_graph(_makex_context, makefile_path_a, graph)
    ref_a = TaskReference("a", makefile_path_a)

    a = graph.get_target(ref_a)

    assert not result.errors

    assert a
    assert a.requires
    assert len(a.requires)

    #assert a.requires == [TaskReference("b", "//nested")]


def test_include_macros(tmp_path: Path, _makex_context):
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

    graph = TargetGraph()

    result = parse_makefile_into_graph(_makex_context, makefile_path_a, graph)
    ref_a = TaskReference("test", makefile_path_a)

    a = graph.get_target(ref_a)
    assert a


def test_include_targets(tmp_path: Path, _makex_context):
    workspace_a = tmp_path
    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text("""include("include.mx", tasks=True); task(name="a")""")

    makefile_path_b = workspace_a / "include.mx"
    makefile_path_b.write_text("""task(name="b")""")

    graph = TargetGraph()

    result = parse_makefile_into_graph(_makex_context, makefile_path_a, graph)
    ref_a = TaskReference("b", makefile_path_a)

    a = graph.get_target(ref_a)
    assert a

    ref_a = TaskReference("a", makefile_path_a)
    a = graph.get_target(ref_a)

    assert a


@pytest.mark.skip
def test_import_macros(tmp_path: Path, _makex_context):
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

    graph = TargetGraph()

    result = parse_makefile_into_graph(_makex_context, makefile_path_a, graph)
    ref_a = TaskReference("test", makefile_path_a)

    a = graph.get_target(ref_a)
    assert a


def test_self_references(tmp_path: Path, _makex_context):
    workspace_a = tmp_path
    workspace_file_a = workspace_a / "WORKSPACE"
    workspace_file_a.touch()

    makefile_path_a = workspace_a / "Makexfile"
    makefile_path_a.write_text(
        """
task(
  name="a",
  inputs={
    "input1": "path1",
    "input2": "path2",
  },
  steps=[
    copy(self.inputs.input1), 
    copy(self.inputs["input2"])
  ]
)
        """
    )

    graph = TargetGraph()

    result = parse_makefile_into_graph(_makex_context, makefile_path_a, graph)
    ref_a = TaskReference("a", makefile_path_a)

    a = graph.get_target(ref_a)
    assert a
