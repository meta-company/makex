# Proposal: Iterable Run list

A feature is proposed which callables passed to runs can be a generator function.

Pros:

- Allows structuring runs list into a function that can branch on conditions.

Cons:

- Hides what will run in shell until execution stages.

```python


def iterator(target):
    for input in target.inputs:
        yield shell()

target(
    name="render-articles",
    requires=[
        glob(""),
    ],
    runs=iterator,
)
```