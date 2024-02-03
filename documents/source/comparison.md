
# Comparison

## Bazel

- Makex favors larger compilation units. 
  - This reduces the number of build files to write and maintain.
  - Less overhead when doing remote execution.
    - Sending and working with several files is often faster than splitting (with the additional network overhead)
- Makex is more explicit by default.
  - 