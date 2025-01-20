import logging
import os
from logging import debug
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    Union,
)

import pytest
from makex.context import Context
from makex.executor import Executor
from makex.makex_file import (
    MakexFile,
    TaskObject,
)
from makex.makex_file_actions import InternalActionBase
from makex.makex_file_parser import TargetGraph
from makex.makex_file_types import (
    PathElement,
    ResolvedTaskReference,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import FileLocation
from makex.target import EvaluatedTask
from makex.workspace import Workspace


class PathMaker:
    def __init__(self, root=None):
        self.root = root or Path.cwd()

    def __truediv__(self, other):
        path = Path(other)
        parent = self.root

        if not path.is_absolute():
            path = parent / path
        else:
            path = path

        return PathElement(*path.parts, resolved=path)

    def path(self, *args):
        path = Path(*args)
        #if not args:
        #    return PathElement(*args, resolved=path)

        parent = self.root

        if not path.is_absolute():
            path = parent / path
        else:
            path = path

        return PathElement(*path.parts, resolved=path)

    __call__ = path


@pytest.fixture
def makex_context(tmp_path):
    # TODO: use this context in the tests
    _workspace = Workspace(tmp_path)

    ctx = Context(environment=os.environ.copy())
    ctx.graph = TargetGraph()
    ctx.debug = True
    ctx.workspace_object = _workspace
    ctx.workspace_cache.add(_workspace)
    ctx.cache = tmp_path / "makex_cache"
    return ctx


def test_sort(tmp_path):
    """
    diamond:
    a
    /\
    bc
    \/
    d


    """
    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)

    pathmaker = PathMaker()
    path = pathmaker.path

    l = fake_location(tmp_path / "Makexfile")

    makex_file = MakexFile(None, tmp_path / "Makexfile")
    d = TaskObject("d", makex_file=makex_file, location=l)
    b = TaskObject("b", requires=[d], makex_file=makex_file, location=l)
    c = TaskObject("c", requires=[d], makex_file=makex_file, location=l)
    a = TaskObject("a", requires=[b, c], makex_file=makex_file, location=l)
    #errors = e.execute_targets(a)

    g = TargetGraph()
    g.add_targets(ctx, a, b, c, d)
    print(list(g.topological_sort_grouped([a])))
    assert True


@pytest.mark.skip(reason="Incomplete.")
def test1(tmp_path):
    """
    diamond:
    a
    /\
    bc
    \/
    d


    """

    path = PathMaker(tmp_path)

    l = fake_location(tmp_path / "Makefilex")

    assert TaskObject("d", location=l) == TaskObject("d", location=l)
    assert TaskObject("a", location=l) != TaskObject("d", location=l)

    assert TaskObject("d", location=l) in {TaskObject("d", location=l), TaskObject("a", location=l)}
    assert TaskObject("d", location=l) not in {TaskObject("c", location=l)}

    # force in paths so we resolve properly
    d = TaskObject("d", path=path("d"), location=l)
    b = TaskObject("b", path=path("b"), requires=[d], location=l)
    c = TaskObject("c", path=path("c"), requires=[d], location=l)
    a = TaskObject("a", path=path("a"), requires=[b, c], location=l)

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    ctx.graph = g = TargetGraph()
    g.add_targets(ctx, a, b, c, d)

    e = Executor(ctx, workers=2)
    errors = e.execute_targets(a)

    # TODO: assert execution order is one of valid

    #assert False
    #assert not errors


def paths(*ps):
    return [PathElement(p) for p in ps]


def path(*args: Union[str, PathLike], parent=None):
    #path = Path(*args)

    #if not path.is_absolute():
    #    path = parent / path
    #else:
    #    path = parent / path

    return PathElement(*args, resolved=None)


