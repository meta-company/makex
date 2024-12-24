(tasks-as-executables)=
# Tasks as Executables

Say, for example, you need to build a compiler/code generator to build another part of your source code.

We shall use two separate makex files to demonstrate this pattern.

The first makex file defines a compiler tool and how to build it (`//tools/makexfile`):

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

The second makex file uses the compiler tool as part of its build process (`//project1/makexfile`):

```python
task(
    name="build",
    steps=[
        execute("//tools:compiler", "input-file", self.path / "output-file")
    ]
)
```

Running `mx //project1:build` will run the `//tools:compiler` task producing an executable named `compiler-binary`.

The `compiler-binary` will be used in the `//project1:build` Task to translate an input file to an output file.

Since `compiler-binary` is the only output of `//tools:compiler` task, it shall be unambiguously used as the binary. 

```{note}
In a future implementation of makex, a task may produce multiple [named] outputs, and one of outputs may be selected as executable 
(in the cases of large compiler toolkits, such as clang).

We're also exploring a concept we're calling `first-class executables`.

At the moment, if you need to work with such multiple-output task patterns, you must create separate tasks using a dependency on the build task, and the built-in lightweight makex copy mechanism to create individual tasks for each executable.
```
