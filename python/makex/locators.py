from typing import Optional

from makex.constants import (
    SYNTAX_2024,
    SYNTAX_2025,
    TASK_PATH_NAME_SEPARATOR,
)
from makex.flags import MAKEX_SYNTAX_VERSION
from makex.python_script import (
    PythonScriptError,
    StringValue,
)


def format_locator(name=None, path=None, syntax=MAKEX_SYNTAX_VERSION) -> str:
    if syntax == SYNTAX_2024:
        if path is None:
            return f"{TASK_PATH_NAME_SEPARATOR}{name}"

        return f"{path}{TASK_PATH_NAME_SEPARATOR}{name}"

    if path is None:
        return f"{name}:"
    return f"{name}{TASK_PATH_NAME_SEPARATOR}{path}"


def parse_locator(locator: str, syntax=MAKEX_SYNTAX_VERSION) -> tuple[str, str]:
    parts = locator.split(TASK_PATH_NAME_SEPARATOR, 1)
    parts_len = len(parts)

    path = None

    if parts_len > 3:
        raise ValueError("Invalid locator. Too many colons: {}".format(locator))

    if syntax == SYNTAX_2024:
        if parts_len == 2:
            path, name = parts
            if not path:
                path = None
        else:
            name = parts[0]
    else:
        if parts_len == 1:
            name = parts[0]
        else:
            name, path = parts
            if not path:
                path = None

    return name, path


def parse_task_reference(
    string: StringValue,
    syntax=MAKEX_SYNTAX_VERSION,
) -> Optional[tuple[StringValue, StringValue]]:
    """
    Parse a simple task reference:
    
    //{path}:{task_name}
    
    :param string: 
    :return: 
    """
    # Parse a task reference; path is optional
    _string = string.value

    # TODO: SYNTAX_2025: fix here.
    if (index := _string.find(TASK_PATH_NAME_SEPARATOR)) == -1:
        return None

    if syntax == SYNTAX_2025:
        if index == 0:
            # TODO: this should be  an error
            #name = StringValue("", string.location)
            raise PythonScriptError(
                f"Locators must include a task name. Invalid locator: {_string!r}",
                location=string.location
            )

        name = StringValue(_string[:index], string.location)
        _path = _string[index + 1:]

        path = StringValue(_path, string.location) if _path else None
    else:
        if index == 0:
            path = None
        else:
            path = StringValue(_string[0:index], string.location)

        name = StringValue(_string[index + 1:], string.location)
    return (path, name)
