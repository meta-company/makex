import logging
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
    InternalActionBase,
    MakexFile,
    TargetObject,
)
from makex.makex_file_parser import TargetGraph
from makex.makex_file_types import (
    PathElement,
    ResolvedTargetReference,
    TargetReferenceElement,
)
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import FileLocation
from makex.target import EvaluatedTarget
from makex.workspace import Workspace


class PathMaker:
    def __init__(self, root=None):
        self.root = root or Path.cwd()

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
    d = TargetObject("d", makex_file=makex_file, location=l)
    b = TargetObject("b", requires=[d], makex_file=makex_file, location=l)
    c = TargetObject("c", requires=[d], makex_file=makex_file, location=l)
    a = TargetObject("a", requires=[b, c], makex_file=makex_file, location=l)
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

    pathmaker = PathMaker()
    path = pathmaker.path

    l = fake_location(tmp_path / "Makefilex")

    assert TargetObject("d", location=l) == TargetObject("d", location=l)
    assert TargetObject("a", location=l) != TargetObject("d", location=l)

    assert TargetObject(
        "d", location=l
    ) in {TargetObject("d", location=l), TargetObject("a", location=l)}
    assert TargetObject("d", location=l) not in {TargetObject("c", location=l)}

    # force in paths so we resolve properly
    d = TargetObject("d", path=path("d"), location=l)
    b = TargetObject("b", path=path("b"), requires=[d], location=l)
    c = TargetObject("c", path=path("c"), requires=[d], location=l)
    a = TargetObject("a", path=path("a"), requires=[b, c], location=l)

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)
    ctx.graph = g = TargetGraph()
    g.add_targets(ctx, a, b, c, d)

    e = Executor(ctx, workers=2)
    errors = e.execute_targets(a)

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

    def transform_arguments(self, ctx: Context, target: EvaluatedTarget):
        pass

    def run_with_arguments(self, ctx: Context, target: EvaluatedTarget, arguments) -> CommandOutput:
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

    o_pathmaker = PathMaker(output)
    opath = o_pathmaker.path

    i_pathmaker = PathMaker(input)
    ipath = i_pathmaker.path

    debug("$SSSSS %s", opath())

    makex_file = MakexFile(None, input_make_file)
    d = TargetObject(
        "d",
        path=opath(),
        requires=[ipath("d")],
        outputs=[opath("d")],
        run=[write("d")],
        location=location,
        makex_file=makex_file,
    )
    b = TargetObject(
        "b",
        path=opath(),
        requires=[ipath("b"), d],
        outputs=[opath("b")],
        run=[write("b")],
        location=location,
        makex_file=makex_file,
    )
    c = TargetObject(
        "c",
        path=opath(),
        requires=[ipath("c"), d],
        outputs=[opath("c")],
        run=[write("c")],
        location=location,
        makex_file=makex_file,
    )
    a = TargetObject(
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
    l = [
        ResolvedTargetReference("d", input_make_file),
        ResolvedTargetReference("b", input_make_file),
        ResolvedTargetReference("c", input_make_file),
        ResolvedTargetReference("a", input_make_file),
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
    assert not executed, f"Got {executed}"

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

    f = TargetObject("f")
    e = TargetObject("e")
    d = TargetObject("d", requires=[f, e])
    c = TargetObject("c", requires=[e])
    b = TargetObject("b", requires=[d])
    a = TargetObject("a", requires=[c])
