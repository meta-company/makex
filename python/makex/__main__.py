import importlib.resources
import logging
import os
import platform
import signal
import sys
from argparse import (
    SUPPRESS,
    Action,
    ArgumentError,
    ArgumentParser,
    Namespace,
)
from pathlib import Path
from typing import (
    Any,
    Literal,
    Sequence,
    Union,
)

from makex._logging import initialize_logging
from makex.command_line import _kill_running_processes
from makex.commands.complete import main_complete
from makex.commands.fix import main_fix_parser
from makex.commands.print_path import main_get_path
from makex.commands.print_workspace import main_workspace
from makex.commands.query_affected import main_affected
from makex.commands.query_inputs import main_get_inputs
from makex.commands.query_outputs import main_get_outputs
from makex.commands.query_tasks import main_targets
from makex.commands.run import main_run
from makex.constants import (
    CONFIGURATION_ARGUMENT_ENABLED,
    TASK_PATH_NAME_SEPARATOR,
    WORKSPACE_ARGUMENT_ENABLED,
)
from makex.flags import VARIANTS_ENABLED
from makex.ui import is_ansi_tty
from makex.version import VERSION

COMPLETE_TARGET = {
    "bash": "_shtab_makex_compgen_paths",
    "zsh": "_shtab_makex_complete_target",
}


def is_color_enabled(color_argument: Literal["no", "auto", "off", "on", "yes"]):
    color_argument = color_argument.lower()
    if color_argument == "auto":
        return is_ansi_tty()
    elif color_argument in {"no", "off"}:
        return False
    elif color_argument in {"yes", "on"}:
        return True

    return None


class Verbosity(Action):
    def __init__(self, *args, default_none=3, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_none = default_none

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: Union[str, Sequence[Any], None],
        option_string: Union[str, None] = ...
    ) -> None:
        """
        --verbose == 3
        --verbose=3 is 3
        --verbose=2 is 2
        --verbose=0 is off
        :param parser:
        :param namespace:
        :param values:
        :param option_string:
        :return:
        """
        value = None
        print("parse values", values, namespace)
        if values is not None:
            try:
                value = int(values)
            except Exception as e:
                raise ArgumentError(
                    self, f"Error parsing verbosity argument. Must be a number. Got {value}"
                )
        else:
            value = self.default_none

        if value is not None:
            namespace.verbose = value
        else:
            namespace.verbose = False

        sys.exit(0)


def _add_global_arguments(base_parser, cache: Path = None, documentation: bool = True, help=None):
    # Allow supressing help so the arguments work before and after the specified command.
    # all arguments should be optional for sphinx
    # documentation = True by default to ease automatic documentation by sphinx

    base_parser.add_argument(
        #"-v",
        "--verbose",
        default=0,
        action="count",
        help=help or
        "Verbosity of makex messaging. Specify multiple times or set to a number between 0 and 3. (The default is 0 and the maximum is 3)."
    )

    if WORKSPACE_ARGUMENT_ENABLED:
        base_parser.add_argument(
            #"-W",
            "--workspace",
            action="store_true",
            default=False,
            help=help or "Path to the current workspace. This should not be used unless necessary."
        )

    base_parser.add_argument(
        # "-d",
        "--debug",
        action="store_true",
        default=False,
        help=help or "Enable debug and logging to the maximum level."
    )

    base_parser.add_argument(
        "--profile-mode",
        choices=["cprofile", "yappi"],
        default="yappi",
        help=SUPPRESS,
        #help="Enable profiling. Specify file name to write stats to a file. - to write to stdout."
    )

    if documentation is False:
        # Hide from documentation
        base_parser.add_argument(
            "--profile",
            #help="Enable profiling. Specify file name to write stats to a file. - to write to stdout.",
            help=SUPPRESS,
        )

    if CONFIGURATION_ARGUMENT_ENABLED:
        base_parser.add_argument(
            #"-C",
            "--configuration",
            action="store_true",
            default=False,
            help=help or "Path to a Makex configuration file. This is not normally required."
        )

    base_parser.add_argument(
        "--color",
        choices=["off", "auto", "on"],
        default="auto",
        help=help or "Print colored messaging."
    )
    #parser.add_argument("--define", nargs="*", action="append", help="define a variable")

    help_text = "The unified external cache/build path."
    if cache:
        help_text += f"[default={cache}]"

    base_parser.add_argument(
        "--cache",
        default=False,
        help=help or help_text,
    )

    if documentation is False:
        base_parser.add_argument(
            # "-d",
            "--python-audit",
            nargs="?",
            action="append",
            help=help or
            "Enable auditing of python audit hooks. Pass a identifier. May be passed multiple times.",
        )
    return base_parser


