# makex

<!-- heading -->

Makex is a new and simplified build and automation tool.

It __*makex*__ stuff happen. 🙂

<!-- heading:end -->

<!-- features -->

## What Makex is used for

- Compiling software/applications/firmware
- Building file systems/trees/images/file archives
- Building and deploying websites and web applications
- Running things repeatably
- Replacing most or all of the other build systems

## Features 🍩

- Task based
- Familiar Syntax
- File Hashing and Checksums
- Dependency Graphs
- Caching
- Workspaces
- Copy on Write

<!-- features:end -->

<!-- links -->
## Links 🔗

- [Documentation](https://meta.company/go/makex)
- [Installation Instructions](https://documents.meta.company/makex/latest/install)
- [Troubleshooting](https://documents.meta.company/makex/latest/trouble)
- Support: [Google Groups](http://groups.google.com/group/makex) or [makex@googlegroups.com](mailto://makex@googlegroups.com)

<!-- links:end -->

<!-- quick-start -->

## Requirements

- Python >= 3.9

## Quick Start

1. Install:

  ```shell
  pip install makex
  ```

2. Define a Makex file and name it `Makexfile` ( or `makexfile` if you prefer):

  ```python 
  task(
      name="hello-world",
      steps=[
          write("hello-world.txt", "Hello World!"),
  
          # or, you can use the shell, but it is not recommended:
          # shell(f"echo 'Hello World!' > {self.path}/hello-world.txt"),
          
          # you may also execute things:
          # execute("echo", "Hello World!"),
          
          # or just print things:
          # print("Hello World!"),
          
          # more actions can go here; such as copying, mirroring or archiving...
      ],
      outputs=[
          "hello-world.txt",
      ],
  )
  ```

3. Run makex, specifying the task name:

  ```shell
  makex run :hello-world
  ```

4. A file at `$PWD/_output_/hello-world/hello-world.txt` shall have the following contents:

  ```
  Hello World!
  ```

Read the [documentation](https://meta.company/go/makex) to learn more.

## Limitations

- Mac support is not tested.
- Windows is not tested or supported (yet).


## Pronunciation 🗣

Makex is pronounced "makes", ˈmeɪks, ˈmeɪkˈɛks (or just "make" 🙂)

## Related

- [Make](https://en.wikipedia.org/wiki/Make_(software))

## Coming Soon

- Dynamic Task/Resource Allocation
- Task Tags/Labels
- Regular Expressions
- Intellij/VSCode integration

```{note}
This is an early release of Makex. Things may change. Those changes will be noted in the HISTORY file (especially major ones).

With that, Makex is being used extensively by us. We've created many tasks and Makex files, and we don't want to create more work. 🫡

If you have any problems, feel free to contact us. 
```
