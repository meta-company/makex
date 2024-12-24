import os
import tarfile

import pytest
from makex.constants import OUTPUT_DIRECTORY_NAME
from makex.context import Context
from makex.executor import Executor
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)
from makex.makex_file_types import (
    ResolvedTaskReference,
    TaskReferenceElement,
)
from makex.workspace import Workspace


@pytest.fixture
def makex_context(tmp_path):
    _workspace = Workspace(tmp_path)

    ctx = Context(environment=os.environ.copy())
    ctx.graph = TargetGraph()
    ctx.debug = True
    ctx.workspace_object = _workspace
    ctx.workspace_cache.add(_workspace)
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
    ref_a = ResolvedTaskReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / OUTPUT_DIRECTORY_NAME / "test"
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
        # copy a file to the Task output
        copy("file1"),
        
        # copy a folder to the Task output
        copy("folder1"),
        
        copy("file2", "folder"),
        
        # TODO: copy a list of files to the Task output
        
        # copy folder to the specified Folder (relative to the task output)
        copy("folder2", "folder"),
        
        # copies a set of files to the specified folder (relative to the task output).
        copy(["file3"], "folder"),
        
        # TODO: copy a list of folders to the Task output
        
        # copies a set of folders to the specified folder (relative to the task output).
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
    ref_a = ResolvedTaskReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / OUTPUT_DIRECTORY_NAME / "test"
    assert (base / "file1").exists()
    assert (base / "folder1").exists()

    assert (base / "folder" / "file2").exists()
    assert (base / "folder" / "folder2").exists()

    assert (base / "folder" / "file3").exists()
    assert (base / "folder" / "folder3").exists()


def test_copy_task_outputs(tmp_path, makex_context):
    """
    Test copy task outputs.
    """
    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="source_task",
    steps=[
        write("test-file", "hello!"),
    ],
    outputs="test-file",
)    

task(
    name="test",
    requires=[
        ":source_task",
    ],
    steps=[
        copy(":source_task"),
    ],
)
    """
    makefile_path.write_text(file)

    #graph = TargetGraph()

    graph = makex_context.graph

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTaskReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / OUTPUT_DIRECTORY_NAME / "test"

    # make sure the file from source_task was copied into the output of the "test" task
    assert (base / "test-file").exists()


def test_execute(tmp_path, makex_context):
    """ Test execute using awk.

        NOTE: Depends on the awk executable being available on the system.

        TODO: figure out a more universal test.
    """
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
    ref_a = ResolvedTaskReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / OUTPUT_DIRECTORY_NAME / "test"
    assert (base / "file1").exists()
    assert (base / "file1").read_text() == "file1"


def test_execute_task_output(tmp_path, makex_context):
    """ Test execute the output of a task within another task.

        NOTE: Depends on the write() action working.
    """

    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="test",
    requires=[
        "//tool:executable"
    ],
    steps=[
        execute("//tool:executable", task_path("test") / "test-1234"),
    ],
    outputs=[
        task_path('test')/'test-1234'
    ]
)    
"""
    makefile_path.write_text(file)

    file = """
task(
    name="executable",
    steps=[
        write("example.sh", '''#!/bin/sh\\necho "$(basename $1)" > $1'''),
        execute("chmod", "+x", task_path('executable')/"example.sh")
    ],
    outputs=task_path('executable')/'example.sh'
)    
"""
    tool_makefile_path = tmp_path / "tool" / "Makexfile"
    (tmp_path / "tool").mkdir(parents=True)

    tool_makefile_path.write_text(file)

    graph = makex_context.graph

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTaskReference("test", makefile_path)
    a = graph.get_target(ref_a)
    assert a

    ref_b = ResolvedTaskReference("executable", tool_makefile_path)
    b = graph.get_target(ref_b)
    assert b

    e = Executor(makex_context, workers=1, graph=graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / OUTPUT_DIRECTORY_NAME / "test"
    assert (base / "test-1234").exists()
    assert (base / "test-1234").read_text() == "test-1234\n"


def test_execute_implicit_requires(tmp_path, makex_context: Context):
    """ Test execute the output of a task within another task. Check that implicit requirement are added to task.

        NOTE: Depends on the write() action working.
    """

    makex_context.implicit_requirements = True

    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="test",
    requires=[
        # XXX: commented out. we want to test this requirement is automatically added.
        # "//tool:executable"
    ],
    steps=[
        execute("//tool:executable", task_path("test") / "test-1234"),
    ],
    outputs=[
        task_path('test')/'test-1234'
    ]
)    
"""
    makefile_path.write_text(file)

    file = """
