(tasks-as-executables)=
# Tasks as Executables (Example)

Say, for example, you need to build a compiler or code generator to build another part of your source code.

We shall use two separate Makex files to demonstrate this pattern.

The first Makex file defines a compiler tool and how to build it (`//tools/Makexfile`):

```python
task(
    name="compiler",
    steps=[
        # steps to build compiler
        ...  
    ],
    outputs="compiler-binary"
)
```

The second Makex file uses the compiler tool as part of its build process (`//project1/Makexfile`):

```python
task(
    name="build",
    steps=[
        execute("compiler://tools", "input-file", self.path / "output-file")
    ]
)
```

Running `makex run build://project1` will run the `compiler` Task (in `//tools`) producing an executable named `compiler-binary`.

The `compiler-binary` will be used in the `build://project1` Task to translate an input file to an output file.

Since `compiler-binary` is the only output of `compiler://tools` Task, it shall be unambiguously used as the executable. 

```{note}
In a future implementation of Makex, a Task may produce multiple [named] outputs, and one of outputs may be selected as executable 
(in the cases of large compiler toolkits, such as clang).

We're also exploring a concept we're calling `first-class executables`.

At the moment, if you need to work with such multiple-output Task patterns, you must create separate Task using a dependency on the build Task, and the built-in lightweight makex copy mechanism to create individual Tasks for each executable.
```
