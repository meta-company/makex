```{eval-rst}
:tocdepth: 3
```
# Makex Files

## Naming

The name of the Makex File should be one of the following:

- `Makexfile`
- `makexfile`
<!-- `Build`
- `BUILD` -->

The default names to search can be changed with the {data}`makex.makex_files<TOML.makex.makex_files>` configurable.


<!--
The name of a file can be specified absolutely.

The list of files to check can be specified on the {option}`command line<makex --makex-file-names>` or configuration file.
--> 

If several of these files exist in a directory, they shall be searched in the order specified. The first match shall be used as the folder's primary (or default) Makex file.

The extension of Makex files is `.mx`.

<!-- They will be tested, in order, for a 
magic marker to see if they are a Makex file and the first Makex-looking file will be parsed. -->

## Syntax

Makex Files are a restricted subset of {ref}`The Python Programming Language<python:reference-index>`.
See the {ref}`differences<python-differences>` for more details.

```{tip}
Keep your Makex Files simple. Don't be too clever. 

The Makex file format/language is designed to be simple (simpler than Python) and easy/fast to process (almost statically, if necessary).

Makex files are designed to evaluate quickly without running subprocesses.
```


## Magic marker/Hashbang/Shebang

A marker `#!makex` at the top of the file both serves to mark the file as a script and to differentiate makex files from other types of files.

At the moment, this marker is entirely optional.

```python
#!makex
```

The word `makex` can be anywhere on the line after the `#!`.

## Commenting

```python

# This is a single line comment.

"""
This is a 
multiline comment.
"""
```

## Strings

Strings are defined as in Python, surrounded by quotation markers (`'` or `"`). 
Multiline strings may be surrounded by triple quotation markers (`"""` or `'''`).

Quotation marks prefixed with the letter `f` denote a formatted string (For example, `f"Example string"`). 
Formatted strings may contain placeholders for variables that shall be rendered when necessary. 
For example, `f"Hello {name}"`, defines a string with a placeholder called `name`.

Depending on how formatting strings are defined and used, their rendering may be deferred. This allows embedding references or paths in strings which can be expanded correctly. Typically, a formatted string with any type of `UnresolvedPath` objects can not be rendered outside the scope of a task definition.

String objects defined in Makex files have the following structure:

```{eval-rst}
.. py:class:: String
  
  The makex string object. You cannot instantiate this object directly.
  Use quotes and/or f-strings to define strings.
  
  .. py:method:: replace(value, substitute)
     
    Replaces all `value` with substitute in a String.
      
    :rtype: String
```

```{note}
A wide range of built-in methods for {py:class}`Python strings <str>` and other primitive types (such as  {py:class}`lists <list>` and  {py:class}`dictionaries <dict>`) are not defined or enabled.
```

## Lists

As in Python, lists in Makex may be defined using the open and closing brackets to define items (For example, `["item1", "item2"]`).

The only supported method is `append`. 
Lists may be concatenated using the `+` or `+=` operators.

It is not recommended to modify (or mutate) lists away from their definition site.

## Mappings

As in Python, Mappings (or Dictionaries) in Makex may be defined using the open and closing braces to define keys and values (For example, `{"key1": "value1", "key2": "value2", ...}`).

Mappings must use Strings for the keys, and the values may be any type as required/used.

It is not recommended to modify (or mutate) Mappings away from their definition site.

## None

The name `None` is used as a null value.

A `None` value in Makex is typically ignored or skipped. `None` values are not serialized to strings.

(functions)=
```{include} syntax-functions.md
:heading-offset: 1
```

(actions)=
```{include} syntax-actions.md
:heading-offset: 1
```

<!--
(environment-variables)=
```{include} syntax-environment.md
:heading-offset: 1
```
-->

## Self Documentation

A multi-line comment string may be included at the top of the Makex file to document it.

This string may be written in markdown with restructured text to provide help or description in other formats/renderings (see [MyST](https://myst-parser.readthedocs.io/en/latest/)).

(python-differences)=
## Differences from Python Syntax

- Import statements (`import ...` or `from ... import ...`) to any standard libraries are not allowed in Makex Files.
  Future versions of Makex shall include modularization features.

- String syntax and functions are restricted.

- Makex has modified syntax for defining functions (called macros). 
  Defining/using functions without a macro decorator is not allowed.

- Several methods on objects such as strings and lists are not [yet] provided.

```{eval-rst}
 
.. todo: document restrictions and syntax.
```

## Formatting

When calling functions or constructing lists or dictionaries you should leave a trailing comma at the end of the list or dictionary.
This helps when adding or changing values later.

It is preferred to break functions/callables with keyword arguments into separate lines with a keyword argument per line.
Actions like `execute()` or `copy()` may be left on a single line if they fit, and may omit the trailing comma.

We plan to introduce automatic formatting. Until then, tools like `yapf` or `black` are recommended to keep your Makex files formatted.

Keep your Makex files simple.

```python

# bad
alist = [1,2,3]

# good
alist = [
    1,
    2,
    3,
]

# bad 
task(
    name="bad", requires=[
        ":bad", ":Bad"
    ],
    ...
)

# good
task(
    name="bad",
    requires=[
        ":bad", 
        ":Bad",
    ],
    ...
)

```


