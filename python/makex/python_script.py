"""

Notes:

- This module designed to stay in a single file.
- Do not import 3rd party.
- Do not split items in this file into separate modules/packages.

"""
import ast
import logging
import sys
import traceback
import types
from abc import (
    ABC,
    abstractmethod,
)
from collections import deque
from copy import copy
from importlib.machinery import ModuleSpec
from io import StringIO
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    BinaryIO,
    Optional,
    Protocol,
    Union,
)

LOGGER = logging.getLogger("python-script")
STRING_VALUE_NAME = "_STRING_"
LIST_VALUE_NAME = "_LIST_"
GLOBALS_NAME = "_GLOBALS_"
FILE_LOCATION_NAME = "_LOCATION_"
FILE_LOCATION_ARGUMENT_NAME = "_location_"
FILE_LOCATION_ATTRIBUTE = "location"


class FileLocation:
    line: int
    column: int
    path: str

    # XXX: optimized with slots because many of these will be created.
    __slots__ = ["line", "column", "path"]

    def __init__(self, line, column, path=None):
        self.line = line
        self.column = column
        self.path = path

    def __repr__(self):
        if self.path:
            return f"FileLocation({self.line}, {self.column}, \"{self.path}\")"
        else:
            return f"FileLocation({self.line}, {self.column})"

    def __str__(self):
        if self.path:
            return f"{self.path}:{self.line}:{self.column}"
        else:
            return f"{self.line}:{self.column}"

    @classmethod
    def from_ast_node(self, node: ast, path: str):
        return FileLocation(
            line=node.lineno,
            column=node.col_offset,
            path=path,
        )


_SENTINEL = object()


def get_location(object, default=_SENTINEL) -> Optional[FileLocation]:
    # Return a FileLocation from an object in a python script.
    if default is _SENTINEL:
        return getattr(object, FILE_LOCATION_ATTRIBUTE)
    return getattr(object, FILE_LOCATION_ATTRIBUTE, default)


def is_function_call(node: ast.Call, name: str):
    if isinstance(node, ast.Call) is False:
        return False

    if isinstance(node.func, ast.Name) and node.func.id == name:
        return True

    return False


def call_function(name, line, column, args=None, keywords=None):
    call = ast.Call(
        func=ast.Name(
            id=name,
            ctx=ast.Load(),
            lineno=line,
            col_offset=column,
        ),
        args=args or [],
        keywords=keywords or [],
        lineno=line,
        col_offset=column,
    )
    return call


class ScriptCallable:
    def __call__(self, *args, _line_: int, _column_: int, **kwargs):
        pass


class ScriptEnvironment(Protocol):
    # TODO: abc this. We should call and use globals() in descendant environments so StringValue/etc work.
    def globals(self) -> dict[str, ScriptCallable]:
        return {
            STRING_VALUE_NAME: StringValue,
            LIST_VALUE_NAME: ListValue,
            GLOBALS_NAME: globals,
            FILE_LOCATION_NAME: FileLocation
        }


Globals = dict[str, str]


class BaseScriptEnvironment(ABC):
    def exit(self):
        # exit the script
        raise StopPythonScript("Script Stopped/Exited by request.")

    @abstractmethod
    def globals(self):
        raise NotImplementedError


class PythonScriptError(Exception):
    path: Path = None
    location: FileLocation = None

    def __init__(self, message, location: FileLocation):
        super().__init__(str(message))
        self.wraps = Exception(message) if isinstance(message, str) else message
        self.location = location

    def with_path(self, path):
        # TODO: not sure why this function exists
        c = copy(self)
        c.path = path
        c.wrap = self.wraps
        return c

    def pretty(self):
        return pretty_exception(self.wraps, self.location)
        #return pretty_exception(self, Path(self.location.path), color=color)


class StopPythonScript(PythonScriptError):
    pass


class PythonScriptFileError(PythonScriptError):
    path: Path
    wraps: Exception

    def __init__(self, wraps, path, location: FileLocation = None):
        super().__init__(str(wraps), location=location)
        self.path = path
        self.wraps = wraps
        #self.location = location


class PythonScriptFileSyntaxError(PythonScriptFileError):
    path: Path
    wraps: Exception
    location: FileLocation

    def __init__(self, wraps, path, location=None):
        super().__init__(wraps, path, location)


def wrap_script_function(f):
    # wraps a script function to have a location= keyword argument instead of our special hidden one
    def wrapper(*args, **kwargs):
        location = kwargs.pop(FILE_LOCATION_ARGUMENT_NAME)
        return f(*args, **kwargs, location=location)

    return wrapper


