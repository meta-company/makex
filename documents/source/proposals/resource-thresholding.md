from numpy.ma.core import minimum---
status: "Draft"
---
# Resource Allocation/Thresholding Control

This document describes a proposal for the control of the resources makex uses.

## Rationale

A static threads/workers/jobs argument (e.g. `--jobs` in make/ninja/mason/bazel/etc) doesn't properly constrain local machine resource allocation.

For example, if a run has a high amount of tasks to run, the tasks may slow the machine down.

Conversely, if one or more task executions use a high amount of memory, newly queued/executed tasks may not run properly with memory being exhausted.

Developers using makex would prefer it didn't use all of their machine's resources. No build tools have obvious ways to control these resource constraints.

Tasks that require minimum memory are uncommon, but do exist. These are typically:

- linker steps/executables
- large scale build tools
- inefficient build tools and packers (e.g. typescript, webpack, etc) 

We need a way to dynamically allocate load based on machine specifications and metrics, and task requirements.

Constraints in order of weight are:

- Memory
  - tasks need a minimum amount of memory
  - tasks may not exhaust memory
- CPU
  - tasks need at least 1 cpu
  - tasks may not exhaust available computation power
- Disk I/O
- Network I/O

## Specification

An argument is added to makex to constrain a resource. 
The argument may be specified multiple times.

The form of the argument is:

```
"--constrain" {namespace} ":" {name} "=" {value} [ "{" {labels} "}" ]
```

- The placeholder `{namespace}` is one of `memory`, `cpu`, `load`, `tasks`.

- The placeholder `{name}` depends on the namespace. This is the limit/name to define a constraint for (e.g. `maximum`, `minimum`, `count`).

- The placeholder `{value}` sets the value for the constraint name. Typically, a number 
  with an optional unit.

- Optional `{labels}` is a set of one or more labels separated by comma. If omitted
the constraint will apply to all tasks.

Labels may be added to tasks which marks their constraints. For example,

```python
task(
    name="example",
    # mark this task as requiring 1G of memory.
    # i.e. do not run this task until 1G of memory is free.
    labels={"memory:minimum=1G"},
    # TODO: maybe a better idea is a separate namespace/type
    #  then we can access self.constraints["memory:maximum"] in tasks.
    #  self.constrains[name] should return an object with several properties
    #  by default, it should return the most primitive/unit value (e.g. bytes, count)
    #  the object should be able to be converted/serialized using different units as potentially required by an executable.
    constraints={"memory:minimum": "1G"}
)
```


Constraints may be defined in the makex configuration file where they may be applied per machine, or per user. (TODO: do constraints merge?; probably yes)

For example:

```toml

[makex]
# ...
# define under the makex global:
constraints=[
    {resource="", value="", labels=[]}
]

# ...
# or use a table:
[[makex.constraints]]
resource="{namespace}:{name}"
value=""
labels=["label1", "label2", "..."]
```


### Label specific thresholding

Any of the thresholds may be restricted or limited to specific labels by prefixing the limit value with a task name followed by the `:` character. (e.g. `--minimum-memory high_memory:1GB` will ensure tasks with the `high_memory` label have at least `1GB` available otherwise their scheduling/execution would cause an error)

### Memory Thresholding

Maximum memory usage thresholding must respect the working memory size of makex, otherwise tasks can not be scheduled.

##### Maximum Memory (`memory:maximum`)

- An integer to limit the memory of work to a maximum.
  - Number of bytes.
  - Minimum is probably at least 10s of megabytes.
  - May be shortened and suffixed with a unit `MB`,`GB`,`TB` (base 2).
- Must accept `auto` (Default) to limit tasks based on memory automatically (near maximum).
  - This setting may use thresholds/hints provided by the system (e.g. linux resource limits)
- Must accept `unlimited` for no memory thresholding.
- Aliased to `--memory`.
- Algorithm:
  - Watch task memory/thread status; if the task+children uses more than maximum; kill it and error.

##### Minimum Memory (`memory:minimum`)

- An integer to set the minimum memory that must be available for a task to be executed.
- Algorithm:
  - Prior to enqueueing a task:
    - If the system has the available memory, run the task immediately
    - If the system has the available memory, but it's being used by other tasks; defer it until those tasks complete. Potentially run other tasks in parallel.
    - If the system does not have the available memory, error.

### CPU Thresholding

One (1) cpu must always be allocated to makex (with a lower priority) to monitor and schedule tasks.
If only 1 CPU is available, it will be shared and scheduled [by the operating system] with task execution.

#### CPU Count (`cpus:maximum`)

