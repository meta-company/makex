import sys
import traceback
from pathlib import Path

from makex._logging import debug
from makex.command_line import (
    _kill_running_processes,
    init_context_standard,
    parse_target,
    print_errors,
    try_change_cwd,
)
from makex.constants import ABSOLUTE_WORKSPACE
from makex.executor import Executor
from makex.locators import format_locator
from makex.makex_file_parser import (
    TargetGraph,
    parse_makefile_into_graph,
)


def main_run(args, extra_args):
    cwd = Path.cwd()

    if args.directory:
        cwd = try_change_cwd(args.directory)

    ctx = init_context_standard(cwd, args)

    debug("Current content: %s", ctx)

    targets = []

    for target in args.tasks:
        ref = parse_target(ctx, cwd, target)
        targets.append(ref)

    ctx.graph = graph = TargetGraph()
    ctx.ui.print(f"Current working directory: {ctx.colors.BOLD}{cwd}{ctx.colors.RESET}")
    for target in targets:

        ctx.ui.print(f"Loading makex file at {target.path}")

        result = parse_makefile_into_graph(ctx, target.path, graph)

        if result.errors:
            print_errors(ctx, result.errors)
            sys.exit(-1)

    targets_to_run = []

    for target in targets:
        t = graph.get_target(target)
        if t is None:
            ctx.ui.print(
                f"Task \"{ctx.colors.BOLD}{target.name}{ctx.colors.RESET}\" not found in {target.path!r}",
                error=True
            )
            sys.exit(-1)

        targets_to_run.append(t)

    ctx.ui.print(f"Executing {len(targets_to_run)} tasks...")

    # TODO: SYNTAX_2025: fix here
    for target in targets_to_run:
        input = target.path_input()

        if input.is_relative_to(ctx.workspace_path):
            input = input.relative_to(ctx.workspace_path)
            input = ABSOLUTE_WORKSPACE + input.as_posix()
            ctx.ui.print(f"- {format_locator(target.name, input, syntax=ctx.makex_syntax_version)}")
        else:
            input = ABSOLUTE_WORKSPACE + input.as_posix()
            ctx.ui.print(f"- {format_locator(target.name, input, syntax=ctx.makex_syntax_version)}")

    # XXX: Currently set to one to avoid much breakage. Things are fast enough, for now.
    workers = args.cpus
    executor = Executor(ctx, workers=workers, force=args.force)

    try:
        executed, errors = executor.execute_targets(*targets_to_run)

        if len(errors):
            print_errors(ctx, errors)
            sys.exit(-1)

    except KeyboardInterrupt as e:
        executor.stop.set()
        _kill_running_processes()
        sys.exit(-1)

    except IOError as e:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        ctx.ui.print(f"There was an IO Error: {e} ({e.filename})", error=True)
        sys.exit(-1)

    except Exception as e:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        sys.exit(-1)