def parser(cache: Path = None, documentation: bool = True):

    #base_parser = ArgumentParser(add_help=False)
    #base_parser = _base_parser(base_parser, cache, documentation)

    system = platform.system()
    if documentation: # XXX: Documentation mode. For sphinx. Don't calculate cpus default.
        cpus = 1
    elif system in {"Linux"}:
        cpus = max(len(os.sched_getaffinity(0)), 1)
    elif system == "windows":
        # Windows
        cpus = psutil.Process().cpu_affinity()
    else:
        # assume at least one cpu is available
        cpus = 1

    # TODO: most of the subcommands use threads in some way.
    def add_threads_argument(subparser):
        subparser.add_argument(
            #"-t",
            "--cpus",
            type=int,
            help=f"Worker CPUs to use for parsing, evaluating and running tasks in parallel. (Default: {cpus})",
            default=cpus
        )

    parser = ArgumentParser(
        prog="makex",
        description="""Makex command line program.\n\nSee https://meta.company/go/makex for the latest documentation.""",
        epilog="""""", #parents=[base_parser],
    )
    _add_global_arguments(parser, cache, documentation)

    base_parser = ArgumentParser(prog="makex", add_help=False)
    _add_global_arguments(base_parser, cache, documentation, help=SUPPRESS)

    # XXX: help argument must be specified otherwise shtab will not see the sub-commands (specifically in the zsh generator)
    #   see: https://github.com/iterative/shtab/blob/eb12748b7068848ddd7b570abcd180df7264332a/shtab/__init__.py#L136
    #   see: https://github.com/python/cpython/blob/58f883b91bd8dd4cac38b58a026397363104a129/Lib/argparse.py#L1220
    #    ("help" in kwargs, if not specified, self._choices_actions will not be filled.)
    subparsers = parser.add_subparsers(
        dest='command',
        title="commands",
        description="Valid commands",
        help="Commands you may enter.",
        required=True,
    )

    ######### run
    subparser = subparsers.add_parser(
        "run",
        help="Run a task or list of tasks.",
        description="Run a task or list of tasks.",
        parents=[base_parser],
    )
    subparser.set_defaults(command_function=main_run)

    action = subparser.add_argument(
        "tasks",
        nargs="+",
    )
    action.complete = COMPLETE_TARGET
    subparser.add_argument(
        "--directory",
        help="Change to directory before evaluating tasks.",
    ) #"-C",

    subparser.add_argument(
        "--force",
        action="store_true",
        help="Always run all tasks even if they don't need to be.",
    ) #"-f",

    subparser.add_argument(
        "--dry",
        action="store_true",
        default=False,
        help="Do a dry run. Nothing will be executed.",
    )

    if VARIANTS_ENABLED:
        subparser.add_argument(
            "--variants",
            nargs="*",
            action="append",
            help="specify variants. name=value command separated. or specify multiple times."
        )

    if False:
        subparser.add_argument(
            "--ignore",
            nargs="*",
            action="append",
            help="Specify file ignore patterns for input/output files.",
        )

    add_threads_argument(subparser)

    ######## path
    subparser = subparsers.add_parser(
        "path",
        help="Get the output path of a task.",
        description="Get the output path of a task.",
        parents=[base_parser],
    )
    subparser.add_argument(
        "task", help="Name and optional path of a task. //path:name, //:name, :name are all valid."
    )
    subparser.add_argument(
        "--real",
        action="store_true",
        help="Return cache path. This may be slower as it must resolve Workspaces.",
        default=False,
    ) #"-r",
    subparser.set_defaults(command_function=main_get_path)

    ######## dot
    subparser = subparsers.add_parser(
        "dot",
        help="Create a dot dependency graph of tasks. Printed to standard output.",
        parents=[base_parser],
    )
    subparser.add_argument("targets", nargs="+")
    subparser.add_argument(
        "--files",
        help="Include/evaluate files/globs. May be slow.",
    ) # "-f", "-f",

    # TODO: this could be a global
    subparser.add_argument(
        "--ignore",
        nargs="*",
        action="append",
        help="Specify file ignore patterns for input/output files.",
    )
    add_threads_argument(subparser)

    ######## affected
    subparser = subparsers.add_parser(
        "affected",
        help="Return a list of tasks affected by changes to the specified files.",
        parents=[base_parser],
    )
    subparser.set_defaults(command_function=main_affected)
    subparser.add_argument("files", nargs="+")
    subparser.add_argument(
        "--scope",
        nargs="+",
        help="expand/narrow the scope of the search. +/- may be added to prefix includes/excludes."
    )

    add_threads_argument(subparser)

    ######## inputs
    subparser = subparsers.add_parser(
        "inputs",
        help="Return the input files of a task. Evaluates the file.",
        parents=[base_parser],
    )
    subparser.set_defaults(command_function=main_get_inputs)
    subparser.add_argument(
        "--ignore",
        nargs="*",
        action="append",
        help="Specify file ignore patterns.",
    )
    subparser.add_argument("targets", nargs="+")
    add_threads_argument(subparser)

    ######## outputs
    subparser = subparsers.add_parser(
        "outputs",
        help="Return the output files of a task. Evaluates the file.",
        parents=[base_parser],
    )
    subparser.set_defaults(command_function=main_get_outputs)
    subparser.add_argument(
        "--ignore",
        nargs="*",
        action="append",
        help="Specify file ignore patterns.",
    )
    subparser.add_argument("output_names", nargs="+")

    add_threads_argument(subparser)

    ######## evaluate
    subparser = subparsers.add_parser(
        "evaluate",
        help="Evaluate the specified Makex File (or paths with Makex Files) for the specified variable.",
        parents=[base_parser],
    )
    subparser.add_argument("file_or_directory")
    subparser.add_argument(
        "variable_name",
        help="Name of the variable to evaluate. Can be target(name).* to evaluated variables of named targets  in the file.",
    )

    ######### targets subcommand
    subparser = subparsers.add_parser(
        "tasks",
        aliases=["list", "targets"], # TODO: remove this.
        parents=[base_parser],
        help="Generate list of targets parsed from the makex file found in path.",
        description="Generate list of targets parsed from the makex file found in path.",
    )
    subparser.set_defaults(command_function=main_targets)
    subparser.add_argument(
        "path",
        nargs="?",
        help="Path to a makex file or directory. The current directory is the default.",
    )
    subparser.add_argument(
        "--paths",
        choices=["absolute", "workspace", "relative"],
        default="workspace",
        help="How to output paths of tasks. `relative` is relative to the current folder.",
    )
    subparser.add_argument(
        "--prefix",
        default=False,
        action="store_true",
        help="May be used to prefix all paths.",
    )

    ######### completions command
    subparser = subparsers.add_parser(
        "completions",
        parents=[base_parser],
        description="Generate completion files for shells.",
        help="Generate completion files for shells.",
    )
    subparser.set_defaults(command_function=main_completions)

    #if HAS_SHTAB:
    #    shtab.add_argument_to(
    #        subparser, option_string=["--shell"], parent=parser, preamble=PREAMBLE
    #    ) # magic!
    #else:
    subparser.add_argument("--shell", choices=["bash", "zsh"])
    subparser.add_argument("--internal", action="store_true", default=False)

    subparser.add_argument(
        "file",
        nargs="?",
        help="The output file to write the completions to. If not specified, will the completion will be written to standard out.",
    )

    ######### workspace command
    subparser = subparsers.add_parser(
        "workspace",
        parents=[base_parser],
        description="Print the current workspace, or the workspace detected at path.",
        help="Print the current workspace, or the workspace detected at path.",
    )
    subparser.set_defaults(command_function=main_workspace)

    subparser.add_argument(
        "path",
        nargs="?",
        help="Path representing a workspace, or inside a workspace.",
    )

    ######### complete command
    subparser = subparsers.add_parser(
        "complete",
        parents=[base_parser],
        help="Print completions for the specified input. This is used for shell completions.",
    )
    subparser.set_defaults(command_function=main_complete)

    subparser.add_argument(
        "string",
        nargs="?",
        help="May be a complete/partial path. May include a target name.",
    )

    ######### version command
    subparser = subparsers.add_parser(
        "version",
        help="Print the makex version",
    )
    subparser.set_defaults(command_function=main_version)

    ######### fix command
    main_fix_parser(subparsers)

    return parser


