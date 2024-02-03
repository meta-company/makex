import logging
import os
import signal
import threading
import time
from collections import deque
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from io import StringIO
from pathlib import Path
from shutil import rmtree
from typing import (
    Optional,
    Union,
)

from makex._logging import (
    debug,
    error,
    info,
    trace,
    warning,
)
from makex.constants import (
    DATABASE_ENABLED,
    DATABASE_FILE_NAME,
    REMOVE_CACHE_DIRTY_TARGETS_ENABLED,
    SYMLINK_PER_TARGET_ENABLED,
)
from makex.context import Context
from makex.errors import (
    ExecutionError,
    MakexError,
    MissingInputFileError,
    MissingOutputFileError,
    MultipleErrors,
)
from makex.file_checksum import FileChecksum
from makex.make_file import (
    FindFiles,
    Glob,
    InternalRunnableBase,
    ListTypes,
    MakexFileCycleError,
    PathElement,
    PathObject,
    ResolvedTargetReference,
    TargetObject,
    TargetReferenceElement,
    _resolve_pathlike,
    find_makex_files,
    resolve_find_files,
    resolve_glob,
    resolve_path_element_workspace,
    resolve_string_path_workspace,
    resolve_target_output_path,
)
from makex.metadata_sqlite import SqliteMetadataBackend
from makex.protocols import FileStatus
from makex.python_script import (
    FileLocation,
    PythonScriptError,
    StringValue,
)
from makex.run import get_running_process_ids
from makex.target import (
    EvaluatedTarget,
    EvaluatedTargetGraph,
    InternalRunnable,
    TargetKey,
    brief_target_name,
)


class TargetResult:
    target: TargetObject
    output: str
    errors: list[Exception]

    def __init__(self, target, output=None, errors=None):
        self.target = target
        self.output = output or ""
        self.errors = errors or []


