import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional


def main_fix_parser(subparsers):
    parser = subparsers.add_parser(
        "fix",
        aliases=["evolve"],
        help="Fix/evolve makex files",
        description="Fixes and evolves makex files to be compatible with new syntax. This should only be used as instructed.",
    )

    fixes = ['syntax_2024', "syntax_2025"]
    parser.add_argument(
        "fix_name",
        help=f'The name of a fix. One of {fixes}',
    )

    parser.add_argument(
        "path",
        help="Path to a makex file to fix.",
    )
    parser.add_argument(
        "--diff",
        action='store_true',
        default=False,
        help="Output a diff instead of the full contents.",
    )
    parser.add_argument(
        "--edit",
        action='store_true',
        default=False,
        help="Edit files in place. Does not output anything to the standard outpujt.",
    )
    parser.add_argument(
        "--formatter",
        default=None,
        help="Specify a formatter executable to run after fixing the file. Arguments are space separated. The formatter must take source code from standard input, and print a formatted version to standard output.",
    )
    parser.set_defaults(command_function=main_fix)


def main_fix(args, extra_args):
    try:
        from libcst.codemod import (
            CodemodContext,
            TransformExit,
            TransformFailure,
            TransformResult,
            TransformSkip,
            diff_code,
            transform_module,
        )
        from libcst.tool import main as libcst_tool_main
    except ImportError:
        print("Error: LibCST could not be imported!\n")
        print("Install the package `pip install makex[fix]` to install the correct LibCST.\n")
        print("Alternatively, try installing the LibCST package directly `pip install LibCST`.\n")
        sys.exit(-1)

    from makex.fixes.version_2024 import AddMakexVersion1
    from makex.fixes.version_2025 import ConvertMakexVersion1

    fix_map = {
        "syntax_2024": AddMakexVersion1,
        "syntax_2025": ConvertMakexVersion1,
    }
    fix = fix_map.get(args.fix_name, None)
    if fix is None:
        print("Unknown fix type", args.fix_name)
        sys.exit(-1)

    path = Path(args.path).expanduser().resolve(strict=True)
    if not path.exists():
        print(f"Can't fix nonexistent path: {path}")
        sys.exit(-1)
    oldcode = path.read_text()

    def print_execution_result(result: TransformResult) -> None:
        for warning in result.warning_messages:
            print(f"WARNING: {warning}", file=sys.stderr)

        if isinstance(result, TransformFailure):
            error = result.error
            if isinstance(error, subprocess.CalledProcessError):
                print(error.output.decode("utf-8"), file=sys.stderr)
            print(result.traceback_str, file=sys.stderr)

    try:
        ctx = CodemodContext()
        transform = fix(ctx)
        #newcode = exec_transform_with_prettyprint(transform, oldcode)
        result = transform_module(transform, oldcode, python_version=None)
        if isinstance(result, (TransformFailure, TransformExit, TransformSkip)):

            print(f"Error fixing file: {path}")
            print_execution_result(result)
            sys.exit(-1)
        newcode = result.code
    except Exception as e:
        logging.exception(e)
        print(e)
        print(f"Error fixing file: {path}")
        sys.exit(-1)

    if args.formatter:
        try:
            formatter_args = shlex.split(args.formatter, posix=True)
            newcode = subprocess.check_output(
                formatter_args,
                input=newcode,
                #universal_newlines=not work_with_bytes,
                encoding="utf-8",
            )
        except Exception as e:
            logging.exception(e)
            print(f"Error running formatter ({args.formatter!r}) after fix: {path}\n\t", e)
            sys.exit(-1)

    if args.edit:
        path.write_text(newcode)
        sys.exit(0)

    if args.diff:
        print(diff_code(oldcode, newcode, 3, filename="stdin"))
    else:
        print(newcode)
