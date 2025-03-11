---
status: Accepted
version: "20250301"
---
(reverse-locators)=
# Reverse locators

To create a more consistent and simple syntax this proposal recommends switching task locators to `task_name:path` syntax (as opposed to `path:task_name`).

For example, `//path/to/project:build` shall change to `build://path/to/project`

This is a major breaking change requiring a fix or temporary opt-out.

This change shall improve the way tasks are referenced both inside and outside Makex files.

## History

Makex task locator syntax is an artifact of a Google inspired pattern for their build tools (Blaze, and Bazel). Google originally chose the syntax to work with their Perforce monorepo [^1].

The original syntax allowed users to specify a folder first, followed by a task (or target) name.

Makex originally adopted this syntax to stay compatible with build tooling developed at MetaCompany.

## Rationale

- Paths are optional, task names are not. This order reflects that.

- Functions in makex have a generalized signature of `f(task_name, path=None)`, where path is optional. This change makes the order consistent.

- Users had to prefix all folder local task names with a colon `:` character. This prefixing was determined to be unnecessary and redundant. The extra colon character made simple names in the task name list confusing in regards to their original definition name.

## Prerequisites

- Path or files in the requirements list must be moved to the task inputs argument.

  See the [related proposal](disallow-files-in-requires.md).

## Implications

- Command line
  - Easier to refer to names in the current folder without `:` markers.
  - Default tasks in a folder are less easy to reference (which we really don't use)
  - More difficult to autocomplete tasks in a folder
    - `://path/to/makexfile` can be used to complete these names, the cursor should be before the colon.
      - we need to handle shell completion by clearing the argument once a name is completed
  
- Task requires list
  - The colon marker was used as an indicator that the requirement is a task (not a file).
    - We can simply use names in this list without a colon.
  - We must disallow files in the requirement list (and have a fix/plan for it).

- Task references
  - Task references use `(task_name, path)` as standard argument form, making this change logical.

## Temporary opt-out

A shall provide a per-file opt-out with a function called in the file, so we can move new users immediately. A file may be marked as opted out by adding the following statement to the top of a makex file.

```python
makex(syntax="2024")
```

Requirements lists in a file with this marker will be parsed as they were before this change (`:task_name`, or `path:task_name`).

## Requirements

- A flag shall be provided during a transition period to enable old locators
  - Non-compliance should be changed quickly.

## Evolution/Fix tool

A tool shall be provided to fix every existing makex file, fixing all requires lists and references. This tool shall be accessible with the makex fix command. The fix shall be named `version_2025`.

The fix tool shall:
- Move any paths/globs/finds for each task to the inputs argument
- Reverse any locators for each task's requirements list.

[^1]: [Your Roots are Showing](https://www.rocketpoweredjetpants.com/2023/05/your-roots-are-showing/)
