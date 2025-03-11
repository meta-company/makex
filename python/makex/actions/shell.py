import os
import shlex
from itertools import chain
from typing import Any

from makex._logging import trace
from makex.context import Context
from makex.errors import ExecutionError
from makex.flags import SHELL_USES_RETURN_CODE_OF_LINE
from makex.makex_file_actions import InternalAction
from makex.makex_file_paths import join_string
from makex.protocols import (
    CommandOutput,
    StringHashFunction,
)
from makex.python_script import (
    FileLocation,
    JoinedString,
    PythonScriptError,
    StringValue,
)
from makex.run import run
from makex.target import (
    ArgumentData,
    Task,
)


class Shell(InternalAction):
    NAME = "shell"
    string: list[StringValue]
    location: FileLocation

    # https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_25

    # -e: Error on any error.
    # -u When the shell tries to expand an unset parameter other than the '@' and '*' special parameters,
    # it shall write a message to standard error and the expansion shall fail with the consequences specified in Consequences of Shell Errors.

    # strict options:
    # -C  Prevent existing files from being overwritten by the shell's '>' redirection operator (see Redirecting Output);
    # the ">|" redirection operator shall override this noclobber option for an individual file.

    # -f: The shell shall disable pathname expansion.

    # -o: Write the current settings of the options to standard output in an unspecified format.
    preamble: str = "set -Eeuo pipefail"

    def __init__(self, string, location):
        self.string = string
        self.location = location

    def transform_arguments(self, ctx: Context, target: Task) -> ArgumentData:
        args = {}
        target_input = target.input_path

        _list = []
        for part in self.string:
            if isinstance(part, StringValue):
                _list.append(part)
            elif isinstance(part, JoinedString):
                _list.append(join_string(ctx, task=target, base=target_input, string=part))
            else:
                raise PythonScriptError(
                    f"Invalid argument to shell. Expected String. Got {type(part)}", self.location
                )

        # TODO: validate string type
        args["string"] = _list
        args["preamble"] = self.preamble

        return ArgumentData(args)

    def run_with_arguments(self, ctx: Context, target: Task, arguments) -> CommandOutput:
        string = arguments.get("string")
        preamble = arguments.get("preamble")

        if not string:
            return CommandOutput(0)

        s_print = "\n".join([f"# {s}" for s in chain(preamble.split("\n"), string)])

        _script = ["\n"]
        _script.append(preamble)
        # XXX: this line is required to prevent "unbound variable" errors (on account of the -u switch)
        _script.append("__error=0")
        #script.append(r"IFS=$'\n'")
        for i, line in enumerate(string):
            #script.append(f"({line}) || (exit $?)")
            if ctx.verbose > 0 or ctx.debug:
                _script.append(
                    f"echo \"{ctx.colors.MAKEX}[makex]{ctx.colors.RESET} {ctx.colors.BOLD}${{PS1:-}}\${ctx.colors.RESET} {line}\""
                )

            # bash: https://www.gnu.org/software/bash/manual/html_node/Command-Grouping.html
            # Placing a list of commands between curly braces causes the list to be executed in the current shell context.
            # No subshell is created. The semicolon (or newline) following list is required.
            if SHELL_USES_RETURN_CODE_OF_LINE:
                _script.append(
                    f"{{ {line}; }} || {{ __error=$?; echo -e \"{ctx.colors.ERROR}Error (exit=$?) on on shell script line {i+1}:{ctx.colors.RESET} {shlex.quote(line)!r}\"; exit $__error; }}"
                )
            else:
                _script.append(f"{{ {line}; }}")
                #script.append(f"( {line} ) || (exit $?)")

        script = "\n".join(_script)
        trace("Real script:\n%s", script)

        cwd = target.input_path
        ctx.ui.print(f"Running shell from {cwd}:\n{s_print}\n")
        if ctx.dry_run is True:
            return CommandOutput(0)
        try:
            #stdin = BytesIO()
            #stdin.write(script.encode("utf-8"))

            # create a real pipe to pass to the specified shell
            read, write = os.pipe()
            os.write(write, script.encode("utf-8"))
            os.close(write)

            output = run(
                [ctx.shell],
                ctx.environment,
                capture=True,
                shell=False,
                cwd=cwd,
                stdin=read, #stdin_data=script.encode("utf-8"),
                color_error=ctx.colors.WARNING,
                color_escape=ctx.colors.RESET,
            )
            # XXX: set the location so we see what fails
            # TODO: Set the FileLocation of the specific shell line that fails
            output.location = self.location
            return output
        except Exception as e:
            raise ExecutionError(e, target, location=self.location) from e

    def hash(self, ctx: Context, arguments: dict[str, Any], hash_function: StringHashFunction):
        return hash_function("\n".join(arguments.get("string", [])))
