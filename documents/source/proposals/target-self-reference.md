---
status: "Draft"
---
# Proposal: Task Self References

Provide a keyword to refer to property values and attributes of a task.


## Rationale

- `task_path(task_name)` is often used within a task to get its path; this is long/error-prone/redundant.
- a task name is often used as part of its input/output (e.g. `*.c -> *.o`)


## Specification

- Keyword should allow referring to properties of a task
- References to properties must all be late bound (after processing/argument transform (after phase 1)) 
- References shall be embeddedable in strings (within a task definition)

(TODO: should we have a nameless task_path? (may introduce error))


For example:

```python

task(
    name="example",
    # list of inputs
    inputs=[
        join(self.name, ".c"),
    ],
    # named inputs
    inputs={
        "source": join(self().name, ".c"),
    },
    steps=[
        execute("clang", "-o", self.path / self.name, self.inputs),
        
        # refer to a named input
        execute("clang", "-o", self.path / self.name, self.inputs.source),

        # using self to bind/access properties
        execute("clang", "-o", self("path") / self("name"), self("inputs").source),
    ]
)
```


## Considerations

- `task_self`
  - this might be the preferred canonical name

- `target`/`task()`/`task` (without specifying a name) 
  - overloaded
  - might cause confusion as to which task we want self from

- `self()`:
  - may confuse existing python users. 
  - may confuse legit use of self keyword within makex files (e.g. defining a class)
  - can be automatically transformed from `self` to `self()` (as long as we are in a task() function call body)

- `self` by itself (without a parenthesis)
  - This requires some "wierd" transformations to the AST to transform `self.property` calls to `SelfPropertyReference(name, location)`.

- We need a second resolution pass to resolve/enrich the self reference to an actual task object wherever it is used.

- We want to retain the location of the property reference where it is used
  - e.g. transforming `self.property_name` to `task_self("property_name", location=FileLocation(..))`

- Properties like self('path') must return a TaskPath object (with no task name), or a specialized type (SelfTaskPath).

## Implementation Details

- The values from self properties can't be immediately serialized to strings.
  - We need to use a join() function and/or late evaluation when a particular joined string is encountered (LateJoinedString?)

