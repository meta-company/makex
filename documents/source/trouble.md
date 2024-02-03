
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


#target which creates a venv which we can use. similar args to target, but less.
python_venv_target(
  name="venv"
  requirements_files=[],
  packages=[], # list of packages we need to install
  runs=[
    # custom stuff to run after we have a venv inside a venv.
  ]
)

-->


(increasing-verbosity)=
### Increasing Verbosity 

Increasing verbosity may help you figure out what's wrong. Use the {option}`--verbose <makex --verbose>` option to trace your output.

To further increase verbosity, see the {option}`--verbose <makex --verbose>` option, or use the {option}`--debug <makex --debug>` option.

## Problems

### My program completes sucessfully, but still has an non-zero exit code.

At the moment, you'll need to fix your tool or wrap it in a script/executable that handles the error and returns a non-zero exit code.

Simplistically, the pattern `(command) || true` is often used in shell scripts, but this is not recommended. A script discerning from real
errors and spurious errors is required. 

This is a common problem with a number of tools (e.g. mypy); and oftentimes, the tool itself should be fixed.

### I see lines starting with `ERROR OUTPUT:` when running makex

Makex prefixes any errors written to standard output by subprocesses with `ERROR OUTPUT:`. This helps identify problems quickly.

If you don't want to see these messages, address the warnings, use a flag to quiet, or improve the executable you are trying to run.

### Makex hangs while running a command

NOTE: If a shell/execute/command waits for input, Makex will hang. This is by design. 
Several targets/runnables may be run in parallel, and it's indeterminable which
target/runnables needs which standard input.

Repeat, all executables makex runs must not require and wait user input (e.g. using readline()).

Some steps to debug a hang:

- {ref}`Increase your verbosity<increasing-verbosity>`, to see which commands are run.
- Find the last thing running before makex hangs. Stop/cancel Makex (usually ctrl+c, but may depend on terminal).
- If it's a shell/execute/command, check if running the command in another shell completes successfully.
  - If the command hangs or waits for input, you'll need to figure out a way to make it run without waiting for input.
  - If the command completes, this may be a problem with Makex. 

### Makex hangs, prints an exception, stack trace, or does something unexpected

Please send us a text copy of the output of the run with the {option}`--debug <makex --debug>` arguments enabled. 

You may email this text as an attachment to [makex@googlegroups.com](mailto://makex@googlegroups.com) or post it (as an attachment) using [Google Groups](https://groups.google.com/g/makex).

### I have some other problem

You may email them at [makex@googlegroups.com](mailto://makex@googlegroups.com) or post it using [Google Groups](https://groups.google.com/g/makex).