class WriteTestAction(InternalActionBase):
    def __init__(self, path: str, text, location=None):
        self.path: str = path
        self.text = text
        self.location = location

    def __repr__(self):
        return f"Write({self.path}) -> {self.text}"

    def hash(
        self,
        ctx: Context,
        arguments: dict[str, Any],
        hash_function: StringHashFunction,
    ):
        return hash_function(f"{self.path}|{self.text}")

    def transform_arguments(self, ctx: Context, target: EvaluatedTask):
        pass

    def run_with_arguments(self, ctx: Context, target: EvaluatedTask, arguments) -> CommandOutput:
        path = Path(self.path)
        if not path.is_absolute():
            path = target.path / self.path

        logging.debug("Writing file at %s", path)
        path.write_text(self.text)

        return CommandOutput(0)


def write(path: str, text=None):
    return WriteTestAction(path, text or str(path))


def fake_location(path):
    return FileLocation(0, 0, path)


def test_input_ouput(tmp_path: Path):
    """
    Test diamond dependencies.

    d
    /\
    cb
    \/
    a

    """

    input = tmp_path / "input"
    input.mkdir()

    output = tmp_path / "output"
    output.mkdir()

    input_make_file = input / "Makexfile"

    input.joinpath("a").write_text("a")
    input.joinpath("b").write_text("b")
    input.joinpath("c").write_text("c")
    input.joinpath("d").write_text("d")

    location = fake_location(input_make_file)

    opath = PathMaker(output)

    ipath = PathMaker(input)

    debug("$SSSSS %s", opath())

    makex_file = MakexFile(None, input_make_file)
    d = TaskObject(
        "d",
        path=opath(),
        requires=[ipath("d")],
        outputs=[opath("d")],
        run=[write("d")],
        location=location,
        makex_file=makex_file,
    )
    b = TaskObject(
        "b",
        path=opath(),
        requires=[ipath("b"), d],
        outputs=[opath("b")],
        run=[write("b")],
        location=location,
        makex_file=makex_file,
    )
    c = TaskObject(
        "c",
        path=opath(),
        requires=[ipath("c"), d],
        outputs=[opath("c")],
        run=[write("c")],
        location=location,
        makex_file=makex_file,
    )
    a = TaskObject(
        "a",
        path=opath(),
        requires=[ipath("a"), b, c],
        outputs=[opath("d")],
        run=[write("a")],
        location=location,
        makex_file=makex_file,
    )

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    ctx.graph = g = TargetGraph()
    g.add_targets(ctx, a, b, c, d)

    e = Executor(ctx, workers=1)
    executed, errors = e.execute_targets(a)

    debug("Executed targets: %s", executed)

    # assert execution order is valid
    l = [
        ResolvedTaskReference("d", input_make_file),
        ResolvedTaskReference("b", input_make_file),
        ResolvedTaskReference("c", input_make_file),
        ResolvedTaskReference("a", input_make_file),
    ]
    #assert l == [d, b, c, a]
    assert l[0] == d
    assert executed == l

    # check the outputs were written
    assert opath("d").resolved.read_text() == "d"
    assert opath("b").resolved.read_text() == "b"
    assert opath("c").resolved.read_text() == "c"
    assert opath("a").resolved.read_text() == "a"

    # Second run without changing anything should not execute
    debug("No changes !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    executed, errors = e.execute_targets(a)
    assert not errors, f"Got {errors}"
    assert len(executed) == 0, f"Tasks were executed when they shouldn't have been: {executed}"

    # Changing d should cause a rebuild of all
    debug("Modify D !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    input.joinpath("d").write_text("d2")
    executed, errors = e.execute_targets(a)
    assert executed
    assert len(executed) == 4
    assert executed == l


def test2():
    """
    TODO: test multiple roots.
    a b
    | |
    c d
    \ /|
     e f
    
    """

    f = TaskObject("f")
    e = TaskObject("e")
    d = TaskObject("d", requires=[f, e])
    c = TaskObject("c", requires=[e])
    b = TaskObject("b", requires=[d])
    a = TaskObject("a", requires=[c])
