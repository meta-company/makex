
# Actions

Each task can accept a list of "Actions" that will be run when the task is executed.


## execute()

```{eval-rst}
.. py:function:: execute(*executable:Union[str|PathLike,list[str|PathLike]])
  
  Execute an executable. 
  
  Executables are run from the task's source folder (the input root).
  
  The first value in executable is the executable to run. 
  This may be a relative path (to a source folder), an absolute path, the name of an executable, or the reference/output of another task.
  If it's a name (without any slashes), it will be searched for in the folders defined inside the PATH environment variable.
  
  Followed by the executable is a variable number of arguments passed to the executable. 
  
  List values in any arguments are "flattened".
  
  Any arguments which evaluate to None will not be included when running the executable.
  
  To execute the output of another Task, you must specify the task name and path of the Task (for example, `execute("//path:task_name", ...)`). 
  See {ref}`Tasks as executables<tasks-as-executables>` for more information. 
  
  .. note:: 
  
    Arguments should be quoted and separated as required by the executable.
    Typically, this means passing each argument and value as a separate string.
   
  .. note::
   
    Arguments are passed to the executable as is, with no shell expansion. 
    If you use `~` to denote a home directory, you will need to expand it, or use the :func:`home()<home>` or :func:`shell()<shell>` functions.
  
  .. If you need system specific shell/variable expansion,
     use the expand() function.
   
  .. note::
  
    When the executable is a reference to the output of another task, currently, the first declared unnamed output of the referred Task is used as the executable.
    The referenced Task should be included in executing task's requirements, though it may be automatically added (implicitly, by configuration).
    For more on this, see Executing the Output of a Task from another Task.
```


## copy()

```{eval-rst}
.. py:function:: copy(paths, destination=None, /)
  
  Copy `paths` (files or folders) to the Task's output directory, or the specified directory `destination`.
  `paths` may be a list of paths or a single path.
  
  If `destination` is a relative path, it will be resolved relative to the Task's output path; this may be used to prefix items in the output.
  Any directories specified in `destination` (by using a directory separator) will be created before copying.
  
  .. If inputs is a list, the destination path must be a directory.
  
  If the destination is empty, the specified `paths` will be copied directly into the Task's output path.
  
  If the destination doesn't exist, it will be created.
  
  An Execution error will be raised if the destination exists, and it is not a directory.
  
  :param Union[PathLike,list[PathLike]] paths: Paths to the file(s) or folder(s) to copy. Relative paths are resolved relative to the makex file (or source folder).
  
  :param PathLike destination: The destination. May be a path relative to the task output path, or an absolute path.
```

```{note}
Makex uses file cloning/copy-on-write/reflinks for lightweight copies of files on supporting filesystems (bcachefs, btrfs, XFS, OCFS2, ZFS (unstable), APFS and ReFSv2).   
```

```{todo}
Implement/document renaming.
```

The copy function has 7 valid forms:

```python
# copy a file to the Task output
copy(file)

# copy a folder to the Task output
copy(folder)

# copy folder to the specified Folder (relative to the task output)
copy(folder, folder)

# list forms:

# copy a list of files to the Task output
copy(files)

# copies a set of files to the specified folder (relative to the task output).
copy(files, folder)

# copy a list of folders to the Task output
copy(folders) 

# copies a set of folders to the specified folder (relative to the task output).
copy(folders, folder) 

```

```{todo}
# copy a file to specified file path.
copy(file, file)
```


## environment()


```{eval-rst}
.. py:function:: environment(dictionary, **arguments)
  
  Set the environment of future actions.
  
  You may pass a dictionary and/or keyword arguments. Using keyword arguments is preferred.
  
  All values must be String or String-like values. String-like values include Path objects. Integers will be converted
  to strings.
  
  :param Optional[dict[str,str]] dictionary: A dictionary of names pointing to values for the environment.
  :param str arguments: Names and values to use for the environment.
```


<!--
## mirror()


```{eval-rst}
.. py:function:: mirror(paths, destination=None, /)
  
  Mirrors files to the destination.
  
  If `destination` is a relative path, it will be resolved relative to the Task's output path; this may be used to prefix items in the output.
  Any directories specified in `destination` (by using a directory separator) will be created before copying.
  
  If the destination is empty, the specified `paths` will be mirrored directly into the Task's output path.
  
  If the destination doesn't exist, it will be created.
  
  Files/folder relative to the task will be mirrored in a relative manner. 
  
  .. An Execution error will be raised if the destination exists, and it is not a directory.
  
  :param Union[PathLike,list[PathLike]] paths: Paths to the file(s) or folder(s) to copy. Relative paths are resolved relative to the makex file.
  
  :param PathLike destination: The destination. May be a path relative to the task output path, or an absolute path.
```

```{note}
This action is experimental and subject to change.
```
-->

## print()

```{eval-rst}
.. py:function:: print(message)
  
  Print a message to standard output.
  
  :param String message: The message to print.
```


## shell()


```{eval-rst}
.. py:function:: shell(*script)
  
  Run script in a system shell.
  
  .. warning:: 
  
    You should seriously avoid use of this function. Shells may introduce unexpected behavior in Makex.
    
    For example, the line `shell(f"rm {SOME_VARIABLE}/bin")`) will attempt to remove your `/bin` directory if
    SOME_VARIABLE is defined as an empty string.  
    
    shell() is there if you really need it, and additional mechanisms will be employed in the future to increase safety. Keep your
    scripts simple.
    
    Makex may a adopt a "strict" mode where all shell scripting is disabled.
  
  By default, Makex will use the detected/system shell (usually, `sh`, or the Bourne Shell `bash`). A shell can be specified in configuration, but it's
  recommened to leave it to autodetect based on platform. 
    
  The passed script is prefixed with a preamble by default: 
  
  .. code-block:: shell
  
    set -Eeuo pipefail
  
  :param script: The script/command line to run. If a list of strings, the strings will concatenated with new line separators
    and run in *one* process/shell.
  :type script: Union[String,list[String]]
  
  .. note::
  
    The syntax of the script depends on the system's shell.
    Variables are expanded according the specified shell's rules. 
```


## write()


```{eval-rst}
.. py:function:: write(file:PathLike, data:Union[str,list[str]], executable:bool=False)
  
  Writes `data` to `file`.
  
  Any intermediate folders specified in the file path will be created as necessary.
  
  :param PathLike file: The destination file. May be a Workspace path, an absolute path (if allowed), or relative path within the Task's output path.
  :param Union[str,list[str]] data: The data to write, may be a list of strings which will be concatenated.
  :param bool executable: Ensure the file is executable.
```