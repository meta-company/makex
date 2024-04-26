
## 20240401

- Sorry for the renames. Naming things is hard.
- Rename all `Target` to `Task`.
  - `Task` is clearer for users not coming from a make background.
- Deprecate `target()` function name. Now named `task(steps=[])` or `Task(steps=[])`.
- Deprecate `path()` function name. Now named `task_path()`.
- Add `actions=` argument to `target()`, replacing `runs=`.
- Add experimental support for macros (`@macro` decorator).
- Add experimental support for including files (`include()` function).
- Add initial support for named outputs.


## 20240204

- Improve copy arguments. See copy() function documentation.
- Disable import statement.
- Make file marker optional.
- Detect/warn/error on assignment of variables to common functions/keywords(target(), path(), etc). 
  - e.g. `target=True` should not be possible.
- Unify the exception hierarchy.
- Rename Runnable to Action.
- Skip None values in path and argument lists.
- Add flag to enable Target.path argument.
