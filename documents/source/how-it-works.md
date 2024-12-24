# How Makex Works

## Run/Execute

For example: 

```shell
makex run :task
```

1. Find the specified makex file(s) based on the task specified.
   - e.g. "$PWD/Makexfile:task"

2. Parsing stage:
   - While there is a queue of makex files to parse:
     1. Repeat the per file parsing steps.
     2. Add any dependent tasks/makex files to the parsing queue.
   - Per file parsing steps:
     - Evaluate the file to produce/collect TaskObjects and information:
       1. Validate and transform the AST.
         - Syntax is Restricted. Imports are disabled.
         - Primitive values and syntax are transformed to contain or pass location information.
       2. Compile the AST into bytecode and execute.
       3. Store each TaskObject produced by `task()` calls in a graph (Graph 1).

3. Evaluation stage (using Graph 1):
   - Start pool with a queue for execution of tasks.
   - For each specified task to run:
     - Find the Task in Graph 1 and all of its dependencies.
     - Evaluate each dependency, and the task into EvaluatedTask objects.
       - Evaluate each of the arguments, such as finds/globs.
       - Queue the EvaluatedTask as necessary for execution (if they are dirty/stale).
       - Add the EvaluatedTask to Graph 2.
   - Execution Pool: While there is a queue of tasks to run/execute:
     - Execute each dependency before reaching the specified task.
     - Run each action of the specified task.