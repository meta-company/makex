import os
import signal
import sys
from pathlib import Path
from typing import (
    Optional,
    Union,
)

from makex._logging import trace
from makex.colors import (
    Colors,
    NoColors,
)
from makex.configuration import (
    collect_configurations,
    evaluate_configuration_environment,
    read_configuration,
)
from makex.constants import (
    ABSOLUTE_WORKSPACE,
    CONFIGURATION_ARGUMENT_ENABLED,
    DIRECT_REFERENCES_TO_MAKEX_FILES,
    SYNTAX_2025,
    TASK_PATH_NAME_SEPARATOR,
    WORKSPACE_ARGUMENT_ENABLED,
)
from makex.context import (
    Context,
    detect_shell,
)
from makex.errors import (
    CacheError,
    ConfigurationError,
    Error,
    GenericSyntaxError,
    MultipleErrors,
)
from makex.flags import MAKEX_SYNTAX_VERSION
from makex.makex_file_parser import parse_makefile_into_graph
from makex.makex_file_types import TaskReference
from makex.run import (
    get_running_process_ids,
    run,
)
from makex.ui import (
    UI,
    early_ui_printer,
    print_error,
)
from makex.workspace import (
    current_workspace,
    get_workspace,
)


def init_context_standard(cwd, args):
    colors = Colors if args.color else NoColors

    verbosity = args.verbose
    if args.debug:
        verbosity = 3

    # Show early ui if verbose OR debug.
    early_ui = early_ui_printer(verbosity, colors)
    early_ui("Loading configuration files...")

    try:
        files = collect_configurations(cwd, verbose=early_ui)
    except GenericSyntaxError as e:
        print(e.pretty(colors))
        sys.exit(-1)

    if CONFIGURATION_ARGUMENT_ENABLED:
        if args.configuration:
            # append the argument provided configuration file last so it takes priority
            try:
                path = Path(args.configuration).resolve()
            except Exception:
                early_ui(
                    f"Error loading configuration file specified with --configuration argument: {args.configuration}",
                    error=True
                )
                sys.exit(-1)

            path = path.resolve()

            if not path.exists():
                early_ui(
                    f"Configuration file specified with --configuration argument does not exist at {path}",
                    error=True
                )
                sys.exit(-1)

            configuration = read_configuration(path)
            files.configuration_files.append(configuration)

    configuration = files.merged()

    early_ui(f"Merged Configuration: {configuration!r}", level=3)

    current_enviroment = os.environ.copy()

    if False and "VIRTUAL_ENV" in current_enviroment:
        # Fix a bug with getting recursive with venv.
        # TODO: We need to strip the PATH too.
        current_enviroment.pop("VIRTUAL_ENV")

    if configuration.environment:
        early_ui(
            f"Evaluating environment from configuration: {configuration.environment}...", level=1
        )
        try:
            configuration_environment = evaluate_configuration_environment(
                shell=configuration.shell or detect_shell(),
                env=configuration.environment,
                current_enviroment=current_enviroment,
                cwd=cwd,
                run=run,
            )
        except ConfigurationError as e:
            early_ui(e, error=True)
            sys.exit(-1)

        if configuration_environment:
            early_ui(f"Environment from configuration: {configuration_environment}", level=1)
            current_enviroment.update(configuration_environment)

    argument = args.workspace if WORKSPACE_ARGUMENT_ENABLED else None
    workspace = current_workspace(
        cwd,
        files=files,
        argument=argument,
        environment=get_workspace(),
    )

    early_ui(f"Current workspace: {workspace.path}", level=1)

    ctx = Context(
        environment=current_enviroment,
        workspace_object=workspace,
        debug=args.debug,
        color=args.color,
        colors=colors,
        ui=UI(verbosity=verbosity, colors=colors),
        dry_run=getattr(args, "dry", False),
        cpus=args.cpus,
    )
    ctx.workspace_cache.add(workspace)
    try:
        ctx = ctx.with_configuration(configuration, early_ui)
    except CacheError as e:
        early_ui(e, error=True)
        sys.exit(-1)

    return ctx