# TODO: Track other primitive types: None/bool/list/dict/int/float
class StringValue(str):
    """
        This is a special type.

        We're doing weird things here.

        Track string value locations because they are usually a source of problems, and we want to refer to that location
        for the user.

        UserString has been considered, and its more work.
    """
    __slots__ = ["value", "location"]

    def __init__(self, data, location=None):
        super().__init__()
        self.value = data
        self.location = location

    def replace(self, *args, _location_=None) -> "StringValue":
        return StringValue(self.value.replace(*args), location=_location_)

    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, args[0])

    def __add__(self, other):
        return StringValue(self.value + other.value, getattr(other, "location", self.location))

    # TODO: __add__ with a non-string should return an internal JoinedString


class DisableImports(ast.NodeVisitor):
    # TODO: disable imports

    def __init__(self, path: PathLike):
        self.path = path

    def visit_Import(self, node):
        print(
            f"""Line {node.lineno} imports modules {
        ', '.join(alias.name for alias in node.names)
        }"""
        )
        raise PythonScriptError(
            "Invalid syntax (Imports are not allowed):",
            FileLocation.from_ast_node(node, self.path)
        )

    def visit_ImportFrom(self, node):
        print(
            f"""Line {node.lineno} imports from module {node.module} the names {
        ', '.join(alias.name for alias in node.names)
        }"""
        )
        raise PythonScriptError(
            "Invalid syntax (Imports are not allowed):",
            FileLocation.from_ast_node(node, self.path)
        )


def _create_file_location_call(path, line, column):
    file_location_call = ast.Call(
        func=ast.Name(
            id=FILE_LOCATION_NAME,
            ctx=ast.Load(lineno=line, col_offset=column),
            lineno=line,
            col_offset=column
        ),
        args=[
            ast.Constant(line, lineno=line, col_offset=column),
            ast.Constant(column, lineno=line, col_offset=column),
            ast.Constant(path, lineno=line, col_offset=column),
        ],
        keywords=[],
        lineno=line,
        col_offset=column,
    )
    return file_location_call


class _DisableAssignments(ast.NodeVisitor):
    """
    Disable assignments:
    - to anything non-script (globals)
    - to specified variables.

    a,b = item
    a,*b = it

    del a

    a = 1
    """
    def __init__(self, path: PathLike, names: set = None):
        self.path = str(path)
        self.names = names or set()

    def check_name(self, node, name):
        if name in self.names:
            raise PythonScriptError(
                f"Can't assign to the name '{name}'. Please rename the variable to something else.",
                location=FileLocation.from_ast_node(node, self.path),
            )

    def visit_NamedExpr(self, node: ast.NamedExpr) -> Any:
        # (walrus)
        if isinstance(node.target, ast.Name):
            self.check_name(node, node.target.id)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        #AnnAssign; assignments with type expressions
        if isinstance(node.target, ast.Name):
            self.check_name(node, node.target.id)

    def visit_Assign(self, node: ast.Assign) -> Any:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.check_name(node, target.id)
            elif isinstance(target, ast.Tuple):
                for element in target.elts:
                    if isinstance(element, ast.Name):
                        self.check_name(element, element.id)
        """
         the following expression can appear in assignment context

         | Attribute(expr value, identifier attr, expr_context ctx)
         | Subscript(expr value, expr slice, expr_context ctx)
         | Starred(expr value, expr_context ctx)
         | Name(identifier id, expr_context ctx)
         | List(expr* elts, expr_context ctx)
         | Tuple(expr* elts, expr_context ctx)

        """


