import os
from dataclasses import (
    dataclass,
    field,
)
from io import StringIO
from pathlib import Path
from typing import (
    Callable,
    Optional,
    Protocol,
    Union,
)

import toml as toml
from makex.constants import (
    CONFIG_NAME_1,
    CONFIG_NAME_2,
    OUTPUT_FOLDER_CONFIGURATION_ENABLED,
    WORKSPACE_FILE_NAME,
)
from makex.errors import (
    GenericFileLocation,
    GenericSyntaxError,
    MakexError,
)


class ConfigurationError(MakexError):
    def __init__(self, message, location: GenericFileLocation):
        super().__init__(message)
        self.location = location


class ConfigurationValue:
    """
        Track string value locations because they are usually a source of problems, and we want to refer to that location
        for the user.
    """
    def __init__(self, value, location: GenericFileLocation = None):
        super().__init__()
        self.value = value
        self.location = location

    #def __str__(self):
    #    return self.value

    #def __new__(cls, *args, **kwargs):
    #    return super().__new__(cls, args[0])


@dataclass
class Configuration:
    path: Path = None

    workspace: str = None

    cache: str = None

    shell: str = None

    file_names: list[str] = field(default_factory=list)

    ignore: list[str] = field(default_factory=list)

    # copy files using reflinks
    # only on supported filesystems.
    # can not cross fs boundaries between workspace and cache_root.
    # None to autodetect; True if the workspace and cache root are on the same filesystem, and if it supports reflinks.
    # True to enable/force
    # False to use old copy
    reflinks: bool = None

    # Path of the output/build directory.
    # This will be applied to anywhere an output path or link to an output path is required.
    output_folder: str = None

    # Allow configuration files to set/evaluate environment variables before run
    environment: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, d, path=None) -> "Configuration":
        # TODO: validate all of these
        root = d.get("makex")
        workspace = root.get("workspace", None)
        cache = root.get("cache", None)
        shell = root.get("shell", None)
        file_names = root.get("file_names", None)
        ignore = root.get("ignore", None)
        reflinks = root.get("reflinks", None)

        if OUTPUT_FOLDER_CONFIGURATION_ENABLED:
            output_folder = root.get("output_folder", None)
        else:
            output_folder = None

        environment = root.get("environment", {})

        environment = {
            k: ConfigurationValue(v, GenericFileLocation(path))
            for k, v in environment.items()
        }
        return cls(
            path=path,
            workspace=workspace,
            cache=cache,
            shell=shell,
            file_names=file_names,
            ignore=ignore,
            reflinks=reflinks,
            output_folder=output_folder,
            environment=environment,
        )

    def merge_other(self, other: "Configuration"):
        assert isinstance(other, Configuration), f"Got {type(other)}"

        if other.workspace is not None:
            self.workspace = other.workspace

        if other.cache is not None:
            self.cache = other.cache
        self.path = other.path if other.path else None

        if other.shell:
            self.shell = other.shell

        if other.ignore:
            self.ignore = self.ignore + other.ignore

        if other.reflinks is not None:
            self.reflinks = other.reflinks

        if other.file_names is not None:
            self.file_names = other.file_names + self.file_names

        if other.output_folder is not None:
            self.output_folder = other.output_folder

        if other.environment:
            self.environment.update(other.environment)

    def to_json(self):
        return {
            "makex":
                {
                    "workspace": self.workspace,
                    "cache_root": self.cache_root,
                    "shell": self.shell,
                    "file_names": self.file_names,
                    "exclude": self.exclude,
                    "reflinks": self.reflinks,
                }
        }


SHELL_MARKER = "shell:"


class RunFunction(Protocol):
    def __call__(
        self,
        executable: str,
        env: dict[str, str],
        capture: bool = False,
        print: bool = True,
        shell: bool = False,
        stdin: Union[int, StringIO] = None,
        cwd: Path = None
    ):
        ...


