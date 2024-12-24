
# Comparison

## Bazel

- Makex favors larger compilation units. 
  - This reduces the number of build files to write and maintain.
  - Less overhead when doing remote execution.
    - Sending and working with several large files is often faster than splitting into small ones (given additional network overhead).

- Bazels is mostly pinned on "non-generic" tasks/actions (one can use genrules but they are inelegant).
  - There is not one, but many different task functions/macros/actions. Instead of just `task()`, one must remember `python_library`, `python_binary`, etc.
    - While these are great for convenience and standardization, especially within a company, they make build files harder to read/process.

  - One must gain an understanding of all of actions and each of their arguments/parameters, aside from gaining an understanding of how they will reflect into the arguments passed to executables to do work/compilation.

- Makex is more explicit by default.
  
- Bazel was developed with the constraints of use by a large (huge) number of both unskilled and skilled engineers.
  - Thus, Bazel removes a lot of sharp edges to cater for the lowest common denominator.
    - E.g. glob's are not implemented for "performance".
  - Makex was designed to be powerful for engineers and safe enough.

- Bazel adopts multiple syntaxes for referring to tasks in external workspaces (e.g. @external).
  - Makex provides a more logical view of both internal and external workspaces.

## CMake

- Cmake is a domain specific language
  - Cmake is declarative and obscures what actions will be executed with what arguments.
  - Writing macros and functions is confusing.
- Improving/modifying built-in tools is cumbersome.

## Make

- Make the language has many problems:
  - Tabs are forced. This frequently confuses new users.
- Make is an ancient tool 
  - uses unconventional syntax to access/escape variables.
- Make is static and unchanging.
  - Improvements to the language or tool are not slated.
- Requires creation of sentinels or other techniques to track inputs/outputs. 
  - [Modification] times is not enough to for simple and correct builds.
  - Make has no built in input file checksumming


<table>
<tr>
<td></td>
<td></td>
</tr>
</table>