class _TransformStringValues(ast.NodeTransformer):
    """
    Transform string and f-strings to be wrapped in a StringValue() with a FileLocation.
    """
    def __init__(self, path: PathLike):
        self.path = path

    def visit_Call(self, node: ast.Call) -> Any:
        if node.func and isinstance(node.func, ast.Name) and node.func.id == FILE_LOCATION_NAME:
            # Don't step on the FileLocation() adding pass.
            # return the node and don't process the FileLocation children.
            return node
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, str):
            line = node.lineno
            offset = node.col_offset

            #logging.debug("Got string cnst %s %s", node.value, node.lineno)
            file_location = _create_file_location_call(self.path, line, offset)

            # TODO: separate the values into JoinedString class so we can evaluate later.
            strcall = ast.Call(
                func=ast.Name(
                    id=STRING_VALUE_NAME,
                    ctx=ast.Load(),
                    lineno=line,
                    col_offset=offset,
                ),
                args=[node],
                keywords=[
                    ast.keyword(
                        arg='location',
                        value=file_location,
                        lineno=line,
                        col_offset=offset,
                    ),
                ],
                lineno=line,
                col_offset=offset,
            )
            return strcall
        else:
            #logging.debug("Got other const %r", node.value)
            return node

    def visit_JoinedStr(self, node: ast.JoinedStr) -> Any:
        line = node.lineno
        offset = node.col_offset

        file_location = _create_file_location_call(self.path, line, offset)

        # TODO: separate the values into JoinedString class so we can evaluate later.
        strcall = ast.Call(
            func=ast.Name(id=STRING_VALUE_NAME, ctx=ast.Load()),
            args=[node],
            keywords=[
                ast.keyword(arg='location', value=file_location),
            ],
            lineno=line,
            col_offset=offset,
        )
        self.generic_visit(node)

        ast.fix_missing_locations(strcall)
        return strcall

    # XXX: Deprecated in 3.8 and unused past that version.
    def visit_Str(self, node):
        self.generic_visit(node)

        line = node.lineno
        offset = node.col_offset

        file_location = _create_file_location_call(self.path, line, offset)
        strcall = ast.Call(
            func=ast.Name(id=STRING_VALUE_NAME, ctx=ast.Load()),
            args=[ast.Str(node.s)],
            keywords=[
                ast.keyword(arg='location', value=file_location),
            ],
            lineno=line,
            col_offset=offset,
        )

        ast.fix_missing_locations(strcall)
        return strcall


class _TransformCallsToHaveFileLocation(ast.NodeTransformer):
    """ This pass gives us the highest possible accuracy for locations of calls.

        Because the ast module doesn't preserve comments/etc, the locations of various things are incorrect when using
        inspect. BONUS: This might be a little faster than using inspect.

        We add the FILE_LOCATION_ARGUMENT_NAME= keyword argument to all known calls in the file.
    """
    def __init__(self, names, path: PathLike):
        # TODO: names should be list of names to ignore
        self._ignore_names = names
        self.path = path
        self.attributes = None

    def visit_Call(self, node: ast.Call):
        #debug(f"#Transform fileloction {node.func} {type(node.func)} {node.func.ctx} {type(node.func.ctx)}")
        func = node.func

        if isinstance(func, ast.Attribute):
            attr_name = func.attr
            attr_of = func.value
            if not (isinstance(attr_of, ast.Name) and isinstance(attr_of.ctx, ast.Load)):
                # could/probably have a str.method e.g. "".join()

                #for child in ast.iter_child_nodes(node):
                #    self.generic_visit(child)
                self.generic_visit(node)
                return node
        elif isinstance(func, ast.Name):
            function_name = func.id

            # XXX: Ignore specific names we need to handle specially; like StringValue and FileLocation.
            if function_name in self._ignore_names:
                self.generic_visit(node)
                return node
        else:
            # can't determine function name. don't know whether to include
            # user is doing something unexpected.
            # TODO: we should raise a PythonScriptError here.
            self.generic_visit(node)
            return node
        self.generic_visit(node)

        #debug(f">Transform fileloction {node.func.id}")
        file_location = _create_file_location_call(self.path, node.lineno, node.col_offset)
        node.keywords = node.keywords or []
        node.keywords.append(ast.keyword(arg=FILE_LOCATION_ARGUMENT_NAME, value=file_location))

        ast.fix_missing_locations(node)
        return node


