#!/usr/bin/env python3

# file    :  split-file-contents.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from typing import Sequence, Optional, List, TypeVar, Type

import os
import sys
import argparse
from dataclasses import dataclass

import logging

log = logging.getLogger(__name__)

from fuzzaide.common.exception import FuzzaideException


def main(argv: Optional[Sequence[str]] = None):
    try:
        config = get_config(argv or sys.argv[1:])
        logging.basicConfig(level=config.log_level)

        log.debug("config=%s", str(config))

        if config.is_dry_run:
            log.debug("THIS IS DRY RUN. NO WRITE OPERATIONS ARE MADE")

        if (config.num_equal_parts or 0) > 0:
            split_to_equal_parts(config)
            return 0

        split_to_chunks_of_up_to_n_bytes(config)
        return 0

    except FuzzaideException as e:
        log.error("wasn't able to perform the operation requested: %s", str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())


_T = TypeVar("_T")


@dataclass(frozen=True)
class Config:
    is_dry_run: bool
    log_level: int
    num_equal_parts: int
    output_prefix: str
    filepath: str
    filesize: int
    names: List[str]
    maxsize: int

    @classmethod
    def from_args(cls: Type[_T], args: argparse.Namespace) -> _T:
        log_level = logging.INFO
        if args.verbose > 0 or args.dry_run:
            log_level = logging.DEBUG

        names: List[str] = []
        if args.names:
            names = args.names.split(",")

        maxsize = get_bytes_from_value_with_suffix(args.maxsize or "0")
        try:
            filesize = os.path.getsize(args.file)
        except OSError as e:
            raise FuzzaideException(f"wasn't able to get file '{args.file}' size: {e}")

        return cls(
            is_dry_run=args.dry_run,
            log_level=log_level,
            num_equal_parts=args.equally,
            output_prefix=args.output_prefix or "",
            filepath=args.file,
            filesize=filesize,
            names=names,
            maxsize=maxsize,
        )

    def __post_init__(self) -> None:
        # XXX: messages logically couple this method with arguments parsing

        if not os.path.isfile(self.filepath):
            raise FuzzaideException(
                f"file is not accessible or doesn't exist: '{self.filepath}'"
            )

        if self.filesize < 1:
            raise FuzzaideException(f"file '{self.filepath}' is empty")

        if not self.maxsize and not self.num_equal_parts:
            raise FuzzaideException(
                "you need to specify mode: -s or -e! See -h for help"
            )

        if self.maxsize and self.num_equal_parts:
            raise FuzzaideException("options -s and -e are mutually exclusive!")

        if self.maxsize and self.names:
            raise FuzzaideException("options -s and -N are mutually exclusive!")

        num_names = len(self.names)
        if num_names > 0 and num_names != self.num_equal_parts:
            raise FuzzaideException(
                "-N param should be comma separated list of file names, count of names should match -e "
                f"argument, but now you have {self.num_equal_parts} file parts and {num_names} names!"
            )


def get_config(argv: Sequence[str]) -> Config:
    args = get_args(argv or sys.argv[1:])
    return Config.from_args(args)


def get_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = create_argument_parser()

    if not argv:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args(argv)

    return args


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="tool to split file equally or into blocks of size specified",
        epilog="this script was born thanks to extraordinary laziness of its author",
    )

    parser.add_argument("-i", "--file", help="file to split", required=True)
    parser.add_argument(
        "-o",
        "--output-prefix",
        help="prefix for names of output files, may start with path for -s, "
        "should be output directory path for -e",
        default=None,
    )

    parser.add_argument(
        "-s",
        "--maxsize",
        help="split to blocks of up to MAXSIZE bytes (k/m/g suffixes supported)",
        type=str,
        metavar="MAXSIZE",
        default=None,
    )
    parser.add_argument(
        "-e",
        "--equally",
        help="split to N blocks of equal size",
        type=int,
        metavar="N",
        default=0,
    )
    parser.add_argument(
        "-N",
        "--names",
        help="comma separated list of names for output files (for use with -e)",
        default=None,
    )

    parser.add_argument("-v", "--verbose", help="be verbose", action="count", default=0)
    parser.add_argument(
        "-D",
        "--dry-run",
        help="perform dry run to see what would happen",
        action="store_true",
    )

    return parser


def get_bytes_from_value_with_suffix(val_with_suffix: str) -> int:
    """
    Convert strings like "100k" to integer values like 102400.
    """

    val_with_suffix = val_with_suffix.lower()
    u = val_with_suffix[-1]

    muls = {
        "k": 1024,
        "m": 1024 * 1024,
        "g": 1024 * 1024 * 1024,
    }

    try:
        if u and u in muls:
            value = int(val_with_suffix[0:-1])
            value *= muls[u]
            return value
        return int(val_with_suffix)
    except ValueError as e:
        raise FuzzaideException(f"wasn't able to convert value with suffix: {e}") from e


def split_to_equal_parts(config: Config) -> None:
    """
    Split file into equal chunks.
    """

    num_parts = config.num_equal_parts
    names = config.names

    if num_parts < 2:
        raise FuzzaideException(f"invalid number of parts to split a file: {num_parts}")

    fsize = config.filesize
    if fsize < num_parts:
        raise FuzzaideException(
            f"file '{config.filepath}' size is only {fsize} bytes. Can't split into {num_parts} even parts"
        )

    output_prefix = config.output_prefix

    need_create_prefix_dir = bool(output_prefix) and not os.path.isdir(output_prefix)

    if need_create_prefix_dir:
        log.debug("creating directory: '%s'", output_prefix)

        if not config.is_dry_run:
            try:
                os.makedirs(output_prefix, exist_ok=True)
            except OSError as e:
                raise FuzzaideException(
                    f"wasn't able to create output directory '{output_prefix}': {e}"
                ) from e

    blocksize = fsize // num_parts

    log.debug(
        "file size is %d. Splitting into %d files of %d bytes each",
        fsize,
        num_parts,
        blocksize,
    )

    name_idx = 0
    try:
        with open(config.filepath, "rb") as f:
            while True:
                data = f.read(blocksize)
                if not data:
                    break
                if len(data) < blocksize:
                    break

                if names:
                    fname = os.path.join(output_prefix, names[name_idx])
                else:
                    fname = output_prefix + str(name_idx)
                log.debug("writing file %s", fname)

                if not config.is_dry_run:
                    with open(fname, "wb") as fout:
                        fout.write(data)

                name_idx += 1

    except OSError as e:
        raise FuzzaideException(
            f"wasn't able to process input/output files: {e}"
        ) from e


def split_to_chunks_of_up_to_n_bytes(config: Config) -> None:
    """
    Split file to chunks of up to given size.
    """

    filepath = config.filepath

    if config.output_prefix:
        output_prefix = config.output_prefix
    else:
        output_prefix = filepath + "_"

    fsize = config.filesize

    blocksize = config.maxsize
    log.debug(
        "file size is %d. Splitting into files of up to %d bytes in size each",
        fsize,
        blocksize,
    )

    name_idx = 0
    try:
        with open(filepath, "rb") as f:
            while True:
                data = f.read(blocksize)
                if not data:
                    break

                fname = output_prefix + str(name_idx)
                log.debug("writing file %s", fname)

                if not config.is_dry_run:
                    with open(fname, "wb") as fout:
                        fout.write(data)
                name_idx += 1
    except OSError as e:
        raise FuzzaideException(
            f"wasn't able to process input/output files: {e}. Please make sure output directory exists"
        ) from e
