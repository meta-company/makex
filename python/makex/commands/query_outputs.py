import sys
from pathlib import Path

from makex.command_line import (
    init_context_standard,
    parse_target,
    print_errors,
)
from makex.executor import Executor
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)


def main_get_outputs(args):
    """
    Return the output files of target/path (optionally recursively).

    :param args:
    :return:
    """
    cwd = Path.cwd()
    ctx = init_context_standard(cwd, args)

    target = parse_target(ctx, cwd, args.target)
    ctx.graph = graph = TargetGraph()
    ctx.ui.print(f"Current working directory: {ctx.colors.BOLD}{cwd}{ctx.colors.RESET}")

    ctx.ui.print(f"Loading makex file at {target.path}")

    result = parse_makefile_into_graph(ctx, target.path, graph)

    if result.errors:
        print_errors(ctx, result.errors)
        sys.exit(-1)

    t = graph.get_target(target)
    if t is None:
        ctx.ui.print(
            f"Task \"{ctx.colors.BOLD}{target.name}{ctx.colors.RESET}\" not found in {target.path}",
            error=True
        )
        sys.exit(-1)

    # XXX: don't execute anything, evaluate the target outputs manually
    executor = Executor(ctx, workers=1, force=args.force)
    evaluated, errors = executor._evaluate_target(t)

    if len(errors):
        print_errors(ctx, errors)
        sys.exit(-1)

    if args.output_names:
        paths = []
        for output_name in args.output_names:
            output = evaluated.outputs.get(output_name)
            paths.append(output.path)
        print(" ".join(paths))
    else:
        for output in evaluated.outputs:
            print(output.path)
