#!/usr/bin/env python3

# file    :  argv-fuzz-cook.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description='tool to prepare arguments for use with AFL include '
                                                 'file argv-fuzz-inl.h',
                                     epilog='this script was born thanks to laziness of its author')
    parser.add_argument('-c', '--cstring', help='print null-symbols as \\x00', action='store_true')
    parser.add_argument('arguments', help='all the args fuzzed program runs with', nargs=argparse.REMAINDER,
                        metavar='<rest arguments>')

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()
    argv = list(map(lambda x: '"' + x + '"' if ' ' in x else x, args.arguments))
    prepped = '\x00'.join(argv) + '\x00\x00'
    if args.cstring:
        print(repr(prepped))
    else:
        print(prepped, end='')

    return 0


if __name__ == '__main__':
    sys.exit(main())
