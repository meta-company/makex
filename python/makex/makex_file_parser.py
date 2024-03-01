import logging
import sys
import time
from collections import deque
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from os import PathLike
from pathlib import Path
from threading import (
    Event,
    current_thread,
)
from typing import (
    Iterable,
    Optional,
)

from makex._logging import (
    debug,
    trace,
)
from makex.constants import DIRECT_REFERENCES_TO_MAKEX_FILES
from makex.context import Context
from makex.errors import ExecutionError
from makex.flags import NESTED_WORKSPACES_ENABLED
from makex.makex_file import (
    FindFiles,
    Glob,
    MakexFile,
    MakexFileCycleError,
    PathElement,
    PathObject,
    ResolvedTargetReference,
    TargetObject,
    TargetReferenceElement,
    find_makex_files,
    resolve_path_element_workspace,
    resolve_string_path_workspace,
    resolve_target_output_path,
)
from makex.protocols import (
    FileProtocol,
    TargetProtocol,
)
from makex.python_script import (
    FileLocation,
    PythonScriptError,
    StringValue,
)
from makex.target import TargetKey
from makex.workspace import Workspace


class ParseResult:
    makex_file: MakexFile = None
    errors: deque[PythonScriptError]

    def __init__(self, makex_file=None, errors=None):
        self.errors = errors
        self.makex_file = makex_file


