# Proposal: Overlay/Named Workspaces (DRAFT)

```{note}
Coming soon. Not implemented yet. These feature is up for discussion.
```

A Workspace may be named or overlayed on top of another Workspace (or all Workspaces).

The names of these Workspaces may be defined in a Workspace file.
TODO: Should they be in a Workspace file?

TODO: Should we handle cloning/checkout/sync?


```python

# no name, no path. this is the current Workspace
workspace(
  
)

# define a Workspace at path/to/target named "workspace-name"
workspace(
  name="workspace-name",
  path="path/to/target",
)

```

The names are embedded into the current Workspace under its root path. The syntax for selected named Workspaces and targets inside is always:

```
//subpath:{target-name}
```


Additionally, named/external Workspaces may be defined in makex configuration files. This can only be done if the configuration
file also defines a `makex.workspace` setting.

Parent Workspaces do not inherit the names of their children.

For example, if path/to/target had a Workspace file:

```python
workspace(
  name="library",
  path="library"
)
```

And in `path/to/target/library/Build` another Workspace was defined:

```python
workspace(
  name="library",
  path="library"
)
```

Executing `//path/to/target/library:build` from the root Workspace should do the right thing (build a library).

Executing `//library:build` from `path/to/target` should select the right thing too (build a library).

Child Workspaces should not reach into their parents. Calling `//..` is not allowed. This may be enforced.

TODO: We may support a `map to all` setting per Workspace where an externally defined Workspace is mapped to all Workspaces.


## Referring to named targets


```

# named
//{workspace-name}/path/to/target

# if any path overrides an externally defined workspace with {workspace-name} in the current root, use that instead
# eg we have //vendor and then an external ws is named vendor, we'd use ours
# if an external was called //vendor/somepackage, then we'd use that whenever //vendor/somepackage was referenced
//{workspace-name}/path/to/target
```