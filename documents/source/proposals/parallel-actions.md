# Parallel actions

We may want a way to parallize certain actions/executions within a task.

For example, to execute 2 executables in parallel.

```python
task(
    name="example",
    steps=[
        ...,
        parallel(
            execute(...),
            execute(...),
        ),
        ...,
    ],
)
```


This may be provided as a hint to makex.

Alternatively, we may want a parallel=True argument to the execute() action to allow it to run in parallel with the next execute action. A execute(parallel=False) (the default) will end the parallelization and all executes after will be sequential.


## Considerations

- The executor must become aware of execute actions parallization, and how many things can be run in parallel at once.
  - We must determine, given complexity, whether to share these cpus with parallelization of tasks themselves.
    - If we have a lot of tasks queued/executing, and high cpu utilization, parallelize less.
    - If utilization is low, parallize more.
