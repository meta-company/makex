---
status: "Draft"
---
# Proposal: First class executables

- Executables may be in source tree, built from a task or available on the system.

- We want to allow mapping keywords to declared argument parameters.
  - execute() function may have reserved keyword arguments (like `environment=`)

- We should allow simple forms of argument validation.
  - Arguments are evaluated/validated during target evaluation/transform (phase 2)

- Referenced using the typical task locator syntax (e.g. `//path:task_name`)


## Syntax

In a Makex File in the root of the workspace, define an executable that can be referenced by name (`//:example`):

```python
executable(
  name="example", 
      
  # reference a system binary
  source="clang",
    
  source="/usr/bin/clang",
    
    
  # reference a file in the workspace
  source="//path/to/clang",    
  
  # reference a specific task+output
  source=":task_name:output_name",
  
  # or  
  source="//path:task_name:output_name",
         
  # or 
  source=task("task_name", "//path").outputs[output_name],
    
  arguments=[
    # define any basic argument metadata/validations
    Positional(),
    Keyword("boolean", "argument_bool", "--keyword"),
    ...
    # any default arguments can be placed in order here as string literals
  ],
    
  # function that takes the arguments passed in whole and validates them
  # raise ArgumentError if any of them are wrong, with the wrong value attached to the error
  validator=lambda x: bool,
    
  # function that evaluates/composed arguments to the executable with the given arguments
  evaluator=lamda x: bool,
    
  defaults=names(),
    
  argument_mapping={
   "name": "--argument ${value}"
  }
)

# or class

class example(executable):
    source = ""
    
    def validator(self):
        pass
    def evaluator(self):
        pass
```

To use this in another task:

```python


task(
    name="test",
    steps=[
        execute("//:example", argument_bool=True, argument_string="test", argument_list=["1","2","3"], argument_int=1),
        
        # or 
        execute("//:example",
                arguments=names(
                    argument_bool=True, 
                    argument_string="test",
                    argument_list=["1","2","3"],
                    argument_int=1
                )
        ),
    ]
)
```

## Questions


- should we automatically chmod +x?


## Implementation Notes

