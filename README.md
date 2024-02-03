# makex

<!-- heading -->

Makex is a new and simplified automation tool, similar to the original [Make](https://en.wikipedia.org/wiki/Make_(software)).

It __*makex*__ stuff happen. 🙂

<!-- features -->

## Features

- Familiar Syntax
- File Hashing and Checksums
- Dependency Graphs
- Caching
- Workspaces

<!-- links -->

## Links

- [Documentation](https://meta.company/go/makex)
- [Installation Instructions](https://meta.company/go/makex/install)
- [Troubleshooting](https://meta.company/go/makex/trouble)
- Support: [Google Groups](http://groups.google.com/group/makex) or [makex+subscribe@googlegroups.com](mailto://makex+subscribe@googlegroups.com)

<!-- quick-start -->


## Quick Start

- Install:

  ```shell
  pip install makex
  ```

- Define a Makex file (name it `Makexfile`):

  ```python
  #!makex
  
  target(
      name="hello-world",
      runs=[
          write("hello-world.txt", "Hello World!"),
  
          # or, you can use the shell, but it's not recommended:
          # shell(f"echo 'Hello World!' > {path('hello-world')}/hello-world.txt"),
      ],
      outputs=[
          "hello-world.txt",
      ],
  )
  ```

- Run makex and the target:

  ```shell
  makex run :hello-world
  ```
 
- A file at `_output_/hello-world/hello-world.txt` will have the following contents:

  ```
  Hello World!
  ```


## Limitations

- Mac support is not tested.
- Windows is not tested or supported (yet).

```{note}
This is an early release of Makex. Things may change. If you have any problems, feel free to contact us. 
```

## Pronunciation

Makex is pronounced "makes", ˈmeɪks, ˈmeɪkˈɛks (or just "make" 🙂).

