---
status: Accepted
version: "20250301"
---

(disallow-files-in-requires)=
# Limit files in the requirements list

This proposal recommends a change to makex disallowing files in the task requirements list.

Having files in the task requirements list was a convenience as users didn't need to enter the task inputs arguments (which was also nonexistent in early Makex versions).

With this proposal, Makex shall restrict the requirements lists to Tasks names/references only.

This change shall absolutely disable using Strings to refer to files in the task requirements list.

This proposal is closely tied with the [Locator Syntax Change Proposal](reverse-locators.md).

## Rationale

This change paves the way for a more logical (reversed) task locator syntax (name first, then path).

Keeping inputs in the inputs list makes logic simple, and reduces potential for duplication (with self references).

Keeping string files out of the requirements list allows us to parse the requirements list as if it were names only; simplifying logic in makex.

## Mitigation

To temporarily opt out of this change. add the following statement to the top of the makex file:

```python
makex(syntax="2024")
```

## Partial opt out

We may still permit explicit file producing functions/references in the requirements list using functions such as
`glob`,`find`, `source` and `path` (anything returning one or Path objects) as a form of optional shorthand.

Such references may be enabled by argument, configuration, or flag (`--files-in-requirements=true`,
`makex.files_in_requirements`, or `MAKEX_FILES_IN_REQUIREMENTS=1` respectively), but shall be disabled by default.

This setting may be removed at any time if we decide it is not worth the branching or maintenance.

## Evolution/Fix tool

A tool shall be provided to fix every existing makex file, fixing all requires lists and references. This tool shall be accessible with the makex fix command. The fix shall be named `version_2025`.

The fix tool shall:

- Move any paths/globs/finds for each task to the inputs argument
- Reverse any locators for each task's requirements list.

[^1]: [Your Roots are Showing](https://www.rocketpoweredjetpants.com/2023/05/your-roots-are-showing/)
