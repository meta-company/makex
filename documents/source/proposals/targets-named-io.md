---
status: "Draft"
---

# Proposal: Named Inputs and Outputs

Sometimes, Tasks may provide multiple named outputs (e.g. `.css` and `.css.map` files when compiling sass/css).

Some tasks may be written and understood more clearly if the input files have names/alias.

DONE: we may need an explicit inputs keyword argument to task to clear things up.
TODO: Retrieving inputs/outputs without a name specified should either [] or all inputs/outputs.
TODO: Do we need separate namespaces for outputs/inputs files? (probably yes)
TODO: Does referring to another task create an implicit dependency? (probably yes, configurable). 

## Function for referring to named/anonymous inputs/outputs

```python

# Target().outputs 
# (harder for the ast. can't get location of outputs reference)
# remote target
Task("hello", "path/to/target").outputs.get("file")

# this should work because it's local:
Task("hello").outputs.get("file")

# get all outputs or nameless outputs
Task("hello").outputs

# getitem slicing
# short:
task[path:name].outputs

# Explicit function handling both inputs/ouputs
Task(name, path, outputs=None, inputs=None) # refers to target output path, or specific output

# simple and explicit
# outputs() function
outputs(task[name:path], *names:str|set[str])
outputs("path:task", *names:str|set) # path:target shorthand
outputs(":task", *names:str|set) # local target shorthand
outputs("task", "path", *names:str|set) # explicit target/path; this syntax won't work with the others.
outputs_of(task)

# returning a object we can refer to named outputs/inputs
outputs("//path:task").name
inputs("//path:task").name

# inputs() function (same as outputs)
inputs(task_reference, *names)

# unified namespace
# cons: which files, outputs or inputs?
files(task_reference, *names)


# implicitly
# anytime a target reference is passed into inputs or actions, refer to its outputs
# executes that receive a dictionary shall flatten the values out as arguments.


# strings
# pros: no new keywords
# cons: limits the names of tasks with dots
"//path/to:task.outputs.name"
"//path/to:task.outputs[0]"

# sans dots (preferred)
"//path/to:task:outputs.name"
"//path/to:task:outputs[0]"

# namespaced (too many colons)
"outputs://path/to:task:name"
"outputs://path/to:task:name"
```


## Named outputs

```{note}
Coming soon. Not implemented yet. 

This feature is up for discussion.
```

The outputs of Tasks can be named.
This may be used to refer to specific outputs of a Task from within the Task, or from another Task.

The output() function is used to both define and refer to named outputs within a target.

The outputs(target_reference, *output_id) reference function may be used to refer to the outputs of another target in a requirements list.
Note: An implicit dependency will be added to the defined target to the referenced target.

For example:

```python

task(
  name="hello",
  steps=[
      write(output("file"), "hello"),
  ],
  outputs=[
      output("file", "hello.txt", ...),
      # or:
      file("file", "hello.txt", ...),
      # or:
      named("file", "hello.txt", ...),
      # or
  ],
)

task(
  name="world",
  steps=[
      write(output("file"), "world"),
  ],
  outputs=[
      output("file", "world.txt", ...),
      # or:
      file("file", "world.txt", ...),
      # or:
      named("file", "hello.txt", ...),
  ],
)

# this will require us to parse path/to/target/Makexfile before we can continue: 
#hello_out = Target("hello", "path/to/target").outputs.get("file")

# this should work because it's local:
#hello_out = Target("hello").outputs.get("file") 

# either way, we shouldn't be able to call Target() outside a target definition
# or, we should be able to use/define them anywhere; error should be on accessing a property before evaluation
# Target References would need to be "enriched" before use
# ok: Target("hello")
# error: Target("hello").outputs 
# error: f"{outputs('hello', id='file')}"
# error: [for output in outputs('hello', id='file')]

task(
  name="hello-world",
  steps=[
      # copies hello.txt and world.txt into the target output
      copy(Task("hello").outputs.get("file")),
      copy(Task("world").outputs.get("file")),
      
      # or (*outputs* of):
      copy(outputs("hello", name="file")), # or name:set = {"file"}
      copy(outputs("world", name="file")), # or name:set = {"file"}
      
      # implicit all outputs or singular
      copy(Task("hello"))
  ]
)

```

### Using the outputs of a target as named inputs

```python
  task(
    requires=[
        # input from the outputs of target
        named("source", outputs("target", name="")),
        input("source", outputs("")),
    ],
    steps=[
        # later ... to copy those outputs
    ]
  )
  ```

## Named Inputs

```{note}
Coming soon. Not implemented yet. 

This feature is up for discussion.
```

Named inputs are provided as a convenience to using variables to reduce input name duplication.

The function input/inputs(name, ...) can be used to define and refer to named inputs.

```python

task(
    name="example",
    inputs = {
        "": [],
        "name": "hello-world.txt",
        # referring to the inputs/outputs of another target:
        "external": task[path:name].outputs['name'],
        
        # implicitly, all outputs or singular
        "external": task[path:name],
    },
    requires=[
        # all bad ideas:
        input("name", "hello-world.txt", ...),
        # or:
        file("name", "hello-world.txt", ...),
        # or:
        self.inputs["name"],
        # or:
        target.inputs["name"],
        # or:
        requirement("name", target)
    ],
    steps=[
        copy(input("name")),
        copy(target.requires["name"]),
        copy(target.inputs["name"]),
        copy(self.requires["name"]),
        copy(self.inputs["name"]),
        copy(requirement("name")),
        copy(input[name:path]),
    ]
)
```

## Function for naming inputs/outputs

Deprecated: we can use dictionaries.

The following function names are being explored:

```

# explicit input output
# con: more things to remember
# pro: explicit
input("file", "hello.txt", ...)
output("file", "hello.txt", ...)

# generic output
# con: not plural
# con: not clear if input/output.
file("file", "hello.txt", ...)

# generic output
# pro: plural
# con: named, what?
named("file", "hello.txt", ...)
```
