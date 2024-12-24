---
status: "Accepted"
version: "20240401"
---
# Proposal: Makex File Macro/Functions

## Rationale

- Common target/action patterns should be sharable.
- Increase terseness.
- Increase reusability. Reduce copy/paste.

## Syntax


```python


@action()
def example_action():
    return [
        shell(),
        execute(),
        ...
    ]


@macro()
def example_macro(name:str, argument1:Path):
    target(
        name=f"example-{name}",
        requires=[
            argument1
        ],
        steps=[
            example_action()
        ],
    )

example_macro(
    name="test",
    argument1=source("path/to/file")
)


```

## Implementation Details

### Traceability

Since macros generate targets we need to trace the caller location using a stack.

In the example above, if there is an error in the target, we need to print the stack up to example_macro.
Calling example_macro should add a name/location to the stack which we store with TargetObjects.