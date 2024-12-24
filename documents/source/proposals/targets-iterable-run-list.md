---
status: "Accepted"
---
# Proposal: Action Functions, Iterable Run list

A feature is proposed which callables passed to the target runs argument can be a generator function.

Pros:

- Allows structuring steps into a function that can branch on conditions (e.g variant/platform).

Cons:

- Hides what will run in shell until we parse and evaluated the iterator.


## Example


```python

@action
def iterator(task):
    for input in task.inputs:
        yield shell()

target(
    name="render-articles",
    requires=[
        glob(""),
    ],
    steps=iterator,
)
```

## Action functions

The function shall take a [mostly] [Evaluated] Task object as the first argument. 
The function shall have access to the task's inputs/outputs and other properties in a natural/programmatic manner.

The function shall yield individual built-in Actions in order. 


## Considerations

- Functions that produce actions must/should be marked/decorated as such. 
  - We need a way to know when to pass the task as an argument. 
  - A new `@action` decorator is proposed. The generic @macro decorator will certainly cause confusion and readability problems later.