"""
This module improves upon Python's argparse:

Provides an argument parser:

- With easy to define global arguments.
- With easy to create nested commands.
- Compatible with documentation generators (globals are only documented once)

NOTE: all arguments to add_argument must be named 
NOTE: long="--long-option", long="--long-option" and/or short="-s" must be specified as keyword arguments to add_argument().


"""
import argparse
from typing import (
    Any,
    Type,
    TypedDict,
)


class _Argument:
    name: str
    long: str
    short: str
    nargs: str
    action: str
    default: None
    required: bool

    # extra data associated with the command/parser
    # used for shtab (to set a completer function for a specific argument, extra["complete"] = {"bash":"", "zsh": ""})
    extra: dict[str, Any]

    def __init__(
        self,
        name=None,
        long=None,
        short=None,
        nargs=None,
        action=None,
        default=None,
        help=None,
        type=None,
        required=True,
        extra=None,
    ):
        """
            Note: name and long/short are mutually exclusive.
        """
        if name is None:
            if long is None and short is None:
                # nothing specified
                raise ValueError("Must specify name; or long/short")
        else:
            if long is not None or short is not None:
                # name and one of long/short specified
                raise ValueError("Must specify name; or long/short")

        self.name = name
        self.long = long
        self.short = short
        self.nargs = nargs
        self.action = action or "store"
        self.default = default
        self.help = help
        self.type = type
        self.required = required
        self.extra = extra or {}

    def add_to_parser(self, _parser: argparse.ArgumentParser, root=False):
        kwargs = {
            "action": self.action,
            "default": self.default if root else argparse.SUPPRESS,
        }
        if self.nargs:
            kwargs["nargs"] = self.nargs

        if self.name:
            if self.required is False:
                kwargs["nargs"] = "?"

            _action = _parser.add_argument(dest=self.name, **kwargs)
        else:
            # XXX: must be expanded like this because argparse is goofy (aka fucked up).
            if self.long and self.short:
                _action = _parser.add_argument(self.short, self.long, **kwargs)
            elif self.short:
                _action = _parser.add_argument(self.short, **kwargs)
            elif self.long:
                _action = _parser.add_argument(self.long, **kwargs)
            else:
                raise ValueError(
                    "Invalid argument combination for argparse. Missing .long and .short"
                )

            for k, v in self.extra.items():
                setattr(_action, k, v)


class _Command:
    name: str
    help: str
    aliases: list[str]
    commands: list["_Command"]
    arguments: list["_Argument"]
    defaults: dict[str, Any]

    def __init__(self, name, help, aliases=None, defaults=None):
        self.name = name
        self.help = help
        self.aliases = aliases or []
        self.arguments = []
        self.commands = []
        self.defaults = defaults or {}

    class _Args(TypedDict):
        name: str
        long: str
        short: str

        # TODO: alias for nargs, ? optional 1, * zero or more, + at least once
        repeat: str

        nargs: str
        action: str
        default: str
        type: Any
        required: bool

        extra: dict[str, Any]

    def add_argument(self, **kwargs: _Args):
        # TODO: if name is set and required=False, check that prior arguments are also required=False. err if not.
        # TODO: long=None, short=None, nargs=None, action=None, default=None
        self.arguments.append(_Argument(**kwargs))

    def add_subcommand(self, name, help=None, aliases=None, defaults=None) -> "_Command":
        command = _Command(name, help=help, aliases=aliases, defaults=defaults)
        self.commands.append(command)
        return command


def _create_parser(
    command: _Command, subparser_action, formatter, documentation=True, command_level=0
):
    _parser = subparser_action.add_parser(
        name=command.name,
        help=argparse.SUPPRESS if documentation else command.help,
        aliases=command.aliases,
        add_help=documentation is False,
        formatter_class=formatter,
    )
    _parser.set_defaults(**command.defaults)

    for argument in command.arguments:
        argument.add_to_parser(_parser, root=True)

    _subparsers = subparser_action.add_subparsers(dest=f"command_{command_level}", required=True)

    for sub_command in command.commands:
        _create_parser(
            sub_command,
            _subparsers,
            formatter,
            documentation,
            command_level=command_level + 1,
        )

    return _parser


class ArgumentParser:
    """
        Improve construction of subcommands and globals with argparse.ArgumentParser.
    """
    def __init__(
        self,
        prog=None,
        description=None,
        epilog=None,
        formatter: Type[argparse.HelpFormatter] = None
    ):
        self._globals: list[_Argument] = []
        self._commands: list[_Command] = []
        self.prog = prog
        self.description = description
        self.epilog = epilog
        self._formatter = formatter or argparse.HelpFormatter

    def add_global_argument(self, **kwargs):
        #self._argparse.add_argument(*args, **kwargs)
        self._globals.append(_Argument(**kwargs))

    def add_subcommand(self, name, help=None, aliases=None) -> _Command:
        command = _Command(name, help, aliases)
        self._commands.append(command)
        return command

    def argparser(self, documentation=True) -> argparse.ArgumentParser:
        """
        Return a compatible ArgumentParser.

        If documentation mode (default=True):

         - removes any global arguments from subcommands.
         - removes the help argument (-h/--help) from subcommands.

        :param documentation: True if in documentation mode.
        :return:
        """
        parser = argparse.ArgumentParser(
            prog=self.prog,
            description=self.description,
            epilog=self.epilog,
            add_help=documentation is True,
            formatter_class=self._formatter,
        )

        for g in self._globals:
            g.add_to_parser(parser, root=True)

        if not self._commands:
            return parser

        _subparsers = parser.add_subparsers(dest="subcommand", required=True)

        for command in self._commands:
            subparser = _subparsers.add_parser(
                name=command.name,
                help=argparse.SUPPRESS if documentation else command.help,
                aliases=command.aliases,
                add_help=documentation is False,
                formatter_class=self._formatter,
            )
            for argument in command.arguments:
                argument.add_to_parser(subparser, root=True)

            for sub_command in command.commands:
                _create_parser(
                    sub_command,
                    subparser,
                    formatter=self._formatter,
                    documentation=documentation,
                )

            if documentation is True:
                # ignore putting duplicates in documentation.
                continue

            for g in self._globals:
                g.add_to_parser(subparser, root=False)

        return parser
