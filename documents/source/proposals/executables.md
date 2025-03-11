---
status: "Draft"
---
# Proposal: First class executables

- Executables may be in source tree, built from a Task or available on the system.

- Referenced using the typical task locator syntax (e.g. `//path:executable_name` or `:executable_name`)

- NONFEATURE: We may want to allow mapping keywords to declared argument parameters.
  - execute() function may have reserved keyword arguments (like `environment=`)

- NONFEATURE: We may want to allow simple forms of argument validation.
  - Arguments are evaluated/validated during target evaluation/transform (phase 2)

## Syntax

In a Makex File in the root of the workspace, define an executable that can be referenced by name (`example://`):

```python
executable(
  name="example", 
      
  # reference a system binary:
  source="clang",
    
  # reference to a file on the system:
  source="/usr/bin/clang",
    
  # reference a file in the workspace:
  source="//path/to/clang",    
  
  # the first (or only) output of a task:
  source="task_name://path",
    
  source="task_name",
  
  # reference a specific task+output:
  source="task_name.outputs.output_name",
  
  # or the outputs of a task, shorthand:
  source="task_name.outputs.output_name://path",
         
  # or the outputs of a task using an explicit reference:
  source=refer("task_name", "//path").outputs.output_name,
)
```

A list of source may be provided to the source argument, to pick the first available.

To use this in another task (within the same makex file):

```python
task(
    name="test",
    steps=[
        execute("example:"),
        
        # or 
        execute(refer("example")),
    ]
)
```

Note: The executable must include a colon (`:`) to indicate the executable is a local task. 


## Static/extra arguments

These arguments will be provided to the executable each time it is invoked before all other arguments.

Variables may be used in arguments to vary them.

```python
executable(
    name="example",
    arguments=[ # TODO: or `positional=`
        "--global",
        # define a slot where all other arguments will go.
        arguments_slot(),
        "--local",
        # any default arguments can be placed in order here as string literals
    ],
)
```

## Mapping arguments from the execute action to the executable

TODO: this complicates the execute signature; potentially causing conflicts between user defined and non-user defined arguments.

```python
executable(
    name="example",
    source="/bin/something",
    arguments={ # TODO: or `mapping=`
        "name": ("--argument", slot()),
        "test": ("--argument", slot()), 
    },
    # define default values for arguments:
    defaults={
        "test": "WORLD"
    }
)

# later...

task(
    name="example-task",
    steps=[
        execute(":example", name="HELLO")
    ]    
)
```

A default argument may be provided by wrapping the value in a tuple

The execute action will render to `/bin/something --argument HELLO --argument WORLD`.

## Defining custom argument validators (High complexity)

```python
executable(
    # function that takes the arguments passed in whole and validates them
    # raise ArgumentError if any of them are wrong, with the wrong value attached to the error
    validator=lambda x: bool,
    # function that evaluates/composed arguments to the executable with the given arguments
    evaluator=lambda x: bool,
)

# alternately, a class syntax:

class example(executable):
    source = ""

    def validator(self):
        pass

    def evaluator(self):
        pass
```
TODO: argument processing can really become complex. This may be a nonfeature.

Before an executable is run, a function may be declared which validates its arguments.
An argument list is provided to the function which have a list of strings with methods approriate for argument processing
(e.g. `String.split` to split a string?, `String.lex` to lex a value from a string, e.g. a list?)


## Executables within archives

Storing an archive of executables within a repository or shared/commmon path is a frequent pattern (especially to bootstrap).

The executable declaration may have a method to declare a file from an archive to be used as executable.

For example,

```python
executable(
  name="example",
  source=archive_file("path/to/file/within", "path/to/archive.zip")
)
```

The entire archive will be extracted as is, and the executable will be used in place.

TODO: maybe adopt `!` separator to access file contents.

## Name helpers

```python
arguments = names(
    argument_bool=True,
    argument_string="test",
    argument_list=["1", "2", "3"],
    argument_int=1
)
```

## argument helpers

```python
args = arguments(
    bool="--bool",
    string=argument("--string"),
    list=argument(name="--list", action="repeat", default=["1", "2", "3"]),
    int=1
)

args(bool=True, string="test", list=["4", "5"], int=3)
```

## Questions

- should we automatically chmod +x whatever referenced file (at most once)?

## Implementation Notes
