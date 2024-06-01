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

If several of these files exist in a directory, they will be searched in the order specified.

<!-- They will be tested, in order, for a 
magic marker to see if they are a Makex file and the first Makex-looking file will be parsed. -->

## Syntax

Makex Files are a restricted subset of {ref}`The Python Programming Language<python:reference-index>`.
See the {ref}`differences<python-differences>` for more details.

```{tip}
Keep your Makex Files simple. Don't be too clever. 
Makex files are designed to evaluate quickly without necessitating the call of subprocesses.
```


## Magic marker/Hashbang/Shebang

A marker `#!makex` at the top of the file both serves to mark the file as a script and to differentiate makex files from other types of files.

At the moment, this marker is entirely optional.

```python
#!makex
```

The word makex can be anywhere on the line after the `#!`.

## Commenting

```python

# This is a single line comment.

"""
This is a 
multiline comment.
"""
```

## Strings

String objects in Makex have the following structure:


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


(actions)=
```{include} syntax-functions.md
:heading-offset: 1
```

(actions)=
```{include} syntax-actions.md
:heading-offset: 1
```

## Self Documentation

A multiline comment string may be included at the top of the file to document the file.

This string may be written in markdown with restructured text to provide help or description in other formats/renderings.

(python-differences)=
## Differences from Python Syntax

- Import statements (`import ...` or `from ... import ...`) to any standard libraries are not allowed in Makex Files.
  Future versions of makex will include modularization features.

- String syntax and functions are restricted.

- Makex has a extra syntax for defining functions (called macros). 
  Defining/using functions without a macro decorator is not allowed.

- Several methods on objects such as strings and lists are not [yet] provided.

```{eval-rst}
 
.. todo: document restrictions and syntax.
```

## Formatting

When calling functions or constructing lists or dictionaries you should leave an extra comma at the end of the list or dictionary.
This helps when adding or changing values later.

It is preferred to break functions/callables with keyword arguments into separate lines with a keyword argument per line.
Actions like `execute()` or `copy()` may be left on a single line if they fit.

We plan to introduce automatic formatting.

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
        Task("bad"), Task("Bad")
    ]
)

# good
task(
    name="bad",
    requires=[
        Task("bad"), 
        Task("Bad"),
    ],
)

```


