import sys
from pathlib import Path

from makex.command_line import (
    _yield_targets,
    find_makex_files,
    init_context_standard,
)
from makex.constants import TASK_PATH_NAME_SEPARATOR
from makex.locators import format_locator
from makex.makex_file_parser import TargetGraph


def main_targets(args, extra_args):
    # Fast function to print targets of specified directory or makex file.
    cwd = Path.cwd()

    #if args.directory:
    #    cwd = try_change_cwd(args.directory)

    ctx = init_context_standard(cwd, args)

    targets = []

    path = args.path

    # TODO: SYNTAX_2025: fix here.
    target_name = None
    if path:
        if path.find(TASK_PATH_NAME_SEPARATOR) > -1:
            path, target_name = path.rsplit(TASK_PATH_NAME_SEPARATOR, 1)

        if path.startswith("//"):
            _path = ctx.workspace_path / path[2:]
        elif not path and target_name:
            _path = cwd
        else:
            _path = Path(path)
            if not _path.is_absolute():
                _path = cwd / _path
    else:
        _path = cwd

    file = find_makex_files(_path, ctx.makex_file_names)

    if not file:
        return sys.exit(-1)

    ctx.graph = graph = TargetGraph()

    directory = file.parent
    workspace_path = directory.relative_to(ctx.workspace_path)
    cwd_relative_path = _path.relative_to(cwd)
    if cwd_relative_path.name == "":
        cwd_relative_path = ""

    #result = parse_makefile_into_graph(ctx, file, ctx.graph)

    prefix = ""
    if args.prefix:
        prefix = ":"
    end = "\n"

    for name, target in _yield_targets(ctx, file, ctx.graph):
        #for name, target in result.makex_file.targets.items():
        if args.paths == "workspace":
            #workspace_path = target.path_input()
            print(f"//{workspace_path}:{name}", end=end)
        elif args.paths == "absolute":
            #workspace_path = target.path_input().resolved.relative_to(target.workspace.path)
            print(f"ABS:{target.path_input()}:{name}", end=end)
        elif args.paths == "relative":
            #workspace_path = target.path_input().resolved.relative_to(target.workspace.path)
            print(f"REL:{cwd_relative_path}:{name}", end=end)
        elif args.paths is None:
            print(format_locator(name, syntax=ctx.makex_syntax_version), end=end)