task(
    name="executable",
    steps=[
        write("example.sh", '''#!/bin/sh\\necho "$(basename $1)" > $1'''),
        execute("chmod", "+x", task_path('executable')/"example.sh")
    ],
    outputs=task_path('executable')/'example.sh'
)    
"""
    tool_makefile_path = tmp_path / "tool" / "Makexfile"
    (tmp_path / "tool").mkdir(parents=True)

    tool_makefile_path.write_text(file)

    graph: TargetGraph = makex_context.graph

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTaskReference("test", makefile_path)
    a = graph.get_target(ref_a)
    print(a.requires)
    assert a
    assert TaskReferenceElement.from_strings("executable", "//tool") in a.requires


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
    ref_a = ResolvedTaskReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / OUTPUT_DIRECTORY_NAME / "test"
    assert (base / "file1").exists()
    assert (base / "file1").read_text() == "file1"


def test_erase(tmp_path, makex_context):
    """ Test the erase command.

        NOTE: depends on write() working.
    """
    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="test",
    steps=[
        write("file1", "test1"),
        write("file2", "test2"),
        
        write("test/file3", "test3"),
        write("file4.py", "# test"),
        
        erase("file2"),
        erase("test"),
        erase(glob("*.py")),
    ]
)    
    """
    makefile_path.write_text(file)

    graph = makex_context.graph

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)

    a = graph.get_target(ResolvedTaskReference("test", makefile_path))
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    base = tmp_path / OUTPUT_DIRECTORY_NAME / "test"

    # check a basic file removal
    assert (base / "file1").exists()

    # check the folder was removed
    assert not (base / "test").exists()

    # check the glob matched
    assert not (base / "file4.py").exists()


def test_mirror(tmp_path):
    # TODO: test mirror works properly
    pass


def test_archive(tmp_path, makex_context):
    makefile_path = tmp_path / "Makexfile"

    file = """
task(
    name="test",
    steps=[
        # copy a file to the Task output
        write("test.txt", "hello!"),
        archive(path="test.tar", files=["test.txt"])
    ]
)    
    """
    makefile_path.write_text(file)
    graph = makex_context.graph

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTaskReference("test", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    # read the archive created and check the member paths
    with tarfile.open(
        makex_context.graph_2.get_task2("test", makefile_path).cache_path / "test.tar"
    ) as f:
        print(f.getnames())
        assert f.getnames() == ["./test.txt"]


def test_archive2(tmp_path, makex_context):
    """ Test archiving with the files from another task.

    """
    makefile_path = tmp_path / "Makexfile"

    file = """
    
task(
    name="build-archive",
    requires=[":build"],
    steps=[
        # create an archive of the build task outputs
        # TODO: we should not need to pass root here. the list of files (and the task_path() argument) should provide the roots.
        #  archiving the files as they are in the fs without a root doesn't really make sense in the context of makex.
        archive(
          path="project.tar", 
          root=task_path("build"),
          files=[
            find(task_path("build")),
          ]
        ),
    ],
)

task(
    name="build",
    steps=[
        write("test.txt", "hello!")
    ]    
)
    """

    makefile_path.write_text(file)
    graph = makex_context.graph

    result = parse_makefile_into_graph(makex_context, makefile_path, graph)
    ref_a = ResolvedTaskReference("build-archive", makefile_path)

    a = graph.get_target(ref_a)
    assert a

    e = Executor(makex_context, workers=1, graph=result.graph)
    executed, errors = e.execute_targets(a)

    assert executed
    assert not errors

    # read the archive created and check the member paths
    with tarfile.open(
        makex_context.graph_2.get_task2("build-archive", makefile_path).cache_path / "project.tar"
    ) as f:
        print(f.getnames())
        assert f.getnames() == ["./test.txt"]
