---
status: "Draft"
---
# Query Language

## Syntax

TODO: these are probably a bad idea because we'll complicate the task url logic.

Refer to a specific task:

`//path:task_name`

Refer to a specific tasks properties:

`//path:task_name:property_name`

Recursive path pattern matching:

`//**/path:*`

Refer to arbitrary task's properties:

`//**:*:property_name`

Refer to specific variants

`//**:task_name?variant1,variant2`

`variant_of(task, variants, ...)`

## Functional Syntax

- `task("path:name") -> Task`: a single task. TODO: returned as a list so it can be merged and iterated with other functions?

- `tasks_in(path, name) -> list[Task]`: tasks matching name/path patterns. produces a list of tasks as outputs.

- `stale(input) -> list[Task]`: tasks that are stale (tasks that need to be run to produce fresh outputs). input is one or more tasks.
  
   In other words, these are tasks who need to be reproduced because outputs are missing, or because the inputs changed.

- `by_label(input, include=set, exclude=set) -> list[Task]`: include/set are sets of strings with tasks to filter/include/exclude to output. input is one or more tasks.
    
  include/exclude are keyword arguments for which labels to use in the sets of tasks to filter. a name in `include` means the task with the label name should be included
  the output. a name in `exclude` means a task with the label name should be excluded from output.

- `task_property(input, property_name, subproperty_index_offset_or_key...) -> Any`: Access a specific property or item within the property. input is one or more tasks.

  property_name  is one of:

  - `name`
  - `requires` a list/set of any task dependencies of a task.
  - `inputs`: a list of files the task uses. any files inputs from requires are merged into the inputs mapping as unnamed inputs. inputs can always be iterated over.
    - unnamed inputs can be accessed by number
    - named inputs can be accesses by name (a string)
  - `outputs` (can't be determined until tasks are run because find/globs.)
  - `steps` (TODO: do we need access to this?)

- `external_requires(inputs) > list[Task]`: tasks that access folders outside their hierarchy. Used to find dependencies external to a specific folder/path. (TODO: better name)

- `glob(pattern) -> GlobPattern`: a glob. used for matching names/files.

- `re(pattern) -> Pattern`: a regular expression. used for matching names/files.

## Operators

`|`: pipe to next filter/predicate/function as a first argument.

`all_of`: combine predicates and return matches from both. (and)
`one_of`: combine predicates and return matches from either/first match. (or)
`not`: exclude specific matches.

## Examples

Tasks under `//path` that are stale:

```
stale(tasks_in("//path"))
```

Tasks under `//path1` or `//path2`:

```
all_of(tasks_in("//path1"), tasks_in("//path1"))
```