- Aliased to `--cpus` (or `--tasks`). 
- An integer to limit the maximum amount of cpus to do work in.
  - Must be a minimum of 1.
- Must accept `auto` (Default) to limit the amount automatically (`min(1, total_cpus - 1)`).
  - This setting may use thresholds/hints provided by the system (e.g. linux resource limits)

#### Tasks (`tasks:running`)

- An integer to limit the amount of tasks to execute in parallel.
  - Must be a minimum of 1.
- Must accept `auto` (Default) to limit the amount automatically (`maximum_cpus`).
- Mostly the same as `cpus:maximum`, but puts restrictions on execution (the Executor).

#### Load (`load:maximum`)

- Aliased to `--load`. 
- An integer representing a percentage of CPU load makex may use averaged over a duration (typically 1 minute).
  - Must be from 1-99.
- Must accept `auto` This means we will keep the system load at "optimum utilization" (near maximum).
- Must accept `unlimited` (Default) for no load thresholding.
- Algorithm:
  - Watch for load status. If load is high, reduce it by:
    - Limiting the amount of tasks queued per quantum


## Considerations

- We may want to maintain a separate argument for the amount of parsing/processing threads makex has/uses (e.g. the existing argument; `--cpus`). 

  - We may want parsing/evalution speed/cpus to be high, while execution truncated/thresholded separately. 

  - At least 1 process/thread must be allocated to the Executor.

  - We may want to still respect the user provided cpus threshold if automatic. `n_worker_threads == max(1, execution_processes < options.maximum_cpus - 1)` 

## Implementation Notes

```python
import enum
from dataclasses import dataclass


@dataclass
class DiskStats:
    """
    
    Via https://www.kernel.org/doc/Documentation/block/stat.txt
    
    /proc/diskstats will return 
    
    [\d] [\d] [\-a-zA-Z0-9_] ... values ...
    
    /sys/block/{disk_name}/stat will reutrn:
    
    ... values ...
    
    :ivar RequestCount read: I/Os number of read I/Os processed
    :ivar RequestCount read_merges:  number of read I/Os merged with in-queue I/O
    :ivar SectorCount read_sectors:  number of sectors read
    :ivar Milliseconds read_ticks:  total wait time for read requests
    :ivar RequestCount write: I/Os number of write I/Os processed
    :ivar RequestCount write_merges:  number of write I/Os merged with in-queue I/O
    :ivar SectorCount write_sectors:  sectors number of sectors written
    :ivar Milliseconds write_ticks:  total wait time for write requests
    :ivar RequestCount in_flight: number of I/Os currently in flight
    :ivar Milliseconds io_ticks: total time this block device has been active
    :ivar Milliseconds time_in_queue: total wait time for all requests
    :ivar RequestCount discard_ios:    number of discard I/Os processed
    :ivar RequestCount discard_merges:   number of discard I/Os merged with in-queue I/O
    :ivar SectorCount discard_sectors:   number of sectors discarded
    :ivar Milliseconds discard_ticks:   total wait time for discard requests
    """
    read_ios: int
    read_merges: int
    read_sectors: int
    read_ticks: int
    write_ios: int
    write_merges: int
    write_sectors: int
    write_ticks: int
    in_flight: int
    io_ticks: int
    time_in_queue: int
    discard_ios: int
    discard_merges: int
    discard_sectors: int
    discard_tocks: int


class Options:
    # user specified options

    # maximum cpus as an integer
    # "auto" to determine a value automatically
    maximum_cpus: Union[int, Literal["auto"], None]

    # maxmimum memory in bytes
    # "auto" to determine value automatically
    maximum_memory: Union[int, Literal["auto"], None]


def get_cpu_times():
    # See : https://man7.org/linux/man-pages/man5/procfs.5.html

    # Read first line from /proc/stat. It should start with "cpu"
    # and contains times spend in various modes by all CPU's totalled.
    #
    with open("/proc/stat") as procfile:
        cpustats = procfile.readline().split()

    if cpustats[0] != 'cpu':
        raise ValueError("First line of /proc/stat not recognised")

    user_time = int(cpustats[1])  # time spent in user space
    nice_time = int(cpustats[2])  # 'nice' time spent in user space
    system_time = int(cpustats[3])  # time spent in kernel space

    idle_time = int(cpustats[4])  # time spent idly
    iowait_time = int(cpustats[5])  # time spent waiting is also doing nothing

    time_doing_things = user_time + nice_time + system_time
    time_doing_nothing = idle_time + iowait_time

    return time_doing_things, time_doing_nothing


def get_utilization():
    # return the cpu utilization from 0-100
    time_doing_things, time_doing_nothing = get_cpu_times()
    return time_doing_things / (time_doing_things + time_doing_nothing) * 100


def get_memory_used_bytes() -> int:
    # (KB on Linux, B on OS X)
    return resource.getrusage(resource.RUSAGE_BOTH).ru_maxrss


def get_total_memory_bytes() -> int:
    pass


def get_free_memory_bytes() -> int:
    pass


def get_task_memory_bytes() -> int:
    pass

class Context:
    # number of tasks currently running
    tasks_running: int

    # number of cpus available
    cpus: int


class Runability(enum.Enum):
    CONTINUE = 1
    DEFER = 2
    ERROR = 3
    
    
class Response:
    runablity:Runability
    error:Exception

    
class ResourceStatus:
    # free memory. less than total.
    free_memory:int

    # memory used by all running tasks
    task_memory_used:int
    
    # total memory available/installed
    total_memory:int

    # memory used by makex and all children
    memory_used:int
    
    # memory used by the makex process alone
    makex_used:int
    

def can_run_task(ctx: Context, options: Options, status:ResourceStatus) -> bool:
    total_memory = status.total_memory
    free_memory = status.free_memory
    task_memory_used = status.task_memory_used
    memory_used = status.memory_used

    # check we are within memory thresholds...
    
    # check we don't exceed maximum memory
    maximum_memory = None

    if isinstance(options.maximum_memory, int):
        maximum_memory = options.maximum_memory
    elif options.maximum_memory == "auto":
        # allow using 90% of the machine's memory for build
        maximum_memory = int(total_memory * 0.9)

    if maximum_memory is not None:
        if memory_used >= maximum_memory:
            # wait until tasks finish/freeing up memory
            return Response(Runability.DEFER)
    
    # check the task has minimum memory available
    # wait if possible for the memory to free up
    minimum_memory = None
    if isinstance(options.minimum_memory, int):
        minimum_memory = options.minimum_memory

    if minimum_memory is not None:
        if minimum_memory >= total_memory:
            return Response(Runability.ERROR, f"Requires {minimum_memory} bytes. System only has {total_memory} installed.")
        
        if minimum_memory <= free_memory:
            if minimum_memory <= task_memory_used:
                # memory is available, but it's being used by others
                return Response(Runability.DEFER, "Wait for other tasks to free up memory resources.")
            
            # we can't free the memory used by other processes
            return Response(Runability.ERROR, f"Requires {minimum_memory} bytes. System only has {total_memory} free.")
            
        
    # check we are within cpu threshold
    # TODO: not necessary. enforced by pool size
    maximum_cpus = None
    if isinstance(options.maximum_cpus, int):
        maximum_cpus = options.maximum_cpus

    if maximum_cpus is not None:
        if ctx.tasks_running >= maximum_cpus:
            # wait until threads free up
            return Response(Runability.DEFER)

    # check we are within CPU "load" threshold
    one_minute_load_average = os.getloadavg()[0] / ctx.cpus

    return Response(Runability.CONTINUE)

```