class Executor:
    # pool of threads and work queue
    pool: ThreadPoolExecutor

    # collect errors because the way concurrent.Futures swallows them
    errors: deque[Exception]

    waiting: deque[TargetObject]

    # will stop the loop if set
    stop: threading.Event

    # XXX: using a list here for easier testing/comparison
    finished: list

    # local cache/map of target hash mapping to target
    # hashes are created/store after a target has successful completion
    _target_hash: dict[str, EvaluatedTarget]

    # keeps dictionary of TargetKey -> True if completed/finished
    _target_status: dict[TargetKey, bool]

    # keep a cache of Target hashes because it's slightly expensive
    _hash_cache: dict[TargetKey, str]

    # our output (and state)
    graph_2: EvaluatedTargetGraph

    # queue of object we need to write to database. doing this because of sqlite issues...
    # sqlite objects can't be accessed from different thread, so we'd need to recreate connections per each, or,
    # keep a queue.
    _database_queue: deque[EvaluatedTarget]

    def __init__(self, ctx: "Context", workers=1, force=False):
        self.ctx = ctx
        self._workers = workers
        self.force = force
        self.analysis_mode = False

        # our input
        self.graph_1 = ctx.graph

        self.stop = threading.Event()

        self._target_hash = {}

        self._disk_metadata = SqliteMetadataBackend(ctx.cache / DATABASE_FILE_NAME)

        self._supports_extended_attribute = (
            FileChecksum.check_supported(ctx.workspace_path) and
            FileChecksum.check_supported(ctx.cache)
        )

        if not self._supports_extended_attribute:
            ctx.ui.print(
                "Makex is running on filesystems without extended attribute support.", error=True
            )

        self._reset()

    def _load_target_metadata(self, target: TargetObject) -> EvaluatedTarget:
        # load target information from metadata
        pass

    def are_dependencies_executed(self, check_target: ResolvedTargetReference):
        try:
            # we don't need to use the cycle checking get_requires here because they've already been loaded into the graph.
            requires = self.graph_1.get_requires(check_target)
        except MakexFileCycleError as e:
            self.errors.append(e)
            self.stop.set()
            return False

        if True:
            requires = list(requires)
            debug("Check target requires ready: %s", requires)

        statuses = []
        for target in requires:
            statuses.append(self._target_status.get(target.key(), False))

        return all(statuses)

    ExecuteResult = tuple[list[EvaluatedTarget], deque[Exception]]

    def _reset(self):
        self._database_queue = deque()
        self.graph_2 = EvaluatedTargetGraph()
        self.pool = ThreadPoolExecutor(self._workers)
        self.finished = []
        self.queued = deque()
        self.errors = deque()
        self.waiting = deque()
        self.stop.clear()

        self._target_status = {}

        # keep the target hashes around for the life of the Executor
        #self._target_hash = {}

        # XXX: must be reset every time we run an execute. Hashes of specific keys may change between runs.
        self._hash_cache = {}

    def _store_database(self, target):
        if DATABASE_ENABLED:
            key = target.key()
            hash = self._get_target_hash(target)
            trace("Storing target in database %s (%s)", key, hash)
            self._disk_metadata.put_target(key, hash)

    def execute_targets(self, *targets: TargetObject) -> ExecuteResult:
        """

        This will block/loop in a thread until all the targets are finished.

        :param targets: A list of TargetObjects as provided by the Makex file parsing.
        :param force:
        :return:
        """
        # returns a list of targets finished/completed and any errors/exceptions
        #self.finished = deque()
        self._reset()

        targets = list(targets)

        debug("Execute %s targets: %r...", len(targets), targets[:max(3, len(targets))])
        # execute targets in parallel
        # do a dfs for each
        for target in targets:
            if target in self.waiting:
                continue

            resolved_target = ResolvedTargetReference(
                target.name, Path(target.makex_file_path), target.location
            )
            if len(target.requires) == 0:
                # execute immediately. no requirements.
                evaluated, errors = self._execute_target(target)
                if errors:
                    return self.finished, errors

            #elif self.are_dependencies_executed(resolved_target):
            # execute immediately. all dependencies are resolved.
            # all dependencies of target are already executed.
            #trace("Execute initial")
            #    self._execute_target(target)
            else:
                # if not isinstance(target, TargetObject):
                #     raise ValueError(f"Invalid target:{target}: {type(target)} {target!r}")

                # add the depedencies of target first, in order
                # add to waiting so we can fetch them later
                if True:
                    # CODE DUPLICATION
                    trace("Queue recursive deps of %s", resolved_target)
                    try:
                        # add all the possible requirements to waiting queue
                        for req in self.graph_1.get_requires_detect_cycles(
                            resolved_target, recursive=True
                        ):
                            trace("Add to waiting %r", req)
                            self.waiting.append(req)
                    except MakexFileCycleError as e:
                        return [], [e]

                trace("Add to waiting %r", resolved_target)
                # add the target itself after its dependencies
                self.waiting.append(resolved_target)

        trace("waiting: %s", self.waiting)
        i = 0
        try:
            while self.stop.is_set() is False:
                # loop until we wait on nothing
                if len(self.waiting) == 0:
                    debug("No more targets waiting for processing.")
                    self.stop.set()
                    continue

                while len(self.queued) == self._workers:
                    #trace("Queue wait")
                    time.sleep(0.1)

                #target = self.waiting.pop(0)
                target = self.waiting.popleft()
                debug("pop waiting %s: %s", target, target.key())

                if target.key() in self.queued:
                    # Target has been already queued for execution. Wait until it is done.
                    #print("target queued. skip", target)
                    continue

                if isinstance(target, ResolvedTargetReference):
                    resolved_target = self.graph_1.get_target(target)

                    if resolved_target is None:
                        #raise Exception(f"Could not find target {target.name} in file {target.path}: {target.location}")
                        self.errors.append(
                            ExecutionError(
                                f"Could not find target {target.name} in file {target.path}",
                                target,
                                target.location
                            )
                        )
                        self.stop.set()
                        break

                    target = resolved_target
                    #target =
                    #assert target

                if not target.requires:
                    # Target has no requirements, execute immediately.
                    evaluated, errors = self._execute_target(target)

                    if errors:
                        self.errors.extend(errors)
                        self.stop.set()
                else:
                    resolved_target = ResolvedTargetReference(
                        target.name, Path(target.makex_file_path), target.location
                    )
                    if self.are_dependencies_executed(resolved_target):
                        #print("!!!exec target", target)
                        evaluated, errors = self._execute_target(target)
                        if errors:
                            self.errors.extend(errors)
                            self.stop.set()
                    else:
                        #print("make waiting again", target, target.requires)
                        # there may be errors during dependency checking
                        trace("Add back to waiting %r", target)
                        self.waiting.append(target)
                i += 1
                #if i == 5:
                #    print("early break")
                #    break
        finally:
            debug("Shutdown and wait for tasks to finish...")
            self.pool.shutdown()

        #if self.errors:
        #    for _error in self.errors:
        #        error(_error)

        #if self.errors:
        #    # We really should be in this loop.
        #    # XXX: send a signal to any processes we created.
        #    for pid in get_running_process_ids():
        #        # send a kill because it's more reliable.
        #        os.killpg(os.getpgid(pid), signal.SIGKILL)

        #if not self.ctx.dry_run:
        #    for target in self.finished:
        #        self._store_database(target)

        return self.finished, self.errors

    def _checksum_file(self, path: Path) -> FileChecksum:
        if self._supports_extended_attribute is False:
            # we need to store the checksum in a database sidecar
            # store the checksum in the database
            if DATABASE_ENABLED is False:
                raise NotImplementedError("No where to store file checksum.")

            fingerprint = FileChecksum.fingerprint(path)

            string_path = str(path)

            checksum = self._disk_metadata.get_file_checksum(string_path, fingerprint)

            if checksum is None:
                # db doesn't have checksum. create one and store it.
                checksum = FileChecksum.make(path, fingerprint)
                self._disk_metadata.put_file(
                    string_path,
                    fingerprint=checksum.fingerprint,
                    checksum_type=checksum.type,
                    checksum=checksum.value,
                )
        else:
            # filechecksum class handles the caching part
            checksum = FileChecksum.create(path)
        return checksum

    def _is_checksum_stale(self, path, checksum: FileChecksum = None):

        if False:
            status = self.metadata.get_file_status(path)
            if status.checksum == checksum:
                return False

        if self._supports_extended_attribute is False:
            if DATABASE_ENABLED is False:
                raise NotImplementedError("No where to check file checksum validity.")

            fingerprint = FileChecksum.fingerprint(path)
            string_path = str(path)

            database_checksum = self._disk_metadata.get_file_checksum(string_path, fingerprint)
            if database_checksum is None:
                return True

            if checksum != database_checksum:
                return True

            return False
        else:
            # filechecksum class handles the caching part
            return FileChecksum.is_fingerprint_valid(path) is False

    def _create_output_link(self, target: EvaluatedTarget, cache: Path, fix=False):
        # TODO: optimize this upwards so it isn't called for each target. or use a filesystem cache
        # link from src() / "_output_" to cache
        linkpath = target.input_path / self.ctx.output_folder_name
        new_path = cache
        if linkpath.exists():
            if not linkpath.is_symlink():
                raise Exception(
                    f"Linkpath {linkpath} exists, but it is not a symlink. Output directory may have been created inadvertantly outside the tool."
                )

            realpath = linkpath.readlink().absolute()

            if realpath != new_path:
                raise Exception(
                    f"Link {linkpath} exists, but it doesn't point to the right place in the cache ({new_path}). "
                    f"The link currently points to {realpath}."
                    f"Output directory may have been created inadvertantly outside Makex. "
                    f" Delete or change this link."
                )
        else:
            if linkpath.exists() is False and linkpath.is_symlink():
                # we have a broken symlink
                if fix:
                    # fix broken links automatically
                    realpath = linkpath.readlink().absolute()
                    logging.debug(
                        "Fixing broken link from %s to %s. Unlinking %s",
                        linkpath,
                        realpath,
                        linkpath
                    )
                    linkpath.unlink()
                else:
                    raise Exception(
                        f"There's a broken link at {linkpath}. Delete or change this link."
                    )

            if not linkpath.parent.exists():
                logging.debug("Creating parent of linked output directory: %s", linkpath.parent)
                linkpath.parent.mkdir(parents=True)

            logging.debug(
                "Symlink %s[%s,symlink=%s] <- %s[%s,symlink=%s]",
                new_path,
                new_path.exists(),
                new_path.is_symlink(),
                linkpath,
                linkpath.exists(),
                linkpath.is_symlink()
            )
            linkpath.symlink_to(new_path, target_is_directory=True)
        #if not lpath.exists():
        #    lpath.symlink_to(cache)
        #else:
        #    if not lpath.is_symlink():
        #        raise ExecutionError(
        #            f"Error creating symlink for target. File at {lpath} is not a symbolic link.",
        #            target
        #        )

    def _evaluate_target(self, target: TargetObject, destroy_output=False) -> EvaluatedTarget:
        # transform the target object into an evaluated object
        # check the inputs of target are available
        seen = set()
        target_input_path = target.path_input()
        target_output_path = None
        ctx = self.ctx
        #trace("Input path set to %s", target_input_path)
        inputs = []
        requires: list[EvaluatedTarget] = []

        # We may have any number of objects passed in target(requires=[]).
        # Translate them for the EvaluatedTarget.
        # XXX: there's some duplication here with _iterate_makefile_requirements
        # XXX: most of this should be duck-typed with a _evaluate() method on the Element. However,
        #  since nodes are part of the makex file scripting api, we can't just expose hidden methods on objects.
        for node in target.requires:
            #trace("Process requirement %r", node)
            if isinstance(node, PathElement):
                path = resolve_path_element_workspace(
                    ctx, target.workspace, node, target_input_path
                )

                if not path.exists():
                    inputs.append(
                        FileStatus(
                            path=path,
                            error=ExecutionError(
                                "Missing input file: {node}", target, node.location
                            ),
                        )
                    )
                else:
                    if not path.is_dir():
                        # checksum the input file if it hasn't been
                        checksum = self._checksum_file(path)
                        seen.add(path)
                        inputs.append(FileStatus(
                            path=path,
                            checksum=checksum,
                        ))
            elif isinstance(node, Glob):
                for path in resolve_glob(
                    ctx, target, target_input_path, node, {ctx.output_folder_name}
                ):
                    #for path in find_files(
                    #    target_input_path, pattern, ignore_names={ctx.output_folder_name}
                    #):
                    #path = Path(path)

                    checksum = self._checksum_file(path)
                    seen.add(path)
                    inputs.append(FileStatus(
                        path=path,
                        checksum=checksum,
                    ))
            elif isinstance(node, FindFiles):
                # find(path, pattern, type=file|symlink)
                if node.path:
                    path = resolve_path_element_workspace(
                        ctx, target.workspace, node.path, target_input_path
                    )
                else:
                    path = target_input_path
                #pattern = node.pattern

                # TODO: optimize find
                i = 0

                debug("Searching for files %s: %s", path, node.pattern)
                for i, file in enumerate(resolve_find_files(ctx, target, path, node.pattern, ignore_names={ctx.output_folder_name})):
                    trace("Checksumming input file %s", file)
                    checksum = self._checksum_file(file)
                    seen.add(file)
                    inputs.append(FileStatus(
                        path=file,
                        checksum=checksum,
                    ))

                if i:
                    debug("Found %s files in %s", i, path)
            elif isinstance(node, StringValue):
                # XXX: This shouldn't happen. StringValues should already be transformed.
                raise NotImplementedError(f"Got {type(node)}: {node}")
            elif isinstance(node, TargetObject):
                # XXX: reference to an internal target
                requirement = self.graph_2.get_target(node)
                requires.append(requirement)
            elif isinstance(node, TargetReferenceElement):
                # XXX: reference to an external target
                # translate the target reference and resolve it
                name = node.name
                # resolve the target reference
                path = node.path
                #debug(
                #    "Evaluate reference %s: %s: %r %s",
                #    name,
                #    path,
                #    path,
                #    node.location if path else None
                #)
                if path is None:
                    # we have a local reference
                    _path = Path(target.makex_file_path)
                    ref = ResolvedTargetReference(name, _path, location=node.location)
                elif isinstance(path, StringValue):
                    _path = resolve_string_path_workspace(
                        ctx, target.workspace, path, target_input_path
                    )
                    #_path = Path(path.value)

                    #if not _path.is_absolute():
                    #    _path = target_input_path / _path

                    # find the makex file inside of path
                    makex_file = find_makex_files(_path, ctx.makex_file_names)

                    if makex_file is None:
                        error = ExecutionError(
                            f"No makex files found in path {_path} for the target's requirements.",
                            target,
                            path.location
                        )
                        #stop_and_error(error)
                        raise error

                    ref = ResolvedTargetReference(name, makex_file, location=path.location)
                elif isinstance(path, PathObject):
                    # XXX: odd case of referring to a build_path in a target referene
                    raise NotImplementedError("")
                elif isinstance(path, PathElement):
                    _path = resolve_path_element_workspace(
                        ctx, target.workspace, path, target_input_path
                    )

                    # find the makex file inside of path
                    makex_file = find_makex_files(_path, ctx.makex_file_names)

                    if makex_file is None:
                        error = ExecutionError(
                            f"No makex files found in path {_path} for the target's requirements.",
                            target,
                            path.location
                        )
                        #stop_and_error(error)
                        raise error

                    ref = ResolvedTargetReference(name, makex_file, location=path.location)
                else:
                    raise NotImplementedError(
                        f"Invalid path in Target Reference. Got {type(path)}: {path}: node={node}"
                    )

                requirement = self.graph_2.get_target(ref)

                if requirement is None:
                    raise ExecutionError(
                        f"Missing requirement in graph: {ref}", target, target.location
                    )
                requires.append(requirement)
            else:
                raise ExecutionError(
                    f"Invalid requirement in target {target.key()} {type(node)}",
                    target,
                    target.location
                )

        outputs: list[FileStatus] = []

        unnamed_outputs = []
        output_dict: dict[Union[str, None], list[FileStatus]] = {None: unnamed_outputs}

        cache_path = None

        # only create if we have runs (or somehow, just outputs)
        #if target.commands or target.outputs:
        target_output_path, cache_path = resolve_target_output_path(ctx, target=target, create=False)

        if target.outputs:
            debug("Rewrite output path %r %r %s", target_output_path, target.path, target)

            def _get_output_file_status(path: Path) -> FileStatus:
                checksum = None
                if path.exists():
                    checksum = self._checksum_file(path)
                status = FileStatus(path, checksum=checksum)
                return status

            # TODO: this method should be moved to the makex file module. _resolve_pathlike() fits the bill.
            def _transform_output_to_path(
                base: Path, value: Union[StringValue, PathElement, PathObject]
            ) -> Path:
                # TODO: we probably won't get any StringValues as they are transformed earlier
                if isinstance(value, StringValue):
                    path = resolve_string_path_workspace(ctx, target.workspace, value, base)
                elif isinstance(value, PathElement):
                    # TODO: we should use the resolved path here
                    path = resolve_path_element_workspace(ctx, target.workspace, value, base)
                elif isinstance(value, PathObject):
                    return value.path
                else:
                    raise NotImplementedError(f"Invalid output type {type(value)}: {value!r}")

                return path

            if target.outputs_dict: # TODO: no branch needed here
                for k, v in target.outputs_dict.items():

                    for value in v:
                        if False:
                            path = _resolve_pathlike(
                                ctx,
                                target,
                                target_output_path,
                                "outputs",
                                value=value,
                                error_string="Invalid output type {type(value)}: {value!r}",
                            )
                        path = _transform_output_to_path(target_output_path, value)
                        trace("Eval outputs %r", path)
                        status = _get_output_file_status(path)
                        if k is None:
                            unnamed_outputs.append(status)
                        else:
                            output_dict.setdefault(k, []).append(status)

                        outputs.append(status)

        # TODO: search for any input files from the last run missing in this one
        if False:
            for file in self._get_last_input_files(target):
                if file not in seen:
                    #errors.append()
                    inputs.append(
                        FileStatus(
                            path=path,
                            error=ExecutionError("Missing input file: {node}", target),
                        )
                    )
                    #errors.append()

        debug("Pre-eval requires %s", requires)
        # Create a Evaluated target early, which we can pass to Runnables so they can easily create arguments (below).
        # XXX:
        runnables = []
        evaluated = EvaluatedTarget(
            name=target.name,
            path=target_output_path,
            input_path=target_input_path,
            inputs=inputs,
            outputs=outputs,
            # TODO: append these commands in a separate thread
            runnables=runnables,
            # use the existing requires list for performance
            # we don't need to copy/recreate here because they key/serialize the same
            requires=requires,
            location=target.location,
            cache_path=cache_path,
            makex_file=target.makex_file,
            workspace=target.workspace,
        )

        # TODO: queue target transformation in a separate pool and return a future here (once evaluated)
        # TODO:

        def figure_out_location(obj, default):
            location = getattr(obj, "location", None)

            if location and isinstance(location, FileLocation):
                return location
            else:
                location = None

            #if location is None and callable(obj):
            #    # XXX: extract the location from the extras added with the python scripting ast
            #    location = FileLocation(
            #        getattr(obj, "_path_"), getattr(obj, "_line_"), getattr(obj, "_column_")
            #    )

            if location is None: # or isinstance(obj, FileLocation) is False:
                return default

            return location

        if target.commands is not None and isinstance(target.commands, ListTypes) is False:
            location = figure_out_location(target.commands, target.location)
            err = PythonScriptError(
                f"Target runs argument must be a list. Got {target.commands!r}", location
            )
            raise err

        for command in target.commands:
            # TODO: check we actually got a runnable

            if isinstance(command, InternalRunnableBase) is False:
                error("Got %s", type(command))

                location = figure_out_location(command, target.location)

                err = PythonScriptError(
                    f"Invalid runnable in target {target}: {command!r}",
                    location,
                )
                raise err

            arguments = command.transform_arguments(ctx, evaluated)
            runnables.append(InternalRunnable(command, arguments))

        return evaluated

    def _memory_has_target(self, hash: str):
        return hash in self._target_hash

    def _check_target_dirty(self, evaluated: EvaluatedTarget) -> tuple[bool, list[Exception]]:

        # XXX: Targets without any outputs are always dirty. We can't compare the outputs.
        if len(evaluated.outputs) == 0:
            trace(f"Target is dirty because it has no outputs. (%s)", evaluated.key())
            return True, []

        # XXX: Targets with outputs, but without any input files or requirements are always dirty.
        if len(evaluated.inputs) == 0 and len(evaluated.requires) == 0:
            trace(
                f"Target is dirty because it has no requirements or inputs. (%s)", evaluated.key()
            )
            return True, []

        h = self._get_target_hash(evaluated)
        trace(f"Target hash is: %s of %r (exists=%s)", h, evaluated.key(), h in self._target_hash)
        # First, Check the in-memory cache
        target_dirty = self._memory_has_target(h) is False

        errors = []

        # Next, Check if the [shared] disk cache has the target
        if DATABASE_ENABLED:
            if True: # only check if the in memory is empty
                db_has_target = self._disk_metadata.has_target(h)

                # We need to verify the outputs here because it's possible they are missing/screwed up, and we were not the ones who produced the target.
                if db_has_target is True:
                    debug(
                        f"Target in database. Checking outputs... (%r, hash=%r).",
                        evaluated.key(),
                        h
                    )
                    if self._check_outputs_stale_or_missing(evaluated):
                        # db has a target produced with the specified hash. outputs are still valid.
                        debug(
                            f"Target is dirty because the outputs are stale (%r).", evaluated.key()
                        )
                        target_dirty = True
                    else:
                        debug(f"Outputs of target are not stale (%r, hash=%r).", evaluated.key(), h)
                        target_dirty = False
                else:
                    debug(
                        f"Target is dirty because the database doesn't have the target (%r, hash=%r).",
                        evaluated.key(),
                        h
                    )
                    target_dirty = True

                if target_dirty is True:
                    return target_dirty, errors

        if target_dirty is False:
            # memory or db has the target
            #debug(f"Skipping target. Not dirty. (%r, hash=%r).", evaluated.key(), h)
            return target_dirty, errors
        else:
            # neither have the target
            debug(
                "Target is dirty because hash isn't in memory or database: (%r, hash=%r)",
                evaluated.key(),
                h,
            )

        if False:
            #hash = evaluated.hash(self.ctx)

            # targets with requires are not dirty by default.
            target_dirty = False

            for input in evaluated.inputs:
                if input.error:
                    # input had an error. mark dirty.
                    errors.append(input.error)
                    target_dirty = True

                if target_dirty:
                    # PERFORMANCE: if we get one we get them all
                    break
                # read the stored checksum/fingerprint for the target
                target_dirty = self._is_checksum_stale(input.path, input.checksum)

                trace(f"Checksum checked for {input.path}: {input.checksum} (dirty={target_dirty})")
                #checksums.append(target_dirty)
            else:
                # targets without any inputs are always dirty.
                target_dirty = True

        if target_dirty is False:
            # check for any missing outputs
            for output in evaluated.outputs:
                path = Path(output.path)
                trace(f"Check output %s: %s", path, path.exists())
                if not path.exists():
                    warning(f"missing output file {output.path}. dirty.")
                    target_dirty = True
            # TODO: check if the outputs target hash is different

        return target_dirty, errors

    def _remove_from_queue(self, target):
        try:
            self.queued.remove(target.key())
        except ValueError as e:
            error("Can't find %s in %s %r", target.key(), self.queued, target)
            raise e from e

    def _mark_target_complete(self, target: EvaluatedTarget, queued=True):
        # queued may be false if we mark it complete before running it
        if queued:
            try:
                self.queued.remove(target.key())
            except ValueError as e:
                error("Can't find %s in %s %r", target.key(), self.queued, target)
                raise e from e

        self._target_status[target.key()] = True

    def _mark_target_executed(self, target: EvaluatedTarget):
        # Mark the target as actually executed; like, a thread was created to run it.
        if target not in self.finished:
            self.finished.append(target)

        try:
            self.queued.remove(target.key())
        except ValueError as e:
            error("Can't find %s in %s %r", target.key(), self.queued, target)
            raise e from e

        self._target_status[target.key()] = True

    def _execute_target(
        self,
        target: TargetObject,
    ) -> tuple[Optional[EvaluatedTarget], Optional[list[Exception]]]:

        # Don't execute any more if we have a stop flag.
        if self.stop.is_set():
            return None, None

        # XXX: Make sure any targets that need to be written are.
        # Otherwise, the Target might not be stored because of a long running Target/process (e.g. a development server target)
        # we're just about to execute.
        self._write_queued_to_database()

        debug(f"Begin evaluate target {target}...")
        # queue the requirements for execution if all dependencies are completed
        try:
            evaluated: EvaluatedTarget = self._evaluate_target(target)
        except (PythonScriptError, ExecutionError) as e:
            #logging.exception(e)
            #self.errors.append(e)
            # XXX: target evaluation errors must stop all execution.
            #self.stop.set()
            return None, [e]
        # TODO: have a future here; once complete, then enable the actual execution. evalutations may come out of order,
        # TODO: so, we have to synchronize the evaluation order with the intended execution order
        """
        
        queue = [a, b, c, d]  # required order of execution, as planned
        
        # put a, b, c and d on evaluation queue/pool (threads=2).
        eval_list = [a, b, c, d]  # queue of things we need to evaluate, futures
        execute_wait_list = [] # finished eval, waiting for exec
        execute_list = []  # queued for execution
        
        # ...
        
        # c evaluates early, needs d. d is still in eval list.
        eval_list = [a, b, d]
        execute_wait_list = [c]
        execute_list = []
        
        # d evauluates early, add to wait
        eval_list = [a, b]
        execute_wait_list = [c,d]
        execute_list = []
        
        # move d to execute because it has no deps
        eval_list = [a, b]
        execute_wait_list = [c]
        execute_list = [d]
        
        # check end of execute_wait_list, see c, all of c in on the execute list.
        # add c to execute 
        eval_list = [a, b]
        execute_wait_list = []
        execute_list = [d, c]
        
        # a evaluates early, but is before/depends b, which hasn't evaluated
        eval_list = [b]
        execute_wait_list = [a]
        execute_list = [d, c]
         
        # b evaluates
        eval_list = []
        execute_wait_list = [a, b]
        execute_list = [d, c]
        
        # execute b because all of it is on execute_list
        eval_list = []
        execute_wait_list = [a]
        execute_list = [d, c, b]
        
        # execute a because all of it is on execute list
        eval_list = []
        execute_wait_list = []
        execute_list = [d, c, b, a]
        
        Execute list is ordered correctly, but it is not topographic, parallelized.
        The execute_list/queue is procesed similarly; waiting for target dependants to finish before starting the target.
        """

        #self.ctx.ui.print(f"Evaluated target: {target.key()}")
        debug("Evaluated target: %s", evaluated.key())

        self.graph_2.add_target(evaluated)

        target_dirty, errors = self._check_target_dirty(evaluated)

        # all([]) -> True
        #target_dirty = all(checksums)

        if self.analysis_mode is True:
            # XXX: make sure to mark complete so we don't hang.
            self._mark_target_complete(evaluated, queued=False)
            return evaluated, errors

        if errors:
            # STOP NOW, Raise errors
            raise MultipleErrors(errors)

        if self.force:
            # force the execution
            self._queue_target_on_pool(evaluated, target_dirty)
            return evaluated, None

        # dirty checking applicable
        if target_dirty is False:
            self._mark_target_complete(evaluated, queued=False)
            #key = target.key()
            #if key in self.queued:
            #    self.queued.remove(key)
            debug("Skipping target. Not dirty. %s", evaluated)
            return evaluated, None

        info("Target has been deemed dirty. Queueing for execution: %s", evaluated.key())
        self._queue_target_on_pool(evaluated, target_dirty)
        return evaluated, None

    def _queue_target_on_pool(self, evaluated: EvaluatedTarget, target_dirty) -> None:
        # TODO: we should get a future here.
        #  if there was an exception, stop everything, both execution and evaluation.
        #  if all the requirements have evaluated (or no requirements), execute.
        #  if not, add to execute wait queue.
        #  process execute wait queue each for each call. check if target all of each targets deps have finished evaluation
        #   if all of the deps have evaluated, push onto execute queue
        #   if none or only some of the deps have evaluated, keep it waiting
        #info(f"Queue target for execution {evaluated}")

        if target_dirty and evaluated.cache_path.exists():
            if REMOVE_CACHE_DIRTY_TARGETS_ENABLED:
                debug("Removing cache of %s (%s) because target is dirty.", evaluated.key(), evaluated.cache_path)
                # remove the cache if the target is dirty
                rmtree(evaluated.cache_path)

        # create a single link from _output_ to cache's _output_
        if not evaluated.cache_path.exists():
            logging.debug("Creating output directory %s", evaluated.cache_path)
            evaluated.cache_path.mkdir(parents=True, exist_ok=True)

        # autogenerated path
        if SYMLINK_PER_TARGET_ENABLED is False:
            # create link Target.input_path / _output_ -> Target.cache_path.parent (_output_)
            self._create_output_link(evaluated, evaluated.cache_path.parent)
        else:
            # create a link from Target.input_path / _output_ / Target.id - > Target.cache_path
            raise NotImplementedError()

        self.queued.append(evaluated.key())
        future = self.pool.submit(self._execute_target_thread, self.ctx, evaluated)
        future.add_done_callback(lambda future, x=evaluated: self.target_completed(x, future))
        return None

    def _get_last_input_files(self, target: EvaluatedTarget) -> list[Path]:
        metadata = self._load_target_metadata(target)
        if metadata is None:
            return []
        return metadata.inputs

    def _check_outputs_stale_or_missing(self, target):
        # Return True if any outputs are missing or stale
        dirty = True
        for output in target.outputs:
            path = output.path
            if path.exists():
                # TODO: do a checksum of the output and compare
                checksum = self._checksum_file(path)

                if self._is_checksum_stale(path, checksum):
                    trace("Checksum of %s is stale: %s", path, checksum)
                    # checksum is not stale
                    dirty = True
                    break
            else:
                # missing output
                dirty = True
                break
        else: # no break; has no outputs, or all checksums/files exist.
            dirty = False

        return dirty

    def get_target_output_errors(self, target: EvaluatedTarget) -> list[Exception]:
        # Check outputs are produced after target execution.
        # return errors if they aren't, or if something else is wrong.
        if self.ctx.dry_run:
            return []

        errors = []
        for output in target.outputs:
            path = output.path
            if not path.exists():
                errors.append(
                    ExecutionError(
                        f"Target failed to create output file. Missing file at: {path}",
                        target,
                        target.location
                    )
                )
        return errors

    def _get_target_hash(self, target: EvaluatedTarget):
        key = target.key()
        hash = self._hash_cache.get(key, None)
        if hash is None:
            hash = self._hash_cache[key] = target.hash(self.ctx, hash_cache=self._target_hash)

        return hash

    def _put_target_hash(self, target: EvaluatedTarget, hash):
        trace("Store target hash %s %s", target.key(), hash)
        self._target_hash[target.key()] = hash

    def target_completed(self, target: EvaluatedTarget, result: Future[TargetResult]):
        # Called after the Future is completed.
        # Called in *this* thread (not the thread in which the target was executed).
        assert isinstance(target, EvaluatedTarget)

        self._mark_target_executed(target)

        debug("Target complete %s", target)

        # store the hash in the cache for later.
        h = self._get_target_hash(target)
        self._put_target_hash(target, h)

        exc = result.exception()
        if exc:
            #logging.debug(exc)
            if self.ctx.debug or not isinstance(exc, (ExecutionError, PythonScriptError)):
                # also show it here on debug mode because it'll get swallowed
                # log unknown/unprintable
                logging.exception(exc)
                pass
            #error("@@@@@@@@ERROR RUNNING TARGET: %s", result.exception())
            #traceback.print_exception(target.exception())
            self.errors.append(exc)
            self.stop.set()
            return

        has_error = False

        if True:
            errors = self.get_target_output_errors(target)

            if errors:
                self.errors += errors
                #self.stop.set()
                #return
                has_error = True

        if has_error:
            return

        # XXX: Store in database as soon as we're done with a success. No later.
        self._queue_for_database(target)

    def _queue_for_database(self, target: EvaluatedTarget):
        if self.ctx.dry_run is True:
            return None

        self._database_queue.append(target)

    def _write_queued_to_database(self):
        if self.ctx.dry_run is True:
            return None

        while self._database_queue:
            target = self._database_queue.popleft()
            trace("Writing queue target %r to database", target.key())
            self._store_database(target)

    def _execute_target_thread(self, ctx: Context, target: EvaluatedTarget):

        # this is run in a separate thread
        debug(f"Begin execution of target: {target} [thread={threading.current_thread().ident}]")

        ctx.ui.print(f"Execute target: {target.key()}")
        output = StringIO()

        # create a copy of the ctx.environment, so we can set ctx.environment variables throughout the process.
        with ctx.new_environment() as subcontext:
            #context = ctx or subcontext
            context = subcontext
            for command in target.runnables or []:
                debug(f"- Execute command (%s): %r", target.name, command)

                if self.analysis_mode:
                    continue

                if True:
                    # XXX: right now we want errors from runnables to propagate outwards.
                    #try:
                    execution = command(context, target)

                    if execution is None or execution.status is None:
                        message = f"Runnable {command!r} did not return a valid output. Got {type(execution)}"
                        raise ExecutionError(message, target, target.location)

                    if execution.status != 0:
                        # \n\n {execution.output} \n\n {execution.error}
                        string = [
                            f"Error running the runnable for target ",
                            f"{brief_target_name(context, target, color=True)}:{target.location.line} (exit={execution.status}) \n",
                            f"\tThe process had an error and returned non-zero status code ({execution.status}). See above for any error output."
                        ]
                        raise ExecutionError("".join(string), target, target.location)

                    if execution.output:
                        # XXX: not required as execution dumps stdout. we may want to capture
                        output.write(execution.output)

                    #except Exception as e:
                    #    logging.exception(e)
                    #   pass

        debug(f"Finished execution of target: {target}")

        return TargetResult(target, output=output.getvalue())

    def execution_completed(self):
        debug("completed!")
