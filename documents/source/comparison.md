
# Comparison

## Bazel

- Makex favors larger compilation units. 
  - This reduces the number of build files to write and maintain.
  - Less overhead when doing remote execution.
    - Sending and working with several files is often faster than splitting (with the additional network overhead)
- Makex is more explicit by default.
  
- Bazel was developed with the constraints of use by a large (huge) number of both unskilled and skilled engineers.
  - Thus, Bazel removes a lot of sharp edges to cater for the lowest common denominator.
    - E.g. glob's are not implemented for performance.
  - Makex was designed to be powerful for engineers and safe enough.
- Bazel adopts multiple syntaxes for referring to targets in external workspaces (e.g. @external).
  - Makex provides a more logical view of both internal and external workspaces.

## CMake

- Cmake is a domain specific language
  - Cmake obscures what actions will be executed with what arguments.
  - Writing macros and functions is confusing

## Make

- Make the language has many problems:
  - Tabs are forced. This frequently confuses new users.
- Make is an ancient tool
- Make is static


<table>
<tr>
<td></td>
<td></td>
</tr>
</table>