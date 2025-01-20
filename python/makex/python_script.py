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
from abc import (
    ABC,
    abstractmethod,
)
from ast import fix_missing_locations
from collections import deque
from copy import copy
from dataclasses import (
    dataclass,
    field,
)
from io import StringIO
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    BinaryIO,
    Callable,
    Optional,
    Protocol,
    Union,
)

# PERFORMANCE: import names directly from the ast module so we don't need to do module lookup
ast_Call = ast.Call
ast_Name = ast.Name
ast_Constant = ast.Constant
ast_Load = ast.Load
ast_keyword = ast.keyword
ast_Attribute = ast.Attribute

LOGGER = logging.getLogger("python-script")
STRING_VALUE_NAME = "_STRING_"
JOINED_STRING_VALUE_NAME = "_JOINED_STRING_"
LIST_VALUE_NAME = "_LIST_"
GLOBALS_NAME = "_GLOBALS_"
FILE_LOCATION_NAME = "_LOCATION_"
FILE_LOCATION_ARGUMENT_NAME = "_location_"
FILE_LOCATION_ATTRIBUTE = "location"

# set of names to ignore
IGNORE_NAMES = {
    STRING_VALUE_NAME,
    FILE_LOCATION_NAME,
    LIST_VALUE_NAME,
    GLOBALS_NAME,
    JOINED_STRING_VALUE_NAME,
}


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


class HasLocation(Protocol):
    """
    A standard protocol nodes should implement, so they may be located (by get_location()).
    """
    location: FileLocation


def get_location(object: HasLocation, default=_SENTINEL) -> Optional[FileLocation]:
    # Return a FileLocation from an object in a python script.
    if default is _SENTINEL:
        return getattr(object, FILE_LOCATION_ATTRIBUTE)
    return getattr(object, FILE_LOCATION_ATTRIBUTE, default)


def is_function_call(node: ast.Call, name: str):
    if isinstance(node, ast_Call) is False:
        return False

    if isinstance(node.func, ast_Name) and node.func.id == name:
        return True

    return False


def call_function(name, line, column, args=None, keywords=None):
    call = ast_Call(
        func=ast_Name(
            id=name,
            ctx=ast_Load(),
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


Globals = dict[str, Any]


class BaseScriptEnvironment(ABC):
    def exit(self):
        # exit the script
        raise StopPythonScript("Script Stopped/Exited by request.")

    @abstractmethod
    def globals(self):
        raise NotImplementedError


class FileLocationProtocol(Protocol):
    line: int
    column: int
    path: str


class PythonScriptError(Exception):
    path: Path = None
    location: FileLocationProtocol = None

    def __init__(self, message, location: FileLocationProtocol):
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


def wrap_script_function(f, **extra):
    # wraps a script function to have a location= keyword argument instead of our special hidden one
    def wrapper(*args, **kwargs):
        location = kwargs.pop(FILE_LOCATION_ARGUMENT_NAME)
        return f(*args, **kwargs, **extra, location=location)

    return wrapper


# TODO: Track other primitive types: None/bool/dict/int/float
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
        self.value: str = data
        self.location: FileLocation = location

    def replace(self, *args, _location_=None) -> "StringValue":
        return StringValue(self.value.replace(*args), location=_location_)

    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, args[0])

    def __add__(self, other):
        return StringValue(self.value + other.value, getattr(other, "location", self.location))

    def __hash__(self):
        return hash(self.value)

    def __eq__(self, other):
        if isinstance(other, StringValue):
            return self.value == other.value
        elif isinstance(other, str):
            return self.value == other
        else:
            return False

    # TODO: __add__ with a non-string should return an internal JoinedString


class JoinedString:
    """
        Special type to allow deferring the evaluation of joined strings (and values inside of them).

        Once ready to evaluate, call evaluate() to produce a StringValue which may be used more normally.

    """
    __slots__ = ["parts", "location"]

    def __init__(self, *parts, location=None):
        self.parts: list[Any] = parts
        self.location: FileLocation = location

    #def evaluate(self, data=None) -> StringValue:
    #    # use the variables/functions in data to evaluate the string parts
    #    return StringValue("".join(self._evaluate(data)), location=self.location)
    #def _evaluate(self, data):
    #    for part in self.parts:
    #        if eval_func := getattr(part, "evaluate", None):
    #            yield eval_func(data)
    #        else:
    #            yield part


class IntegerValue:
    # XXX: subtypes of int can't have slots. (TypeError: nonempty __slots__ not supported for subtype of 'int')
    __slots__ = ("value", "location")

    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, args[0])

    def __init__(self, value, location: FileLocation):
        self.value: int = value
        self.location: FileLocation = location

    def __int__(self):
        return self.value

    def __index__(self):
        return self.value

    def __add__(self, other):
        if isinstance(other, IntegerValue) is False:
            raise RuntimeError(f"Can't add {self!r} with {type(other)}.")
        return IntegerValue(self.value + other.value, other.location)

    def __iadd__(self, other):
        if isinstance(other, IntegerValue) is False:
            raise RuntimeError(f"Can't add {type(other)} to {self!r}.")
        self.value += other.value
        return self

    def __sub__(self, other):
        # self - other
        if isinstance(other, IntegerValue) is False:
            raise RuntimeError(f"Can't subtract {type(other)} from {self!r}.")
        return IntegerValue(self.value - other.value, other.location)

    def __isub__(self, other):
        # self -= other
        if isinstance(other, IntegerValue) is False:
            raise RuntimeError(f"Can't subtract {self!r} with {type(other)}.")

        self.value -= other.value
        return self

    def __mul__(self, other):
        # self * other
        if isinstance(other, IntegerValue) is False:
            raise RuntimeError(f"Can't multiply {self!r} with {type(other)}.")
        return IntegerValue(self.value * other.value, other.location)

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return 'IntegerValue(%s)' % self.value


