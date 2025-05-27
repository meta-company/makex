import sys
from pathlib import Path

from makex.build_path import get_build_path
from makex.command_line import (
    init_context_standard,
    parse_target,
)
from makex.workspace import which_workspace


def main_get_path(args, extra):
    """
    Return build path of specified of target
    :param args:
    :return:
    """
    cwd = Path.cwd()
    ctx = init_context_standard(cwd, args)
    ref = parse_target(ctx, cwd, args.task)

    #debug("Current environment: %s", pformat(os.environ.__dict__, indent=2))

    if ref is None:
        print(f"Invalid task reference: {args.task!r}")
        sys.exit(-1)

    target_input = ref.path

    # assume the default/detected
    workspace = ctx.workspace_object

    if args.real:
        workspace = which_workspace(workspace.path, target_input)

    obj = get_build_path(
        objective_name=ref.name,
        variants=[],
        input_directory=target_input.parent,
        build_root=ctx.cache,
        workspace=workspace.path,
        workspace_id=workspace.id,
        output_folder=ctx.output_folder_name,
    )

    # TODO: allow getting the path of a specific output file

    path, link = obj

    if args.real:
        print(path)
        sys.exit(0)

    print(link)
    sys.exit(0)
