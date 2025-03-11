---
status: "Draft"
---
# Query Language




## Functional Syntax

The syntax may be expressed entirely functionally:

```
first(tasks_in("//projects/*/..."), "build")
```

Functional syntax may be detected automatically with a regular expression.


- `task(task_reference) -> Task`: a single task. TODO: returned as a list so it can be merged and iterated with other functions?

- `tasks(path_expression, task_name) -> list[Task]`: tasks matching name/path patterns. produces a list of tasks as outputs. tasks are returned iterative deepening search (IDS), meaning the shallowest tasks first.

- `shallowest(path_expression, task_name) -> Task` returns the first task named task_name. 

- `stale(input:list[Task]) -> list[Task]`: tasks that are stale (tasks that need to be run to produce fresh outputs). input is one or more tasks.
  
   In other words, these are tasks who need to be reproduced because outputs are missing, or because the inputs changed.

- `filter_tagged(input:list[Task], include=set, exclude=set) -> list[Task]`: include/set are sets of strings with tasks to filter/include/exclude to output. input is one or more tasks.
    
  include/exclude are keyword arguments for which labels to use in the sets of tasks to filter. a name in `include` means the task with the label name should be included
  the output. a name in `exclude` means a task with the label name should be excluded from output.
  
  TODO: what to do with untagged?

- `property(input:list[Task], property_name, subproperty_index_offset_or_key...) -> Any`: Access a specific property or item within the property. input is one or more tasks.

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

### Operators

`|` (or `>`): pipe to next filter/predicate/function as a first argument.

TODO: `>` may be preferred to avoid breaking shells.

`all_of`: combine predicates and return matches from both. (and)
`one_of`: combine predicates and return matches from either/first match. (or)
`not`: exclude specific matches.
`equals`: equals
`not_equal`: not_equal
`in`: within a set
`not_in`: not within a set
`or`: logical or
`and`: logical and

### Examples

Tasks under `//path` that are stale:

```
stale(shallowest(tasks("//path"), "build"))

# or:

tasks("//path") > shallowest("build") > stale()
```

Tasks under `//path1` or `//path2`:

```
all_of(tasks("//path1"), tasks("//path2"))

tasks("//path1") and tasks("//path2") > ...

tasks("//path1") and tasks("//path2") > {
  ...
  # handle tasks here, create more pipes:
}

```

Access specific property:

```
tasks("//path") > property("requires") 
```

Tasks matching property predicate:

```
tasks("//path") > filter(property("requires") "=="  "value"  ) 
tasks("//path") > filter(property("requires") "in"  ["value"]) 
tasks("//path") > filter(property("requires") "!="  "value"  )
```

## Natural Syntax

Refer to a specific task:

`task_name://path`

Refer to a specific tasks properties:

`task_name://path:property_name`

or:

`task_name.property_name://path`

TODO: `task_name` may be a regular expression?

Recursive path/task pattern matching:

`*://projects/**`

Refer to specific variants

`variant_of(task, variants, ...)`

The first argument is a path or group of paths to operate within:

```shell

"//path1 | ..." 

"(//path1/... //path1/...) | ..."
```

Or it is one or more task expressions:

```shell

"task://path1/... "

"task1://path1/... task2://path2/... | "
```

The remaining arguments are filters, separated with a pipe.