def evaluate_configuration_environment(
    shell: str,
    env: dict[str, str],
    current_enviroment: dict[str, str],
    cwd,
    run: RunFunction,
) -> dict[str, str]:
    d = {}
    for k, v in env.items():
        value = v.value

        if isinstance(value, dict):
            script = value.get("shell", None)
            if script is not None:

                read, write = os.pipe()
                os.write(write, script.encode("utf-8"))
                os.close(write)
                print(shell, script)
                process = run(
                    shell,
                    env=current_enviroment,
                    capture=True,
                    shell=False,
                    print=False,
                    cwd=cwd,
                    stdin=read,
                )
                if process.status != 0:
                    location: GenericFileLocation = getattr(v, "location", None)
                    raise ConfigurationError(
                        f"Invalid shell command when evaluating environment variables from the file {location.path}:\n\t{value}\n:{process.output}\n{process.error}",
                        location=location
                    )
                # XXX: newline is removed so paths evaluate easy
                v = process.output.strip("\n")
        elif isinstance(value, str):
            pass
        elif isinstance(value, bool):
            value = "1" if value else "0"
        else:
            raise ConfigurationError(
                f"Invalid environment variable value type {type(value)} for {k} when evaluating environment variables from the file {value.location.path}:\n\t{v}",
                location=value.location
            )

        d[k] = v

    return d


@dataclass
class ConfigurationFiles:
    workspace_files: list[Path]
    configuration_files: list[Configuration]
    local_configuration: Optional[Configuration]
    global_configuration: Optional[Configuration]

    def merged(self) -> Configuration:
        merged = Configuration()
        if self.global_configuration:
            merged.merge_other(self.global_configuration)
        if self.local_configuration:
            merged.merge_other(self.local_configuration)

        for c in self.configuration_files:
            merged.merge_other(c)

        return merged


def read_configuration(path: Path) -> Configuration:
    with path.open("r") as f:
        try:
            d = toml.load(f)
            return Configuration.from_json(d)
        except toml.TomlDecodeError as e:
            l = GenericFileLocation(path, e.lineno, e.colno)
            raise GenericSyntaxError(str(e), location=l, type="Configuration") from e
        except Exception as e:
            raise Exception(f"Error loading configuration file at {path}: {e} {type(e)}")


def collect_configurations(
    cwd: Path, parents=True, verbose: Callable[[str], None] = lambda x: None
) -> ConfigurationFiles:
    """ An expensive (IO) routine to collect all related configuration/marker files for makex.

        We search for workspaces and configurations both so we don't need to do it twice separately.

        TODO: we should be able to cache this between executions, but we should mark dirty and reload
        if one of them doesn't exist or has been changed.

    """

    workspace_files_found = []
    config_files_found = []

    if parents:
        parent = cwd
        while parent and parent.name:
            workspace_file = parent / WORKSPACE_FILE_NAME
            config_file1 = parent / CONFIG_NAME_1
            config_file2 = parent / CONFIG_NAME_2

            if workspace_file.exists():
                workspace_files_found.append(workspace_file)

            if config_file1.exists():
                verbose(f"Reading configuration file at {config_file1}")
                config_files_found.append(read_configuration(config_file1))
            elif config_file2.exists():
                verbose(f"Reading configuration file at {config_file2}")
                config_files_found.append(read_configuration(config_file2))
            parent = parent.parent

    # TODO: these should be different for windows
    local = Path("~/.config", CONFIG_NAME_1).expanduser()

    if local.exists():
        verbose(f"Reading configuration file at {local}")
        local = read_configuration(local)
    else:
        local = None

    global_file = Path("/etc", CONFIG_NAME_1).expanduser()

    if global_file.exists():
        verbose(f"Reading configuration file at {global_file}")
        global_file = read_configuration(global_file)
    else:
        global_file = None

    return ConfigurationFiles(
        workspace_files=workspace_files_found,
        configuration_files=config_files_found,
        local_configuration=local,
        global_configuration=global_file,
    )
