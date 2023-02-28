#!/usr/bin/env python3

# file    :  split-dir-contents.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information


from typing import TypeVar, Iterable, Sequence, Tuple, Optional, List

import os
import sys
import math
import glob
import shutil
import argparse

import logging

log = logging.getLogger(__name__)

from fuzzaide.common.exception import FuzzaideException


def main(argv: Optional[Sequence[str]] = None):
    args = get_args(argv or sys.argv[1:])

    setup_logging(args.verbose, args.dry_run)

    if args.dry_run:
        log.warning("THIS IS DRY RUN, NO ACTUAL WRITE OPERATIONS ARE MADE")

    post_process_input_output_paths(args)

    filenames = select_input_files(args.input_dir, select_hidden=args.all)
    num_files = len(filenames)

    if num_files < 1:
        log.error("no files to process")
        return 1

    num_dirs = math.ceil(len(filenames) / args.chunk_size)

    message = "%d files from %s to %s0" % (
        num_files,
        args.input_dir,
        args.output_prefix,
    )

    if num_dirs > 1:
        message += "-%s" % (args.output_prefix + str(num_dirs - 1))

    if args.move:
        log.info("will MOVE %s", message)
    else:
        log.info("will COPY %s", message)

    for dirnum, filepaths in enumerate_chunks(filenames, args.chunk_size):
        try:
            process_chunk(
                filepaths,
                args.output_prefix + str(dirnum),
                is_dry_run=args.dry_run,
                force=args.force,
                is_move=args.move,
            )
        except FuzzaideException as e:
            log.error("%s", str(e))
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())


def setup_logging(verbose: int, dry_run: bool) -> None:
    if verbose > 1:
        log_level = logging.DEBUG
    elif verbose > 0 or dry_run:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(level=log_level, format="%(levelname)-8s | %(message)s")


def post_process_input_output_paths(args: argparse.Namespace) -> None:
    args.input_dir = os.path.normpath(args.input_dir)

    if args.output_prefix != "":
        return

    if args.input_dir == ".":
        args.output_prefix = "split_chunk"
        return
    args.output_prefix = args.input_dir + "_chunk"


def select_input_files(input_dir: str, select_hidden: bool) -> List[str]:
    filenames = glob.glob(os.path.join(input_dir, "*"))

    if select_hidden:
        filenames.extend(glob.glob(os.path.join(input_dir, ".*")))

    filenames = sorted(filter(lambda path: os.path.isfile(path), filenames))
    return filenames


def get_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = create_argument_parser()

    if not argv:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args(argv)

    check_args_for_common_mistakes(args)

    return args


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="tool to split directory into multiple directories by copying files",
        epilog="USE WITH EXTRA CARE, always test with --dry-run",
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        help="input directory from which you want to copy files",
        default=".",
    )
    parser.add_argument(
        "-o",
        "--output-prefix",
        help="prefix name of output directories",
        required=False,
        default="",
    )
    parser.add_argument(
        "-n",
        "--chunk-size",
        help="copy up to NUMFILES of files to each new directory",
        metavar="NUMFILES",
        type=int,
        required=True,
    )
    parser.add_argument(
        "-f",
        "--force",
        action="count",
        default=0,
        help="allow copying to (-f) and overwriting files "
        "(-ff) in non-empty output directories",
    )
    parser.add_argument(
        "-m", "--move", help="move files instead of copying", action="store_true"
    )
    parser.add_argument(
        "-D",
        "--dry-run",
        help="dry run to show you what would have happened",
        action="store_true",
    )
    parser.add_argument(
        "-A", "--all", help="also copy hidden files", action="store_true"
    )
    parser.add_argument(
        "-v", "--verbose", help="verbose output", action="count", default=0
    )

    return parser


def check_args_for_common_mistakes(args: argparse.Namespace) -> None:
    if not os.path.isdir(args.input_dir):
        sys.exit(f"this doesn't seem like existing directory: {args.input_dir}")

    if args.chunk_size < 1:
        sys.exit("chunk size (NUMFILES) should be more than 0")


_T = TypeVar("_T")


def enumerate_chunks(
    collection: Sequence[_T], n: int
) -> Iterable[Tuple[int, Sequence[_T]]]:
    """
    Iterate over `collection` in chunks of up to `n` items.
    On each iteration yield zero-based index and up to `n` items from the collection.
    """
    idx = 0
    for i in range(0, len(collection), n):
        yield idx, collection[i : i + n]
        idx += 1


def process_chunk(
    filepaths: Sequence[str],
    destination: str,
    is_dry_run: bool,
    force: int,
    is_move: bool,
) -> None:
    log.info("processing %d files, destination: %s", len(filepaths), destination)

    if os.path.exists(destination):
        if not os.path.isdir(destination):
            raise FuzzaideException(f"can't access path {destination} as directory")

        log.debug("directory already exists: %s", destination)

        out_dir_has_files = bool(os.listdir(destination))
        if out_dir_has_files:
            if force > 0:
                log.warning(
                    "directory already exists and contains some files: %s. CONTINUING due to --force",
                    destination,
                )
            else:
                raise FuzzaideException(
                    f"directory already exists and contains some files: {destination}.\n"
                    "You can:\n\t1) use (some other) --output-prefix\n"
                    "\t2) manually clean up your files\n"
                    "\t3) specify -f or --force to allow copying to non-empty directories"
                )
    else:
        log.debug("creating directory %s", destination)
        if not is_dry_run:
            try:
                os.makedirs(destination)
            except OSError as e:
                raise FuzzaideException(
                    f"wasn't able to create directory {destination}: {e}"
                ) from e

    filepath = "<unknown>"  # satisfy pyright
    try:
        for filepath in filepaths:
            process_file(filepath, destination, force, is_dry_run, is_move)
    except OSError as e:
        raise FuzzaideException(f"can't copy/move file {filepath}: {e}") from e


def process_file(
    filepath: str, destination: str, force: int, is_dry_run: bool, is_move: bool
) -> None:
    """
    Move or copy a single file `filepath` to directory `destination`.
    """
    fname = os.path.basename(filepath)
    if not os.path.exists(os.path.join(destination, fname)) or force > 1:
        log.debug("%s -> %s", filepath, destination)
        if is_dry_run:
            return

        shutil.copy(filepath, destination)

        if is_move:
            os.remove(filepath)

        return

    log.warning(
        "skipping file %s because same name is used in destination directory %s (-ff to "
        "overwrite)",
        filepath,
        destination,
    )
