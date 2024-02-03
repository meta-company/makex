
# Named outputs


```{note}
Coming soon. Not implemented yet. 

This feature is up for discussion.
```

The outputs of Targets can be named.
This may be used to refer to specific outputs of a Target from within the target, or from another Target.

The output() function is used to both define and refer to named outputs within a target.

The outputs(target_name, target_path, output_id) reference function may be used to refer to the outputs of another target.
Note: An implicit dependency will be added to the defined target to the referenced target.

For example:

```python

target(
  name="hello",
  runs=[
      write("hello.txt", "hello")
  ]
  outputs=[
      output("file", "hello.txt"),
  ]
)

target(
  name="world",
  runs=[
      write("world.txt", "world")
  ]
  outputs=[
      output("file", "world.txt")
  ]
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
      copy(Target("hello").outputs.get("file"))
      copy(Target("world").outputs.get("file"))
      
      # or (*outputs* of):
      copy(outputs("hello", name="file")) # or set, {"file"}
      copy(outputs("world", name="file")) # or set, {"file"}
  ]
)

```

## Named Inputs

```{note}
Coming soon. Not implemented yet. 

This feature is up for discussion.
```

Named inputs are provided as a convenience to using variables to reduce input name duplication.

The function input(name, ...) can be used to define and refer to named inputs.

```python

target(
    name="example",
    inputs=[
        input("name", "hello-world.txt")
    ],
    runs=[
        copy(input("name"))
    ]
)
```