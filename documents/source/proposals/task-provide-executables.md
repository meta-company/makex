# Provide Executables

Provide a way for tasks to provide executables to dependant tasks.

The proposal allows for tasks to export executables that other tasks can use.

## Rationale

Executing the outputs of a task is longwinded:

```python
task(
    steps=[
        execute("compiler://path/to/compiler-project", ...)
    ]
)
```


## Example

```python
task(
    name="tool",
    executables={'example-executable': 'bin/example-executable'},
    steps=[
        # steps to produce example-executable in the tasks output
    ]
    ...
)

task(
    name="example",
    requires=["tool"],
    steps=[
        execute("example-executable", ...)
    ]
)
```

## Pros

- Makes unnecessary the path hard coding from execute actions.

## Cons

- Makes the path to each execute action and executable visually/statically implicit.
- Requires users to know this pattern.
  - The connection is hidden.

## TODO

- Explore alternate syntax (or prefix) so that users are aware this is a imported executable.
  - e.g. `execute("!example-executable")`
  - `"!example-executable"`
  - `"~example-executable"`
  - `"//example-executable"`
  - This may help the extraneous colon `:` when refererring to local tasks providing executables.

- This [may] conflict with executable tasks (or tasks providing a single executable output).
  - Revisit/deprecate that proposal?

- Instead of a separate key (`executables`), use a function to mark the output (`executable` or `mark`)
