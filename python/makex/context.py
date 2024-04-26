import re
import shutil
from copy import copy
from dataclasses import (
    dataclass,
    field,
)
from pathlib import Path
from typing import (
    Callable,
    Pattern,
)

from makex.colors import (
    ColorsNames,
    NoColors,
)
from makex.configuration import Configuration
from makex.constants import (
    BUILT_IN_REFLINKS,
    DEFAULT_IGNORE_PATTERN,
    MAKEX_FILE_NAMES,
    OUTPUT_DIRECTORY_NAME,
    WORKSPACE_FROM_CONFIGURATION_ENABLED,
)
from makex.errors import CacheError
from makex.file_system import (
    safe_reflink,
    same_fs,
)
from makex.patterns import combine_patterns
from makex.platform_object import PlatformObject
from makex.ui import UI
from makex.workspace import (
    Workspace,
    WorkspaceCache,
)

if BUILT_IN_REFLINKS:
    import makex.file_cloning as reflink
else:
    import file_cloning


@dataclass
class Context:
    """
    Define a generic context so that subclasses can be defined with properties with types local to the subclass.

    TODO: copy the values so they are all private self.__dict__[fqn.].
    TODO: contexts should have their own namespaces. Context.cast() method should return the accessors for the specific type
    TODO: ...or, we should just restrict Unions to not have conflicting implementations of property names

    """
    # environment variables
    environment: dict[str, str] = field(default_factory=dict)

    # graph is used everywhere so it is attached to context
    # TODO: rename as we need two graphs (graph1 and graph2).
    # TODO: this doesn't really need to be in this Context object
    graph: "TargetGraph" = None

    # platform query is used everywhere
    platform: PlatformObject = None

    # used to show messaging
    ui: UI = field(default_factory=UI)

    # The workspace path and detected workspace
    #workspace_path: Path = None

    # The root/initial workspace detected when starting makex.
    workspace_object: Workspace = None

    workspace_cache: WorkspaceCache = field(default_factory=WorkspaceCache)

    # Path to the cache we prefer
    cache: Path = Path("~/.cache/makex/").expanduser()

    # a pattern used to ignore all files from input, output, glob, and find
    ignore_pattern: Pattern = re.compile(DEFAULT_IGNORE_PATTERN)

    # preferred copy file function
    # may be changed to use reflinks
    copy_file_function: Callable[[str, str], None] = shutil.copy

    # the configuration file
    # TODO: this isn't really used, we expand Configuration into context
    configuration: Configuration = None

    # stack of workspaces as we enter directories that are detected as separate workspaces
    _workspace_stack: list[Workspace] = field(default_factory=list)

    # debug enabled
    # tracing and any expensive debug will use this flag
    debug: bool = False

    # verbosity level
    # 1 is low, 3 is high
    verbose: int = 0

    # Map of color names to strings
    colors: ColorsNames = NoColors

    # True if color enabled.
    # TODO: We probably don't need this.
    color: bool = False

    # TODO: detect the current shell here early if any
    # otherwise use automatic
    shell: str = "/bin/sh"

    # names of makex files (Makexfile, makexfile, Build)
    makex_file_names = MAKEX_FILE_NAMES

    # name of the output directory/link (_output_)
    output_folder_name = OUTPUT_DIRECTORY_NAME

    dry_run: bool = False

    # True if copy on write is enabled on the workspace and cache.
    # this will automatically be detected.
    copy_on_write = False

    @property
    def workspace_path(self):
        if self._workspace_stack:
            return self._workspace_stack[-1].path

        return self.workspace_object.path

    def push_workspace(self, workspace: Workspace):
        self._workspace_stack.append(workspace)

    def pop_workspace(self) -> Workspace:
        return self._workspace_stack.pop()

    def current_workspace(self):
        if self._workspace_stack:
            return self._workspace_stack[-1]

        return self.workspace_object

    def with_configuration(self, configuration: Configuration, early_ui) -> "Context":
        ctx = copy(self)
        ctx.configuration = configuration

        if configuration.ignore:
            ctx.ignore_pattern = combine_patterns(configuration.ignore)

        if WORKSPACE_FROM_CONFIGURATION_ENABLED:
            if configuration.workspace:
                # override WORKSPACE use the workspace defined in the configuration file
                workspace = Path(configuration.workspace).expanduser()
                if not workspace.exists():
                    raise Exception(
                        f"Workspace {configuration.workspace} defined in configuration file at {configuration.path} doesn't exist at {workspace}"
                    )

                ctx.workspace_object = Workspace(workspace)

        cache = ctx.cache

        if configuration.cache:
            # XXX: overwrite ctx.cache here instead of creating a new object
            ctx.cache = cache = Path(configuration.cache).expanduser()
            cache = cache

        if not cache.exists():
            # TODO: create the cache dir here?
            early_ui(f"Creating cache at {cache}")
            try:
                cache.mkdir(parents=True)
            except Exception as e:
                raise CacheError(f"Error creating cache directory at {cache}: {e}")

        # check this after we have a cache and workspace
        if configuration.reflinks is None:
            # configuration specified automatic detection of reflinks
            if same_fs(ctx.workspace_path, ctx.cache) and reflink.supported_at(ctx.workspace_path):
                ctx.copy_file_function = safe_reflink
                ctx.copy_on_write = True

        if configuration.file_names:
            # TODO: validate string of
            ctx.makex_file_names = set(configuration.file_names)

        if configuration.output_folder:
            ctx.output_folder_name = configuration.output_folder

        return ctx

    def new_environment(self, env=None) -> "EnviromentContextManager":
        return EnviromentContextManager(self, env or {})


class EnviromentContextManager:
    def __init__(self, ctx: Context, env: dict = None):
        self.ctx = ctx
        # create a new dict/copy
        self.env = {**ctx.environment, **env}
        self.old_env = self.ctx.environment

    def __enter__(self):
        self.ctx.environment = self.env
        return self.ctx

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ctx.environment = self.old_env