class TargetGraph:
    # NOTE: We use TargetObject here because we use isinstance checks

    targets: list[TargetObject]

    def __init__(self):
        # TODO: we could probably merge TargetKey and file keys and all of these dictionaries.

        # TargetKey -> object
        self.targets: dict[TargetKey, TargetObject] = {}

        # map of TargetKey to all of it's requirements
        self._requires: dict[TargetKey, list[TargetObject]] = {}

        # map of TargetKey to all the Files/paths it provides
        self._provides: dict[TargetKey, list[PathLike]] = {}

        # map from all the files inputting into TargetObject
        self._files_to_target: dict[PathLike, set[TargetObject]] = {}

        # map from TargetKey to all the targets it provides to
        self._provides_to: dict[TargetKey, set[TargetObject]] = {}

    def __contains__(self, item: ResolvedTargetReference):
        return item.key() in self.targets

    def get_target(self, t) -> Optional[TargetObject]:
        #debug("Find %s in %s. key=%s", t, self.targets, t.key())
        return self.targets.get(t.key(), None)

    def in_degree(self) -> Iterable[tuple[TargetObject, int]]:
        for key, target in self.targets.items():
            yield (target, len(self._provides_to.get(key, [])))

    def add_targets(self, ctx: Context, *targets: TargetObject):
        assert isinstance(ctx, Context)
        assert ctx.workspace_object

        for target in targets:
            self.add_target(ctx, target)

    def _process_target_requirements(
        self,
        ctx: Context,
        target: TargetObject,
    ) -> Iterable[TargetObject]:

        target_input_path = target.path_input()
        makex_file_path = Path(target.location.path)

        for require in target.requires:
            if isinstance(require, PathElement):
                # a simple path to a file.. declared as Path() or automatically parsed
                # resolve the input file path
                if False:
                    path = require._as_path()

                    if not path.is_absolute():
                        # make path relative to target
                        path = target_input_path / path

                path = resolve_path_element_workspace(
                    ctx, target.workspace, require, target_input_path
                )

                # point file -> current target
                self._files_to_target.setdefault(path, set()).add(target)
                continue
            elif isinstance(require, TargetObject):
                # add to rdeps map
                self._provides_to.setdefault(require.key(), set()).add(target)
                # add to requires map
                #requirements.append(require)
                # TODO: this is for tests only. should yield a ResolvedTargetReference
                yield require
            elif isinstance(require, TargetReferenceElement):
                # reference to a target, either internal or outside the makex file
                name = require.name.value
                path = require.path

                #trace("reference input is %r: %r", require, path)

                location = require.location
                if isinstance(path, StringValue):
                    # Target(name, "some/path")
                    location = path.location
                    #_path = Path(path.value)
                    _path = resolve_string_path_workspace(
                        ctx, target.workspace, path, target_input_path
                    )
                elif isinstance(path, PathElement):
                    # Target(name, Path())
                    location = path.location

                    _path = resolve_path_element_workspace(
                        ctx, target.workspace, path, target_input_path
                    )
                elif path is None:
                    # Target(name)
                    _path = makex_file_path
                elif isinstance(path, str):
                    # XXX: this is used for testing only. we should not be dealing with str (instead we should a StringValues)
                    location = FileLocation(None, None, target.location)
                    _path = Path(path)
                else:
                    raise ExecutionError(
                        f"Invalid target reference path: Type: {type(path)} {path}",
                        target,
                        getattr(path, "location", None)
                    )

                if not _path.is_absolute():
                    _path = target_input_path / _path

                if _path.is_dir():
                    # find the makexfile it's referring to
                    file = find_makex_files(_path, ctx.makex_file_names)
                    if file is None:
                        raise ExecutionError(
                            f"No makex file found at {_path}. Invalid target reference.",
                            target,
                            path.location
                        )
                else:
                    file = _path

                #trace("Got reference %r %r", name, file)
                #requirements.append(ResolvedTargetReference(name, path))
                yield ResolvedTargetReference(name, file, location=location)
            elif isinstance(require, (FindFiles, Glob)):
                # These things will be resolved in a later pass.
                # TODO: we may want to resolve these early and keep a cache.
                pass
            else:
                raise NotImplementedError(f"Type: {type(require)}")

    def add_target(self, ctx: Context, target: TargetObject):
        # add targetobjects during parsing

        # add all the targets we encountered during evaluation
        self.targets[target.key()] = target

        key = target.key()
        self._requires[key] = requirements = []

        if target.requires:
            #### process the requirements, a list of PathElement(input file) | StringValue | Target
            for requirement in self._process_target_requirements(ctx, target):
                requirements.append(requirement)

        self._provides[key] = provides = []

        #trace("Add target to graph: %r", target)
        output_path, real_path = resolve_target_output_path(ctx, target)

        if output_path:
            pass

        if target.outputs:
            for output in target.all_outputs():
                if isinstance(output, PathElement):
                    output = resolve_path_element_workspace(
                        ctx, target.workspace, output, output_path
                    )
                    #output = output._as_path()

                    #if not output.is_absolute():
                    # make path relative to target
                    #    output = output_path / output
                elif isinstance(output, PathObject):
                    output = output.path
                elif isinstance(output, StringValue):
                    output = Path(output.value)

                    if not output.is_absolute():
                        # make path relative to target
                        output = output_path / output

                elif isinstance(output, (FindFiles, Glob)):
                    pass
                else:
                    raise NotImplementedError(f"Invalid output type {type(output)} {output}")

                provides.append(output)

    def get_requires(
        self,
        target: TargetProtocol,
        recursive=False,
        _seen: set = None,
    ) -> Iterable[TargetObject]:
        # XXX: faster version of get_requires without cycle detection. used by the executor/downstream
        # query the graph for requirements in reverse order (farthest to closest)
        # TODO: we should be able to remove _seen entirely.
        _seen = set() if _seen is None else _seen

        if target in _seen:
            return

        _seen.add(target)

        for requirement in self._requires.get(target.key(), []):
            if requirement in _seen:
                continue

            if recursive:
                yield from self.get_requires(requirement, recursive=recursive, _seen=_seen)

            yield requirement

    def get_requires_detect_cycles(
        self,
        target: TargetProtocol,
        recursive=False,
        _stack: list = None,
        _seen: set = None
    ) -> Iterable[TargetObject]:
        # query the graph for requirements in reverse order (farthest to closest)
        _stack = list() if _stack is None else _stack
        _seen = set() if _seen is None else _seen

        #trace("Get requires and detect cycles %r", target)
        if target in _stack:
            return

        _stack.append(target)

        _seen.add(target)

        for requirement in self._requires.get(target.key(), []):
            requirement: TargetObject = requirement

            if requirement in _seen:
                continue

            if requirement in _stack:
                #error("CYCLES %r: %r", requirement, _seen)
                target = self.targets.get(requirement.key())
                # reverse so we see the most recent file depended on.
                reverse = [self.targets.get(s.key()) for s in reversed(_stack)]
                raise MakexFileCycleError(
                    f"Internal cycle detected: {requirement!r}", target, reverse
                )

            if recursive:
                yield from self.get_requires_detect_cycles(
                    requirement, recursive=recursive, _stack=_stack, _seen=_seen
                )

            yield requirement

        _stack.pop()

    def get_outputs(self, *targets, recursive=False) -> Iterable[FileProtocol]:
        # reverse dependencies of targets
        # targets outputs + outputs for each of targets.requires
        for target in targets:
            yield from self._provides.get(target, [])

            if recursive:
                yield from self.get_outputs(target.requires)

    def topological_sort_grouped(self: "TargetGraph", start: list[TargetObject]):
        # For testing purposes.
        indegree_map = {v: d for v, d in self.in_degree() if d > 0}
        zero_indegree = [v for v, d in self.in_degree() if d == 0]

        while zero_indegree:
            yield zero_indegree
            new_zero_indegree = []
            for v in zero_indegree:
                for child in self.get_requires_detect_cycles(v):
                    indegree_map[child] -= 1
                    if not indegree_map[child]:
                        new_zero_indegree.append(child)
            zero_indegree = new_zero_indegree


