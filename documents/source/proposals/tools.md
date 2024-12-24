---
status: "Draft"
---
# Tool Primitives

This proposal defines tool primitives for defining the version of externally provided tools.

## Rationale

Tool/executables should be hashed. Different versions may produce different output.

This is handled in-system with tasks whose output(s) are tools/executables. Currently, executables may be built and used entirely within makex.

## Specification

Externally provided tools should be versioned/tagged, and the version should be easy to obtain by running the tool,
or inspecting one its related files.

### tool(path, version=execute|shell)

a tool() or require_tool() primative. e.g. `PYTHON = tool("/usr/bin/python", version=execute|shell)`

If an action is specified for version argument, it inspects/loads/prints the version for tool so it can be hashed when used.

The version argument is called before any use of the tool during task evaluation.

The version may be provided as a constant as a String/Integer literal or from an Environment Variable.

## Rejected Ideas

### LDD

would be nice if we could run ldd and get a hash, but this might not actually be accurate or comprehensive. executables may dynamically load outside declared object files in elf/etc.

### Binary Inspection

TODO: Does elf have any standard version/build headers we can use to distinguish?

This won't help us with tools that are non binary (e.g. scripts)

### Version Variable Reference

(probably not useful. YAGNI). Can be accomplished by a direct reference to a tasks output in an execute() or shell() action.

Version argument may be a reference to a variable in another makex file. 

For example:

```python

EXAMPLE_TOOL = tool(
    path=task["//path/to/task":"task_name"].output, 
    version=variable("//path/to/folder", "VERSION")
)
```