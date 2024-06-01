

# Example

A contrived example of a makex file:

```python


CUSTOM_BUILD_PATH = path("build")

task(
    name="build",
    path=None or CUSTOM_BUILD_PATH,
    require=[
        # Request a task called build in another file or directory.
        Task("build", file_or_directory),
        
        
        # A local task.
        ":local",
        
        # A task somewhere else, in directory called folder.
        "path/to/folder:build",
        
        # Require a file.
        file_path,
    ],
    steps=[
        # echo test > $CUSTOM_BUILD_PATH/test
        execute("echo", "test").with_environment({}).write_to(CUSTOM_BUILD_PATH / "test"),
         
        f"echo f > {CUSTOM_BUILD_PATH}/test",
        
        # Call another task explicitly. 
        # This will automatically append a requirement to the task, but it will not run it until we reach here
        Task("other", file_or_directory),
    ],
    
    outputs=[
        file_path,
        CUSTOM_BUILD_PATH / "test"
    ]
)

task(
    name="test",
    require=[
        ":build"
    ]
    run = [
        execute("test.sh")
        
    ]
)

```

## Complex multi-platform build

```{note}
This isn't yet fully implemented.
``` 

```python

makex(shell="/bin/bash")

variant(
    name="version",
    default="latest",
    alias="v"
)

variant(
    name="platform", 
    choices=["windows", "linux", "mac"], # limit to specific choice
    default=Platform.os_type,
    
    # alias the values for output
    alias={
        "windows": "win",
    }
)

variant(
    name="optimization",
    choices=["good", "better", "best"], # limit to specific choice
    default="best",
    # only mac/linux support optimization
    enable=Platform.os_type.one_of("linux","mac"),
    
    # alias the values for output
    alias={
        "good": "o1",
        "better": "o2",
        "best": "o3",
    }
)

# exported variable?
VARIABLE = variant(
    id="VARIABLE",
    value=""
)

# transformed to:
# VARIABLE = variable(id="VARIABLE", value="output-file", default="default")
VARIABLE = "output-file"


# create a local build path; separate for each platform X optimization
BUILD = path(variants=["platform","optimization"])

# default task. all things are built.
task(requires=[task("*")])

# each task is given a separate build path
task(
    id="",
    path="",
    
    # constrain to variants
    only=[],
    variants=[Variant("optimization").one_of("linux")],
    
    requires=[
        Task("task", file_or_directory, variants=Variant("optimization")),
        file_or_directory,
    ],
    steps=[
        # echo test > BUILD
        execute("echo", "test", output=BUILD/variable),
        copy(task.outputs),
        
        build_path(task("task")),
        
        # mangle the {BUILD} variable to $$$$$$BUILD$$$$$$$ and replace when we actually run 
        f"echo f > {BUILD}/{VARIABLE} ",
        
        
        # not needed:call("task", file_or_directory),
    ],
    
    outputs=[
        file_or_directory,
        BUILD / VARIABLE
    ]
)

# Build an archive
task(
    id="archive",
    requires=[
        glob(""),
        
        
        find("test/tst", name=regexp(), type="fsd"),
    ],
    steps=[
        # make a standard source folder name-version which we will archive
        #folder(BUILD/"folder/project-{VERSION}"),
        
        copy(glob("*"), BUILD/"folder/project-{VERSION}", exclude=[".git"]),
        # or cp -r * {BUILD}/folder/project-{VERSION}/
        
        archive(BUILD/"folder", BUILD/"file.zip", type="zip")
        # or zip -C {BUILD}/folder/project-{VERSION}
    ]
)

```