class ListValue:
    """
        This changes the behavior of lists and list comprehensions in python so that + or += means append.

        We also implement radd so we can retain one large list whenever we merge it with others.
    """
    # TODO: move to non syntax specific file
    initial_value: list
    location: FileLocation

    __slots__ = ["initial_value", "location", "appended_values"]

    def __init__(self, value, _location_: FileLocation):
        assert isinstance(value, list)
        self.initial_value = value
        self.appended_values = deque()
        self.appended_values.extend(value)
        self.location = _location_

    def append(self, value, _location_):
        self.appended_values.append(value)

    def __iter__(self):
        return self.appended_values.__iter__()

    def __getitem__(self, index):
        return self.appended_values[index]

    def __radd__(self, other):
        if isinstance(other, list):
            self.appended_values.extendleft(other)
        #elif isinstance(other, GlobValue):
        #
        #    for i in other:
        #        self.appended_values.insert(0, i)
        #
        #    self.prepended_values.extend(other._pieces)
        #    self.appended_values.appendleft(other)
        #elif isinstance(other, StringValue):
        #    self.appended_values.appendleft(other)
        elif isinstance(other, ListValue):
            self.appended_values.appendleft(*other.appended_values)
            #self.prepended_values.extend(other.appended_values)
        else:
            raise Exception(f"Cant add {other}{type(other)} to {self}")
        return self

    def __add__(self, other):
        if isinstance(other, list):
            self.appended_values.extend(other)
        #elif isinstance(other, StringValue):
        #    self.appended_values.append(other)
        #elif isinstance(other, GlobValue):
        #    self.appended_values.append(other)
        elif isinstance(other, ListValue):
            self.appended_values.extend(other.appended_values)
        else:
            self.appended_values.append(other)
        return self

    __iadd__ = __add__


class _TransformListValues(ast.NodeTransformer):
    """
        Wrap each list in a ListValue. This will allow late evaluation of globs/etc.

        node(
            inputs=[]+glob()
        )

        node(
            inputs=ListValue([])+glob()
        )

        node(
            inputs=glob()+[]
        )

        node(
            inputs=glob()+ListValue([])
        )
    """
    def __init__(self, path: str):
        self.path = path

    def visit_List(self, node):
        #if len(node.elts) > 0:
        #    return ast.copy_location(node, node)
        #return ast.copy_location(ast.NameConstant(value=None), node)
        line = node.lineno
        offset = node.col_offset

        _node = ast.Call(
            func=ast.Name(id=LIST_VALUE_NAME, ctx=ast.Load(), lineno=line, col_offset=offset),
            args=[node],
            keywords=[],
            lineno=line,
            col_offset=offset,
        )

        file_location = _create_file_location_call(self.path, line, offset)
        _node.keywords.append(
            ast.keyword(
                arg=FILE_LOCATION_ARGUMENT_NAME,
                value=file_location,
                lineno=line,
                col_offset=offset
            )
        )

        #for child in ast.iter_child_nodes(node):
        #    self.visit(child)

        #ast.fix_missing_locations(_node)
        self.generic_visit(node)
        return _node

    visit_ListComp = visit_List


