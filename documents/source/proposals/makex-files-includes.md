# Proposal: Makex File Includes

Common functions to generate targets may be desired. Instead of duplicating these, we propose an include function
in makex files to include the contents of another makex file.

```python

include("//path/to/file.makex")


function()
```

//path/to/file.makex:

```python


def function():
    target(
        
    )
```

## Applications

- Common deployment/build patterns
- SDKS, Virtual enviroments and such

## Cons

- Target locations may be obscured. This will affect user interface. Errors may be shown from the wrong place.
  - We'd need to unroll the stack for more makex files.
- Includes processing will slow down evaluation.

## Considerations


- We may want to expose a better api for user constructed targets/functions/macros.
  - eg. `export_macro()`, `export_target_type()`
  - Include might not be the right name for this; `load()` might be better.
- Recursive includes are probably unnecessary.
