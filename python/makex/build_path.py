#!/usr/bin/env python3
"""
Simple standalone tool to generate build paths confirming to the build-tool specifications (version 1).

Build Path Format:

{build_root}/{workspace-id}/{project_path}/{BUILD_FOLDER_NAME}/{objective_name}-{variants}/{working_folder}

Variants are serialized with the following algorithm:

# gather bounded variants (with =) into list
# gather unbounded variants into list
# sort each list independently
# join the lists (bounded + unbounded) using a `,` separator character.

If no objective name or variants are specified:

{build_root}/{workspace-id}/{project_path}/{BUILD_FOLDER_NAME}/{DEFAULT_OBJECTIVE}/{working_folder}

working_folder is one of: output/interim

TODO: add root argument to change build root
TODO: write metadata to build root for external tools?

Environment Variables:

WORKSPACE: path to the workspace which to base all paths from.
META_BUILD: path to the build root where interim/outputs are stored

"""
import argparse
import logging
import os
import sys
from pathlib import Path

DEFAULT_BUILD_ROOT = "~/.cache/build-tool/"

WORKSPACE_VAR = "WORKSPACE"
BUILD_PATH_VAR = "META_BUILD"

# NOTE: ; breaks makefiles.
# separator between object and variants
OBJECTIVE_VARIANT_SEPARATOR = "-"

# separator between variants
VARIANT_SEPARATOR = ","

# Constants
BUILD_FOLDER_NAME = "_build_"
OUTPUT_NAME = "output"
INTERIM_NAME = "interim"

# TODO: rename to _external_
DEFAULT_OBJECTIVE = "_external_"
DEFAULT_VARIANT = ""
DEFAULT_LINK = "_build_"


class OutputPathComponent:
    # names/strings of the output path components
    BUILD_FOLDER_NAME = BUILD_FOLDER_NAME
    DEFAULT_LINK = DEFAULT_LINK
    VARIANT_SEPARATOR = VARIANT_SEPARATOR
    OBJECTIVE_VARIANT_SEPARATOR = OBJECTIVE_VARIANT_SEPARATOR


# XXX: Unused in makex.
def create_output_path(new_path: Path, linkpath: Path=None, fix=False):
    """
    Create the output path.

    :param new_path: Path to create an output directory at.
    :param linkpath: Optionally link to linkpath.
    :param fix: Optionally, fix broken links.
    :return:
    """
    # TODO: we need a faster of version of this which uses a cache for checking file status
    if not new_path.exists():
        logging.debug("Creating output directory %s", new_path)
        new_path.mkdir(parents=True, exist_ok=True)

    if linkpath is None:
        return

    if linkpath.exists():
        if not linkpath.is_symlink():
            raise Exception(
                f"Linkpath {linkpath} exists, but it is not a symlink. Output directory may have been created inadvertently outside the tool."
            )
    else:
        if linkpath.exists() is False and linkpath.is_symlink():
            # we have a broken symlink
            if fix:
                realpath = linkpath.readlink().absolute()
                logging.debug("Fixing broken link from %s to %s", linkpath, realpath)
                if not fix:
                    raise Exception(f"There's a broken link at {linkpath}.")
                # fix broken links automatically
                linkpath.unlink()
            else:
                raise Exception("Could not create")

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


def get_build_path(
    objective_name,
    variants,
    input_directory,
    build_root,
    workspace,
    workspace_id,
    output_folder,
    names=OutputPathComponent,
):
    """
    Used by apis.

    :param objective_name:
    :param variants:
    :param input_directory:
    :param build_root:
    :param workspace:
    :param workspace_id:
    :param names:
    :return:
    """
    if workspace is None:
        workspace = _get_workspace()

    output_folder = output_folder or names.BUILD_FOLDER_NAME

    cwd = input_directory or Path.cwd()

    base_path, new_path, objective, variants_string = _construct_paths(
        for_path=cwd,
        build_path=build_root,
        objective_name=objective_name,
        variants=variants,
        variant_separator=names.VARIANT_SEPARATOR,
        workspace=workspace,
        workspace_id=workspace_id,
        output_folder=output_folder,
        names=OutputPathComponent,
    )
    #logging.trace("Constructed path for %s: base=%s new_path=%s, objective=%s", objective_name, base_path, new_path, objective)

    linkpath = input_directory / output_folder / objective
    return new_path, linkpath


