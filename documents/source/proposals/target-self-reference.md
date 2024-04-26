# Proposal: Target Self References

Provide a keyword to refer to property values and attributes of a target.

For example:

```python

target(
    name="example",
    requires=[
        join(self.name, ".c"),
    ],
    steps=[
        execute("clang", "-o", self.name, self.inputs),
    ]
)
```


## Considerations

- `target`:
  - overloaded

- `self`:
  - may confuse existing python users. 

## Implementation Details

The values from self properties can't be immediately serialized to strings.
We need to use a join() function and/or late evaluation.