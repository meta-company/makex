# Variants

```{note} The implementation of this is not yet completed. 
```

```{note} 

Evaluation of variants may slow down evaluation of the path command as we need to traverse up to the Workspace (WORKSPACE) or filesystem root (`/`) to evaluate all Makex files in parent directories.

This may not be concern anymore.

```

Variants are instrumented by a type of variable feature.

Variants can be defined and used in a Makex file like any other variable:

```python

NAME = variant(
    name="platform",
    choices=["windows", "linux", "mac"], # limit to specific choice
    default=Platform.os_type,
    
    # alias the values for output
    alias={
    "windows": "win",
    }
)

if NAME == "linux":
    print("We're running linux")


```

Variants specified on the command line set the variants for top-level Makex files.

If a variant is not found in the Makex file, all the Makex files in parent folders, up to the root(`/`) or Workspace(WORKSPACE) will be evaluated and searched for the variant. 

In other words, variants in child Makex files inherit those of all the parents.

If it is still not found after this search, an error is raised.

All the current variants of Makex file all the way to the Makex file of the root task are in a variable VARIANTS.

Variants can be specified on the command line or tasks.

```shell

makex run path/to/task?optimization=best
```


Example of python variant, controllable in a number of ways

```python


# allow tweaking of data before we define a variant
if Platform.os_name == "linux":
    DATA = {}
elif Platform.os_name == "windows":
    DATA = {}
else:
    error("unsupported platform")
    DATA = {}

PYTHON_ENV = E.get("PYTHON_VERSION",None) # version number in environment variable

variant(
    name="python-version",
    #default=f"{E.PYTHON}", # environment variable must be set or
    # use the system to detect variants
    default=execute("python", "import sys; v=sys.version_info(); print(f\"{v.major}.{v.minor}\")"),
    choices=["system", "3.6", "3.9"],
    choices={
        "system": {},
        "3.6": {},
        "3.9": {},
        "4.0": {},
    },
    data={
        # merge in data
        **DATA,
        # default was variable was evaluated/used, use default stuff
        # merge in the default data + matching choice data
        # all values should/must be strings (or stringlike).
        variant.default: {
            "binary": shell("whereis python")
        },
        "3.6": {
            "binary": "/usr/bin/python3.9",
            
        },
        "3.9": {
            "binary": "/usr/bin/python3.6"
        },
        "4.0": {
            # depend on file in workspace (if any tasks produce them, build them first)
            #"binary": Path("//path/to/cpython/4.0/bin/python"),
            # build the specified task to make binary (build them before running any tasks depending on the variant)
            "binary": Task("cpython", "//path/to/cpython/4.0").output["binary"],
        }
    }
)


if variant("python-version") == "3.9":
    print("python 3.9")

print(f"Python {variant('python-version').choices}")

print(f"Python {variant('python-version').data.binary}")

PYTHON = variant('python-version').get("binary")
PYTHON = variant_data("python-version", "binary")

task(
    # task varies on the python version
    #varies=["python"],
    # task varies on the python version
    variants=["python-version"],
    steps=[
        execute(PYTHON, "-V")
    ]
)

```

# UndeterminedVariantData(variant_name, data_name)

If a variant doesn't have a default and isn't specified (e.g. when analyzing), the data will return
`UndeterminedVariantData(variant_name, data_name)`.

Undetermined data shall be iterable, returning a UndeterminedVariantDataList(variant_name, data_name). Iterating over/appending
variant data in the top level of a Makex file should still work properly:

```python

variant(
    name="example-variant",
    choices={
        "v1": ["-v1"],
        "v2": ["-v2"],
    }
)

ARGS = variant["example-arguments"]["v1"]
ARGS += ["-example-argument"]

task(
    name="example-task",
    steps=[
        execute("executable", ARGS)
    ]
)
```

If the `example-variant` choice is not specified, `ARGS` shall be an UndeterminedVariantList with one value (`-example-argument`).
The execute function should error because of this undetermined value.

Upon execution of tasks, actions like `execute()` should respond early when one of their arguments is undetermined.


## branching/conditions based on variants (if_variant, if_not_variant)

`if_variant(variant_specifier, *values)` can be used to vary the arguments to a task. 
If the variant is in effect, the values are included in argument values; otherwise they are ignored.

`if_not_variant()` is available which is the opposite of `if_variant`: if the variant is NOT in effect, the values are included
in argument values.

Variant specifier may be a string, or a set of strings (`variant_specifier = str|set[str]`).

For example:

```python

task(
  name="example",
  requires=[
    if_variant(variant_specifier, ":example-requirement")
  ],
  steps=[
    if_variant(variant_specifier, execute(...))
  ],
  outputs=[
  
  ]
)
```

TODO: or `if_true(variant_enabled(), ...)`


##  branching entire tasks based on variants

If you would like to enable/disable entire tasks based on the specified variant(s), the variants argument to tasks may be used to do so:

For example:

```python

task(
    name="example",
    variants={"win32","macos"}
)
```

The example task will only run for win32/macos variants.


## Using a specific variant of a task from another

```python

task(
    name="example",
    requires=[
        variant_of(":dep", "variant1")
    ],
    steps=[
        # long hand task reference
        copy(reference(":dep", "variant")),
        copy(variant_of(":dep", "variant")),
        
        # rewire StringValue to retain binary operations
        copy(vary(":dep", "variant" & "variant")),
        
        # copy both of the variants
        copy(vary(":dep", AND("win32", "darwin"))),
        
        # copy one of the variants; depending on which one is active during running the task
        copy(vary(":dep", OR("win32", "darwin"))),
        
        # ???
        copy(vary(":dep", ONE_OF("win32", "darwin"))),
        
        # use a shorthand task reference
        copy(task[:"dep":"variant"]),
        
        # shorthand string based references
        copy(":dep:variant"),
        copy(":dep:variant1 & variant2"),
        
    ]
)


task(
    name="dep",
    steps=[
        # ... produce some output ...
    ]
)
```
