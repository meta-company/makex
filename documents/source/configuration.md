# Configuration

## File

The Makex configuration file allows one to override some aspects of makex. 
A configuration file is not required for basic use of Makex.

The configuration file itself may be located in a number of places:

- In the current working directory or its parents (as `makex.toml` or `.makex.toml`).
- The user's configuration directory (`~/.config/makex.toml`).
- The global/system configuration directory (`/etc/makex.toml`)

These locations are checked in order, and the configuration is merged with the same precedence.
For example, this means that a `make.toml` in the current working directory overrides any values in the users or global.

## Sections

### makex

toml configuration files are specified with sections. `makex` is the primary section to configure makex.

```{eval-rst}


.. todo:: this doesn't work for some reason: 
.. _posix_sh: https://pubs.opengroup.org/onlinepubs/009695399/utilities/xcu_chap02.html

.. data:: makex
   :canonical: toml.makex
   
   The root section.
    
    .. attribute:: shell
       :type: Optional[string]
       :canonical: TOML.makex.shell
       :no-index:
       
       .. warning::
         
         Changing this value may make your Makex files incompatible with others. It's best to not touch this unless you know what you are doing.
         This option may be removed in the future.
         
       The shell that should be used when running the shell() action and anything else using a shell.
       
       Set to a string/path of the shell you want to use (e.g. `/bin/sh`).
       
       Leave empty to automatically detect from the running shell (or use the system shell).
       
       It's recommended to use the most simple shell possible (and one that is compatible with the expand() function).
       The Shell Command Language of `/bin/sh` as defined in the `Posix Standard <https://pubs.opengroup.org/onlinepubs/009695399/utilities/xcu_chap02.html>`_ is typically recommended and detected.
       
       Default is null to autodetect.

    .. attribute: makex-files  

    .. todo:: we have an issue with a dash above. type reference fails to be emitted.

    .. attribute:: makex_files
       :type: Optional[list[string]]
       :canonical: TOML.makex.makex_files
       
       A list of file names that should be checked for makex files automatically.
       
       Default is `["Makexfile","makexfile"]`.
       
       .. "Build"
       
    .. attribute: workspace
       :type: string
       :canonical: TOML.makex.workspace
      
       A path to a Workspace. Paths are relative to the file. Dot (```"."```) can be used to mark the directory of the configuration file as the Workspace.
       
       See :doc:`the Workspaces documentation <workspaces>` for more information.
       
    .. attribute: ignore
       :type: Optional[list[string]]
       
       A list of names, globs or regular expressions of files/folders that should be execluded from all Makex operations.
       
       These exclusions will apply to all globs/finds and inputs.
       
       The prefixes `re:` and `glob:` are used to denote regular expressions and globs. 
      
       Makex will always ignore it's default output directory (`_output_`).   
       
       .. note:: 
       
         Makex is configured to ignore common files/folders usually not used as inputs/outputs.
         
         The list of these things include common cache/test folders (e.g. `.venv`, `__pycache__`, `.pytest_cache`),
         repository folders (e.g. `.hg` or `.git`), files typically not included in outputs (`*.pyc`) and any
         task output folders (named `_output_`).
       
            

```

## Environment Variables

Environment variables override some aspects of makex.

```{eval-rst}

.. envvar:: WORKSPACE

   The current Workspace. See :doc:`the Workspaces documentation <workspaces>` for more information.
```


```{eval-rst}

.. envvar:: PATH

   On POSIX/Unix/Linux, this is used to resolve the paths of executables.
```