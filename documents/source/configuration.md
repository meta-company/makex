# Configuration

## File

The Makex configuration file allows one to override some aspects of Makex. 
A configuration file is not required to use Makex.

The configuration file itself may be located in several places:

<!-- In the current working directory or its parents (as `makex.toml` or `.makex.toml`). -->
- The user's configuration directory (`~/.config/makex/makex.toml`).
- The global/system configuration directory (`/etc/makex/makex.toml`)

These locations are checked in order, and the configuration is merged with the same precedence.
<!--For example, this means that a `make.toml` in the current working directory overrides any values in the users or global.-->

TOML configuration files are specified with sections.

An example configuration

```toml
[makex]
shell="/bin/sh"
makex_files=["Makexfile", "makexfile"]
```

## Settings

:::{confval} makex

`makex` is the primary section to configure Makex.
:::

:::{confval} makex.shell
:type: Optional[string]
:default: automatic 


The shell that should be used when running the shell() action and anything else using a shell.

Set to a string/path of the shell you want to use (e.g. `/bin/sh`).

Leave empty to automatically detect from the running shell (or use the system shell).

It's recommended to use the most simple shell possible (and one that is compatible with the expand() function).
The Shell Command Language of `/bin/sh` as defined in the [Posix Standard](https://pubs.opengroup.org/onlinepubs/009695399/utilities/xcu_chap02.html) is typically recommended and detected.

Default is null to autodetect.

:::{warning}
Changing this value may make your Makex files incompatible with others. It's best to not touch this unless you know what you are doing.

This option may be removed in the future.
:::

:::

:::{confval} makex.makex_files
:type: Optional[list[string]]
:default: ["Makexfile", "makexfile"]

A list of file names that should be checked for makex files automatically.

:::

## Environment Variables

Environment variables override some aspects of Makex.

```{eval-rst}

.. envvar:: WORKSPACE

   The path of the current Workspace. See :doc:`the Workspaces documentation <workspaces>` for more information.
```


```{eval-rst}

.. envvar:: PATH

   On POSIX/Unix/Linux, this is used to resolve the paths of executables.
```
