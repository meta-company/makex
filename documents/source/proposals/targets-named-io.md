# Proposal: Named Inputs and Outputs

TODO: we may need an explicit inputs keyword argument to target to clear things up.
TODO: Do we need separate namespaces for outputs/inputs files?
TODO: Retrieving inputs/outputs without a name specified should either [] or all inputs/outputs.
TODO: Retreive unnamed inputs/outputs.
TODO: Does referring to another target create an implicit dependency? (probably yes). 




## Function for referring to named inputs/outputs

```python

# Target().outputs 
# (harder for the ast. can't get location of outputs reference)
# remote target
Target("hello", "path/to/target").outputs.get("file")

# this should work because it's local:
Target("hello").outputs.get("file")

# get all outputs or nameless outputs
Target("hello").outputs

# getitem slicing
# short:
target[name:path].outputs

# Explicit function handling both inputs/ouputs
Target(name, path, output=None, input=None) # refers to target output path, or specific output

# simple and explicit
# outputs() function
outputs(target[name:path], *names:str|set[str])
outputs("path:target", *names:str|set) # path:target shorthand
outputs(":target", *names:str|set) # local target shorthand
outputs("target", "path", *names:str|set) # explicit target/path; this syntax won't work with the others.
outputs_of(target)
# inputs() function (same as inputs)
inputs(target_reference, *names)

# unified namespace
# cons: which files, outputs or inputs?
files(target_reference, *names)

```


## Named outputs

```{note}
Coming soon. Not implemented yet. 

This feature is up for discussion.
```

The outputs of Targets can be named.
This may be used to refer to specific outputs of a Target from within the target, or from another Target.

The output() function is used to both define and refer to named outputs within a target.

The outputs(target_reference, *output_id) reference function may be used to refer to the outputs of another target in a requirements list.
Note: An implicit dependency will be added to the defined target to the referenced target.

For example:

```python

target(
  name="hello",
  runs=[
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

target(
  name="world",
  runs=[
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

target(
  name="hello-world",
  runs=[
      # copies hello.txt and world.txt into the target output
      copy(Target("hello").outputs.get("file")),
      copy(Target("world").outputs.get("file")),
      
      # or (*outputs* of):
      copy(outputs("hello", name="file")), # or name:set = {"file"}
      copy(outputs("world", name="file")), # or name:set = {"file"}
  ]
)

```

### Using the outputs of a target as named inputs

```python
  target(
    requires=[
        # input from the outputs of target
        named("source", outputs("target", name="")),
        input("source", outputs("")),
    ],
    runs=[
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

target(
    name="example",
    inputs = {
        "": [],
        "name": "hello-world.txt",
        # referring to the inputs/outputs of another target:
        "external": target[path:name].outputs['name'],
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
    runs=[
        copy(input("name")),
        copy(target.requires["name"]),
        copy(target.inputs["name"]),
        copy(self.requires["name"]),
        copy(self.inputs["name"]),
        copy(requirement("name")),
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
