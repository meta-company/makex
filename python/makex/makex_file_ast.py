import ast
from typing import Any

from makex.makex_file_syntax import (
    _TARGET_REFERENCE_NAME,
    MAKEX_FUNCTION_TASK,
    MAKEX_FUNCTION_TASK_SELF_INPUTS,
    MAKEX_FUNCTION_TASK_SELF_NAME,
    MAKEX_FUNCTION_TASK_SELF_OUTPUTS,
    MAKEX_FUNCTION_TASK_SELF_PATH,
)
from makex.python_script import (
    FILE_LOCATION_ARGUMENT_NAME,
    GLOBALS_NAME,
    FileLocation,
    PythonScriptError,
    call_function,
    create_file_location_call,
    is_function_call,
)

ast_Attribute = ast.Attribute
ast_Call = ast.Call
ast_Constant = ast.Constant
ast_keyword = ast.keyword
ast_Load = ast.Load
ast_Name = ast.Name


class InsertAST(ast.NodeTransformer):
    """
        Inserts asts directly before all the nodes in ast.Module's body.
    """
    def __init__(self, path, asts: list[ast.AST]):
        self.path = path
        self.asts = asts

    def visit_Module(self, node: ast.Module) -> Any:
        node.body = self.asts + node.body


class ProcessIncludes(ast.NodeTransformer):
    """
        Adds a globals() argument to include() calls so that the environment can modify its own globals.

        e.g. include(path) will be transformed to include(path, _globals=globals())

        TODO: includes should be at the top of the file; enforcing this is tricky.
        we need to scan the body for any include() calls.
        if any include() is found after any other statement, raise an error
    """
    def __init__(self, path: str):
        self.path = path
        self.includes_seen: list[tuple[str, FileLocation]] = []

    def visit_Call(self, node: ast.Call) -> Any:
        if is_function_call(node, "include") is False:
            return node

        line = node.lineno
        col = node.col_offset

        #location = FileLocation(line, col, self.path)
        #if other_nodes_seen:
        #    raise PythonScriptError("Includes must be at the top of a file.", location)
        #else:
        #self.includes_seen.append((node.args[0].value, location))

        node.keywords.append(
            ast_keyword(
                arg='_globals', # TODO: move this up to a constant.
                value=call_function(GLOBALS_NAME, line, col),
                lineno=line,
                col_offset=col,
            )
        )
        #debug("Transform include %s", ast.dump(node))
        return node


class TransformGetItem(ast.NodeTransformer):
    """
        Transforms Task Reference Slice Syntax: task[name:path] into a TaskReference(name, path, location=)

        We need to do this so we can get accurate FileLocations of task references later on.

        TODO: we can't know if we are overriding a user defined variable named task. This doesn't really matter because
          the task function/object should never be redefined in a Makex file. Investigate if this may be an issue.

    >>> print(ast.dump(ast.parse('task["test1":"test2":"test3"]', mode='single'), indent=4))

        Subscript(
            value=Name(id='task', ctx=Load()),
            slice=Slice(
                lower=Constant(value='test1'),
                upper=Constant(value='test2'),
                step=Constant(value='test3')),
            ctx=Load()
            )
        )
    """
    NAME = "task"

    def __init__(self, path):
        super().__init__()
        self.path = str(path)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        if isinstance(node.value, ast_Name) is False:
            self.generic_visit(node)
            return node
        if node.value.id != self.NAME:
            self.generic_visit(node)
            return node

        line = node.lineno
        offset = node.col_offset
        slice: ast.Slice = node.slice

        lower = slice.lower or ast_Constant(None, lineno=line, col_offset=offset)
        upper = slice.upper or ast_Constant(None, lineno=line, col_offset=offset)
        step = slice.step or ast_Constant(None, lineno=line, col_offset=offset)
        file_location = create_file_location_call(self.path, line, offset)

        reference_call = ast_Call(
            func=ast_Name(
                id=_TARGET_REFERENCE_NAME,
                ctx=ast_Load(),
                lineno=line,
                col_offset=offset,
            ),
            args=[],
            keywords=[
                ast_keyword(
                    arg='name',
                    value=upper,
                    lineno=line,
                    col_offset=offset,
                ),
                ast_keyword(
                    arg='path',
                    value=lower,
                    lineno=line,
                    col_offset=offset,
                ),
                ast_keyword(
                    arg=FILE_LOCATION_ARGUMENT_NAME,
                    value=file_location,
                    lineno=line,
                    col_offset=offset,
                ),
            ],
            lineno=line,
            col_offset=offset,
        )
        return reference_call


