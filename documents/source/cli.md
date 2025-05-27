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

(makex-fix)=
```{eval-rst}
.. autoprogram:: makex.__main__:parser()
   :prog: makex
   :start_command: fix
   
```


:::{note}
The fix tool requires [LibCST](https://libcst.readthedocs.io/en/latest/), which, is not packaged with Makex.

LibCST must be installed, so it is available for Python and Makex to import (in a `site-packages` folder).

To install the approriate LibCST, run `pip install makex[fix]`.
:::


:::{note}
Some parts of the file may not be fully fixed after running this command.

Users should verify the fixed Makexfile is correct and functional.
:::

:::{note}
Comments may not be preserved after fixing a file, especially those _within_ a Task definition.
:::

:::{warning}
Before running the fix command, make sure you've backed up your Makex files.

The `--edit` flag will edit files in place potentially destroying them.
:::

To fix all files in a folder or workspace, use fix command along with the system `find` command. For example:

```shell

# replace with the fix name
FIX_NAME=""

EDIT=""

# Uncomment this line to make edits in place
#EDIT="--edit"

find -iname Makexfile -exec makex fix $(EDIT) $(FIX_NAME) {} ";" .
```