class BooleanValue:
    __slots__ = ("value", "location")

    def __init__(self, value: bool, location: FileLocation):
        self.value: bool = value
        self.location: FileLocation = location

    def __bool__(self):
        return self.value

    def __repr__(self):
        return 'BooleanValue(%s)' % self.value


class NoneValue:
    def __init__(self, location: FileLocation):
        self.location = location


class _DisableImports(ast.NodeVisitor):
    """
        Disables import statements in the two forms.
    """
    def __init__(self, path: PathLike):
        self.path = path

    def visit_Import(self, node):
        names = ', '.join(alias.name for alias in node.names)
        print(f"""Line {node.lineno} imports modules {names}""")
        raise PythonScriptError(
            "Invalid syntax (Imports are not allowed):",
            FileLocation.from_ast_node(node, self.path)
        )

    def visit_ImportFrom(self, node):
        names = ', '.join(alias.name for alias in node.names)
        logging.error(f"""Line {node.lineno} imports from module {node.module} the names {names}""")
        raise PythonScriptError(
            "Invalid syntax (Imports are not allowed):",
            FileLocation.from_ast_node(node, self.path)
        )


def create_file_location_call(path, line, column):
    file_location_call = ast_Call(
        func=ast_Name(
            id=FILE_LOCATION_NAME,
            ctx=ast_Load(lineno=line, col_offset=column),
            lineno=line,
            col_offset=column
        ),
        args=[
            ast_Constant(line, lineno=line, col_offset=column),
            ast_Constant(column, lineno=line, col_offset=column),
            ast_Constant(path, lineno=line, col_offset=column),
        ],
        keywords=[],
        lineno=line,
        col_offset=column,
    )
    return file_location_call


