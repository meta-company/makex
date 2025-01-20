---
status: "Draft"
---

# Executable Argument Abstractions

Forming arguments to executable is common, and currently inelegant, as one must form lists with the correct sequences.

We propose some additional function/syntax for building and using argument lists.

Passing a dictionary to execute should flatten it correctly.
Values in the dictionary must be values that would otherwise serialize to argument lists.

```python


# this will produce all long arguments except for 1 letter.
# cleaner/convenient syntax for the most common/defacto standard
# XXX: the word mapping is confusing here.
execute("example", mapping(name1="value1", name_2="value2", n="3"))

# we want to specify which are --long and which are -short arguments.
# There is no consistent standard. anything might use anything.
# the dash prefixes make things explicit.
execute("example", {"--name1": "value1", "--name_2": "value2", "-n": "3"})
# expands to --name1 value1 --name_2 value2 and -n 3

# we may want = to merge keys/values. keys ending with = will signify this.
# it is unlikely that "=" will ever be part of a key
execute("example", {"--name1=": "value1", "--name_2=": "value2", "-n": "3"})

# lists values should repeat the argument
execute("example", {"--name1=": ["value1.1","value1.2"]})
# producing: example --name1=value1.1 --name1=value1.2


# TODO: should repeating the key (i.e. a list/tuple) serialize the list? (probably not)
```
