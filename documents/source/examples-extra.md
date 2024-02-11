

## Example

A contrived example of a makex file:

```python


CUSTOM_BUILD_PATH = path("build")

target(
    name="build",
    path=None or CUSTOM_BUILD_PATH,
    require=[
        # Request a target called build in another file or directory.
        Target("build", file_or_directory),
        
        
        # A local target.
        ":local",
        
        # A target somewhere else, in directory called folder.
        "path/to/folder:build",
        
        # Require a file.
        file_path,
    ],
    runs=[
        # echo test > $CUSTOM_BUILD_PATH/test
        execute("echo", "test").with_environment({}).write_to(CUSTOM_BUILD_PATH / "test"),
         
        f"echo f > {CUSTOM_BUILD_PATH}/test",
        
        # Call another target explicitly. 
        # This will automatically append a requirement to the target, but it will not run it until we reach here
        Target("other", file_or_directory),
    ],
    
    outputs=[
        file_path,
        CUSTOM_BUILD_PATH / "test"
    ]
)

target(
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

# default target. all things are built.
target(requires=[target("*")])

# each target is given a separate build path
target(
    id="",
    path="",
    
    # constrain to variants
    only=[],
    variants=[Variant("optimization").one_of("linux")],
    
    requires=[
        Target("target", file_or_directory, variants=Variant("optimization")),
        file_or_directory,
    ],
    runs=[
        # echo test > BUILD
        execute("echo", "test", output=BUILD/variable),
        copy(target.outputs),
        
        build_path(target("target")),
        
        # mangle the {BUILD} variable to $$$$$$BUILD$$$$$$$ and replace when we actually run 
        f"echo f > {BUILD}/{VARIABLE} ",
        
        
        # not needed:call("target", file_or_directory),
    ],
    
    outputs=[
        file_or_directory,
        BUILD / VARIABLE
    ]
)

# Build an archive
target(
    id="archive",
    requires=[
        glob(""),
        
        
        find("test/tst", name=regexp(), type="fsd"),
    ],
    runs=[
        # make a standard source folder name-version which we will archive
        #folder(BUILD/"folder/project-{VERSION}"),
        
        copy(glob("*"), BUILD/"folder/project-{VERSION}", exclude=[".git"]),
        # or cp -r * {BUILD}/folder/project-{VERSION}/
        
        archive(BUILD/"folder", BUILD/"file.zip", type="zip")
        # or zip -C {BUILD}/folder/project-{VERSION}
    ]
)

```