def _handle_signal_interrupt(_signal, frame):
    # TODO: attempt to shutdown pool gracefully
    # self.pool.shutdown()
    # self.pool.shutdown(cancel_futures=True)
    print('You pressed Ctrl+C or the process was interrupted!')
    _kill_running_processes()
    sys.exit(-1)


def _handle_signal_terminate(_signal, frame):
    # TODO: attempt to shutdown pool gracefully
    # self.pool.shutdown()
    # self.pool.shutdown(cancel_futures=True)
    print('You pressed Ctrl+C or the process was interrupted!')

    # send a kill because it's more reliable.
    _kill_running_processes()

    sys.exit(-1)


def main_completions(args, extra_args):
    # XXX: Performance: Do a late import shtab because we probably don't need most of the time.
    HAS_SHTAB = False
    try:
        import shtab
        HAS_SHTAB = True
    except ImportError:
        pass

    if args.file:
        file = Path(args.file).expanduser().resolve(strict=False)
    else:
        file = None

    output = sys.stdout
    if file:
        file.parent.mkdir(parents=True, exist_ok=True)
        try:
            output = file.open("w")
        except PermissionError:
            print(f"Error opening the output file. Permission denied: {file}")
            sys.exit(-1)

    if args.internal is False and HAS_SHTAB is False:
        COMPLETIONS_PACKAGE = "makex.data.completions"
        resource_name = f"makex.{args.shell}"
        # load static completions from data directory
        if not importlib.resources.is_resource(COMPLETIONS_PACKAGE, resource_name):
            print(
                f"Error: Could not find static shell script for {resource_name} in {COMPLETIONS_PACKAGE}."
            )
            sys.exit(-1)
        print(importlib.resources.read_text(COMPLETIONS_PACKAGE, resource_name), file=output)
        sys.exit(-1)
    else:
        if HAS_SHTAB is False:
            print("shtab is not installed. pip install shtab")
            sys.exit(-1)

        from makex._shtab import PREAMBLE
        shell = args.shell
        _parser = parser(documentation=False)
        script = shtab.complete(_parser, shell=shell, preamble=PREAMBLE)
        print(script, file=output)

    return 0