def _get_parser():
    parser = argparse.ArgumentParser(description="""Create build paths.""")
    #parser.add_argument('command', metavar='N', type=int, nargs='+', help='an integer for the accumulator')
    #parser.add_argument('--sum', help='sum the integers (default: find the max)')
    subparsers = parser.add_subparsers(help='Commands', dest="command")

    subparser = subparsers.add_parser(
        "clear",
        help="Clear the folder(s) created by this tool (objective specific, interim and output)."
    )
    subparser.add_argument(
        'objective', nargs="?", help='The objective to clear.', default=DEFAULT_OBJECTIVE
    )
    subparser.add_argument(
        '-v',
        '--variants',
        nargs="?",
        action="append",
        help='@ may be specified to clear all variants.'
    )
    subparser.add_argument(
        '-r',
        '--recursive',
        action="store_true",
        help='Clear all build folders under the path as well.'
    )

    subparser = subparsers.add_parser("create", help="aaa")
    subparser.add_argument(
        'objective',
        #nargs="+",
        help=f'The objective to work on. Variants may be specified inline after a ? separator. Default={DEFAULT_OBJECTIVE}',
        default=DEFAULT_OBJECTIVE
    )
    subparser.add_argument(
        '-v',
        '--variants',
        nargs="?",
        action="append",
        help='the variants for the objective. can be specified multiple times.'
    )
    #subparser.add_argument('--output', action="store_true", help='create and print the output path.')
    #subparser.add_argument('--interim', action="store_true", help='create and print the interim path.')
    subparser.add_argument(
        '--separator',
        default=VARIANT_SEPARATOR,
        help=f'variant separator. default={VARIANT_SEPARATOR}'
    )
    subparser.add_argument(
        '--link',
        nargs='?',
        const=True,
        default=True,
        help=f'use --link=linkname to specify the name of the link directory. This is the default.'
    )

    subparser.add_argument(
        '--no-link',
        action="store_false",
        dest="link",
        help=f'disable link creation. output cache paths instead.'
    )
    subparser.add_argument('-p', "--print", action="store_true", help='dry run. print only')

    # TODO: input command.
    subparser = subparsers.add_parser(
        "input", help="Link/copy/overlay some input to the build path."
    )

    subparser = subparsers.add_parser("get", help="Link/copy/overlay some input to the build path.")
    subparser.add_argument(
        'objective',
        #nargs="+",
        help='The objective to work on.',
        default=DEFAULT_OBJECTIVE,
    )
    subparser.add_argument(
        '-v', '--variants', nargs="?", action="append", help='the variants for the objective'
    )
    #subparser.add_argument('--output', action="store_true", help='create and print the output path.')
    #subparser.add_argument('--interim', action="store_true", help='create and print the interim path.')
    subparser.add_argument('--separator', default=VARIANT_SEPARATOR, help='variant separator')
    return parser


def _get_project_path(for_path: Path, workspace_path: Path = None):

    if workspace_path is None:
        assert for_path.is_absolute()
        return for_path
    try:
        return for_path.relative_to(workspace_path)
    except:
        raise Exception(f"path {for_path} not in workspace {workspace_path}!")


def _get_workspace():
    workspace = os.environ.get(WORKSPACE_VAR, None)

    if workspace is None:
        return workspace
        #raise Exception(f"Missing workspace env variable ({WORKSPACE_VAR})!")

    workspace = Path(workspace).expanduser()
    return workspace


def _get_environ(external_build_root=DEFAULT_BUILD_ROOT):
    workspace = os.environ.get(WORKSPACE_VAR, None)
    build_path = os.environ.get(BUILD_PATH_VAR, external_build_root)

    if workspace is None:
        raise Exception(f"Missing workspace env variable ({WORKSPACE_VAR})!")

    if build_path is None:
        # USE DEFAULT
        raise Exception("Missing build path env variable!")

    workspace = Path(workspace).expanduser()
    build_path = Path(build_path).expanduser()

    # TODO: check if both absolute/etc
    return (workspace, build_path)


def _serialize_variants(strings, variant_separator=VARIANT_SEPARATOR):
    if not strings:
        return ""

    # XXX: the user might pass multiple variants in one -v argument
    strs = []
    for string in strings:
        strs.extend(string.split(VARIANT_SEPARATOR))

    bounded = []
    unbounded = []
    # first sort by bound variants, then by unbound
    for variant in sorted(strs):
        if "=" in variant:
            bounded.append(variant)
        else:
            unbounded.append(variant)

    variants_string = variant_separator.join(sorted(bounded) + sorted(unbounded))
    return variants_string


def _construct_paths(
    for_path,
    build_path,
    objective_name,
    variants,
    variant_separator,
    workspace,
    workspace_id,
    output_folder,
    names=OutputPathComponent,
):
    relative_path = _get_project_path(for_path, workspace)
    if variants:
        variants_string = _serialize_variants(variants, names.VARIANT_SEPARATOR)
        objective = f"{objective_name}{names.OBJECTIVE_VARIANT_SEPARATOR}{variants_string}"
    else:
        objective = objective_name
        variants_string = ""

    base_path = build_path / relative_path
    if workspace_id is None:
        new_path = build_path / "_root_" / relative_path / output_folder / objective
    else:
        new_path = build_path / workspace_id / relative_path / output_folder / objective

    return base_path, new_path, objective, variants_string


