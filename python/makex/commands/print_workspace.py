from pathlib import Path

from makex.command_line import (
    init_context_standard,
    try_change_cwd,
)


def main_workspace(args, extra_args):
    # Fast function to print targets.
    # XXX: this is used in bash completions and should return early.
    cwd = Path.cwd()

    if args.path:
        # change to the path and let initialization detect the workspace.
        cwd = try_change_cwd(args.path)

    ctx = init_context_standard(cwd, args)
    print(ctx.workspace_path)
