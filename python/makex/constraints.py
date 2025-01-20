import enum
import logging
import os
from resource import (
    RUSAGE_CHILDREN,
    RUSAGE_SELF,
    RUSAGE_THREAD,
    getrusage,
)
from typing import (
    Iterable,
    Literal,
    Optional,
)

from makex.target import EvaluatedTask

ConstraintName = Literal["memory:minimum"]


class Constraint:
    name: ConstraintName
    value: int
    labels: Optional[set[str]]

    def __init__(self, name, value, labels=None):
        self.name = name
        self.value = value
        self.labels = labels

    def __repr__(self):
        return f"Constraint({self.name!r}, {self.value!r}, labels={self.labels!r})"


class ConstraintOptions:
    def __init__(self):
        self._constraints = []

    def add_constraint(self, constraint: Constraint):
        self._constraints.append(constraint)

    def get(self, name, labels: set = None) -> Iterable[Constraint]:
        """
        Get the constraints associated with the given name.
        
        :param name: name of the constraint 
        :param labels: the labels of the task to match constraints.
        :return: 
        """
        for constraint in self._constraints:
            if constraint.name != name:
                continue

            if constraint.labels:
                if labels is None:
                    # constraint is label constrained, and task isn't.
                    continue

                if not (constraint.labels & labels):
                    # constraint doesn't match labels
                    continue

                yield constraint

            yield constraint

    def get_all(self, labels=None) -> dict[ConstraintName, Constraint]:
        """
        Return all constraints; optionally filtered by labels.
        
        The most specific constraint will be returned if there are multiple constraints for the same name.
        
        :param labels: 
        :return: 
        """
        d = {}
        for constraint in self._constraints:
            specificity = 1
            if constraint.labels:
                if labels is None:
                    # constraint is label constrained, and task isn't.
                    continue

                matching_labels = constraint.labels & labels

                if not (matching_labels):
                    # constraint doesn't match labels
                    continue

                specificity = specificity + len(constraint.labels & labels)
                d.setdefault(constraint.name, []).append((specificity, constraint))

            d.setdefault(constraint.name, []).append((specificity, constraint))

        print(d)
        # sort the constraints by specificity, pick the topmost
        return {k: list(sorted(constraints, reverse=True))[0][1] for k, constraints in d.items()}


class Runability(enum.Enum):
    CONTINUE = 1
    DEFER = 2
    ERROR = 3


class Response:
    runablity: Runability
    message: str

    def __init__(self, runability: Runability, message: str = None):
        self.runability = runability
        self.message = message


class MemoryStatus:
    def __init__(self, size, resident, shared, text, data):
        self.size: int = size
        self.resident: int = resident
        self.shared: int = shared
        self.text: int = text
        self.data: int = data


_USAGE_KEYS = {
    'Buffers:',
    'Cached:',
    'MemFree:',
}


class MemoryInfo:
    def __init__(self, free, total, used):
        self.free = free
        self.total = total
        self.used = used


class Linux:
    @staticmethod
    def get_memory_info() -> Optional[MemoryInfo]:
        """
        Free from /proc/meminfo
        :return: 
        """
        try:
            with open('/proc/meminfo', 'r') as file:
                free = 0
                total = 0
                for line in file:
                    parts = line.split()
                    # * 1000 because values are in kB
                    if parts[0] == 'MemTotal:':
                        total = int(parts[1]) * 1000
                    elif parts[0] in _USAGE_KEYS:
                        free += int(parts[1]) * 1000
                used = total - free
                return MemoryInfo(free, total, used)
        except Exception as e:
            logging.exception(e)
            return None

    @staticmethod
    def get_process_memory(pid: int = "self") -> MemoryStatus:
        """
        read from /proc/[pid]/statm
        
        if pid is "self", return self
        
        The columns are:

        size       (1) total program size (same as VmSize in /proc/[pid]/status)
        resident   (2) resident set size (same as VmRSS in /proc/[pid]/status)
        shared     (3) number of resident shared pages (i.e., backed by a file) (same as RssFile+RssShmem in /proc/[pid]/status)
        text       (4) text (code)
        lib        (5) library (unused since Linux 2.6; always 0)
        data       (6) data + stack
        dt         (7) dirty pages (unused since Linux 2.6; always 0)
        
        :param pid: 
        :return: 
        """
        with open(f"/proc/{pid}/statm", "r") as f:
            size, resident, shared, text, library, data, dt = f.readline().split(" ")

            return MemoryStatus(
                size=int(size),
                resident=int(resident),
                shared=int(shared),
                text=int(text),
                data=int(data),
            )


class SystemState:
    # free memory. less than total.
    free_memory: int

    # memory used by all running tasks
    task_memory_used: int

    # total memory available/installed
    total_memory: int

    # memory used by makex and all children
    memory_used: int

    # memory used by the makex process alone
    makex_used: int

    def __init__(
        self,
        free_memory: int,
        task_memory_used: int,
        total_memory: int,
        memory_used: int,
        makex_used: int,
    ):
        self.free_memory = free_memory
        self.task_memory_used = task_memory_used
        self.total_memory = total_memory
        self.memory_used = memory_used
        self.makex_used = makex_used

    @classmethod
    def build(cls, task_threads: list[int] = None):
        #self = getrusage(RUSAGE_SELF)
        #children = getrusage(RUSAGE_CHILDREN)
        #thread = getrusage(RUSAGE_THREAD)

        info = Linux.get_memory_info()
        free_memory = info.free
        memory_used = info.used

        total = info.total
        # alternatively,
        #total = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')

        makex_used = Linux.get_process_memory()

        task_memory_used = None

        for thread in task_threads or []:
            task_memory_used = Linux.get_process_memory(thread).resident

        return cls(
            memory_used=memory_used,
            makex_used=makex_used,
            task_memory_used=task_memory_used,
            free_memory=free_memory,
            total_memory=total,
        )


def can_run_task(
    task: EvaluatedTask,
    options: ConstraintOptions,
    state: SystemState,
) -> Response:
    total_memory = state.total_memory
    free_memory = state.free_memory
    task_memory_used = state.task_memory_used
    memory_used = state.memory_used

    constraints = options.get_all(labels=task.labels)
    # check we are within memory thresholds...

    if False:
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

    if constraint := constraints.get("memory:minimum"):
        minimum_memory = constraint.value

    if minimum_memory is not None:
        if minimum_memory >= total_memory:
            return Response(
                Runability.ERROR,
                message=f"Requires {minimum_memory} bytes. System only has {total_memory} installed.",
            )

        if minimum_memory <= free_memory:
            if minimum_memory <= task_memory_used:
                # memory is available, but it is being used by others
                return Response(
                    Runability.DEFER,
                    message="Wait for other tasks to free up memory resources.",
                )

            # we can't free the memory used by other processes
            return Response(
                Runability.ERROR,
                message=f"Requires {minimum_memory} bytes. System only has {total_memory} free.",
            )

    if False:
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

    # Just let it continue/run...
    return Response(Runability.CONTINUE)
