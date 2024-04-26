import logging
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
    STORE_TASK_HASH_IN_OUTPUT_FILES,
    SYMLINK_PER_TARGET_ENABLED,
)
from makex.context import Context
from makex.errors import (
    ExecutionError,
    MultipleErrors,
)
from makex.file_checksum import FileChecksum
from makex.makex_file import (
    InternalActionBase,
    MakexFileCycleError,
    TargetObject,
    find_makex_files,
    resolve_find_files,
    resolve_glob,
    resolve_path_element_workspace,
    resolve_string_path_workspace,
    resolve_target_output_path,
)
from makex.makex_file_types import (
    FindFiles,
    Glob,
    ListTypes,
    PathElement,
    PathObject,
    ResolvedTargetReference,
    TargetReferenceElement,
)
from makex.metadata_sqlite import SqliteMetadataBackend
from makex.protocols import FileStatus
from makex.python_script import (
    FileLocation,
    PythonScriptError,
    StringValue,
)
from makex.target import (
    EvaluatedTarget,
    EvaluatedTargetGraph,
    InternalAction,
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


_XATTR_OUTPUT_TARGET_HASH = b"user.makex.target_hash"

from os import (
    getxattr,
    removexattr,
    setxattr,
)


def _get_xattr(path, attribute: bytes):
    try:
        return getxattr(path, attribute)
    except OSError as e:
        if e.errno == 61:
            return b""
        raise e


def _set_xattr(path, attribute: bytes, value: bytes):
    return setxattr(path, attribute, value)


def _remove_xattr(path, attribute):
    return removexattr(path, attribute)


def figure_out_location(obj, default):
    location = getattr(obj, "location", None)

    if location and isinstance(location, FileLocation):
        return location
    else:
        location = None

    if location is None: # or isinstance(obj, FileLocation) is False:
        return default

    return location


# TODO: this method should be moved to the makex file module. _resolve_pathlike() fits the bill.
def _transform_output_to_path(
    ctx, target, base: Path, value: Union[StringValue, PathElement, PathObject]
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


ExecuteResult = tuple[list[EvaluatedTarget], deque[Exception]]


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
    # sqlite objects can't be accessed from a different thread, so we'd need to recreate connections per each, or,
    # keep a queue.
    _database_queue: deque[EvaluatedTarget]

    _executed_keys: set[str]

    def __init__(self, ctx: "Context", workers=1, force=False):
        self.ctx = ctx
        self._workers = workers
        self.force = force
        self.analysis_mode = False

        # our input
        self._graph_1 = ctx.graph

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

    def _are_dependencies_executed(self, check_target: ResolvedTargetReference):
        try:
            # we don't need to use the cycle checking get_requires here because they've already been loaded into the graph.
            requires = self._graph_1.get_requires(check_target)
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

        # keep the target hashes around for the life of the Executor. Uncomment for development.
        #self._target_hash = {}

        # XXX: must be reset every time we run an execute. Hashes of specific keys may change between runs.
        self._hash_cache = {}

        self._executed_keys = set()

    def _store_database(self, target):
        if self.ctx.dry_run:
            return

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
                # add the dependencies of target first, in order
                # add to waiting so we can fetch them later
                if True:
                    # CODE DUPLICATION
                    trace("Queue recursive deps of %s", resolved_target)
                    try:
                        # add all the possible requirements to waiting queue
                        for req in self._graph_1.get_requires_detect_cycles(
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

                if self.errors:
                    debug("Execution had errors. Stopping")
                    break

                #target = self.waiting.pop(0)
                target = self.waiting.popleft()
                debug("Pop waiting %s: %s", target, target.key())

                if target.key() in self.queued:
                    # Target has been already queued for execution. Wait until it is done.
                    debug("target queued. skip: %s", target.key())
                    continue

                if isinstance(target, ResolvedTargetReference):
                    resolved_target = self._graph_1.get_target(target)

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
                    if self._are_dependencies_executed(resolved_target):
                        evaluated, errors = self._execute_target(target)
                        if errors:
                            self.errors.extend(errors)
                            self.stop.set()
                    else:
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

        # XXX: We must call this here to flush any queued to the database before we execute again.
        self._write_queued_to_database()

        return self.finished, self.errors

    def _checksum_file(self, path: Path) -> FileChecksum:
        if self._supports_extended_attribute is False:
            # we need to store the checksum in a database sidecar
            # store the checksum in the database
            if DATABASE_ENABLED is False:
                raise NotImplementedError("No where to store file checksum.")

            fingerprint = FileChecksum.get_fingerprint(path)

            string_path = str(path)

            checksum = self._disk_metadata.get_file_checksum(string_path, fingerprint)

            if checksum is None:
                # db doesn't have checksum. create one and store it.
                checksum = FileChecksum.make(path, fingerprint)
                self._disk_metadata.put_file(
                    string_path,
                    fingerprint=checksum.fingerprint,
                    checksum_type=checksum.type.value,
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
            # XXX: FS doesn't support xattr. Use the database to store/retrieve checksums.
            if DATABASE_ENABLED is False:
                raise NotImplementedError("No where to check file checksum validity.")

            fingerprint = FileChecksum.get_fingerprint(path)
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
        debug(
            "Symlink %s [exists=%s,symlink=%s] <- %s [exists=%s,symlink=%s]",
            new_path,
            new_path.exists(),
            new_path.is_symlink(),
            linkpath,
            linkpath.exists(),
            linkpath.is_symlink()
        )

        if linkpath.exists():
            if not linkpath.is_symlink():
                raise Exception(
                    f"Linkpath {linkpath} exists, but it is not a symlink. "
                    f"Output directory may have been created inadvertantly outside the tool."
                )

            realpath = linkpath.readlink().absolute()

            if realpath != new_path:

                if fix:
                    linkpath.unlink()
                    linkpath.symlink_to(new_path, target_is_directory=True)
                else:
                    raise Exception(
                        f"Link {linkpath} exists, but it doesn't point to the right place in the cache ({new_path}). "
                        f"The link currently points to {realpath}. "
                        f"Output directory may have been created inadvertantly outside Makex. "
                        f" Delete or change this link."
                    )
        else:
            # linkpath doesn't exist.
            if linkpath.is_symlink():
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
            #else:
            #    raise ExecutionError(
            #        f"Error creating symlink for target. File at {linkpath} is not a symbolic link.",
            #        target,
            #    )

            if not linkpath.parent.exists():
                logging.debug("Creating parent of linked output directory: %s", linkpath.parent)
                linkpath.parent.mkdir(parents=True)

            linkpath.symlink_to(new_path, target_is_directory=True)

    def _get_output_file_status(self, path: Path) -> FileStatus:
        checksum = None
        if path.exists():
            checksum = self._checksum_file(path)
        status = FileStatus(path, checksum=checksum)
        return status

    def _evaluate_target(self,
                         target: TargetObject,
                         destroy_output=False) -> tuple[EvaluatedTarget, list[Exception]]:
        # transform the target object into an evaluated object
        # check the inputs of target are available
        seen = set()
        target_input_path = target.path_input()
        target_output_path = None
        ctx = self.ctx
        #trace("Input path set to %s", target_input_path)
        inputs = []
        requires: list[EvaluatedTarget] = []
        errors = []

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
                    error = ExecutionError("Missing input file: {node}", target, node.location)
                    errors.append(error)

                    inputs.append(FileStatus(path=path, error=error))
                else:
                    if path.is_dir():
                        continue

                    # checksum the input file if it hasn't been
                    checksum = self._checksum_file(path)
                    seen.add(path)
                    inputs.append(FileStatus(
                        path=path,
                        checksum=checksum,
                    ))
            elif isinstance(node, Glob):
                try:
                    for path in resolve_glob(
                        ctx, target, target_input_path, node, {ctx.output_folder_name}
                    ):
                        checksum = self._checksum_file(path)
                        seen.add(path)
                        inputs.append(FileStatus(
                            path=path,
                            checksum=checksum,
                        ))
                except FileNotFoundError as e:
                    raise PythonScriptError(f"Error finding files: {e}", node.location)

            elif isinstance(node, FindFiles):
                # find(path, pattern, type=file|symlink)
                if node.path:
                    path = resolve_path_element_workspace(
                        ctx, target.workspace, node.path, target_input_path
                    )
                else:
                    path = target_input_path

                # TODO: optimize find
                i = 0

                debug("Searching for files %s: %s", path, node.pattern)
                try:
                    for i, file in enumerate(resolve_find_files(ctx, target, path, node.pattern, ignore_names={ctx.output_folder_name})):
                        #trace("Checksumming input file %s", file)
                        checksum = self._checksum_file(file)
                        seen.add(file)
                        inputs.append(FileStatus(
                            path=file,
                            checksum=checksum,
                        ))
                except FileNotFoundError as e:
                    raise PythonScriptError(f"Error finding files: {e}", node.location)

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
                #debug("Evaluate reference %s: %s: %r %s", name, path, path, node.location if path else None)
                if path is None:
                    # we have a local reference
                    _path = Path(target.makex_file_path)
                    ref = ResolvedTargetReference(name, _path, location=node.location)
                elif isinstance(path, StringValue):
                    _path = resolve_string_path_workspace(
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
                elif isinstance(path, PathObject):
                    # XXX: odd case of referring to a build_path in a target reference
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

        unnamed_outputs: list[FileStatus] = []
        output_dict: dict[Union[int, str, None], Union[FileStatus, list[FileStatus]]] = {
            None: unnamed_outputs
        }

        # only create if we have runs (or somehow, just outputs)
        target_output_path, cache_path = resolve_target_output_path(ctx, target=target)

        if target.outputs:
            #debug("Rewrite output path %r %r %s", target_output_path, target.path, target)
            # TODO: use a method on TargetObject to get/transform outputs
            for k, path_like in target.outputs_dict.items():

                if isinstance(path_like, list):
                    for value in path_like:
                        path = _transform_output_to_path(ctx, target, target_output_path, value)
                        trace("Check target output: %s", path)
                        status = self._get_output_file_status(path)
                        if k is None:
                            unnamed_outputs.append(status)
                        else:
                            output_dict.setdefault(k, []).append(status)

                        outputs.append(status)
                else:
                    path = _transform_output_to_path(ctx, target, target_output_path, path_like)
                    trace("Check target output: %s", path)
                    status = self._get_output_file_status(path)
                    if k is None:
                        unnamed_outputs.append(status)
                    else:
                        output_dict[k] = status

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

        #debug("Pre-eval requires %s", requires)
        # Create a Evaluated target early, which we can pass to Actions so they can easily create arguments (below).
        actions: list[InternalAction] = []
        evaluated = EvaluatedTarget(
            name=target.name,
            path=target_output_path,
            input_path=target_input_path,
            inputs=inputs,
            outputs=outputs,
            output_dict=output_dict,
            # TODO: append these commands in a separate thread
            actions=actions,
            # use the existing requires list for performance
            # we don't need to copy/recreate here because they key/serialize the same
            requires=requires,
            location=target.location,
            cache_path=cache_path,
            makex_file=target.makex_file,
            workspace=target.workspace,
        )

        # TODO: queue target transformation in a separate pool and return a future here (once evaluated)

        if target.commands is not None and isinstance(target.commands, ListTypes) is False:
            location = figure_out_location(target.commands, target.location)
            err = PythonScriptError(
                f"Target actions argument must be a list. Got {target.commands!r}", location
            )
            raise err

        for command in target.commands:
            # TODO: check we actually got a Action
            if isinstance(command, ListTypes):
                for c in command:
                    if isinstance(c, InternalActionBase) is False:
                        location = figure_out_location(c, target.location)

                        err = PythonScriptError(
                            f"Invalid action in target {target}: {c!r}",
                            location,
                        )
                        raise err
                    else:
                        arguments = c.transform_arguments(ctx, evaluated)
                        actions.append(InternalAction(c, arguments))
            elif isinstance(command, InternalActionBase) is False:
                location = figure_out_location(command, target.location)

                err = PythonScriptError(
                    f"Invalid action in target {target}: {command!r}",
                    location,
                )
                raise err
            else:
                arguments = command.transform_arguments(ctx, evaluated)
                actions.append(InternalAction(command, arguments))

        return evaluated, errors

    def _memory_has_target(self, hash: str):
        return hash in self._target_hash

    def _check_target_dirty(
        self,
        evaluated: EvaluatedTarget,
        h=None,
    ) -> tuple[bool, list[Exception]]:

        h = h or self._get_target_hash(evaluated)
        target_key = evaluated.key()

        trace(f"Target hash is: %s of %r (exists=%s)", h, target_key, h in self._target_hash)

        if target_key in self._executed_keys:
            # we just executed this target, report it as dirty.
            # TODO: determine if this is correct.
            trace(f"Target is dirty because it was just executed in this process. (%s)", target_key)
            return True, []

        # TODO: we need to cache dirty checking so this doesn't go too deep.
        for require in evaluated.requires:
            dirty, _ = self._check_target_dirty(require)
            if dirty:
                trace("Requirement of %s is dirty: %s", evaluated.key(), require.key())
                return True, []

        # XXX: Targets without any outputs are always dirty. We can't compare the outputs.
        if len(evaluated.outputs) == 0:
            trace(f"Target is dirty because it has no declared outputs. (%s)", target_key)
            return True, []

        # XXX: Targets with outputs, but without any input files or requirements are always dirty.
        if len(evaluated.inputs) == 0 and len(evaluated.requires) == 0:
            trace(f"Target is dirty because it has no requirements or inputs. (%s)", target_key)
            return True, []

        # First, Check the in-memory cache
        target_dirty = self._memory_has_target(h) is False

        errors = []

        _outputs_checked = False
        # Next, Check if the [shared] disk cache has the target
        if DATABASE_ENABLED:
            if True: # only check if the in memory is empty
                db_has_target = self._disk_metadata.has_target(target_key, h)

                # We need to verify the outputs here because it's possible they are missing/screwed up, and we were not the ones who produced the target.
                if db_has_target is True:
                    debug(
                        f"Target in database. Checking outputs... (%r, hash=%r).",
                        evaluated.key(),
                        h
                    )

                    if self._check_outputs_stale_or_missing(evaluated, h):
                        # db has a target produced with the specified hash. outputs are still valid.
                        debug(f"Target is dirty because the outputs are stale (%r).", target_key)
                        target_dirty = True
                    else:
                        debug(f"Outputs of target are not stale (%r, hash=%r).", target_key, h)
                        target_dirty = False

                    _outputs_checked = True
                else:
                    debug(
                        f"Target is dirty because the database doesn't have the target (%r, hash=%r).",
                        target_key,
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
                target_key,
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

        if _outputs_checked is False and target_dirty is False:
            # check for any missing outputs...
            target_dirty = self._check_outputs_stale_or_missing(evaluated, None)

        return target_dirty, errors

    def _remove_from_queue(self, target):
        try:
            self.queued.remove(target.key())
        except ValueError as e:
            error("Can't find %s in %s %r", target.key(), self.queued, target)
            raise e from e

    def _mark_target_complete(self, target: EvaluatedTarget):
        # Mark a target as complete. This is called when the target is not dirty.
        self._target_status[target.key()] = True

    def _mark_target_executed(self, target: EvaluatedTarget):
        # Mark the target as actually executed; like, a thread was created to run it.
        if target not in self.finished:
            self.finished.append(target)
            self._executed_keys.add(target.key())

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
        #  Otherwise, the Target mights not be cached/stored properly because of a long running Target/process
        #  (e.g. a development server target) we're just about to execute that doesn't terminate properly.

        # TODO: handle the database problem and endless targets better
        #if target.endless:
        self._write_queued_to_database()

        if target.path:
            if target.path.resolved:
                # XXX: a fully resolved path was passed to the target output
                #  Don't delete because it could be somewhere on the users filesystem which they don't expect to be deleted.
                # TODO: we should remove this branch once we remove use of Target.path
                delete_output = False
            else:
                delete_output = True
        else:
            delete_output = True

        debug(f"Begin evaluate target {target}...")
        # queue the requirements for execution if all dependencies are completed
        try:
            evaluated, errors = self._evaluate_target(target)

            if errors:
                raise MultipleErrors(errors)
        except (PythonScriptError, ExecutionError) as e:
            #logging.exception(e)
            #self.errors.append(e)
            # XXX: target evaluation errors must stop all execution.
            #self.stop.set()
            return None, [e]

        # TODO: have a future here; once complete, then enable the actual execution. evaluations may come out of order,
        #  so, we have to synchronize the evaluation order with the intended execution order
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
        
        # d evaluates early, add to wait
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
        
        Execute list is ordered correctly, but it is not topographic/parallelized.
        The execute_list/queue is processed similarly; waiting for target dependants to finish before starting the target.
        """

        #self.ctx.ui.print(f"Evaluated target: {target.key()}")
        debug("Evaluated target: %s", evaluated.key())

        self.graph_2.add_target(evaluated)

        target_dirty, errors = self._check_target_dirty(evaluated)

        # all([]) -> True
        #target_dirty = all(checksums)

        if self.analysis_mode is True:
            # XXX: make sure to mark complete so we don't hang.
            self._mark_target_complete(evaluated)
            return evaluated, errors

        if errors:
            # STOP NOW, Raise errors
            raise MultipleErrors(errors)

        if self.force:
            # force the execution
            self._queue_target_on_pool(evaluated, delete_output, hash)
            return evaluated, None

        # dirty checking applicable
        if target_dirty is False:
            self._mark_target_complete(evaluated)
            #self._queue_for_database(evaluated)
            debug("Skipping target. Not dirty: %s", evaluated.key())
            return evaluated, None

        info("Target has been deemed dirty. Queueing for execution: %s", evaluated.key())
        self._queue_target_on_pool(evaluated, delete_output, hash)
        return evaluated, None

    def _queue_target_on_pool(self, evaluated: EvaluatedTarget, delete_output, hash) -> None:
        # TODO: we should get a future here.
        #  if there was an exception, stop everything, both execution and evaluation.
        #  if all the requirements have evaluated (or no requirements), execute.
        #  if not, add to execute wait queue.
        #  process execute wait queue each for each call. check if target all of each targets deps have finished evaluation
        #   if all of the deps have evaluated, push onto execute queue
        #   if none or only some of the deps have evaluated, keep it waiting
        #info(f"Queue target for execution {evaluated}")

        cache_exists = evaluated.cache_path.exists()
        if cache_exists:
            if REMOVE_CACHE_DIRTY_TARGETS_ENABLED and delete_output:
                debug(
                    "Removing cache of %s (%s) because target is dirty.",
                    evaluated.key(),
                    evaluated.cache_path
                )
                # remove the cache if the target is dirty
                rmtree(evaluated.cache_path)
                evaluated.cache_path.unlink(missing_ok=True)

                logging.debug("Creating output directory %s", evaluated.cache_path)
                evaluated.cache_path.mkdir(parents=True, exist_ok=True)
        # create a single link from _output_ to cache's _output_
        elif cache_exists is False:
            logging.debug("Creating output directory %s", evaluated.cache_path)
            evaluated.cache_path.mkdir(parents=True, exist_ok=True)

        debug("Output2 %s", list(evaluated.input_path.iterdir()))
        # autogenerated path
        if SYMLINK_PER_TARGET_ENABLED is False:
            # create link Target.input_path / _output_ -> Target.cache_path.parent (_output_)
            self._create_output_link(evaluated, evaluated.cache_path.parent)
        else:
            # create a link from Target.input_path / _output_ / Target.id - > Target.cache_path
            raise NotImplementedError()

        self.queued.append(evaluated.key())
        future = self.pool.submit(self._execute_target_thread, self.ctx, evaluated, hash)
        future.add_done_callback(lambda future, x=evaluated: self._target_completed(x, future))
        return None

    def _get_last_input_files(self, target: EvaluatedTarget) -> list[Path]:
        metadata = self._load_target_metadata(target)
        if metadata is None:
            return []
        return metadata.inputs

    def _check_output_hash_valid(self, path: Path, hash: str):
        # check the hash stored in the output file matches our target
        if hash != _get_xattr(path, _XATTR_OUTPUT_TARGET_HASH).decode("ascii"):
            trace("Target.hash != output.hash: %s %s", path, hash)
            return False

        return True

    def _check_outputs_stale_or_missing(self, target: EvaluatedTarget, target_hash: str):
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

                # TODO: check if the outputs target hash is different
                if STORE_TASK_HASH_IN_OUTPUT_FILES and self._check_output_hash_valid(
                    path, target_hash
                ) is False:
                    dirty = True
                    break
            else:
                # missing output
                dirty = True
                break
        else: # no break; has no outputs, or all checksums/files exist.
            dirty = False

        return dirty

    def _get_target_output_errors(self, target: EvaluatedTarget) -> list[Exception]:
        # Check outputs are produced after target execution.
        # return errors if they aren't, or if something else is wrong.
        if self.ctx.dry_run:
            # Dry runs can't have any errors because they didn't do anything.
            # TODO: check if this is right.
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

    def _target_completed(self, target: EvaluatedTarget, result: Future[TargetResult]):
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
            if self.ctx.debug or isinstance(exc, (ExecutionError, PythonScriptError)) is False:
                # also show it here on debug mode because it'll get swallowed
                # log unknown/unprintable
                logging.exception(exc)
                pass
            #error("ERROR RUNNING TARGET: %s", result.exception())
            self.errors.append(exc)
            self.stop.set()
            return None

        if True:
            errors = self._get_target_output_errors(target)

            if errors:
                self.errors += errors
                #self.stop.set()
                return None

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

    def _write_target_hash_to_outputs(self, target_hash: bytes, outputs: list[FileStatus]):
        #target_hash_bytes = target_hash.encode("utf-8")
        for output in outputs:
            _set_xattr(output.path, _XATTR_OUTPUT_TARGET_HASH, target_hash)

    def _execute_target_thread(self, ctx: Context, target: EvaluatedTarget, target_hash):
        # this is run in a separate thread...
        debug(f"Begin execution of target: {target} [thread={threading.current_thread().ident}]")

        ctx.ui.print(f"Execute target: {target.key()}")
        output = StringIO()

        # create a copy of the ctx.environment, so we can set ctx.environment variables throughout the process.
        with ctx.new_environment() as subcontext:
            #context = ctx or subcontext
            context = subcontext
            for command in target.actions or []:
                debug(f"- Execute command (%s): %r", target.name, command)

                if self.analysis_mode:
                    continue

                # XXX: right now we want errors from Actions to propagate outwards.
                #try:
                execution = command(context, target)

                if execution is None or execution.status is None:
                    message = f"Action {command!r} did not return a valid output. Got {type(execution)}"
                    raise ExecutionError(message, target, command.location or target.location)

                trace("Execution return status: %s", execution)

                if execution.status != 0: #not in {0, CORRECTED_RETURN_CODE}:
                    # \n\n {execution.output} \n\n {execution.error}
                    string = [
                        f"Error running the action for target ",
                        f"{brief_target_name(context, target, color=True)}:{target.location.line} (exit={execution.status}) \n",
                        f"\tThe process had an error and returned non-zero status code ({execution.status}). See above for any error output."
                    ]
                    raise ExecutionError(
                        "".join(string), target, command.location or target.location
                    )

                if execution.output:
                    # XXX: not required as execution dumps stdout. we may want to capture
                    output.write(execution.output)

                #except Exception as e:
                #    logging.exception(e)
                #   pass

        debug(f"Finished execution of target: {target}")

        if STORE_TASK_HASH_IN_OUTPUT_FILES:
            self._write_target_hash_to_outputs(target_hash, target.outputs)

        return TargetResult(target, output=output.getvalue())