def _split_locator(locator: str):
    objective = None
    if ":" not in locator:
        path = locator
    else:
        path, objective = locator.split(":")

    if path.startswith("//"):
        path = path[2:]

    variants = []
    if objective is None:
        objective = DEFAULT_OBJECTIVE

        if "?" in path:
            path, variants = path.split("?")
            variants = [variants]

    else:
        if "?" in objective:
            objective, variants = objective.split("?")
            variants = [variants]

    return path, objective, variants


def _get_output_path(args):
    # return the absolute path to objective

    #if args.output:
    #    working_folder = OUTPUT_NAME
    #elif args.interim:
    #    working_folder = INTERIM_NAME
    #else:
    #    raise Exception("--output or --interim expected")

    working_folder = args.objective

    variants = args.variants

    objective_path, objective_name, variants = _split_locator(args.objective)

    workspace, build_path = _get_environ()

    cwd = workspace / objective_path

    #relative_path = get_project_path(cwd, workspace)
    paths = _construct_paths(
        for_path=cwd,
        build_path=build_path,
        objective_name=objective_name,
        variants=variants,
        variant_separator=args.separator,
        workspace=workspace,
    )
    base_path, new_path, objective, variants_string = paths

    #new_path /= working_folder

    source_path = base_path / BUILD_FOLDER_NAME

    #if not new_path.exists():
    #    raise Exception(f"Path {new_path} does not exist")

    print(source_path)
    return sys.exit(0)


def _create_output_path(args):
    if args.link == False:
        pass

    #if args.output:
    #    working_folder = OUTPUT_NAME
    #elif args.interim:
    #    working_folder = INTERIM_NAME
    #else:
    #    raise Exception("--output or --interim expected")

    variants = args.variants
    working_folder = objective_name = args.objective

    if "?" in objective_name:
        objective_name, variants = objective_name.split("?")
        variants = [variants]
        working_folder = objective_name

    workspace, build_path = _get_environ()

    cwd = Path.cwd()
    #relative_path = get_project_path(cwd, workspace)
    paths = _construct_paths(
        for_path=cwd,
        build_path=build_path,
        objective_name=objective_name,
        variants=variants,
        variant_separator=args.separator,
        workspace=workspace,
    )
    base_path, new_path, objective, variants_string = paths
    #new_path /= working_folder

    if args.print:
        # TODO: add --print-link
        print(new_path)
        return sys.exit(0)

    debug = False

    if debug:
        print("Create", new_path)

    if not new_path.exists():
        new_path.mkdir(parents=True, exist_ok=True)

    if args.link:
        source_path = base_path / BUILD_FOLDER_NAME

        linkpath = args.link if isinstance(args.link, str) else DEFAULT_LINK
        linkpath = cwd / Path(linkpath)

        if debug:
            print(f"Link from {source_path } to {linkpath}")

        if linkpath.exists():
            if not linkpath.is_symlink():
                raise Exception(
                    f"Linkpath {linkpath} exists, but it is not a symlink. Build directory may have been created inadvertently outside the use of build-tool."
                )
        else:
            linkpath.symlink_to(source_path)

        print((Path(linkpath) / objective)) # / working_folder))
    else:
        print(new_path)


def _clear_output_path(args):
    variants = args.variants
    objective_name = args.objective

    workspace, build_path = _get_environ()

    all_variants = False
    if variants == ["@"]:
        variants.pop()
        all_variants = True

    cwd = Path.cwd()
    #relative_path = get_project_path(cwd, workspace)

    paths = _construct_paths(
        for_path=cwd,
        build_path=build_path,
        objective_name=objective_name,
        variants=variants,
        variant_separator=VARIANT_SEPARATOR,
        workspace=workspace
    )
    base_path, objective_path, objective, variants_string = paths

    if args.recursive:
        if objective_name != DEFAULT_OBJECTIVE:
            print("Objective name and recursive are mutually exclusive. Specify one or the other.")
            sys.exit(-1)

        # walk under path searching for BUILD_FOLDER.. don't follow two BUILD_FOLDERs
        if all_variants:
            print(f"Clear {base_path}**/*{BUILD_FOLDER_NAME}")
        else:
            print(f"Clear {base_path}**/*{BUILD_FOLDER_NAME}/*;{variants_string}")
    else:
        # just delete the BUILD_FOLDER at path
        if all_variants:
            print(f"Clear {objective_path}*")
        else:
            print(f"Clear {objective_path}")


def main():
    args = _get_parser().parse_args()

    if args.command == "clear":
        _clear_output_path(args)
    elif args.command == "create":
        _create_output_path(args)
    elif args.command == "get":
        _get_output_path(args)
    else:
        raise Exception("Unknown command.")

    sys.exit(0)


if __name__ == "__main__":
    main()
