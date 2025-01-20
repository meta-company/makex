# Task Locators

Tasks are referred to using a Task Locator (or "Locator").

A Task Locator is a name and optional path concatenated together:

```
{path}:{name}
```

The path may be:

- relative (`{path}`)
- absolute to the filesystem. starting with one (1) slash. (`/{path}`).
- absolute to the current workspace. starting with two (2) slashes. (`//{path}`).

The path may not contain any parts with current/parent folder operators (`.` or `..`). 

The name must start with an `[a-zA-Z]` and may use `[a-zA-Z0-9_\-]` after that.


