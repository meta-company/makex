import operator
import os
import sys
from pathlib import Path

from makex.command_line import GlobalArgs
from makex.context import Context
from makex.executor import Executor
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)
from makex.scoping import (
    ParsedScope,
    parse_scope,
)


class AffectedArgs(GlobalArgs):
    """
        affected --scope //* paths or stdin

    """

    # list of paths that are marked as changed to find dependent tasks.
    # paths may be relative, absolute, or workspace
    paths: list[str]

    # list of paths to change scope of makex file searches
    scope: list[str]


def _find_files(path, names: set[str]):
    # XXX: use os.scandir for performance
    for entry in os.scandir(path):
        if entry.is_file():
            if entry.name in names:
                yield Path(entry.path, entry.name)
        elif entry.is_dir():
            yield from _find_files(entry, names)


def main_affected(args: AffectedArgs, extra_args):
    """
    Return all the targets affected by a change in the specified files.

    Allow output to tree format which can be "executed" in dependency order, or a list.

    - name: ""
      path: ""
      requires:
      - name: ""
        path: ""
      - ...

    - name: ""
      path: ""
      requires:
      - name: ""
        path: ""

    :param args:
    :param extra_args:
    :return:
    """
    # find all the makexfile under path
    # add them all to the graph

    # for the specified targets, return the reverse dependencies
    # eg. we change a project, we want to query all dependents and their dependents to rebuild them

    scopes: list[ParsedScope] = [parse_scope(scope) for scope in args.scope or []]

    cwd = Path.cwd()
    ctx = Context()
    ctx.graph = graph = TargetGraph()
    ctx.ui.print(f"Current working directory: {ctx.colors.BOLD}{cwd}{ctx.colors.RESET}")

    for scope in scopes:
        for makefile in _find_files(scope.path, names={"Makexfile"}):
            result = parse_makefile_into_graph(ctx, makefile, graph)

    if len(args.paths) == 1 and args.paths[0] == "-":
        paths = [Path(line) for line in sys.stdin.readlines()]
    else:
        paths = [Path(path) for path in args.paths]

    # start an executor in analysis mode to evaluate tasks
    executor = Executor(ctx, workers=args.threads, force=True, analysis=True)

    # evaluate all the targets we've collected into graph 2.
    executor.execute_targets(ctx.graph.get_all_tasks())

    # query the evaluated task graph for the specified paths and which targets they are required by
    graph = executor.graph_2
    affected_tasks = list(
        graph.get_affected(paths, scopes=list(map(operator.attrgetter("path"), scopes)))
    )

    for task in affected_tasks:
        print(task)