def main_version(args, extra_args):
    print(VERSION)


def main():

    signal.signal(signal.SIGINT, _handle_signal_interrupt)
    signal.signal(signal.SIGTERM, _handle_signal_terminate)

    args, extra_args = parser(documentation=False).parse_known_args()

    if args.python_audit:
        events = set(args.python_audit)

        def audit(event, args):
            if event in events:
                print(f'audit: {event} with args={args}')

        sys.addaudithook(audit)

    level = logging.NOTSET

    #if args.verbose >= 1:
    #    level = logging.INFO

    if args.debug:
        level = logging.TRACE

    args.color = is_color_enabled(args.color)

    initialize_logging(level=level, color=args.color)

    profile_output = None
    if args.profile:
        if args.profile != "-":
            profile_output = Path(args.profile)

        if args.profile_mode == "cprofile":
            import cProfile

            #import pstats
            profiler = cProfile.Profile()
            profiler.enable()
        elif args.profile_mode == "yappi":
            import yappi
            yappi.set_clock_type("wall") # Use set_clock_type("wall") for wall time
            yappi.start()

    try:
        if TASK_PATH_NAME_SEPARATOR in args.command:
            # handle running a target with the second argument to makex
            # e.g. makex :target
            function = main_run
            extra_args = args.command + extra_args
        else:
            function = args.command_function

        function(args, extra_args)
    finally:
        if args.profile:
            if args.profile_mode == "cprofile":
                profiler.disable()
            elif args.profile_mode == "yappi":
                yappi.stop()

            #return pstats.Stats(profiler)
            if profile_output:
                if args.profile_mode == "cprofile":
                    profiler.dump_stats(profile_output)
                elif args.profile_mode == "yappi":
                    if profile_output.name.endswith(".callgrind"):
                        yappi.get_func_stats().save(profile_output, "callgrind")
                    else:
                        yappi.get_func_stats().save(profile_output, "pstat")
            else:
                if args.profile_mode == "cprofile":
                    profiler.print_stats()
                elif args.profile_mode == "yappi":
                    yappi.get_func_stats().print_all()
                    yappi.get_thread_stats().print_all()


if __name__ == "__main__":
    main()
