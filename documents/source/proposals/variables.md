# Proposal: Unbound/Free/Bound/Non-local Variables and Variants

Various ideas have been floated and experimented regarding "free" variables for makex.

Environment variables may be used, but we've found they are a bit too free form, and they also don't have namespacing leading to long environment variable names.
Environment variable incur additional overhead for each time they must be processed (usually in their own special way, with their own special APIs).

This proposal describes a feature for makex allowing to declare and use unbound/free or bound variables to vary tasks.

When a task is varied by unbound variables, it may produce variants of outputs by binding the variables and evaluating the task
with those new variables. 

# Definitions

- Bound Variable: A variable that has been bound with a value (either explicitly, or by default value).
- Output Variant: A variant of output produced by a varied task.
- Task Variant: A variant of a task produced by evaluating the task with bound/set variables.
- Unbound Variable: A variable that requires a value. (aka a Free variable)

## Defining a free/bound/unbound variable

Variables should be defined in capital letters to improve their visibility.

A variable may a `string`, `integer`, `boolean`, `path` (an absolute, relative or workspace path).
By default, variables are strings.

```python


# a bound variable, 
# with a local name SOME_VARIABLE, for convenience
SOME_VARIABLE = variable(
    name="some_variable",
    
    # type may be string, integer, or boolean
    type="string",
    
    # define a value for the variable immediately. making it bound.
    value="",
    
    # set a value from the platform object
    value=platform.architecture,
    
    # set a value from the environment
    environment="SOME_VARIABLE",
    
    # list available options for the variable
    options=[],
)
```

Variables should not be used outside of a task definition except for aliasing them.

Variables (e.g. of list or set types) should not be iterated over with a for loop, e.g to create variations of tasks.
(TODO: ban if/for at the top level, or just prohibit branching/iterating over variables?)

Variables should not be used to define input files as it may make static analysis challenging. 
This is not enforced, but may be. 

Variables use the same namespace as tasks and executable, and they must be uniquely named among these items.

## Limiting the choices of variables

## Varying the task/name based on variables

Variables of type string may be used for parts of the task definition (e.g. the task name).
This may be used to create different tasks (and outputs) based on the variable set, all with the same base name.
TODO: probably bad idea. just serialize+hash the variables used and values as part of task folder name.

```python
task(
    name=f"example-{variable(':architecture')}"
    ...
)
```

## Binding to environment variables

Variables may be bound to environment variables at declaration, by passing the environment variable name.

```python
variable(
    name="example",
    environment="EXAMPLE"
)
```

The variable coersion from the environments value depends on the type.
If a string, the value will be as is.
If an integer, the value will be converted to an integer.
If a boolean, `1`,`true`,`TRUE` will evaluate to truth, and `0`, `false`, `FALSE` will evaluate to false.

### Automatic environment variables

Alternatively, each variable may be [automatically] defined a unique name which may be set by environment variables (a named formed from the workspace path and variable name; uppercase and underscore separating components).

For example a variable `//path/to/variables:variable_name` will be available as
`PATH_TO_VARIABLES_VARIABLE_NAME` in the environment variables.

## Using a variable in a task

Variables may be used throughout a task declaration; in the steps, the environment variables,
the requirements, or any branches/selects.

A reference to a variable may be obtained with the variable function `variable("variable_name")` (called with/without keyword) arguments.
The variable name must be passed as a String.



## Varying tasks based on the value of a variable

Any unbound variables within a task will cause it to become a varied task.
When a task is referenced as a requirement it may be explicitly varied with the `vary` function `vary(task_reference, **kwargs)`. 

TODO: this internal varying may prove trouble.

The `vary` function may be passed keyword arguments to bind local/unbound variables in the referred to task.
TODO: kwargs may make inspection/analysis/refactor more trouble. consider using variables with some operator or method e.g. `variable("variable) == "somevalue"` or `variable("variable").bind(value)`.

TODO: this may be best as separate feature (`parameters`).

For example:

```python

VERSION = variable(
    name="version",
)

task(
    name="example",
    requires=[
        # TODO: duplication here. requires as dict?
        "task:subpath",
    ],
    inputs={
        "subtask_file": vary("subpath:task", version=VERSION, **{":version": VERSION}).outputs.file
    }
)
```

in `subpath/makexfile`:

```python

task(
    name="task",
    outputs={
        "file": f"example-{variable(":version", inherit=True)}.tar.gz"
    },
    steps=[
          archive(
              name=self.outputs.file,
              ...
          ),
    ]
)

```

TODO: maybe allow explicitly inheriting variables from a parent makex file (the first in which the variable was defined in).

## Global Variables

Some variables may be defined globally. 
The benefit of this being a user doesn't have to think about where they are defined.
Global variables are by convention instead of by explict declaration.
Users should document any use of a global, and provide defaults as necessary when they are referenced or use.

Global variables are prefixed with a special marker (`@`).
This marker was chosen so the variable may be entered on the command line without quotes.

TODO: consider a separate keyword to access and reference them instead of prefixes (e.g. `global(name, default)`)

