# Steps function

See: [the older proposal](targets-iterable-run-list).

We may want to define some complex operations that can't be described with a simple declarative task body.

A function may be provided to the steps argument of the task to provide an algorithmic execution plan.

Unfortunately, Python doesn't have braces and lambdas, so these definitions will become verbose.

The function may yield actions to execute them.

The function is provided a Task object to introspect certain values of the task (replacing `self`).

Variables may be accessed using the variable argument by calling it with the name the of the variable.

```python


def steps(task, variable, **kwargs):
    if platform.architecture in {"x86"}:
        yield execute(...)
    else:
        yield execute(...)


task(
    name="example",
    steps=steps,
)
```
