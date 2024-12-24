# Macros

```{note}
This is a new/experimental feature and subject to change.

The intent of this feature is to explore ideas in build systems. 

This feature may be disabled or removed.
```

Macros allow defining functions that create tasks or return values.

For example, in a Makex File:

```python
@macro
def make_task(name):
    task(
        name=f"{name}-task"
    )

make_task(name="example")
```

Macros must be called with keyword arguments.