# Workspaces

Workspaces define the roots or boundaries of projects or a repository.

Workspaces use the special `//` prefix marker in paths to refer to tasks consistently in a workspace without having to use relative paths (e.g the double dot marker (`..`)) or other mechanisms. 

Tasks can not reach out of their Workspace for dependencies (for example, using `//..`). 
For that matter, the double dot path traversal operator is disabled entirely in Makex Paths.

Usage of Workspaces is not required. 
If the Workspace is not defined, the root of the filesystem of the current working directory will be used as the Workspace.

Defining a Workspace is highly recommended.

## Defining a Workspace

Workspaces are defined using the {envvar}`WORKSPACE<WORKSPACE>` environment variable or a `WORKSPACE` file.

Using the environment variable to set a workspace is preferred as it is simpler to switch workspaces. 
If you plan to work on a [mostly] self-contained repository, a WORKSPACE file may be appropriate in the root of the repository. 
It is recommended to export the WORKSPACE environment variable to all shells so that you can use makex and reference tasks from any folder.
<!--
the {data}`workspace<TOML.makex.workspace>` in a Makex configuration file
the {option}`workspace <makex --workspace>` command line argument
-->

## Workspace File

Aside from setting the {envvar}`WORKSPACE<WORKSPACE>` environment variable, one may create a `WORKSPACE` file at the root of a Workspace.
This will let Makex know the directory with the `WORKSPACE` file is the root of the Workspace.

This is simply an empty file (at the moment), though it may be expanded with other functionality. 

A `WORKSPACE` file should be left in the filesystem to mark boundaries between Workspaces.

## The current Workspace

The current Workspace is detected as follows, with the first match being the current Workspace:

<!-- The {option}`--workspace<makex --workspace>` command line argument. -->

<!-- The {data}`makex.workspace<TOML.makex.workspace>` setting in a Makex Configuration File specified with the {option}`--configuration <makex --configuration>` command line argument.-->

- A file named WORKSPACE file detected inside current working directory or one of its parents.
- The {envvar}`WORKSPACE<WORKSPACE>` environment variable.
- The root/anchor of the current working directory.

<!-- - The {data}`makex.workspace<TOML.makex.workspace>` setting in of the global Makex Configuration Files (`~/.config/makex.toml` or `/etc/makex.toml`). -->

<!-- The {data}`makex.workspace<TOML.makex.workspace>` setting in Makex Configuration Files from the current working directory or one of the parents.

## Referring to Tasks in a Workspace

The prefix marker `//` is used to denote a Workspace path.

A Task Locator takes the following form: `path:task_name`. The Path may be omitted to refer to tasks within the same Makex file
or the task may in a Makexfile in a subfolder, or it may be an absolute path.

## Nested Workspaces

A Workspace may be contained within another Workspace.

This may be done by copying or [symbolically] linking the nested Workspace into its parent or container Workspace.  

If a run crosses or enters a new Workspace, the Workspace is automatically detected and provided appropriately to the Tasks.

The detection is made for each makex file inside a Workspace in the following order of precedence:

- A file named WORKSPACE file detected inside makex file's directory or one of its parents.
- The {envvar}`WORKSPACE<WORKSPACE>` environment variable.

<!--
The current Workspace detection algorithm doesn't apply to nested/named Workspaces.

- The {data}`makex.workspace<TOML.makex.workspace>` in a Makex Configuration File specified with the {option}`--configuration <makex --configuration>` command line argument.
- The {option}`--workspace<makex --workspace>` command line argument.
- The {data}`makex.workspace<TOML.makex.workspace>` setting in Makex Configuration Files from one of the parents of the current working directory.
- The {data}`makex.workspace<TOML.makex.workspace>` setting in of the global Makex Configuration Files (`~/.config/makex.toml` or `/etc/makex.toml`) 
- The root/anchor of the "current" directory. The current directory is the path of the task's Makex file. 
-->
