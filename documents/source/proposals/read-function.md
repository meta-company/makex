# Read Function

Support passing a path to write for amalgamations and concatenations:

```python 
write("file.c", ["\n// begin file\n", read(path()), "\n// end file\n"])
```
