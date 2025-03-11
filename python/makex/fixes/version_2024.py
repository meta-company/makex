import argparse

import libcst as cst
from libcst import (
    Expr,
    SimpleString,
)
from libcst._nodes.module import Module
from libcst.codemod import (
    CodemodContext,
    VisitorBasedCodemodCommand,
)


class AddMakexVersion1(VisitorBasedCodemodCommand):
    # Add a description so that future codemodders can see what this does.
    DESCRIPTION: str = "Converts raw strings to constant accesses."

    @staticmethod
    def add_args(arg_parser: argparse.ArgumentParser) -> None:
        pass

    def __init__(self, context: CodemodContext) -> None:
        super().__init__(context)

    def leave_Module(self, original_node: "Module", updated_node: "Module") -> "Module":
        makex_call = cst.SimpleStatementLine(
            [cst.Expr(cst.parse_expression('makex(version="2024")'))]
        )
        if (
            isinstance(original_node.body[0].body[0], Expr) and
            isinstance(original_node.body[0].body[0].value, SimpleString)
        ):
            return original_node.with_changes(
                body=[original_node.body[0], makex_call, *original_node.body[1:]]
            )
        else:
            return original_node.with_changes(body=[makex_call, *original_node.body])
