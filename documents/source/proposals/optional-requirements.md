---
status: "Accepted"
version: "20250501"
---

# Proposal: Optional Task Requirements

Tasks may have optional requirements in the form of files or other tasks.

These task/file requirements may not be defined purposely (e.g. because we don't need them), or because they haven't been defined/produced yet.

## Example

Building several components, some of which may not have a makex file.

```python

COMPONENTS = [
    "component1",
    "component2",
]

task(
    name="build",
    requires=[
        [optional(f"components/{component_name}:build") for component_name in COMPONENTS],
    ],
    steps=[
        ...
    ],
)
```

## Proposed Names

- `optional`

- `optional_task`
  - Con: Too long

- `task(name, optional=True)`
  - This reference syntax hasn't been formalized yet. 


## Considerations

- The current implementation only handles optional task references. Optional files are not yet specified here (and they may not be required).
