---
status: "Draft"
---
# Query Language

## Syntax


Refer to a specific task:

`//path:task_name`

Refer to a specific tasks properties:

`//path:task_name:property_name`

Recursive path pattern matching:

`//**/path:*`

Refer to arbitrary task's properties:

`//**:*:property_name`


Refer to specific variants

`//**:task_name?`

`variant_of(task, variants, ...)`

## Predicates


`task("path:name")`: a single task.

`tasks_in(path, name)`: tasks matching name/path patterns. produces a list of tasks as outputs.

`stale(input)`: tasks that are stale (tasks that need to be run to produce fresh outputs). input is one or more tasks.

`by_label(input, include, exclude)`: include/set are sets of strings with tasks to filter/include/exclude to output. input is one or more tasks.

`property_of(input, property_name, subproperty_index_offset_or_key...)`: Access a specific property or item within the property. input is one or more tasks.

## Operators

`|`: pipe to next filter/predicate

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

