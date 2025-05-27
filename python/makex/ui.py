import os
import random
import re
import sys
from io import StringIO
from pathlib import Path

#import progressbar
from makex.colors import (
    ColorsNames,
    NoColors,
)
from makex.errors import (
    ExecutionError,
    ExternalExecutionError,
    MakexFileCycleError,
    MultipleErrors,
)
from makex.python_script import (
    FileLocation,
    PythonScriptError,
    PythonScriptFileError,
)


def is_ansi_tty() -> bool:
    """
    Checks if stdout supports ANSI escape codes and is a tty.
    https://stackoverflow.com/a/75703990
    """

    tty = os.isatty(sys.stdout.fileno())
    term = os.environ.get("TERM", None)
    if not tty:
        # check common environment variables
        pycharm = os.environ.get("PYCHARM_HOSTED", None)
        if pycharm is not None:
            tty = bool(int(pycharm))
            return tty

    if term is None:
        return False

    find_words = {"dumb", "unknown", "lpr", "print"}

    tmpl = "(?=f{word})"
    tmpl = "|".join(tmpl.format(word=word) for word in find_words)
    pattern = re.compile(f"({tmpl})", re.U)
    if pattern.match(term):
        return False

    if force := os.environ.get("FORCE_COLOR", None):
        return True

    if ls_colors := os.environ.get("LS_COLORS", None):
        return True

    return False


class UI:
    def __init__(self, verbosity=None, colors=NoColors):
        self.colors = colors
        self.verbosity = verbosity or 0
        self.warnings = []

    def warn(self, message, location: FileLocation = None):
        _location = ""
        if location:
            _location = f"@ {location}"
        print(
            f"{self.colors.MAKEX}[makex]{self.colors.RESET}{self.colors.WARNING}[WARNING]{self.colors.RESET}: {message}{_location}",
            flush=True
        )
        self.warnings.append((message, location))

    def progress(self):
        pass

    def progress_multijob(self, steps: dict[str, tuple[int, int]]):

        jobs = [
            # Each job takes between 1 and 10 steps to complete
            # curr, max
            [0, random.randint(1, 10)] for i in range(25) # 25 jobs total
        ]
        widgets = [
            progressbar.Percentage(),
            ' ',
            progressbar.MultiProgressBar('jobs', fill_left=True),
        ]

        max_value = sum([total for progress, total in jobs])
        with progressbar.ProgressBar(widgets=widgets, max_value=max_value) as bar:
            jobs = [(job_name, steps) for job_name, n in steps.items()]

            progress = sum(progress for progress, total in steps.values())
            bar.update(progress, jobs=jobs, force=True)

    def print(self, message, verbose=1, first_prefix=None, error=False):
        if error:
            print(
                f"{self.colors.MAKEX}[makex]{self.colors.RESET} {self.colors.ERROR}ERROR:{self.colors.RESET}: {message}",
                flush=True,
            )
            return None

        if self.verbosity == 0:
            return None

        if verbose > self.verbosity:
            return None

        #for line in message:
        print(f"{self.colors.MAKEX}[makex]{self.colors.RESET} {message}", flush=True)


def pretty_file(location, colors: ColorsNames, context=(1, 2)):
    location = location

    buf = StringIO()
    context_before, context_after = context
    with Path(location.path).open("r") as f:
        for i, line in enumerate(f):
            li = i + 1

            if li >= location.line - context_before and li < location.line:
                buf.write(f"  {li}: " + line)
            elif li <= location.line + context_after and li > location.line:
                buf.write(f"  {li}: " + line)
            elif li == location.line:
                buf.write(f">>{li}: " + line)

    return buf.getvalue()


def pretty_makex_file_exception(exception, location: FileLocation, colors: ColorsNames):
    # TODO: remove colors from this pretty_exception
    buf = StringIO()
    buf.write(
        f"{colors.ERROR}Error{colors.RESET} inside a Makexfile: '{colors.BOLD}{location.path}{colors.RESET}:{location.line}'\n\n"
    )

    buf.write(f"{colors.ERROR}{exception}{colors.RESET}'\n\n")
    with Path(location.path).open("r") as f:
        for i, line in enumerate(f):
            li = i + 1

            if li >= location.line - 1 and li < location.line:
                buf.write(f"  {li}: " + line)
            elif li <= location.line + 2 and li > location.line:
                buf.write(f"  {li}: " + line)
            elif li == location.line:
                buf.write(f">>{li}: " + line)

    return buf.getvalue()


def early_ui_printer(max_level: int, colors: ColorsNames):
    # we need an early ui before configuration/context is loaded
    def f(message, level=1, error=False):
        if error:
            print(f"{colors.ERROR}ERROR:{colors.RESET} {message}")
            return
        if level <= max_level:
            print(f"{colors.MAKEX}[makex]{colors.RESET} {message}")

    return f


def print_error(colors: ColorsNames, error):

    if isinstance(error, (PythonScriptFileError, PythonScriptError)):
        print(pretty_makex_file_exception(error, error.location, colors=colors))
    elif isinstance(error, MakexFileCycleError):
        print(format_cycle_error(error, colors=colors))
    elif isinstance(error, MultipleErrors):
        for error in error.errors:
            print_error(colors, error)
    elif isinstance(error, (ExecutionError, ExternalExecutionError)):
        if error.location:
            print(pretty_makex_file_exception(error.error, error.location, colors=colors))
        else:
            print("Execution Error:", error)
    else:
        print(f"{type(error)} Error:")
        print(error)


def format_cycle_error(self, colors: ColorsNames) -> str:
    string = StringIO()
    string.write(f"{colors.ERROR}ERROR:{colors.RESET} Cycles detected between targets:\n")
    string.write(f" - {self.detection.key()} {self.detection}\n")

    if self.detection.location:
        string.write(pretty_file(self.detection.location, colors))

    first_cycle = self.cycles[0]
    string.write(f" - {first_cycle.key()}\n")

    if first_cycle.location:
        string.write(pretty_file(first_cycle.location, colors))

    stack = self.cycles[1:]
    if stack:
        string.write("Stack:\n")
        for r in stack:
            string.write(f" - {r}\n")

    return string.getvalue()
