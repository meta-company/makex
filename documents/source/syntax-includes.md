# Including Makex Files

```{note}
This is a new/experimental feature and subject to change. 
```

Makex provides an `include()` function to include the contents of another Makex File.

This is useful to reduce duplication and share common patterns among a project or its components.

It's signature follows:

```{eval-rst}
.. py:function:: include(path, search=False, tasks=False, required=True)
  
  Include the specified path.
  
  :param String path: Path of the file to import. May be a Workspace path, an absolute path, or relative path.
  
  :param bool search: If True, search the path specified in the current directory up the current workspace until it is found.
  
  This will search for the file in the including Makex File's folder and all folders up to its Workspace.
  
  :param bool tasks: Include any tasks defined in the file.
  
  :param bool required: If True (the default), the file to include must exist; an error will be raised if it is not found..

```

Files to be included should be suffixed with the `.mx` extension.

```{note}
While you may create tasks in an included file, this is not recommended and disabled by default.

Use `include(tasks=True)` to include any tasks defined in the included file.
```

## Example

For example, given a Makex file to be included (`//tools.mx`)
and a Makexfile which includes (`//projects/Makexfile`); the including Makex File
can call a macro (`make_task`) which registers a task in itself:

The `//project/Makexfile` file:

```python

include("tools.mx", search=True)

make_task()
```

The `//tools.mx` file:

```python
@macro
def make_task():
    task(
        name="example-task"
    )
```

As demonstrated, when `search=True` the include function will search the Makex File's folder and all
parent folders up to the current workspace for the file to include.


# Optional Includes

Optional includes may be used to define macros and tasks which are not necessarily required.