def parse_makefile_into_graph(
    ctx: Context,
    path: Path,
    graph: TargetGraph,
    threads=2,
    allow_makex_files=DIRECT_REFERENCES_TO_MAKEX_FILES,
) -> ParseResult:
    assert ctx.workspace_object

    # link from path -> path so we can detect cycles
    linkages: dict[ResolvedTargetReference, list[ResolvedTargetReference]] = {}

    # set this event to stop the parsing loop
    stop = Event()

    # any errors collected during parsing
    errors = deque()

    # any makefiles completed (either success or error)
    completed: deque[Path] = deque()

    # paths added to thread pool ready to parse
    executing: deque[Path] = deque()

    # waiting to be queued for work; requirements added from other files
    input_queue: deque[Path] = deque([path])

    _initial = path
    _finished: dict[Path, MakexFile] = {}

    def stop_and_error(error):
        stop.set()
        errors.append(error)

    def _iterate_target_requires(
        makefile_path: Path,
        makefile: MakexFile,
        target: TargetObject,
    ) -> Iterable[ResolvedTargetReference]:
        # yields a list of Paths the specified makefile requires
        #debug("Check requires %s -> %s", target, target.requires)
        #target_input = makefile.directory
        target_input = target.path_input()
        workspace = target.workspace

        assert isinstance(workspace, Workspace)

        for require in target.requires:
            trace("Process requirement %s", require)
            if isinstance(require, TargetObject):
                # we have a Target object.
                # TODO: This is used in testing. Not really important.
                # Manually constructed target objects.
                trace("Yield target", require)
                makex_file = require.makex_file_path
                yield ResolvedTargetReference(
                    require.name, Path(makex_file), location=require.location
                )

            elif isinstance(require, TargetReferenceElement):
                name = require.name
                path = require.path
                #debug("Got reference %s %s", name, path)
                if isinstance(path, StringValue):
                    # Target(name, "path/to/target")
                    #trace("Path is string value: %r", path)
                    search_path = resolve_string_path_workspace(
                        ctx, target.workspace, path, target_input
                    )

                    trace("Resolve search path from string %r: %s", path, search_path)
                    # we could have a directory, or we could have a file
                    if search_path.is_file():
                        if allow_makex_files:
                            yield ResolvedTargetReference(name, search_path, path.location)
                            continue
                        else:
                            error = ExecutionError(
                                "References directly to makex files are not allowed."
                                " Strip the makex file name.",
                                target,
                                path.location
                            )
                            stop_and_error(error)
                            raise error
                    #trace("Searching path for makex files: %s", search_path)
                    makex_file = find_makex_files(search_path, ctx.makex_file_names)

                    trace("Resolved makex file from string %s: %s", path, makex_file)
                    if makex_file is None:
                        error = ExecutionError(
                            f"No makex files found in path {search_path} {path!r} for the target's requirements."
                            f" Tried: {ctx.makex_file_names!r} {target}",
                            target,
                            path.location
                        )
                        stop_and_error(error)
                        raise error
                    yield ResolvedTargetReference(name, makex_file, path.location)
                elif isinstance(path, PathElement):
                    # allow users to specify an absolute path to
                    # Target(name, Path("path/to/something")))
                    search_path = resolve_path_element_workspace(
                        ctx, target.workspace, path, target_input
                    )
                    trace("Resolve search path from %r: %s", path, search_path)

                    # we could have a directory, or we could have a file
                    if search_path.is_file():

                        if allow_makex_files:
                            yield ResolvedTargetReference(name, search_path, path.location)
                            continue
                        else:
                            error = ExecutionError(
                                "References directly to makex files are not allowed. Strip the makex file name.",
                                target,
                                path.location
                            )
                            stop_and_error(error)
                            raise error
                            break

                    makex_file = find_makex_files(search_path, ctx.makex_file_names)

                    trace("Resolved makex file from pathelement %s: %s", path, makex_file)
                    if makex_file is None:
                        error = ExecutionError(
                            f"No makex files found in path {search_path} for the target's requirements.",
                            target,
                            path.location
                        )
                        stop_and_error(error)
                        raise error

                    yield ResolvedTargetReference(name, makex_file, path.location)
                elif path is None:
                    # Target(name)
                    # we're referring to this file. we don't need to parse anything.
                    yield ResolvedTargetReference(name, makefile_path, require.location)
                else:
                    debug("Invalid ref type %s: %r", type(path), path)
                    exc = Exception(f"Invalid reference path type {type(path)}: {path!r}")
                    stop_and_error(exc)
                    raise exc


    def finished(makefile_path: Path, makefile: Future[MakexFile]):
        makefile_path = Path(makefile_path)
        trace("Makefile parsing finished in thread %s: %s", current_thread().ident, makefile_path)

        e = makefile.exception()
        if e:
            if not isinstance(e, (ExecutionError, PythonScriptError)):
                logging.error("Makefile had an error %s %r", e, e)
                logging.exception(e)

            stop_and_error(e)
            mark_path_finished(makefile_path)
            return

        makefile = makefile.result()

        _finished[makefile_path] = makefile

        if makefile.targets:
            trace(
                "Adding %d targets from makefile...",
                len(makefile.targets), #makefile.targets[:min(3, len(makefile.targets))]
            )

            # we're done. add the target references to the parsing input queue
            for target_name, target in makefile.targets.items():
                trace("Add target to graph %s %s ", target, target.key())
                try:
                    graph.add_target(ctx, target)
                except ExecutionError as e:
                    stop_and_error(e)
                    mark_path_finished(makefile_path)
                    return

                t_as_ref = ResolvedTargetReference(
                    target.name, Path(target.makex_file_path), target.location
                )

                trace("Check requires %s -> %r", target.key(), target.requires)

                # TODO: store this iteration for later (target evaluation in Executor)
                #  we're duplicating code there.
                iterable = _iterate_target_requires(
                    makefile=makefile,
                    makefile_path=makefile_path,
                    target=target,
                )
                for reference in iterable:
                    # Check for any cycles BETWEEN files and targets.
                    cycles = linkages.get(reference, None)
                    #trace("Linkages of %s: %s", reference, cycles)
                    linkages.setdefault(t_as_ref, list()).append(reference)
                    if cycles and (t_as_ref in cycles):
                        mark_path_finished(makefile_path)
                        error = MakexFileCycleError(
                            f"Cycle detected from {reference.key()} to {cycles[-1].key()}",
                            target,
                            cycles,
                        )
                        stop_and_error(error)
                        raise error

                    #trace("Got required path %s", reference)
                    if reference.path in completed:
                        trace("Path already completed %s. Possible cycle.", reference)
                        continue

                    trace("Add to parsing input queue %s", reference)
                    input_queue.append(reference.path)
                    target.add_resolved_requirement(reference)

        trace("Remove from deque %s", makefile_path)
        mark_path_finished(makefile_path)

    def mark_path_finished(makefile_path: Path):
        completed.append(makefile_path)

        if makefile_path in executing:
            executing.remove(makefile_path)

    def parse(ctx:Context, path:Path, workspace:Workspace):
        # We're in a parse thread...

        # TODO: keep the makex file data in memory since it's probably small.

        # TODO: create a checksum of the file here.
        # TODO: check the cache for an ast. if no ast in cache, create one by parsing.
        # TODO: the ast will be annotated with FileLocation

        """
        TODO: use the following object for caching. we need to pickle it.
        class FileMetadata:
            # the path of the file
            path: str

            # the ast of the file
            ast: ast.AST

            # files that were included
            includes: list[str]

            # checksum of the file at the time of parsing
            checksum: str

            # original source text
            source: str

        # load the includes into the cache so include() works as intended. then, parse the specified path
        for include in metadata.includes:
            parse(ctx, include, workspace)
        """
        return MakexFile.parse(ctx, path, workspace)

    pool = ThreadPoolExecutor(threads)

    try:
        while stop.is_set() is False:

            if len(input_queue) == 0:
                debug("Stopped. Empty queue.")
                stop.set()
                continue

            while len(executing) == threads:
                # TODO: leave extra threads for include processing?
                debug("queue wait. %s", executing)
                time.sleep(0.1)

            path = input_queue.pop()

            if path in executing:
                # The path is currently executing. Wait.
                input_queue.append(path)
                time.sleep(0.1)
                continue

            if path not in completed:
                # Path not executing, and not completed, queue it on pool...
                if NESTED_WORKSPACES_ENABLED:
                    workspace_of_makefile: Workspace = ctx.workspace_cache.get_workspace_of(path)
                    trace(
                        "Detected workspace of makefile at path %s: %s",
                        path,
                        workspace_of_makefile
                    )
                else:
                    # Use the root/initial workspace if no nesting.
                    workspace_of_makefile = ctx.workspace_object

                debug(
                    "Queue MakeFile for parsing %s (workspace=%s) ...", path, workspace_of_makefile
                )

                f = pool.submit(
                    parse,
                    ctx=ctx,
                    path=Path(path),
                    workspace=workspace_of_makefile,
                )
                # We must use a lambda passing the path because if we have
                #  an Exception we won't know which file caused it.
                f.add_done_callback(lambda future, p=path: finished(p, future))

                executing.append(path)
                input_queue.append(path)
                # XXX: this sleep is required so that is_set isn't called repeatedly (thousands of times+) when running.
                time.sleep(0.1)

    finally:
        debug("Wait for pool to shutdown...")
        pool.shutdown()

    return ParseResult(makex_file=_finished.get(_initial), errors=errors)


def parse_target_string_reference(
    ctx: Context,
    base,
    string,
    check=True,
) -> Optional[ResolvedTargetReference]:
    # resolve the path/makefile?:target_or_build_path name
    # return name/Path
    parts = string.split(":", 1)
    if len(parts) == 2:
        path, target = parts
        path = Path(path)
        if not path.is_absolute():
            path = base / path

        if path.is_symlink():
            path = path.readlink()
    else:
        target = parts[0]
        path = base

    if path.is_dir():
        if check:
            # check for Build/Makexfile in path
            path, checked = find_makex_files(path, ctx.makex_file_names)
            if path is None:
                ctx.ui.print(
                    f"Makex file does not exist for target specified: {target}", error=True
                )
                for check in checked:
                    ctx.ui.print(f"- Checked in {check}")
                sys.exit(-1)

    return ResolvedTargetReference(target, path=path)