def find_makex_files(path, names):
    for name in names:
        file = path.joinpath(name)
        if file.exists():
            return file

    return None


class GlobalArgs:
    pass


def _yield_targets(ctx, file, graph):
    result = parse_makefile_into_graph(ctx, file, graph)

    for name, target in result.makex_file.targets.items():
        yield name, target


def _find_makefile_and_yield(ctx, directory):
    file = find_makex_files(directory, ctx.makex_file_names)

    if not file:
        return None

    yield from _yield_targets(ctx, file, ctx.graph)


def print_errors(ctx: Context, errors: Union[Exception, MultipleErrors]):
    colors = ctx.colors

    if errors:
        print(f"{colors.ERROR}{colors.BOLD}The execution had errors:{colors.RESET}\n")

    for error in errors:
        print("---------------")
        print_error(colors, error)


def try_change_cwd(cwd: str):
    cwd = Path(cwd)
    if not cwd.exists():
        print(f"Error changing to specified directory: Path {cwd} doesn't exist.")
        sys.exit(-1)
    os.chdir(cwd)
    return cwd


def _kill_running_processes():
    # XXX: send a signal to any processes we created.
    for pid in get_running_process_ids():
        os.killpg(os.getpgid(pid), signal.SIGKILL)


def parse_target(
    ctx,
    base: Path,
    string: str,
    check=True,
    syntax=MAKEX_SYNTAX_VERSION,
) -> Optional[TaskReference]:
    """
    A variation of parse target which prints errors
    :param base:
    :param string:
    :param check:
    :return:
    """

    # resolve the path/makefile?:target_or_build_path name
    # return name/Path
    # TODO: SYNTAX_2025: must be fixed here.
    parts = string.split(TASK_PATH_NAME_SEPARATOR, 1)
    check_upwards = False
    if len(parts) == 2:
        if syntax == SYNTAX_2025:
            task_name, _path = parts
        else:
            _path, task_name = parts
        path = Path(_path)

        if not task_name:
            ctx.ui.print(f"Invalid task name {task_name!r} in argument: {string!r}.", error=True)
            sys.exit(-1)

        if path.parts and path.parts[0] == ABSOLUTE_WORKSPACE:
            trace("Translate workspace path %s %s", path, ctx.workspace_object.path)
            path = ctx.workspace_object.path.joinpath(*path.parts[1:])
        elif not path.is_absolute():
            path = base / path
        elif path.is_symlink():
            path = path.readlink()
    else:
        task_name = parts[0]
        path = base
        check_upwards = True

    #trace("Parse target %s -> %s:%s %s %s", string, target, path, parts, path.parts)
    if path.is_dir():
        #if check:
        # check for Build/Makexfile in path
        file = find_makex_files(path, names=ctx.makex_file_names)
        if file is None:
            if check_upwards:
                # task path was omitted; search upwards for makex file
                if not path.is_relative_to(ctx.workspace_path):
                    raise Error(f"Can't run task. Current folder ({path}) is not in workspace.")

                found = None
                for parent in [path] + list(path.parents):
                    file = find_makex_files(parent, names=ctx.makex_file_names)
                    if file is None:
                        continue

                    if parent == ctx.workspace_path:
                        break

                    found = file

                if found is None:
                    raise Error(f"No makex file found in {path} or parent folders.")

                file = found

            else:

                ctx.ui.print(
                    f"Makex file does not exist for task specified: {task_name}", error=True
                )
                for check in ctx.makex_file_names:
                    ctx.ui.print(f"- Checked in {path/check}")
                sys.exit(-1)
    elif path.is_file():
        if DIRECT_REFERENCES_TO_MAKEX_FILES is False:
            raise Error(
                f"Direct references to Makex files not permitted. Path to task is not a folder. Got {path}."
            )
        file = path
    else:
        raise NotImplementedError(f"Unknown file type {path}")

    return TaskReference(task_name, path=file)
