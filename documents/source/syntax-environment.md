# Environment Variables

Environment variables can be accessed using the `Environment` object (or `E` for short).

Any use of environment variables in a Makex file is recorded. 
If any environment variable changes, 
the tasks in that makex file become stale.

A default value of an empty string `""` may be provided.

```python

SOME_VARIABLE = Environment.get("SOME_VARIABLE", "")

# or (the same thing):
SOME_VARIABLE = E.get("SOME_VARIABLE", "")

...
```
