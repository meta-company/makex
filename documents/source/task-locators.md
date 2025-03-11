# Task Locators

Tasks are referred to using a Task Locator (or "Locator").

A Task Locator is a Task name, and an optional colon `:` and path concatenated together. The syntax is:

```peg
TaskLocator ← TaskName ( ( ":" Path ) / ":"? ) $
TaskName ← [A-Za-z] [0-9A-Za-z_]*
```

Examples of Task locators are below:

```
task_name://path

task_name:path

task_name:

task_name
```

The `path` is a folder containing the [Makex file](makex-files.md) defining the Task.

The `path` may be:

- relative (`path/...`)
- absolute to the filesystem. starting with one (1) slash. (`/path/...`).
- absolute to the current [Workspace](workspaces.md). starting with two (2) slashes. (`//path/...`).

The `path` _may not_ contain any parts with current/parent folder operators (`.` or `..`). 

The Task name (`task_name`) must start with an `[A-Za-z]`.


:::{note}

In a previous version of makex, the syntax of locators was `path:task_name`. 

[This has since been reversed.](breaking/20250301.md)

:::