def add_location_keyword_argument(node: ast.Call, path, line, column):
    file_location = create_file_location_call(path, line, column)
    node.keywords.append(
        ast_keyword(
            arg=FILE_LOCATION_ARGUMENT_NAME,
            value=file_location,
            lineno=line,
            col_offset=column,
        )
    )


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
        if isinstance(node.target, ast_Name):
            self.check_name(node, node.target.id)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        #AnnAssign; assignments with type expressions
        if isinstance(node.target, ast_Name):
            self.check_name(node, node.target.id)

    def visit_Assign(self, node: ast.Assign) -> Any:
        for target in node.targets:
            if isinstance(target, ast_Name):
                self.check_name(node, target.id)
            elif isinstance(target, ast.Tuple):
                for element in target.elts:
                    if isinstance(element, ast_Name):
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
    def __init__(self, path: PathLike, late_joined=False):
        self.path = path
        self.late_joined = late_joined

        if self.late_joined is False:
            self.visit_JoinedStr = self.visit_JoinedStr1
        else:
            self.visit_JoinedStr = self.visit_JoinedStr2

    def visit_Call(self, node: ast.Call) -> Any:
        if node.func and isinstance(node.func, ast_Name) and node.func.id == FILE_LOCATION_NAME:
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
            # TODO: separate the values into JoinedString class so we can evaluate later.
            strcall = ast_Call(
                func=ast_Name(
                    id=STRING_VALUE_NAME,
                    ctx=ast_Load(),
                    lineno=line,
                    col_offset=offset,
                ),
                args=[node],
                keywords=[
                    ast_keyword(
                        arg='location',
                        value=create_file_location_call(self.path, line, offset),
                        lineno=line,
                        col_offset=offset,
                    ),
                ],
                lineno=line,
                col_offset=offset,
            )
            return strcall
        else:
            # TODO: transform whatever constant here into the appropriate type (e.g. NoneValue, BoolValue,FloatValue)
            #logging.debug("Got other const %r", node.value)
            return node

    def visit_JoinedStr1(self, node: ast.JoinedStr) -> Any:
        line = node.lineno
        offset = node.col_offset

        # Wrap the entire JoinedStr into a StringValue()
        strcall = ast_Call(
            func=ast_Name(id=STRING_VALUE_NAME, ctx=ast_Load()),
            args=[node],
            keywords=[
                ast_keyword(
                    arg='location',
                    value=create_file_location_call(self.path, line, offset),
                ),
            ],
            lineno=line,
            col_offset=offset,
        )
        self.generic_visit(node)

        fix_missing_locations(strcall)
        return strcall

    def visit_JoinedStr2(self, node: ast.JoinedStr) -> Any:
        line = node.lineno
        offset = node.col_offset

        self.generic_visit(node)

        # separate the values into JoinedString class, so we can evaluate the parts later.
        values = []
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                values.append(value.value)
            else:
                values.append(value)

        strcall = ast_Call(
            func=ast_Name(id=JOINED_STRING_VALUE_NAME, ctx=ast_Load()),
            args=values,
            keywords=[
                ast_keyword(
                    arg='location',
                    value=create_file_location_call(self.path, line, offset),
                ),
            ],
            lineno=line,
            col_offset=offset,
        )
        fix_missing_locations(strcall)
        return strcall

    # XXX: Deprecated in 3.8 and unused past that version.
    def visit_Str(self, node):
        self.generic_visit(node)

        line = node.lineno
        offset = node.col_offset

        strcall = ast_Call(
            func=ast_Name(id=STRING_VALUE_NAME, ctx=ast_Load()),
            args=[ast.Str(node.s)],
            keywords=[
                ast_keyword(
                    arg='location',
                    value=create_file_location_call(self.path, line, offset),
                ),
            ],
            lineno=line,
            col_offset=offset,
        )

        fix_missing_locations(strcall)
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

        if isinstance(func, ast_Attribute):
            attr_name = func.attr
            attr_of = func.value
            if not (isinstance(attr_of, ast_Name) and isinstance(attr_of.ctx, ast_Load)):
                # could/probably have a str.method e.g. "".join()
                #for child in ast.iter_child_nodes(node):
                #    self.generic_visit(child)
                self.generic_visit(node)
                return node
        elif isinstance(func, ast_Name):
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
        file_location = create_file_location_call(self.path, node.lineno, node.col_offset)
        node.keywords = node.keywords or []
        node.keywords.append(ast_keyword(arg=FILE_LOCATION_ARGUMENT_NAME, value=file_location))

        fix_missing_locations(node)
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

    def __init__(self, value: list, _location_: FileLocation):
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
        elif isinstance(other, ListValue):
            self.appended_values.appendleft(*other.appended_values)
            #self.prepended_values.extend(other.appended_values)
        else:
            #self.appended_values.appendleft(other)
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

        _node = ast_Call(
            func=ast_Name(id=LIST_VALUE_NAME, ctx=ast_Load(), lineno=line, col_offset=offset),
            args=[node],
            keywords=[
                ast_keyword(
                    arg=FILE_LOCATION_ARGUMENT_NAME,
                    value=create_file_location_call(self.path, line, offset),
                    lineno=line,
                    col_offset=offset
                )
            ],
            lineno=line,
            col_offset=offset,
        )

        #for child in ast.iter_child_nodes(node):
        #    self.visit(child)

        #ast.fix_missing_locations(_node)
        self.generic_visit(node)
        return _node

    visit_ListComp = visit_List


