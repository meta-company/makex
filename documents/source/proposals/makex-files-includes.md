# Proposal: Makex File Includes

Common macros/functions to generate targets are desired.

Common targets may be desired.

Instead of duplicating these, we propose an include function in makex files 
to include the contents of another makex file.

```python

# mark an optional include. will be ignored if not found.
# used for includes in private workspaces.
include("//path/to/file.makex", optional=True)


# search for file.mx if it is not found in the current directory.
# XXX: should we allow search for relative paths?
# XXX: what of searching with absolute paths?
include("file.mx", search=True)
```

## Applications

- SDKS, Virtual environments and such.
- Building a set of modules/components uniformly.
- Creating a commons for deployment/build patterns.

## Cons

- Target locations may be obscured. This will affect user interface. Errors may be shown from the wrong place.
  - We'd need to unroll the stack for more makex files.
- Includes processing will slow down evaluation.

## Considerations

- We may want to expose a better api for user constructed targets/functions/macros.
  - eg. `export_macro()`, `export_target_type()`
  - Include might not be the right name for this; `load()` might be better.
- Recursive includes are probably unnecessary (or not recommended). We may limit this stack artificially.
- Include must not create cycles.
- Include should allow searching in the parents/upwards of the directory (explicitly).
  - search for Included file should not cross workspace boundaries (unless specified).
- Targets created in included files must be copied and the pointer to the Makex File transformed to the file including.
  - path() and other functions will not be resolved logically so simple copies probably won't work nicely. best to just include/exec the ast again.
    - otherwise, path() will resolve relative to the included file (we don't want that)