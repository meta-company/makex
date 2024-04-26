import os
import random
import re
import sys
from io import StringIO
from pathlib import Path

import progressbar
from makex.colors import (
    ColorsNames,
    NoColors,
)
from makex.python_script import FileLocation


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

    return tty


class UI:
    def __init__(self, verbosity=None, colors=NoColors):
        self.colors = colors
        self.verbosity = verbosity or 0

    def warn(self, message):
        print(
            f"{self.colors.MAKEX}[makex]{self.colors.RESET}{self.colors.WARNING}[WARNING]{self.colors.RESET}: {message}"
        )

    def error(self, message):
        print(message, file=sys.stderr)

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
        f"{colors.ERROR}Error{colors.RESET} inside a Makexfile '{colors.BOLD}{location.path}{colors.RESET}:{location.line}'\n\n"
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
