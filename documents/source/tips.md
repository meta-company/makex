# Tips


## Break out long command lines into scripts or wrappers

If you frequently use an executable in your source that requires a long set of arguments, instead of repeating
them in Makex files, make a unifying wrapper script/executable that will accept a shortened version of the arguments (e.g. those that are required). 

For example, you have Makex files littered through your workspace:

```python

task(
    name="build",
    steps=[
        execute("some-executable", "long", "set", "of", "arguments", ..., "input-file"),
        # ... possibly more execute steps that can be merged into a unified script.
    ]
)
```


Make an executable script (`some-executable-wrapper`): 

```shell
#!/bin/sh

$input_file=$1

some-executable long set of arguments $input_file

# ... add more executable steps as necessary.
```

And change your Makex file:

```python

task(
    name="build",
    steps=[
        execute("some-executable-wrapper", "input-file"),
    ]
)
```

A folder containing these executable tools or scripts is recommended.