class TransformSelfReferences(ast.NodeTransformer):
    """

        Transforms usage of self in the file.

        e.g.
        task(
            name="test",
            execute=[
                write(self.path / f"{self.name}.txt", "hello"),
            ]
        )

        should transform:
        - self.name into __task_self_name__()
        - self.path into __task_self_name__()
        - self.inputs into __task_self_inputs__()
        - self.outputs into __task_self_outputs__()

        NOTE: self references must be entirely within the task call; they can't be separated.
        
        TODO: avoid transforming self if we are in a python class definition.
    """

    _attr_map = {
        "name": MAKEX_FUNCTION_TASK_SELF_NAME,
        "path": MAKEX_FUNCTION_TASK_SELF_PATH,
        "inputs": MAKEX_FUNCTION_TASK_SELF_INPUTS,
        "outputs": MAKEX_FUNCTION_TASK_SELF_OUTPUTS,
    }

    def __init__(self, path):
        super().__init__()
        self.path = str(path)
        self._transform_self_references = True

    def visit_Call(self, node: ast.Call) -> Any:
        if is_function_call(node, MAKEX_FUNCTION_TASK) is False:
            self.generic_visit(node)
            return node

        # transform self references
        self._transform_self_references = True

        self.generic_visit(node)

        # end transforms
        self._transform_self_references = False

        return node

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if self._transform_self_references is False:
            self.generic_visit(node)
            return node

        node_value = node.value

        if isinstance(node_value, ast_Name) and node_value.id == "self":
            if isinstance(node_value.ctx, ast_Load) is False:
                self.generic_visit(node)
                return node

            ## simple attribute access; self.name or self.path
            attr = node.attr
            line = node.lineno
            offset = node.col_offset
            location = create_file_location_call(self.path, line, offset)

            attr_mapping = self._attr_map.get(attr, None)

            if attr_mapping is None:
                raise PythonScriptError(f"Invalid self task attribute {attr}", location=location)

            reference_call = ast_Call(
                func=ast_Name(
                    id=attr_mapping,
                    ctx=ast_Load(),
                    lineno=line,
                    col_offset=offset,
                ),
                args=[],
                # XXX :location is added by later pass
                keywords=[
                    #    ast_keyword(
                    #        arg=FILE_LOCATION_ARGUMENT_NAME,
                    #        value=location,
                    #        lineno=line,
                    #        col_offset=offset,
                    #    ),
                ],
                lineno=line,
                col_offset=offset,
            )
            return reference_call
        elif isinstance(node_value, ast_Attribute) and node_value.value.id == "self":
            # sub attribute access
            # eg. self.outputs.test
            """
            print(ast.dump(ast.parse('self.outputs.test'), indent=4))
            
            Expr(
                value=Attribute(
                    value=Attribute(
                        value=Name(id='self', ctx=Load()),
                        attr='outputs',
                        ctx=Load()
                    ),
                    attr='test',
                    ctx=Load()
                )
            )
            """

            line = node.lineno
            offset = node.col_offset
            location = create_file_location_call(self.path, line, offset)

            namespace = node_value.attr
            namespace_name = node.attr

            attr_mapping = self._attr_map.get(namespace, None)

            reference_call = ast_Call(
                func=ast_Name(
                    id=attr_mapping,
                    ctx=ast_Load(),
                    lineno=line,
                    col_offset=offset,
                ),
                args=[ast_Constant(namespace_name)],
                # XXX: location argument is added by a later pass
                keywords=[
                    #    ast_keyword(
                    #        arg=FILE_LOCATION_ARGUMENT_NAME,
                    #        value=location,
                    #        lineno=line,
                    #        col_offset=offset,
                    #    ),
                ],
                lineno=line,
                col_offset=offset,
            )
            return reference_call
        else:
            self.generic_visit(node)
            return node
