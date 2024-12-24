---
status: "Draft"
---
# Better Macro Syntax

Currently, we have a `@macro` decorator to define/export a macro, and the file defining the macro must be `include()`-ed to use the macro.

The dependency on the `include` function is an issue, as we may want to disable/remove the include function. `include` is a goofy construct, likely prone to error or confusion.

As an improvement to referring or calling macros, we may want to use a twist on our task query/selection syntax (`//path:macro_name`).

For example, calling a `macro()` function defined in a file called `macros.mx` in the root of the Workspace:

```python

call(`//macros.mx:macro`, **kwargs)

```

Obviously, macros must not conflict with possible task names. This is unlikely if the macros are defined in a separate file, but may happen if a macro is used in the same file as it is defined.

This doesn't really change performance much. As an optimization we may delay the `call` evaluation until later.

Like `include()`, we may want to allow a direct reference to a makex file in the first argument to `call()` so:

- we don't need to create redundant directories to contain makex files containing commonly used macros.
- we can create separate files for separate macros

