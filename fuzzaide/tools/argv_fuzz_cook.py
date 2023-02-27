#!/usr/bin/env python3

# file    :  argv-fuzz-cook.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from typing import Sequence, Optional

import sys
import argparse


def main(argv: Optional[Sequence[str]] = None):
    args = get_args(argv or sys.argv[1:])
    prepped = process_args(args.arguments)

    if args.cstring:
        print(repr(prepped))
    else:
        print(prepped, end="")

    return 0


def get_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = create_argument_parser()
    if not argv:
        parser.print_help()
        sys.exit(0)

    return parser.parse_args(argv)


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="tool to prepare arguments for use with AFL include "
        "file argv-fuzz-inl.h",
        epilog="this script was born thanks to laziness of its author",
    )
    parser.add_argument(
        "-c", "--cstring", help="print null-symbols as \\x00", action="store_true"
    )
    parser.add_argument(
        "arguments",
        help="all the args fuzzed program runs with",
        nargs=argparse.REMAINDER,
        metavar="<rest arguments>",
    )

    return parser


def process_args(args: Sequence[str]) -> str:
    argv = list(map(lambda x: '"' + x + '"' if " " in x else x, args))
    prepped = "\x00".join(argv) + "\x00\x00"
    return prepped


if __name__ == "__main__":
    sys.exit(main())
