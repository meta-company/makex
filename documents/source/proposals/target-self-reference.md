# Proposal: Target Self References

Provide a keyword to refer to property values and attributes of a target.

For example:

```python

target(
    name="example",
    requires=[
        join(self.name, ".c"),
    ],
    runs=[
        execute("clang", "-o", self.name, self.inputs),
    ]
)
```


## Considerations

- `target`:
- `self`:
  - may confuse users. 

## Implementation Details

The values from self properties can't be serialized to strings. We need to use a join() function and/or late evaluation.