"""
The makex api.

"""

from pathlib import Path


class Target:
    """

    :cvar path: A path to the target's output directory.
    """
    path: Path


class Context:
    pass


class Help:
    url: str
    text: str
    markdown: str
    html: str


class Action:
    def help(self):
        # return help documents
        pass

    def arguments(self):
        # return the arguments the Action takes, in order, but also named for keyword arguments.
        # handle different types automatically like, list of path, path, dict[str], etc
        pass

    def run(self, ctx: Context, target: Target):
        # do whatever is required to run
        pass


class WindowsPath:
    pass
