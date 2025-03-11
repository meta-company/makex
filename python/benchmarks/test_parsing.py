from makex.context import Context
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)
from makex.workspace import Workspace


def test_parsing(benchmark, tmp_path):
    makexfile = """
task(
    name="test",
    steps=[]
)
    """

    a = tmp_path / "Makexfile"

    a.write_text(makexfile)

    ctx = Context()
    ctx.workspace_object = Workspace(tmp_path)

    def parse(makexfile: str):
        graph = TargetGraph()
        result = parse_makefile_into_graph(ctx, a, graph)

    benchmark(parse, makexfile)
