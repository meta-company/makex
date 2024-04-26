# Macros

```{note}
This is a new feature under discussion and subject to change. 
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