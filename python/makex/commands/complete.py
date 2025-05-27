import os
from os.path import normpath
from pathlib import Path

from makex.command_line import (
    _find_makefile_and_yield,
    init_context_standard,
)
from makex.constants import (
    SYNTAX_2025,
    TASK_PATH_NAME_SEPARATOR,
)
from makex.locators import format_locator
from makex.makex_file_parser import TargetGraph


def main_complete(args, extra_args):
    """
    TODO: rename to shell-complete

    Complete the specified argument (path/target/etc).

    :param args:
    :param extra_args:
    :return:
    """
    # XXX: this is used in bash completions and should return fast/early.
    cwd = Path.cwd()

    #if args.directory:
    #    cwd = try_change_cwd(args.directory)

    ctx = init_context_standard(cwd, args)
    ctx.graph = graph = TargetGraph()

    string = args.string or ""

    parts = string.rsplit(TASK_PATH_NAME_SEPARATOR, 1)

    target_name = ""

    has_target_marker = False
    if len(parts) == 2:
        if ctx.makex_syntax_version == SYNTAX_2025:
            target_name, path = parts
        else:
            path, target_name = parts
        has_target_marker = True
    else:
        if ctx.makex_syntax_version == SYNTAX_2025:
            path = parts[0]
        else:
            target_name = parts[0]
            path = cwd

    def escape_print(string):
        print(f'''{string}''')

    # TODO: SYNTAX_2025: fix here.
    def print_task(name, path=None):
        locator = format_locator(name, path)
        print(locator)

    escape_print(f"mark:{string.replace('/','__')}")
    if not path:

        if target_name:
            for name, target in _find_makefile_and_yield(ctx, cwd):
                if has_target_marker:
                    if name.startswith(target_name):
                        print_task(name)
                else:
                    print_task(name)
        else:
            for name, target in _find_makefile_and_yield(ctx, cwd):
                print_task(name)
        # checking the cwd
        #print(f":NOPATH_TARGETS-{target}-{len(target)}")

        if has_target_marker:
            pass
        else:
            for entry in sorted(os.scandir(cwd), key=lambda x: x.name):
                if not entry.is_dir():
                    continue
                print_task(f"{entry.name}")
    elif path.startswith("//"):

        workspace_path_string = path[2:]
        normalized_path = normpath(workspace_path_string)
        has_ending_slash = workspace_path_string.endswith("/") is True
        workspace_path = Path(normalized_path)
        is_root = len(workspace_path.parts) == 0

        if is_root:
            # print targets at root of workspace
            #print("Targets of ", ctx.workspace_path)
            workspace_absolute_path = ctx.workspace_path
        else:
            workspace_absolute_path = ctx.workspace_path / workspace_path

        if workspace_absolute_path.exists():

            # print any targets
            target_prefix = f"//{workspace_path}" if not is_root else "//"

            if not has_ending_slash:
                #print(f"{prefix}:EXXI")
                # check the path for any default makexfiles/targets
                if target_name:
                    for name, target in _find_makefile_and_yield(ctx, workspace_absolute_path):
                        if has_target_marker:
                            if name.startswith(target_name):
                                print_task(name, target_prefix)
                        else:
                            print_task(name, target_prefix)

                if is_root is False and target_prefix:
                    escape_print(f"{target_prefix}/")

            # print any subdirectories
            if has_ending_slash or is_root:
                target_prefix = f"//{workspace_path}" if workspace_path.name else "/"
                for entry in os.scandir(workspace_absolute_path):
                    if not entry.is_dir():
                        continue
                    escape_print(f"{target_prefix}/{entry.name}")

        else:
            name = workspace_absolute_path.name
            search_parent = workspace_absolute_path.parent
            parent = workspace_path.parent

            if is_root:
                prefix = "//"
            else:
                prefix = f"//{parent}" if parent.name else "/"

            # try to complete the directory
            for entry in os.scandir(search_parent):
                if not entry.is_dir():
                    continue

                if entry.name.startswith(name):
                    escape_print(f"{prefix}/{entry.name}")

    elif path.startswith("/"):
        # we have an absolute path
        has_ending_slash = path[1:].endswith("/") is True
        absolute_path = normpath(path)
        absolute_path = Path(absolute_path)
        absolute_path_parent = absolute_path.parent
        is_root = len(absolute_path.parts) == 1

        if is_root:
            absolute_path_parent = Path("/")

        if absolute_path.exists():
            target_prefix = f"{absolute_path}" if is_root is False else ""
            if is_root is False and has_ending_slash is False:
                escape_print(f"{target_prefix}/")

            if target_name:
                for name, target in _find_makefile_and_yield(ctx, absolute_path):
                    if has_target_marker:
                        if name.startswith(target_name):
                            print_task(name, target_prefix)
                    else:
                        print_task(name, target_prefix)

            if has_ending_slash or is_root:
                # list the specific subdirectory
                for entry in os.scandir(absolute_path):
                    if not entry.is_dir():
                        continue

                    escape_print(f"{target_prefix}/{entry.name}")

        else:
            # list the parent
            for entry in _scandir_check_prefix(absolute_path_parent, absolute_path.name):
                print(entry.path)

    else:
        # we have a relative path
        has_ending_slash = path.endswith("/")
        path = normpath(path)
        relative_path = Path(path)
        absolute_path = cwd / relative_path
        absolute_path_parent = absolute_path.parent

        if has_ending_slash:
            # print the subdirectory
            for entry in os.scandir(absolute_path):
                if not entry.is_dir():
                    continue
                escape_print(f"{relative_path}/{entry.name}")
            pass
        else:
            if absolute_path.exists():
                target_prefix = relative_path.as_posix()
                escape_print(f"{target_prefix}/")
                # print any targets
                for name, target in _find_makefile_and_yield(ctx, absolute_path):
                    if has_target_marker:
                        if name.startswith(target_name):
                            print_task(name, target_prefix)
                    else:
                        print_task(name, target_prefix)
            else:
                for entry in _scandir_check_prefix(absolute_path_parent, absolute_path.name):
                    escape_print(f"{entry.name}")


def _scandir_check_prefix(path, prefix):
    for entry in os.scandir(path):
        if not entry.is_dir():
            continue

        if entry.name.startswith(prefix):
            yield entry
