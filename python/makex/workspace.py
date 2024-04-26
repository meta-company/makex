import hashlib
import os
import os.path
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import (
    Iterable,
    Optional,
    Union,
)

from makex.configuration import (
    Configuration,
    ConfigurationFiles,
)
from makex.constants import (
    WORKSPACE_ARGUMENT_ENABLED,
    WORKSPACE_FILE_NAME,
    WORKSPACE_FROM_CONFIGURATION_ENABLED,
)


def workspace_id(my_string: str):
    return hashlib.shake_256(my_string.encode()).hexdigest(5)


def _find_root(cwd: Path):
    """
    """
    return Path(cwd.anchor)


class DetectionType(Enum):
    ARGUMENT = 1
    WORKSPACE_FILE = 2
    ENVIRONMENT = 3
    CONFIGURATION_FILE = 4
    ROOT = 5


@dataclass(frozen=True)
class Detection:
    type: DetectionType

    # path to workspace detected
    path: Path

    # a path to the detection type
    object: Union[str, Configuration, Path] = None


class WorkspaceFile:
    """
    Define a file format in which we can define the workspace and the names/paths of external workspaces.

    """


@dataclass
class Workspace:
    # Path of the workspace, a directory.
    path: Path

    # File which this workspace was defined
    file: Path

    # short readable name [a-zA-Z_][a-zA-Z0-9\-._@]+
    # used in workspace prefixes
    name: str = None

    # or hash:
    # workspaces should return unique ids
    # if they aren't explicitly defined, the name or path is used to generate one
    #id: str = None

    # map of external workspace names to their actual paths
    externals: dict[str, Path] = None

    def __init__(self, path, name=None, id=None):
        self.path = path
        self.name = name
        self._id = id
        self.file = None

    @property
    def id(self):
        if self._id is not None:
            return self._id

        if self.name:
            return workspace_id(self.name)

        return workspace_id(self.path.as_posix())

    def __hash__(self):
        return str(self.id)

    def __eq__(self, other):
        return self.id == other.id


class WorkspaceCache:
    def __init__(self):
        # map of path parts tuple to which workspace it belongs to
        self._cache: dict[tuple[str], Workspace] = {}

    def add(self, workspace: Workspace):
        # manually add workspaces, as defined in config
        # TODO: we should be able to define externally provided workspaces in detected workspace files
        # ... or, tooling should be able to feed in the names/locations of workspaces
        # //workspace-name/path/to/target
        self._cache[workspace.path.parts] = workspace

    def get_by_name(self, name, path):
        """
        Return a workspace by name. This is used for externally defined workspaces.
        :param name:
        :param path:
        :return:
        """
        # get the workspace of path and check if defined any workspaces by name
        workspace = self.get_workspace_of(path)
        external = workspace.externals.get(name, None)

        if external:
            return external

        # check the parents for any externally defined names
        for parent in self.get_parents(workspace):
            external = parent.externals.get(name, None)
            if external:
                return external

        return None

    def get(self, path: Path):
        return self._cache.get(path.parts, None)

    def _get(self, path: tuple[str]):
        return self._cache.get(path, None)

    def get_parents(self, workspace: Workspace) -> Iterable[Workspace]:
        # get parent workspaces of workspace (or the workspace at "root")
        pass

    def get_workspace_of(self, directory: Path):
        """
        NOTE: This method is performance sensitive as it may be called on a large number of paths/targets.

        :param directory: Directory to get the workspace of.
        :return: If there is a WORKSPACE file in directory, this will return that Workspace. Otherwise,
        search the parents of directory for a valid workspace.
        """
        #print(f"Get workspace of {directory}")
        # find the workspace of path
        # or find a Workspace/Workspace file in path or one of its parents
        str_path = directory.as_posix()

        directory_parts = directory.parts
        workspace = self._get(directory_parts)
        if workspace is not None:
            return workspace

        # search upwards for a WORKSPACE file
        # do the key matching faster by expanding directory.parts into Iterable[tuple[str,...]] using _iterate_parents
        exists = os.path.exists
        for parent_key in _iterate_parents(directory_parts):
            test = self._get(parent_key)

            if test is not None:
                # found a workspace in parent
                return test
            ## check for workspace file if we haven't
            #test = Path(*parent_key) / WORKSPACE_FILE_NAME
            if len(parent_key) == 1:
                # we've reached the root/anchor
                return Workspace(_find_root(directory))

            test_path = os.path.join(*parent_key)
            test = os.path.join(test_path, WORKSPACE_FILE_NAME)

            if exists(test):
                #print(f"Workspace at exists {test}")
                workspace_path = test_path
                workspace = Workspace(Path(workspace_path))
                self._cache[parent_key] = workspace

                # cache everything from directory -> workspace
                for key in _iterate_parents(directory_parts):
                    if key == parent_key:
                        break
                    self._cache[key] = workspace
                self._cache[directory.parts] = workspace
                return workspace
            else:
                #print(f"Does not exist at {test}")
                continue

        # no workspace detected in parents, use root
        return Workspace(_find_root(directory))


