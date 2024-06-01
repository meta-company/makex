import os

import pytest

from makex.context import Context
from makex.executor import Executor
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)
from makex.makex_file_types import ResolvedTargetReference
from makex.workspace import Workspace


@pytest.fixture
def makex_context(tmp_path):
    ctx = Context(environment=os.environ.copy())
    ctx.workspace_object = Workspace(tmp_path)
    return ctx


def test_write(tmp_path, makex_context):
    """
    Test write action.
    """
    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="test",
    steps=[
        write("file1", "file1"),
    ]
)    
"""
    makefile_path.write_text(file)

    graph = TargetGraph()

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTargetReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / "_output_" / "test"
    assert (base / "file1").exists()
    assert (base / "file1").read_text() == "file1"


def test_copy(tmp_path, makex_context):
    """
    Test copy actions variants.
    """
    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="test",
    steps=[
        copy("file1"),
        copy("folder1"),
        
        copy("file2", "folder"),
        copy("folder2", "folder"),
        
        copy(["file3"], "folder"),
        copy(["folder3"], "folder"),
    ]
)    
"""
    makefile_path.write_text(file)
    file1 = tmp_path / "file1"
    file1.write_text("file1")
    file2 = tmp_path / "file2"
    file2.write_text("file2")
    file3 = tmp_path / "file3"
    file3.write_text("file3")
    folder1 = tmp_path / "folder1"
    folder1.mkdir(parents=True)
    folder2 = tmp_path / "folder2"
    folder2.mkdir(parents=True)
    folder3 = tmp_path / "folder3"
    folder3.mkdir(parents=True)

    graph = TargetGraph()

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTargetReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / "_output_" / "test"
    assert (base / "file1").exists()
    assert (base / "folder1").exists()

    assert (base / "folder" / "file2").exists()
    assert (base / "folder" / "folder2").exists()

    assert (base / "folder" / "file3").exists()
    assert (base / "folder" / "folder3").exists()


def test_execute(tmp_path, makex_context):
    """ Test execute using awk. """
    makefile_path = tmp_path / "Makexfile"

    file = """
OUTPUT = task_path('test')/'file1'
task(
    name="test",
    steps=[
        #execute("sed", "-i", "$a\file1", task_path('test')/"file1"),
        execute("awk", f'BEGIN{{ printf "file1" >> "{OUTPUT}" }}'),
    ]
)    
"""
    makefile_path.write_text(file)

    graph = TargetGraph()

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTargetReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / "_output_" / "test"
    assert (base / "file1").exists()
    assert (base / "file1").read_text() == "file1"


def test_shell(tmp_path, makex_context):
    """
    Test shell action.
    """
    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="test",
    steps=[
        shell(f"echo -n 'file1' > {task_path('test') / 'file1'}"),
    ]
)    
"""
    makefile_path.write_text(file)

    graph = TargetGraph()

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTargetReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / "_output_" / "test"
    assert (base / "file1").exists()
    assert (base / "file1").read_text() == "file1"


def test_mirror(tmp_path):
    # TODO: test mirror works properly
    pass