The type of a global variable may be declared when it is assigned (e.g. `@variable=type=value`, where type is `string`, `integer`, `path`)

Global variables may be specified on the commmand line, directly as arguments, or using the `--global` parameter.

```shell
makex run @global_name=type=value

# or:
makex run --global global_name=type=value
```

Global variables may be defined in a makex configuration file under the `[makex.globals]` key. For example:

```toml
[makex.globals]
name="type=value"
```

## Specifying variables on the command line

Variables may be referenced like any Task (e.g. `//path:variable_name`).

To set a variable from the command line pass an assignment along with any targets to run (e.g.
`//path:variable_name=value` or `:variable_name=value`, or
`@variable_name=value` globally for wherever variable_name is used).

Values on the command line are parsed depending on the variable type. 

If a variable is a list/set type, it may be specified multiple times to add items to the list.
Alternatively, a shorthand syntax may be used for both lists and sets (e.g. `//path:variable_name="['1','2',...]"`).

## Referring to variables in a parent makex file

Oftentimes, a variable will be needed from a parent make file as part of a build (e.g. a release/version number, or platform/architecture).

Variables may be left undefined and unbound in a makex file. 

Before a task with such unbound/defined variables is evaluated, the variables must be bound to a value. The value is bound when:

- it explicitly bound by a dependant task (e.g. `vary()`).
- it is bound using the command line 
- it is bound using the environment
- it defined/bound by a makex file in the parent folder?

## Variables as requirements

Variables may (and should) be explicitly specified in the tasks requirements like any other task reference.

A variables in the tasks requirements means the variable must be fulfilled before evaluating the task.

## TODO: Variables and executable declarations

TODO: As executables declarations may reference targets (to be able to produce them), we need to define how they will interact.

In this use case, typically one is defining the architecture or version of an executable to be produced.

```python

task(
    name="produce-executable",
    steps=[    
        print("Produce executable with arch: ", variable(":architecture"))
        ...
    ],
    outputs="executable"
)

executable(
    name="executable",
    source=":produce-executable",
)

task(
    name="example",
    steps=[
        execute(":executable")
    ]
)
```

## Proposed Names

These are all variable related words/concepts that we're exploring for this feature.

- variable*
  - heavily overloaded
  - name != variable
  - may be prefixed (e.g. declared variable, defined variable, or explicit variable)
- unbound*
  - decent as all variables defined this way are unbound/free until they are bound and evaluated.
  - "bound until the last moment"
  - it also means the are _unbound_, potentially producing any number of variants
    - may be limited by "choices" argument
- unknown
  - variable in an equation that needs to be solved for (we're not solving for anything here) 
  - too mathy
- indeterminate
  - does not stand for any value; used as a placeholder in formulae
  - long/difficult to spell
- parameter*
  - unbound variable 
  - possible confusion with function parameters/arguments (which have more confusion themselves)
  - overloaded (in the function sense); may be prefixed (e.g. custom parameter)
- argument
  - bound variable
  - overloaded (in the function sense)
- free variable
  - aka unbound/free
  - free in what sense?
- real variable
  - unbound/free  
  - real in what sense?
- apparent variable
  - unbound/free
  - apparent to what/who?
- applicable variable
  - unbound/free 
  - applicable to what/who?
- bound variable 
  - a variable with a value 
- placeholder
  - wordy 
- dummy variable
  - i.e. a bound variable  
  - wordy 
- flux(ion)
  - to flow (flowing out)
  - not really relevant, but may be suitable
- fluent
  - not relevant
- non_local
  - decent name as a reference to a variable. e.g `nonlocal("variable")`
  - lua: upvalue
- mutable
- changeable

## Rejected Ideas

### List/Set/Iterable type variables

List/set may cause more issues than it is worth (e.g. iterations we can't evaluate at parse time).

Users may be confused about when they will evaluated, or in what context they may be evaluated.
lists/sets/dicts will probably present many footguns and confusion.

Iteration may be done by wrapping all list/dict comprehensions with a internal type which evaluates string when a task
(e.g. `[item for item in variable('example')]` would be translated into `Iterator(variable('example'), "item", "item")`)
Or we could just pull the AST out at parse time, passing it as an argument to a late evaluation function, which
later will be evaluated with new variables.

### Iterating over variables

An idea was to allow for variables to be iterated over within a task definition by using the `iterate(f, variable)` function.
The function would be provided to map may return a value for each item passed to it (or `None`).

This would be be used to transform variables before they are passed as arguments to executables.

These extra functions and complexity was deemed unnecessary.

## Comparing variables

An idea was to allow for variables to compared with other values (but not other variables).

Adding operators to variables is too complex and error prone.

A simple branching/select/switch statement/function may be used to allow for switching on a variables value.

```python

task(
    name="example",
    inputs={
        "file": switch(
            variable("os"), 
            case("linux", "linux-file.txt"), 
            case("windows", "windows-file.txt"),
        )
    }
)

```

## See Also

- https://en.wikipedia.org/wiki/Free_variables_and_bound_variables
- 