### Unix/Linux/BSD

`os.getloadavg()`: "Return the number of processes in the system run queue averaged over the last 1, 5, and 15 minutes or raises OSError if the load average was unobtainable."

`os.process_cpu_count()` (logical CPUs in current process) < `os.cpu_count()` (logical CPUS in the __system__)

#### Python resource module 

- https://docs.python.org/library/resource.html#resource-usage
- http://man7.org/linux/man-pages/man2/getrusage.2.html
- https://stackoverflow.com/questions/938733/total-memory-used-by-python-process
 
`RUSAGE_BOTH`:  Pass to getrusage() to request resources consumed by both the current process and child processes.
`RUSAGE_CHILDREN`: Pass to getrusage() to request resources consumed by child processes of the calling process which have been terminated and waited for.

| index | field      | resource                     |
|-------|------------|------------------------------|
| 2     | ru_maxrss  | maximum resident set size    |
| 3     | ru_ixrss   | shared memory size           |
| 4     | ru_idrss   | unshared memory size         |
| 5     | ru_isrss   | unshared stack size          |
| 9     | ru_inblock | block input operations       |
| 10    | ru_oublock | block output operations      |
| 14    | ru_nvcsw   | voluntary context switches   |
| 15    | ru_nivcsw  | involuntary context switches |

`resource.getrlimit(resource)`: Returns a tuple (soft, hard) with the current soft and hard limits of resource.
These are useful but platform dependent. We may still want to respect these, especially `RLIMIT_CPU`, `RLIMIT_NPROC` and `RLIMIT_RSS`.
A value of `RLIM_INFINITY` is unlimited.

## TODO:

- Consider allowing thresholding by task labels.
