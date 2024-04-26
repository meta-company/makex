# Proposal: Iterable Run list

A feature is proposed which callables passed to the target runs argument can be a generator function.

Pros:

- Allows structuring runs list into a function that can branch on conditions (e.g variant/platform).

Cons:

- Hides what will run in shell until we parse and evaluated the iterator.

```python


def iterator(target):
    for input in target.inputs:
        yield shell()

target(
    name="render-articles",
    requires=[
        glob(""),
    ],
    steps=iterator,
)
```