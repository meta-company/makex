

# Task parameters

It has been found that we'd like to parameterize tasks in some way.

This document/proposal explores some ways to accomplish that.

## Specification


### Declaration/use

```python

VERSION = parameter(name="version", type="string")

task(
    name="task_name",
    outputs={
        "file": f"somefile-{VERSION}.txt"
    },
    steps=[
        write(self.outputs.file, f"{VERSION}")
    ]
)
```

Parameters should declared outside of a task and reused.

TODO: An arbirary string parameter may be used inside of the task by name only?


### Calling a parameterized task on the command line

A seperate command is allocated to call tasks.

```shell

makex call //path/to/task:task_name parameter1=value parameter2=value
```

TODO: multiple.

### Calling/referencing a parameterized task (as a part of another task)

```python
SOME_TASK = call(":task_name", parameter1="", parameter2="", ...)

task(
    name="example",
    requires=[
        "task_name:"
    ],
    steps=[
        # do something with SOME_TASK, or its outputs
        # SOME_TASK.outputs.file
    ]
)
```

### Interactive parameters

If a task is run, and parameters are not provided, Makex may request the values interactively.
