import argparse
from copy import copy
from typing import Optional

from libcst import (
    Arg,
    Call,
    Comma,
    Dict,
    DictElement,
    Element,
    Expr,
    List,
    Name,
    Newline,
    ParenthesizedWhitespace,
    RemovalSentinel,
    SimpleStatementLine,
    SimpleString,
    SimpleWhitespace,
    TrailingWhitespace,
)
from libcst.codemod import (
    CodemodContext,
    VisitorBasedCodemodCommand,
)
from makex.constants import SYNTAX_2025
from makex.locators import format_locator


class ConvertMakexVersion1(VisitorBasedCodemodCommand):
    # Add a description so that future codemodders can see what this does.
    DESCRIPTION: str = "Converts makex files to version 2 syntax.."

    @staticmethod
    def add_args(arg_parser: argparse.ArgumentParser) -> None:
        pass

    def __init__(self, context: CodemodContext) -> None:
        super().__init__(context)
        self._process_calls = True

    def visit_FunctionDef(self, node: "FunctionDef") -> Optional[bool]:
        self._process_calls = False

    def leave_FunctionDef(self, original_node: "FunctionDef", updated_node: "FunctionDef") -> None:
        self._process_calls = True
        return original_node

    def fix_task(self, original_node: "Call", updated_node: "Call") -> "Call":
        new_arguments = []
        inputs_argument = None
        inputs_argument_position = None
        requires_argument = None
        requires_argument_position = None

        new_input_items = []
        new_require_items = []
        argument_indent = " " * 4

        # leave trailing commas
        end_of_arguments = Comma(
            whitespace_before=SimpleWhitespace(
                value='',
            ),
            whitespace_after=ParenthesizedWhitespace(
                first_line=TrailingWhitespace(
                    whitespace=SimpleWhitespace(
                        value='',
                    ),
                    comment=None,
                    newline=Newline(
                        value=None,
                    ),
                ),
                empty_lines=[], # indent=True,
                # last_line=SimpleWhitespace(value='    '),
            ),
        )
        comma = Comma(
            whitespace_before=SimpleWhitespace(value=''),
            # whitespace_after=ParenthesizedWhitespace(
            #    first_line=TrailingWhitespace(
            #        whitespace=SimpleWhitespace(value=''),
            #        comment=None, #newline=Newline(value=None),
            #    ),
            #    empty_lines=[], #indent=True,
            #    #last_line=SimpleWhitespace(value=''),
            # ),
            whitespace_after=SimpleWhitespace(
                value=' ',
            ),
        )

        for i, argument in enumerate(updated_node.args):
            new_arguments.append(argument)
            if argument.keyword and argument.keyword.value == "inputs":
                inputs_argument = argument
                inputs_argument_position = i
            elif argument.keyword and argument.keyword.value == "requires":
                requires_argument = argument
                requires_argument_position = i
                _list: List = argument.value
                # elements = cast(list[Union[SimpleString, Call]], argument.value.elements)
                for list_element in _list.elements:
                    if isinstance(list_element.value, SimpleString):
                        # handle string values in the requirements list:
                        if ":" in list_element.value.value:
                            parts = list_element.value.value[1:-1].split(":", 1)
                            if len(parts) == 2:
                                path, name = parts
                            else:
                                name = parts[0]
                                path = None

                            if path:
                                val = f"{name}:{path}"
                                new_require_items.append(
                                    Element(value=SimpleString(f'"{val}"'), comma=comma)
                                )
                            else:
                                new_require_items.append(
                                    Element(value=SimpleString(f'"{name}"'), comma=comma)
                                )
                        else:
                            # PATH detected, add it to the inputs list
                            new_input_items.append(list_element.with_changes(comma=comma))

                    elif isinstance(list_element.value, Call) and list_element.value.func.value in {
                        "glob", "find", "path", "task_path"
                    }:
                        # handle string values
                        new_input_items.append(list_element.with_changes(comma=comma))
                    else:
                        new_require_items.append(list_element.with_changes(comma=comma))

        if new_input_items:
            if inputs_argument is None:
                # no inputs argument defined. create a new one.
                arg = Arg(
                    keyword=Name(
                        value='inputs',
                        lpar=[],
                        rpar=[],
                    ),
                    value=List(elements=new_input_items),
                    comma=end_of_arguments,
                )

                if requires_argument_position:
                    new_arguments.insert(requires_argument_position + 1, arg)
                else:
                    new_arguments.append(arg)

            else:
                # add it to the original inputs argument
                # inputs is either a list or a map.
                if isinstance(inputs_argument.value, Dict):
                    # if map, add to unnamed key
                    d: Dict = inputs_argument.value
                    new_dict_elements = []
                    # true if we need to add a dict element with _ key
                    add_unnamed = True
                    for dict_element in d.elements:
                        key: str = dict_element.key.value.strip("'\"")
                        value = dict_element.value
                        if key == "_":
                            add_unnamed = False
                            # existing key with _; fix it
                            if isinstance(value, SimpleString):
                                # value is a string, create a list and add it back
                                new_value = List(elements=[Element(value), *new_input_items])
                                new_dict_elements.append(dict_element.with_changes(value=new_value))
                            elif isinstance(value, List):
                                new_value = value.with_changes(
                                    elements=[*value.elements, *new_input_items]
                                )
                                new_dict_elements.append(dict_element.with_changes(value=new_value))
                            else:
                                raise NotImplementedError()
                        else:
                            # add existing, unmodified
                            new_dict_elements.append(dict_element)
                            pass

                    if add_unnamed:
                        l = List(elements=new_input_items)
                        new_dict_elements.append(DictElement(key=SimpleString('"_"'), value=l))

                    new_arguments[inputs_argument_position] = inputs_argument.with_changes(
                        value=d.with_changes(elements=new_dict_elements)
                    )

                elif isinstance(inputs_argument.value, List):
                    # if list, just append
                    old_elements = inputs_argument.value.elements
                    new_list = inputs_argument.value.with_changes(
                        elements=[*old_elements, *new_input_items]
                    )
                    _rewrite_inputs_argument = inputs_argument.with_changes(value=new_list)

                    for i, argument in enumerate(copy(new_arguments)):
                        if argument == inputs_argument:
                            new_arguments[i] = _rewrite_inputs_argument
                elif isinstance(inputs_argument.value, SimpleString):
                    # create a list, adding the old value, then all the new values
                    elements = [Element(value=inputs_argument.value), *new_input_items]
                    new_arguments[inputs_argument_position] = inputs_argument.with_changes(
                        value=List(elements=elements)
                    )

        if requires_argument:
            _rewrite_requires = requires_argument.with_changes(
                value=List(elements=new_require_items)
            )
            for i, argument in enumerate(copy(new_arguments)):
                if argument == requires_argument:
                    new_arguments[i] = _rewrite_requires

        return updated_node.with_changes(args=new_arguments)

    def fix_execute(self, original_node: "Call", updated_node: "Call") -> "Call":
        first_argument = original_node.args[0]

        string: SimpleString = first_argument.value

        if not isinstance(string, SimpleString):
            # user is doing something funny with execute first argument
            return original_node

        if ":" in string.value:
            parts = string.value[1:-1].split(":", 1)
            if len(parts) == 2:
                path, name = parts
            else:
                name = parts[0]
                path = None
            locator = format_locator(name, path, syntax=SYNTAX_2025)
            new_path = SimpleString(f'"{locator}"')
            new_arg = original_node.args[0].with_changes(value=new_path)

            extra_args = original_node.args[1:] if len(original_node.args) > 1 else []
            updated_node = original_node.with_changes(args=[new_arg, *extra_args])
            return updated_node
        return original_node

    def visit_Call(self, node: "Call") -> Optional[bool]:
        if isinstance(node, Call) and node.func.value == "makex":
            for arg in node.args:
                if arg.keyword.value != "syntax":
                    continue

                if isinstance(arg.value, SimpleString) is False:
                    continue

                value = arg.value.value.strip("'\"")
                if value == "2025":
                    raise Exception("File already converted")

    def leave_Call(self, original_node: "Call", updated_node: "Call") -> "BaseExpression":
        if self._process_calls is False:
            return original_node

        function_name = updated_node.func.value
        if function_name == "task":
            return self.fix_task(original_node, updated_node)
        elif function_name == "execute":
            return self.fix_execute(original_node, updated_node)
        elif function_name == "copy":
            return self.fix_execute(original_node, updated_node)
        elif function_name == "makex":
            new_args = []
            for arg in updated_node.args:
                if arg.keyword.value == "syntax":
                    continue
                else:
                    new_args.append(arg)

            return updated_node.with_changes(args=new_args)
        return updated_node

    def leave_Module(self, original_node: "Module", updated_node: "Module") -> "Module":
        new_body = []
        for node in updated_node.body:
            if isinstance(node, SimpleStatementLine) and len(node.body):
                expr = node.body[0]
                if isinstance(expr, Expr):
                    call = expr.value
                    if isinstance(call, Call) and call.func.value == "makex" and not (call.args):
                        continue
                new_body.append(node)

        return updated_node.with_changes(body=new_body)
