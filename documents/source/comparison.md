# Comparison to other tools

## Bazel

- Makex favors larger compilation units. 
  - This reduces the amount of build files to write and maintain.
    - Bazel projects can explode with numerous per folder build files.
  - Large units means less overhead when doing remote execution.
    - Sending and working with several large files is often faster than splitting into small ones (given additional network overhead).

- Bazel defines __many__ "non-generic" task producing functions/macros/actions (one can use `genrule`, but is inelegant).
  - Rather than just `task()` (in Makex), one must remember `cc_binary`, `cc_module`, `cc_module_binary`, `python_library`, `python_binary`, etc in Bazel.
    - While these are great for convenience and standardization, especially within a company, they make build files harder to read/process.

  - One must gain an understanding of all actions and each of their arguments/parameters/types, aside from gaining an understanding of how they will reflect into the arguments passed to executables to perform work/compilation.
  - We think executables (and their arguments) already provide this abstraction.

- Makex is more explicit by default.
  - Standard executables with arguments have priority over "actions".
  
- Bazel was developed with the constraints of use by a large (huge) amount both unskilled and skilled engineers.
  - Therefore, Bazel removes sharp edges to cater to the lowest common denominator.
    - For example, glob's were not implemented for "performance" (and possibly "correctness").
  - Makex was designed to be powerful and safe enough for engineers of all kinds.

- Bazel adopts an alternate locator syntax for referring to tasks in external workspaces (For example, the `@external` prefix).
  - Makex provides a single logical view of both internal and external workspaces.

- Inspecting the outputs of Bazel is complicated.

## Buck

- Buck is a cheap, poorly designed copy (or rip-off) of Google's blaze/bazel.
  - Buck lacks a coherent vision (of its own).
- Buck's development and progress is based on the shoddy engineering and whims of Facebook.

## CMake

- Cmake is a domain specific language with uncommon syntax.
  - Cmake is declarative and obscures what executables shall be executed with what arguments.
  - Writing macros and functions is confusing.
- Improving/modifying built-in tools is cumbersome.
- A typical pattern is to create an empty folder and call cmake inside of it to separate the build outputs from the source.
  - One has to name this directory, create it, switch to it, and clean it.
  - This is unnecessary in Makex.
- Limited list data structures.
- No Mapping data structure.

## Make

- Make is an ancient, static and unchanging tool that shall not change or improve.
  - Improvements to the language or tool are not slated.
- Make syntax is uncommon and obscure.
  - Tabs are forced. This frequently confuses new users.
  - Uses an unconventional syntax to access/escape variables.
  - Uses variables such as `$<`, `$@`, `$^` to refer to inputs/outputs/dependencies/etc.
- Make provides no help, introspection, analysis or visualization tools.
  - Accessing the list of targets in make file is convoluted.
- Make provides no access to the build graph.
- Make requires creation of sentinels or other techniques to track inputs/outputs. 
  - Make has no built-in input file check-summing or hashing. 
  - Uses file modification times to check if a target needs to be rebuilt.
    - [Modification] times is not enough for correct builds.
- Make requires the defining a target to `clean` the outputs of a build.
- Make provides no isolation of the inputs/source or outputs.
  - One must manually create and define output folders.
- Make requires calling make in a subprocess to build targets in a sub folder; recursively.
  - This prevents proper resource allocation and scheduling as no one process can moderate.
  - Subprocesses and context switches shall happen whether the sub-target needs rebuilding or not.
- No list data structure.
- No mapping data structure.

## Meson

- Does not support globs.

## Ninja

- Ninja build files are not intended to be "written by hand" (but instead generated).
- Ninja lacks features such as string manipulation.
- Does not support globs.

<!--
<table>
<tr>
<td></td>
<td></td>
</tr>
</table>
-->
