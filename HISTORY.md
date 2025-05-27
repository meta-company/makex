# History

This document lists major releases and changes for the Makex project.

Versions are identified by the pattern `YYYYMMSS` (A date with sequence number; year (`YYYY`), month (`MM`), sequence (`SS`)).

## 20250501

- Allow joined strings in output file paths.
- Allow joining paths with joined strings.
- Improve task requirements error reporting.
- Handle slices in self references (e.g. `self.outputs["example"]` and `self.inputs["example"]`). This syntax is NOT preferred.
- Allow joined strings in executable names.


## 20250301

- **BREAKING CHANGE**: Task Locator pattern reversal!
  - For example, `//path:task_name` it is now `task_name://path`, or `:task_name` is now `task_name`.
  - See the [documentation](breaking/20250301.md) about this breaking change and tools to automatically fix.
  - Old Makex files MUST be fixed ASAP.
- **BREAKING CHANGE**: Path/Files in the task requirements are not allowed!
  - Files/paths must be specified in the `task.inputs` list or mapping.
  - See the [documentation](breaking/20250301.md) about this breaking change and tools to automatically fix.
  - Old Makex files MUST be fixed ASAP.
- The `copy` function now overwrites files and folders.
- Fix an issue with copy on write not being detected.
- Improve recursive folder copying performance significantly.
- Improve parsing speed significantly.
- Improve path resolution.
- Improve documentation.
- Add experimental `task_outputs(name, path=None).output_name` function/expression.
- Add `makex fix` command.


## 20250101

- Add experimental support for Task self references. See the documentation/proposal.
- Add experimental support for named inputs/outputs. See the documentation/proposal.
- Add experimental support for optional requirements. See the documentation/proposal.
- Add experimental support for using Paths in Globs as a pattern.
- Enable temporary argument to control maximum CPUs used by makex (`--cpus`).
- Remove Environment variables support and documentation for upcoming improvements to variables.
- Add a new way to set environment variables for a task: the environment argument.
- Deprecate the `Path()` constructor, replacing with `path()`.

## 20241201

- Allow executing the outputs of another task.
- Add support for running `makex run :task` anywhere within a descendant directory.
- Add `erase()` action to erase files from task outputs.
- Allow using globs and expressions for the copy action.
- Allow using the copy action to copy the outputs of one task to the outputs of another using simple task locators.

## 20240701

- Improve `copy()` with `glob()` and `find()` functions.
- Fix makex return/exit code on error.
- Fix error handling of `include(required=False)`.

## 20240602

- Add support for building makex with pyoxidizer (`makex run :pyoxidizer`).

## 20240601

- Fix/improve `copy()` action.
- Improve source() function. Accept `Path` objects in arguments.
- Add `Path.with_suffix()` function.
- Make assorted minor improvements.
- Fix `path` command output.
- Remove dependency on progressbar.
- Fix environment variable getter.
- Add experimental `archive()` action.

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

- Improve copy arguments. See `copy()` function documentation.
- Disable import statement.
- Make file marker optional.
- Detect/warn/error on assignment of variables to common functions/keywords(target(), path(), etc). 
  - e.g. `target=True` should not be possible.
- Unify the exception hierarchy.
- Rename Runnable to Action.
- Skip None values in path and argument lists.
- Add flag to enable Target.path argument.

## 20240103

- Initial public release.

## ... (2024-01-12)

- Project conceived.
