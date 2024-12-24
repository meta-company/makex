---
status: "Accepted"
version: "20241201"
---
# Erase Action

Provide an `erase()` action that will remove specific files from a task's output.

## Rationale

- Removing files from a Task's output is common (e.g. before distribution/deployment, or for downstream Task output consumers).
- `rm -rf` and related removal tools are fairly dangerous. 
- There is no reason we need to force users to call the shell or execute system specific tools to remove files from a task's output.

## Specification

```python

Removeable = Union[Path,TaskPath,String,Glob,RegularExpression,Find,list["Removable"]]

def erase(*paths:tuple[Removeable]):
    ...
```

Remove the files specified or found. 

If the files don't exist, no error will be generated.

If the file is an absolute path, it will be absolute to the Task's output path.

If the path is a folder, it will be removed recursively.

Files outside the task's output path MUST NOT be removed/erased/deleted.

## Example

```python
task(
    name="example",
    steps=[
        # actions producing outputs; some which we may not want in the final task output.
        ...,
        
        # erase a single file
        erase("path/to/file"),

        # erase files matching glob
        erase(glob("path/to/files/*.ext")),
        
        # erase files matching regular expression
        erase(re()),
    ]
)
```

## Implementation Notes

- Erase can't really evaluate its arguments until its run (and prior steps have run).
  - All of the arguments must be hashable/serializable.