class PythonScriptFile:
    @dataclass
    class Options:
        pre_visitors: list = field(default_factory=list)
        post_visitors: list = field(default_factory=list)

        imports_enabled: bool = False
        import_function: Optional[Callable] = None
        disable_assigment_names: set = field(default_factory=set)
        late_joined_string: bool = False
        transform_lists: bool = True

        # False: none
        # True: Use default
        builtins: bool = False

    extra_visitors = None
    pre_visitors = None
    importer = None
    enable_imports = False
    disable_assigment_names = set()
    late_joined_string = False

    def __init__(
        self,
        path: PathLike,
        globals: Optional[Globals] = None,
        options=None,
    ):
        self.path = str(path)
        self.globals = globals or {}
        self.options = options
        if options:
            self.extra_visitors = options.post_visitors
            self.pre_visitors = options.pre_visitors
            self.importer = options.import_function or self._importer
            self.enable_imports = options.imports_enabled
            self.disable_assignment_names = options.disable_assigment_names
            self.late_joined_string = options.late_joined_string

    def _ast_parse(self, f: BinaryIO):
        # XXX: must be binary due to the way hash_contents works
        buildfile_contents = f.read()
        f.seek(0)
        # transform to ast
        tree = ast.parse(buildfile_contents, filename=self.path, mode='exec')
        return tree

    def set_disabled_assignment_names(self, names: set):
        self.disable_assignment_names = names

    def parse(self, file: Union[BinaryIO]) -> ast.AST:
        # TODO: use hasattr(file, "read") instead of isinstance

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
        # Catch some early errors
        # TODO: enable this once we have options
        if False:
            t = _DisableImports(self.path)
            t.visit(tree)

        t = _DisableAssignments(self.path, self.disable_assignment_names)
        t.visit(tree)

        for visitor in self.pre_visitors:
            visitor.visit(tree)

        # XXX: calls should be transformed first
        t = _TransformCallsToHaveFileLocation(IGNORE_NAMES, self.path)
        t.visit(tree)

        # XXX: string values and primitives should be transformed next
        t = _TransformStringValues(self.path, late_joined=self.late_joined_string)
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
        #print(ast.dump(tree, indent=2))

        if not isinstance(tree, ast.AST):
            raise ValueError(f"Expected AST argument. Got {type(tree)}")

        scope = self.globals

        # TODO: make this line optional, default true
        scope["__builtins__"] = {}

        if self.enable_imports:
            scope["__builtins__"] = {"__import__": self.importer}

        scope[STRING_VALUE_NAME] = StringValue
        scope[FILE_LOCATION_NAME] = FileLocation
        scope[LIST_VALUE_NAME] = ListValue
        scope[GLOBALS_NAME] = globals
        scope[JOINED_STRING_VALUE_NAME] = JoinedString

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


def pretty_exception(exception, location: FileLocationProtocol):
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