class PythonScriptFile:
    def __init__(
        self,
        path: PathLike,
        globals: Globals = None,
        importer=None,
        pre_visitors=None,
        extra_visitors=None,
        enable_imports=False,
    ):
        #self._env = env
        self.path = str(path)
        self.globals = globals or {}
        self.disable_assignment_names = set()
        self.extra_visitors = extra_visitors or []
        self.pre_visitors = pre_visitors or []
        self.enable_imports = enable_imports
        self.importer = importer or self._importer

        # transform attribute calls to have line/column information
        #self._all_globals = self._env.globals()
        #self._all_globals.update(self.globals)

    def _ast_parse(self, f: BinaryIO):
        # XXX: must be binary due to the way hash_contents works
        buildfile_contents = f.read()
        f.seek(0)
        # transform to ast
        tree = ast.parse(buildfile_contents, filename=self.path, mode='exec')
        return tree

    def set_disabled_assignment_names(self, names: set):
        self.disable_assignment_names = names

    #def _get_env_attr(self, name):
    #    if self._env.has_global(name):
    #        return self._env.get_global(name)

    #    try:
    #        return self._all_globals.get(name)
    #    except ValueError as e:
    #        raise PythonScriptError(f"{name} not defined in global scope.")

    def parse(self, file: Union[BinaryIO]) -> ast.AST:
        # parse and process the ast.
        # TODO: prefix the modules to execute with the ast to include
        try:
            tree = self._ast_parse(file)
        except SyntaxError as e:
            exc_type, exc_message, exc_traceback = sys.exc_info()
            l = FileLocation(e.lineno, e.offset, self.path)
            raise PythonScriptError(e, location=l) from e

        self._parse(tree)

        return tree

    def _parse(self, tree: ast.AST):
        # set of names to ignore
        ignore = {STRING_VALUE_NAME, FILE_LOCATION_NAME, LIST_VALUE_NAME, GLOBALS_NAME}

        # Catch some early errors
        if False:
            t = DisableImports(self.path)
            t.visit(tree)

        t = _DisableAssignments(self.path, self.disable_assignment_names)
        t.visit(tree)

        for visitor in self.pre_visitors:
            visitor.visit(tree)

        # XXX: calls should be transformed first
        t = _TransformCallsToHaveFileLocation(ignore, self.path)
        t.visit(tree)

        # XXX: string values and primitives should be transformed next
        t = _TransformStringValues(self.path)
        t.visit(tree)

        t = _TransformListValues(self.path)
        t.visit(tree)

        for visitor in self.extra_visitors:
            visitor.visit(tree)

    def _importer(self, name, globals=None, locals=None, fromlist=(), level=0):
        # level = 1 if relative import. e.g from .module import item
        # TODO: improve this error location
        raise ImportError("Imports are disabled here.")

    def execute(self, tree: ast.AST):
        if not isinstance(tree, ast.AST):
            raise ValueError(f"Expected AST argument. Got {type(tree)}")
            # TODO: use hasattr(file, "read") instead of isinstance
            #tree = file
        #else:
        #    tree = self.parse(file)
        from importlib.abc import Loader

        class CustomModule(types.ModuleType):
            def __init__(self, name):
                super().__init__(name)
                self.macros = {}

            def __getattribute__(self, item):
                if item == "__dict__":
                    return self.__dict__

                macro = self.macros.get(item, None)

                if macro is None:
                    raise PythonScriptError(
                        f"Can't import {item} from {self.name}", FileLocation(0, 0, "//")
                    )
                return macro

        class MakexLoader(Loader):
            def create_module(self, spec: ModuleSpec) -> Union[types.ModuleType, None]:
                print("CREATING MODULE", spec)
                module = types.ModuleType(spec.name)
                #exec(code, module.__dict__)

                return module

            def exec_module(self, module: types.ModuleType) -> None:
                print("Exec module", module)
                pass

        #scope = self._env.globals()
        #scope.update(self.globals)
        scope = self.globals
        #scope["__getattr__"] = self._get_env_attr

        scope["__builtins__"] = {}

        if self.enable_imports:
            scope["__builtins__"] = {"__import__": self.importer}
        #print(ast.dump(tree, indent=2))

        scope[STRING_VALUE_NAME] = StringValue
        scope[FILE_LOCATION_NAME] = FileLocation
        scope[LIST_VALUE_NAME] = ListValue
        scope[GLOBALS_NAME] = globals

        try:
            code = compile(tree, self.path, 'exec')
            exec(code, scope, scope)
        except TypeError as e:
            #LOGGER.exception(e)
            exc_type, exc_message, exc_traceback = sys.exc_info()
            # COMPAT: PYTHON 3.5+
            tb1 = traceback.TracebackException.from_exception(e)
            # go backwards in the stack for non-makex errors
            for item in tb1.stack:
                if item.filename == self.path:
                    location = FileLocation(item.lineno, 0, self.path)
                    break
            else:
                last = tb1.stack[-1]
                location = FileLocation(last.lineno, 0, self.path)
            raise PythonScriptError(e, location=location) from e

        except (IndexError, NameError, AttributeError) as e:
            #LOGGER.exception(e)
            exc_type, exc_message, exc_traceback = sys.exc_info()
            # COMPAT: PYTHON 3.5+
            tb1 = traceback.TracebackException.from_exception(e)
            last = tb1.stack[-1]

            l = FileLocation(last.lineno, 0, last.filename)
            for item in tb1.stack:
                print("TRACE", item)
                #if item.filename == self.path:
                #    location = FileLocation(item.lineno, 0, self.path)
                #    break

            raise PythonScriptError(e, location=l) from e

        except StopPythonScript as e:
            # python script exited
            #LOGGER.exception(e)
            tb1 = traceback.TracebackException.from_exception(e)
            last = tb1.stack[-1]
            l = FileLocation(last.lineno, 0, self.path)
            raise PythonScriptError(e, location=l) from e

        except ImportError as e:
            tb1 = traceback.TracebackException.from_exception(e)
            last = tb1.stack[-1]
            l = FileLocation(last.lineno, 0, self.path)
            raise PythonScriptError(e, location=l) from e
        except SyntaxError as e:
            #LOGGER.exception(e)
            exc_type, exc_message, exc_traceback = sys.exc_info()
            l = FileLocation(e.lineno, e.offset, self.path)
            raise PythonScriptError(e, location=l) from e

        return code


def pretty_exception(exception, location: FileLocation):
    # TODO: remove colors from this pretty_exception
    buf = StringIO()
    buf.write(f"Error inside a Makexfile '{location.path}:{location.line}'\n\n")
    buf.write(f"{exception}\n\n")
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
