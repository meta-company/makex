"""
Makex constants.

These are:
 - defaults
 - flags/things we won't typically change.
 - flags hidden from people.

"""
# higher priority config file name
CONFIG_NAME_1 = "makex.toml"

# lower priority/hidden config file name
CONFIG_NAME_2 = ".makex.toml"

WORKSPACE_FILE_NAME = "WORKSPACE"

MAKEX_FILE_NAMES = {"Makexfile", "makexfile"} #"Build",

OUTPUT_DIRECTORY_NAME = "_output_"

# Flags we don't want to wire into configuration/enviroment/context (yet):

# enable the --workspace argument
WORKSPACE_ARGUMENT_ENABLED = False

# enable using workspaces defined in configuration files
WORKSPACE_FROM_CONFIGURATION_ENABLED = False

# enable configuration files on the command line
CONFIGURATION_ARGUMENT_ENABLED = False

# Enable parallel evaluation.
# TargetObjects (from the parsing stage) are evaluated in parallel on a separate queue.
# This should speed up globbing/finds/etc.
# We may want to limit the threads for evaluation so as to not block up execution
#   (eval qlen < execution qlen = max threads). (unless we have "infinite" execution threads).
#   execution_qlen = max(1, max_threads-1) # 3
#   tmp = max_threads - execution_threads  # 1
#   evals_qlen = max(1, tmp) # 1
# we may lose ability to do things like glob caching on a separate thread
# (or we could pass these globs/cached objects back to the caller)
PARALLEL_EVALUATION_ENABLED = False

# If True a symbolic link will be created for each target output folder
# Otherwise only one symbolic link will be created.
# Some tools break if there is a symlink per target (or if the target output folder itself is a symlink);
# (notably, venv: https://github.com/python/cpython/blob/1e4f00ebd8db44a031b61eed0803b4c3d731aed7/Lib/venv/__init__.py#L121)
# these tools should be fixed.
SYMLINK_PER_TARGET_ENABLED = False

# If True, output folders/paths will point to the cache instead of the symbolically linked path
OUTPUT_DIRECTLY_TO_CACHE = False

# Enable direct references to makex files in target locators
# If True, //path/to/Makexfile:target is valid.
# XXX: Probably remove.
DIRECT_REFERENCES_TO_MAKEX_FILES = False

# Enable // marker in Targets/Paths in makex files.
WORKSPACES_IN_PATHS_ENABLED = True

# Enable configuration of output folders in makex configuration files.
OUTPUT_FOLDER_CONFIGURATION_ENABLED = False

DATABASE_FILE_NAME = "makex.sqlite"

DATABASE_ENABLED = True

# If True, make all environment variables available as globals.
ENVIRONMENT_VARIABLES_IN_GLOBALS_ENABLED = False

# If True, create a hash of enviroment variables; which will be included in target hash.
# XXX: Probably remove.
HASH_USED_ENVIRONMENT_VARIABLES = True

# Mode for any directories created.
NEW_DIRECTORY_MODE = 0o777

# True to remove the cache/output of dirty targets.
# XXX: This may be temporarily disabled because it causes some unexpected bevahior when composing a output directory from
# multiple targets.
# TODO: We don't want to have to clear things manually, but we also want multiple targets to be able to
#  write into the same output path. We might as well enforce isolation between targets.
# TODO: See about a STRICT_MODE flag which may "fix" this.
# TODO: If target A depends on B, but B uses the path of A, this should probably cause a cycle error.
REMOVE_CACHE_DIRTY_TARGETS_ENABLED = True

DEFAULT_IGNORE_NAMES = {
    '.pytest_cache',
    '.hg',
    '.git',
    '__pycache__',
    '.venv',
}

# TODO: we may actually want to include pyc...
DEFAULT_IGNORE_EXTENSIONS = {
    '.pyc',
}

if False:
    _parts = "|".join(name for name in DEFAULT_IGNORE_NAMES)
    DEFAULT_IGNORE_NAMES_PATTERNS = {r'(?s:.*({name}))\Z'.format(name=_parts)}

    _parts = "|".join(name.replace(".", r"\.") for name in DEFAULT_IGNORE_EXTENSIONS)
    DEFAULT_IGNORE_EXTENSIONS_PATTERNS = {r'(?s:.*({name}))\Z'.format(name=_parts)}

    DEFAULT_IGNORE_PATTERNS = DEFAULT_IGNORE_NAMES_PATTERNS | DEFAULT_IGNORE_EXTENSIONS_PATTERNS

    DEFAULT_IGNORE_PATTERN = "^(?={0})".format("|".join(DEFAULT_IGNORE_PATTERNS))
else:
    # precompile the pattern for reduced start up time.
    DEFAULT_IGNORE_PATTERN = '^(?=(?s:.*(\.pyc))\Z|(?s:.*(_output_|.pytest_cache|.hg|.venv|.git|__pycache__))\Z)'

# True to use builtin reflinks instead of reflinks pypi package
BUILT_IN_REFLINKS = True

# Ignore None arguments in various lists as they may be the result of a condition.
# NOTE: This will likely be the default.
IGNORE_NONE_VALUES_IN_LISTS = True

# Enable Slice with target(). target[:"name"] target["path":"name"]
TARGET_GETITEM_ENABLED = False

# Despite possible collisions/etc, sha1 is the fastest for hashing Targets
# sha1 is at least 2x as fast as shake/md5
HASHING_ALGORITHM = "sha1"


# If True, the task hash will be stored in any declared output files (in an extended attribute).
STORE_TASK_HASH_IN_OUTPUT_FILES = False


# Included files will have all globals available to them (defined prior to the include() call)
PASS_GLOBALS_TO_INCLUDE = False