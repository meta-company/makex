# Simple Task Selector

We want to be able to select tasks, e.g. recursively.

We also want to be able to use this on the command line.

This is a different, more natural, syntax than querying (TODO: should we proceed?)

```
# select all the build-project tasks in the projects folder
# build-project tasks are always top level in this example:
build-project://projects/...


# select the first task named build in the projects folder
# the first is also the topmost
//projects/... | first(build) 

```
