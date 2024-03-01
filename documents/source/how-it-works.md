# How Makex Works

# Run/Execute

For example: 

```shell
makex run :target
```

1. Find the specified makex file(s) based on the target specified.
   - e.g. "$PWD/Makexfile:target"
2. Parsing stage:
   - While there is a queue of makex files to parse:
     1. Repeat the per file parsing steps.
     2. Add any dependent targets/makex files.
   - Per file parsing steps:
     - Evaluate the file to produce/collect TargetObjects and information:
       1. Validate and transform the AST.
         - Syntax is Restricted. Imports are disabled.
         - Primitive values and syntax are transform to contain or pass location information.
       2. Compile the AST into bytecode and execute.
       3. Store each TargetObject produced by `target()` calls in a graph (Graph 1).

3. Evaluation stage (using Graph 1):
   - For each specified target to run:
     - Find the Target in Graph 1 and all of its dependencies.
     - Evaluate each dependency and the target into EvaluatedTarget.
       - Evaluate each of the arguments, such as finds/globs.
       - Queue them as necessary (if they are dirty/stale).
   - Execution Pool: While there is a queue of targets to run/execute:
     - Execute each dependency before reaching the specified target.
     - Run each action of the specified target.