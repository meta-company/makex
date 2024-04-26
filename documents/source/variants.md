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

Variants specified on the command line set the variants for top level Makex files.

If a variant is not found in the Makex file, all the Makex files in parent folders, up to the root(`/`) or Workspace(WORKSPACE)
will be evaluated and searched for the variant. 

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

task(

    # pex varies on the python variant
    #varies=["python"],
    # pex varies on the python variants
    variants=["python-version"],
    steps=[
        execute(PYTHON, "-V")
        ]
)

```


