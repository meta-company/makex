# makex

<!-- heading -->

Makex is a new and simplified build and automation tool.

It __*makex*__ stuff happen. 🙂

<!-- features -->


## What Makex is used for

- Compiling software/applications/firmware
- Building file systems/trees/file archives
- Building and deploying websites and web applications
- Running things in a repeatable manner
- Replacing most or all of the other build systems

## Features 🍩

- Task based
- Familiar Syntax
- File Hashing and Checksums
- Dependency Graphs
- Caching
- Workspaces
- Copy on Write

<!-- links -->

## Links 🔗

- [Documentation](https://meta.company/go/makex)
- [Installation Instructions](https://documents.meta.company/makex/latest/install)
- [Troubleshooting](https://documents.meta.company/makex/latest/trouble)
- Support: [Google Groups](http://groups.google.com/group/makex) or [makex@googlegroups.com](mailto://makex@googlegroups.com)

<!-- quick-start -->


## Quick Start

1. Install:

  ```shell
  pip install makex
  ```

2. Define a Makex file (name it `Makexfile`):

  ```python 
  task(
      name="hello-world",
      steps=[
          write("hello-world.txt", "Hello World!"),
  
          # or, you can use the shell, but it's not recommended:
          # shell(f"echo 'Hello World!' > {task_path('hello-world')}/hello-world.txt"),
      ],
      outputs=[
          "hello-world.txt",
      ],
  )
  ```

3. Run makex and the target:

  ```shell
  makex run :hello-world
  ```

4. A file at `_output_/hello-world/hello-world.txt` shall have the following contents:

  ```
  Hello World!
  ```

## Limitations

- Mac support is not tested.
- Windows is not tested or supported (yet).

```{note}
This is an early release of Makex. Things may change. If you have any problems, feel free to contact us. 
```

## Pronunciation 🗣

Makex is pronounced "makes", ˈmeɪks, ˈmeɪkˈɛks (or just "make" 🙂)

## Related

[Make](https://en.wikipedia.org/wiki/Make_(software))

## Coming Soon

- Task Self References
- Custom Action Functions/Macros
- Tags/Labels
- Regular Expressions
- Named Inputs/Outputs
- Intellij/VSCode integration