import ast
import logging
import sys
import time
import types
from collections import deque
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from itertools import chain
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
    error,
    trace,
)
from makex.constants import (
    DIRECT_REFERENCES_TO_MAKEX_FILES,
    PASS_GLOBALS_TO_INCLUDE,
)
from makex.context import Context
from makex.errors import ExecutionError
from makex.flags import (
    INCLUDE_MULTIPLE_LEVEL_ENABLED,
    NESTED_WORKSPACES_ENABLED,
)
from makex.makex_file import (
    MACRO_NAMES_MODULE_VARIABLE,
    MACROS_MODULE_VARIABLE,
    TARGETS_MODULE_VARIABLE,
    MakexFile,
    MakexFileCycleError,
    MakexFileScriptEnvironment,
    TargetObject,
    find_makex_files,
    resolve_path_element_workspace,
    resolve_string_path_workspace,
    resolve_target_output_path,
)
from makex.makex_file_types import (
    FindFiles,
    Glob,
    PathElement,
    PathObject,
    ResolvedTargetReference,
    TargetReferenceElement,
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
    graph: Optional["TargetGraph"] = None

    def __init__(self, makex_file=None, errors=None, graph=None):
        self.errors = errors
        self.makex_file = makex_file
        self.graph = graph


class TargetGraph:
    # NOTE: We use TargetObject here because we use isinstance checks

    targets: dict[TargetKey, TargetObject]

    def __init__(self) -> None:
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
        makex_file_path = Path(target.makex_file_path)

        for require in target.requires:
            if isinstance(require, PathElement):
                # a simple path to a file.. declared as Path() or automatically parsed
                # resolve the input file path
                path = resolve_path_element_workspace(
                    ctx, target.workspace, require, target_input_path
                )
                # point file -> current target
                self._files_to_target.setdefault(path, set()).add(target)
                continue
            elif isinstance(require, TargetObject):
                # add to requires/rdeps map
                self._provides_to.setdefault(require.key(), set()).add(target)
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

                trace("Got reference %r %r", name, file)
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
        key = target.key()
        self.targets[key] = target
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

        #if target.outputs:
        for output in target.all_outputs():
            if isinstance(output, PathElement):
                output = resolve_path_element_workspace(ctx, target.workspace, output, output_path)
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
        _seen: Optional[set] = None,
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
        _stack: Optional[list] = None,
        _seen: Optional[set] = None
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
            #requirement: TargetObject = requirement

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


def parse_makefile_into_graph(
    ctx: Context,
    path: Path,
    graph: Optional[TargetGraph] = None,
    threads=2,
    allow_makex_files=DIRECT_REFERENCES_TO_MAKEX_FILES,
) -> ParseResult:
    assert ctx.workspace_object

    graph = graph or TargetGraph()

    # link from path -> path so we can detect cycles
    linkages: dict[ResolvedTargetReference, list[ResolvedTargetReference]] = {}

    # set this event to stop the parsing loop
    stop = Event()

    # any errors collected during parsing
    errors: deque[Exception] = deque()

    # any makefiles completed (either success or error)
    completed: deque[Path] = deque()

    # paths added to thread pool ready to parse
    executing: deque[Path] = deque()

    # waiting to be queued for work; requirements added from other files
    input_queue: deque[Path] = deque([path])

    _initial = path
    _finished: dict[Path, MakexFile] = {}

    # TODO: keep a cache of included/parsed Makex files so we can include them as needed
    makex_file_cache: dict[Path, MakexFile] = {}
    makex_ast_cache: dict[Path, ast.AST] = {}
    makex_module_cache: dict[Path, types.ModuleType] = {}

    # TODO:keep a map of paths checked for relative path resolution so we can skip stat calls
    # eg. we have //file.mx and //somepath/Makefile
    # we are in //somepath/Makexfile and we do include("file.mx")
    # path_check_cache[tuple("//somepath", "file.mx")] = False
    # path_check_cache[tuple("//", "file.mx")] = True
    path_check_cache: dict[tuple[PathLike, str], bool] = {}

    def stop_and_error(_error):
        error("Makexfile parser had an error %s", _error)
        if ctx.debug:
            logging.exception(_error)
        stop.set()
        errors.append(_error)

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
                trace("Yield target: %s", require)
                makex_file = require.makex_file_path
                yield ResolvedTargetReference(
                    require.name, Path(makex_file), location=require.location
                )

            elif isinstance(require, TargetReferenceElement):
                target_name = require.name
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
                            yield ResolvedTargetReference(target_name, search_path, path.location)
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
                    yield ResolvedTargetReference(target_name, makex_file, path.location)
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
                            yield ResolvedTargetReference(target_name, search_path, path.location)
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

                    yield ResolvedTargetReference(target_name, makex_file, path.location)
                elif path is None:
                    # Target(name)
                    # we're referring to this file. we don't need to parse anything.
                    trace(f"Reference to {target_name} doesn't have path, using {makefile_path}")
                    yield ResolvedTargetReference(target_name, makefile_path, require.location)
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
                if ctx.debug:
                    # TODO: Enable if debugging makex. Otherwise disable not to pollute the error messages with tracebacks.
                    logging.error("Makefile had an error %s %r", e, e)
                    logging.exception(e)

            stop_and_error(e)
            mark_path_finished(makefile_path)
            return

        _makefile = makefile.result()

        _finished[makefile_path] = _makefile

        if _makefile.targets:
            trace(
                "Adding %d targets from makefile: %s...",
                len(_makefile.targets),
                _makefile.targets.keys(), #[:min(3, len(makefile.targets))]
            )

            # we're done. add the target references to the parsing input queue
            for target_name, target in _makefile.targets.items():
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
                    makefile=_makefile,
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


    def search_makex_file(
            ctx: Context,
            workspace: Workspace,
            base: Path,
            search_path: str,
            search_parents=True,
    ):
        if search_path.startswith("//"):
            full_path = workspace.path / search_path[2:]

            if not full_path.exists():
                return None
            return full_path

        if search_parents:
            iterable: Iterable[Path] = chain([base], base.parents)
        else:
            iterable = [base]

        for parent in iterable:
            debug(f"Checking for {search_path} in {parent}.")
            full_path = parent / search_path
            key = (full_path, search_path)
            checked = path_check_cache.get(key, None)
            if checked is False:
                # we've checked this search_path+path combo before
                # it didn't find anything. continue.
                # TODO: stop at workspace boundary
                pass
            elif checked is True:
                # we've checked this search_path+path combo before
                # we've found something here.
                return full_path
            else:
                # we need to do a stat call
                exists = full_path.exists()
                path_check_cache[key] = exists

                if exists:
                    return full_path

            if full_path == workspace.path:
                return None

        else: # no break
            # we haven't found anything.
            return None

    def include_function(
        ctx: Context,
        workspace: Workspace,
        base: Path,
        search_path: str,
        makex_file: MakexFile,
        location: FileLocation,
        search=False,
        globals=None,
        stack=None,
        targets=False,
        required=True,
        extra=None,
    ) -> tuple[Optional[types.ModuleType], Optional[MakexFile]]:
        # function used in the environment to include makex files
        # search_path argument is as-is from the Makex file.
        # handles relative and workspace paths.
        stack = stack or []

        full_path = search_makex_file(ctx, workspace, base, search_path, search_parents=search)

        if full_path is None:
            if required:
                raise PythonScriptError(f"Could not find file to include: {search_path}", location)
            else:
                return None, None

        if full_path in stack:
            raise PythonScriptError(f"Include cycle detected at {full_path}", location)

        # if True, use exec to execute module code
        EXECUTE_INCLUDED_MODULE_CODE = True

        _extra_globals = extra or {}

        file = makex_file_cache.get(full_path, None)
        if file is None:
            stack.append(full_path)

            # define an include function bound to our local stack
            if INCLUDE_MULTIPLE_LEVEL_ENABLED:

                def _include(base, search_path, location, stack=stack):
                    return include_function(
                        ctx=ctx,
                        workspace=workspace,
                        base=base,
                        search_path=search_path,
                        makex_file=makex_file,
                        location=location,
                        stack=stack
                    )

            #debug("Including file with globals %s", globals)
            if EXECUTE_INCLUDED_MODULE_CODE:

                file = MakexFile.parse(
                    ctx,
                    full_path,
                    workspace,
                    globals=globals if PASS_GLOBALS_TO_INCLUDE else _extra_globals,
                    #globals=None,
                    include_function=None,
                )
            else:
                debug("Execute code with globals %s", globals)
                file = MakexFile.parse(
                    ctx,
                    full_path,
                    workspace,
                    globals=globals,
                    include_function=None,
                )

            posix_full_path = full_path.as_posix()

            if EXECUTE_INCLUDED_MODULE_CODE is False:
                module = types.ModuleType(search_path)
                module.__file__ = posix_full_path
                # record the list of macros, for performance
                setattr(module, MACROS_MODULE_VARIABLE, file.macros)
                setattr(module, MACRO_NAMES_MODULE_VARIABLE, set(file.macros.keys()))
                # insert the macros into the synthesized modules
                module.__dict__.update(file.macros)
                makex_module_cache[full_path] = module

            makex_file_cache[full_path] = file

        if EXECUTE_INCLUDED_MODULE_CODE:
            # XXX: alternate implementation using cached code objects.
            #makex_file = MakexFile(ctx, Path(location.path))
            #targets = {}
            env = MakexFileScriptEnvironment(
                ctx=ctx,
                directory=full_path.parent,
                path=full_path,
                makex_file=makex_file,
                # we must point to the includers targets dictionary so macros register targets in the includer
                targets=makex_file.targets,
                workspace=workspace
            )

            # block registration of targets unless specified explicitly
            env.block_registration = True if targets is False else False

            new_globals = {**globals, **env.globals(), **_extra_globals}
            #new_globals = {**env.globals()}#, **_extra_globals}
            new_module = types.ModuleType(full_path.as_posix())
            new_module.__file__ = full_path.as_posix()
            new_module.__dict__.update(new_globals)
            debug("Execute code with globals %s", new_globals)
            exec(file.code, new_module.__dict__)

            env.block_registration = False
            #debug("TARGETS %s", env.targets)
            # import the globals in the dict; don't overwrite the imported macros
            #module = pickle_experiment(module)
            #module.__dict__.update(new_globals)
            return new_module, file
        else:
            exclude = set()
            exclude |= getattr(module, MACRO_NAMES_MODULE_VARIABLE, set())
            exclude |= set(TARGETS_MODULE_VARIABLE)
            new_globals = {k: v for k, v in module.__dict__.items() if k not in exclude}
            #debug("Copy module globals %s", new_globals)
            new_module = types.ModuleType(search_path)
            new_module.__dict__.update(new_globals)
            new_module.__dict__[TARGETS_MODULE_VARIABLE] = targets = {}
            return new_module, file

    def import_function(
        ctx, workspace, base, name, globals=None, locals=None, fromlist=(), level=0
    ):
        """
        Returns a new module for import statements.

        We must create a new module with the right context/globals available. path() and target() functions
        used in macros must resolve relative to the importer.

        :param ctx:
        :param workspace:
        :param base:
        :param name:
        :param globals:
        :param locals:
        :param fromlist:
        :param level:
        :return:
        """
        # level = 1 if relative import. e.g from .module import item
        trace("Import requested: %s from %s", fromlist, name)
        #trace("__import__ globals: %s", globals)
        # parse/execute the file, get ast, compile, execute
        #spec = spec_from_file_location(name, "/path.mx", loader=MakexLoader())
        #module = module_from_spec(spec)
        full_path = None

        search_path = f"{name}.mx"
        full_path = search_makex_file(ctx, workspace, base, search_path)

        if full_path is None:
            raise ImportError(f"Could not find file to include: {search_path}")

        #if full_path in stack:
        #    raise PythonScriptError(f"Include cycle detected at {full_path}", location)

        posix_full_path = full_path.as_posix()

        #file = makex_file_cache.get(full_path, None)
        #if file is None:
        if True:
            # stack.append(full_path)
            # define an include function bound to our local stack
            #if MULTIPLE_LEVEL_INCLUDE_ENABLED:
            #    def _include(base, search_path, location, stack=stack):
            #        return include_function(ctx, workspace, base, search_path, location=location, stack=stack)

            debug("Parsing imported file %s", full_path)
            file = MakexFile.parse(
                ctx=ctx,
                path=full_path,
                workspace=workspace,
                globals=globals,
                include_function=None,
            )
            makex_file_cache[posix_full_path] = file

        debug("Adding macros from %s: %s", posix_full_path, file.macros)

        # build and return a module
        module = types.ModuleType(name)
        module.__file__ = posix_full_path
        # XXX: make targets register into included makex file
        #module.__dict__["_TARGETS_"] = globals["_TARGETS_"]

        # insert the macros into the synthesized modules
        module.__dict__.update(file.macros)
        #exec(code, module.__dict__)
        return module

    def parse(ctx: Context, path: Path, workspace: Workspace):
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

        # XXX: a custom import function with arguments bound to our current context
        def _import(*args, ctx=ctx, workspace=workspace, path=path.parent, **kwargs):
            return import_function(ctx, workspace, path, *args, **kwargs)

        return MakexFile.parse(
            ctx,
            path,
            workspace,
            include_function=include_function,
            importer=_import,
        )

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
                #  an Exception, we won't know which file caused it.
                def _done_callback(future, _path=path):
                    finished(_path, future)

                f.add_done_callback(_done_callback)

                executing.append(path)
                input_queue.append(path)
                # XXX: this sleep is required so that is_set isn't called repeatedly (thousands of times+) when running.
                time.sleep(0.1)

    finally:
        debug("Wait for pool to shutdown...")
        pool.shutdown()

    return ParseResult(makex_file=_finished.get(_initial), errors=errors, graph=graph)
