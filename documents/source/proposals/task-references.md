---
status: Draft
---

# Explicit Task References

This proposal describes a feature in makex to support arbitrarily referring to tasks (or their parameters, such as their outputs).


## Rationale

Referring to tasks in makex is currently done in shorthand, with strings.
We want to add a _standard_ way to explicitly refer to tasks within the file or outside of it.

## Specification

```python

# Task callable/function alternate (only with positional arguments).
# task with keyword arguments is a declaration, task with positional arguments is a call/reference
# Pro: clear/short/terse
# Pro: reuses the task keyword
# Con: reuses the task keyword. Hard to explain/document.
task("name", "path")


# Using task as a container:
# Pro: clear/short/terse
# Pro: reuses the task keyword
# Pro: allows separating path/name naturally, using the colon separator marker
# Con: reuses the task keyword
# Con: requires ast transformation (slower)

## OK: Using task as a type of container
task["path":"name"]

## BAD: lots of character junk to remember 
task["path":"name"].outputs("output_name")

## Better: less junk.
task["path":"name"].outputs.output_name

# OK: Using a reference in other functions
task_outputs(task["path":"name"], "output_name", ...)

# BETTER: Similar to task_path
task_outputs("task_name","task_path").output_name

# Explicit reference function:
# Pro: no ast transformations required (faster)
# Pro: allows multiple calling conventions
# Pro: allows separating the path/name as strings, enabling construction without string formatting
# Con: verbose
# Con: allows multiple calling conventions

## OK: Using an explicit reference function with a single locator parameter
reference("{path}:{name}")

## OK: Using an explicit reference function with a separated locator parameter
reference("name", "path")

## BAD: packing too much into the function
reference("{path}:{name}", "outputs", "output_name")

## OK: accessing the outputs of a reference. 
## BAD: chains may be less readable, especially with long references
reference(...).outputs("output_name")

# OK: Using a reference in other functions
task_outputs(reference(...), "output_name", ...)

```
