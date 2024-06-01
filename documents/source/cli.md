# Command Line Interface

```{eval-rst}
.. autoprogram:: makex.__main__:parser()
   :prog: makex
   :maxdepth: 1
   :strip_usage:
```

```{note}
At the moment, the global flags must be specified AFTER the [sub]command.
```

```{note}
Makex installs a copy of itself with the alias `mx`.
```

## Commands

Makex has several commands.

```{eval-rst}
.. autoprogram:: makex.__main__:parser()
   :prog: makex
   :start_command: run
   
```

```{eval-rst}
.. autoprogram:: makex.__main__:parser()
   :prog: makex
   :start_command: tasks
   
```

```{eval-rst}
.. autoprogram:: makex.__main__:parser()
   :prog: makex
   :start_command: path
   
```

```{eval-rst}
.. autoprogram:: makex.__main__:parser()
   :prog: makex
   :start_command: workspace
   
```


```{eval-rst}
.. autoprogram:: makex.__main__:parser()
   :prog: makex
   :start_command: completions
   
```