def _iterate_parents(parts: tuple[str]) -> Iterable[tuple[str, ...]]:
    all_parts = parts
    i = len(parts)
    while i >= 0:
        yield all_parts[0:i]
        i -= 1


def current_workspace(
    cwd,
    files: ConfigurationFiles = None,
    argument=None,
    environment: Optional[Path] = None,
):
    iterable = detect_workspaces(
        cwd,
        files=files,
        argument=argument,
        environment=environment,
    )
    n: Detection = next(iter(iterable))
    return Workspace(n.path)


def which_workspace(
    current_workspace: Path,
    directory: Path,
) -> Workspace:
    # with a current workspace and a directory, and optional files. figure out
    # should only be used for one offs.
    # use the WorkspaceCache for more advanced uses
    parent = directory
    while parent and parent.name:
        workspace_file = parent / WORKSPACE_FILE_NAME

        if workspace_file.exists():
            return Workspace(parent)

        parent = parent.parent

    return Workspace(_find_root(current_workspace))


def detect_workspaces(
    cwd: Path,
    files: ConfigurationFiles,
    argument: Optional[Path] = None,
    environment: Optional[Path] = None,
) -> Iterable[Detection]:
    """ Return the currently detected workspaces from the given arguments/state.

        - --workspace argument
        - WORKSPACE file autodetected inside one of first parent
        - WORKSPACE environment
        - makex.workspace defined in makex.toml configuration files in one of first parents
        - makex.workspace defined in configuration files:
          - home/local first
          - then global
        - If all else fails, the workspace is the root of the filesystem at CWD.

        This is an iterable so we don't do expensive checks/loads if we don't need them.

        :param cwd:
        :return:
    """
    if WORKSPACE_ARGUMENT_ENABLED:
        if argument:
            yield Detection(DetectionType.ARGUMENT, argument)

    if files and files.workspace_files:
        # the topmost WORKSPACE file is the current workspace
        yield Detection(DetectionType.WORKSPACE_FILE, files.workspace_files[-1])

    if environment:
        yield Detection(DetectionType.ENVIRONMENT, environment)

    if WORKSPACE_FROM_CONFIGURATION_ENABLED:
        if files.configuration_files:
            for config in files.configuration_files:
                workspace = conf_read_workspace(config)
                if workspace:
                    yield Detection(DetectionType.CONFIGURATION_FILE, workspace)

        if files.local_configuration:
            workspace = conf_read_workspace(files.local_configuration)
            if workspace:
                yield Detection(DetectionType.CONFIGURATION_FILE, workspace)

        if files.global_configuration:
            workspace = conf_read_workspace(files.global_configuration)
            if workspace:
                yield Detection(DetectionType.CONFIGURATION_FILE, workspace)

    yield Detection(DetectionType.ROOT, _find_root(cwd))


def conf_read_workspace(config: Configuration):
    # expand the workspace variable in config
    # error if it's not valid
    if config.workspace:
        workspace = Path(config.workspace).expanduser()
        if not workspace.exists():
            raise Exception(
                f"Workspace {workspace} path defined in configuration file {config} does not exist."
            )
        return workspace

    return None


def get_workspace():
    workspace = os.environ.get("WORKSPACE", None)
    if not workspace:
        return None
    #    raise Exception("WORKSPACE NOT DEFINED")
    return Path(workspace).expanduser().absolute()
