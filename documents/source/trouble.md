
# Troubleshooting

## Tips

<!-- ### Python Virtual Environments

Show an example of using the environment function to modify a PATH and variables to enter a venv.

environment({
  "PATH": posix_path_add(".venv/bin", before=True), 
  "PATH": Environment.get("PATH").prepend(".venv/bin", ":",)
  # ...
})

TODO: provide built in tooling. load("//tools/makex/python/venv.mx.py","python_venv_enter", python_venv_enter="pyvenv")

# runnable to enter a venv for later executables. This will fix/adjust the path environment automatically.
python_venv_enter(environment=[":venv], )


#task which creates a venv which we can use. similar args to task, but less.
python_venv_task(
  name="venv"
  requirements_files=[],
  packages=[], # list of packages we need to install
  steps=[
    # custom stuff to run after we have a venv inside a venv.
  ]
)

-->


(increasing-verbosity)=
### Increasing Verbosity 

Increasing verbosity may help you figure out what's wrong. Use the {option}`--verbose <makex --verbose>` option to trace your output.

To further increase verbosity, see the {option}`--verbose <makex --verbose>` option, or use the {option}`--debug <makex --debug>` option.

## Problems

### My program completes successfully, but still has a non-zero exit code.

At the moment, you'll need to fix your tool or wrap it in a script/executable that handles the error and returns a non-zero exit code.

Simplistically, the pattern `(command) || true` is often used in shell scripts, but this is not recommended. A script discerning from real
errors and spurious errors is required. 

This is a common problem with a number of tools (e.g. mypy); and oftentimes, the tool itself should be fixed.

### I see lines starting with `ERROR OUTPUT:` when running makex

Makex prefixes any errors written to the standard error output (stderr) by subprocesses with `ERROR OUTPUT:`. This helps identify problems quickly.

If you don't want to see these messages, address the warnings, use a flag to quiet, or improve the executable you are trying to run.

### Makex seems slow handling large files

Makex generates checksums of input/output files. At the moment, this is currently done in a single process. 

It's usually best to just wait for the file hashing to complete for the set of input files.

You may omit large output files from the Task's outputs and this will prevent hashing them.

<!--
offline checksumming
-->

### Makex hangs while running a command

NOTE: If a shell/execute/command waits for input, Makex will hang. This is by design. 
Several executables may be run in parallel, and it is indeterminable which
one needs or will wait for standard input.

Repeat, all executables Makex runs must not require and wait user input (e.g. using readline()).

Some steps to debug a hang:

1. {ref}`Increase your verbosity<increasing-verbosity>`, to see which commands are run.
2. Find the last thing running before makex hangs. Stop/cancel Makex (usually ctrl+c, but may depend on terminal).
3. If it's a shell/execute/command, check if running the command in another shell completes successfully.
  - If the command hangs or waits for input, you'll need to figure out a way to make it run without waiting for input.
  - If the command completes, this may be a problem with Makex. 

### Makex hangs during copying a folder

This can happen if the folder or its contents has recursive symlinks.

### Makex hangs, prints an exception, stack trace, or does something unexpected

Please send us a text copy of the output of the run with the {option}`--debug <makex --debug>` arguments enabled. 

You may email this text as an attachment to [makex@googlegroups.com](mailto://makex@googlegroups.com) or post it (as an attachment) using [Google Groups](https://groups.google.com/g/makex).

### I have some other problem

You may email them to [makex@googlegroups.com](mailto://makex@googlegroups.com) or post it using [Google Groups](https://groups.google.com/g/makex).
