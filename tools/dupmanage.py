#!/usr/bin/env python3

# this script is WIP, it may be not production ready AT ALL # TODO: remove this line once script has become useful
# check LICENSE file in repository
# author: https://github.com/fuzzah

import os
import sys
import glob
import hashlib
import argparse


def main():
    # TODO: remove WIP tag
    parser = argparse.ArgumentParser(description='[WIP] %(prog)s - search and manage files with duplicate contents',
                                     epilog="Note: to use wildcards on huge amount of files you can quote your pattern\
                                     and btw ALWAYS BE CAREFUL WITH WHAT YOU TYPE. NO WARRANTY. NO REFUNDS")
    parser.add_argument('-v', '--verbose', help='print more messages', action='store_true')

    parser.add_argument('-r', '-R', '--recursive', help='also check files in subdirectories',
                        action='store_true')

    parser.add_argument('-H', '--hash', metavar='name', help='hash function to use, default is sha1', type=str,
                        default='sha1')
    parser.add_argument('-L', '--list-hashes', help='list supported hash algorithms', action='store_true')

    parser.add_argument('paths', metavar='<dir/file pattern>', help='files and directories to check', nargs='*',
                        default=[os.path.join('.', '*')])

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

    verbose = print if args.verbose else lambda *a, **k: None

    verbose("\n-------Parameters--------")
    for key, value in vars(args).items():
        verbose('args.' + key, value, sep=': ')
    verbose("----End of parameters----\n")

    if args.list_hashes:
        print('Sorted list of available file hashing algorithms:')
        print(', '.join(sorted(hashlib.algorithms_available)))
        return 0

    try:
        hashlib.new(args.hash)
    except Exception as e:
        sys.exit("Can't use hash function '%s'" % args.hash)

    def hashfile(filepath, blocksize=2**23): # read by 8 megabytes
        if not os.path.isfile(filepath):
            return None
        h = hashlib.new(args.hash)
        try:
            with open(filepath, 'rb') as f:
                while True:
                    data = f.read(blocksize)
                    if not data:
                        break
                    h.update(data)
        except Exception as e:
            print("Wasn't able to check file '%s': %s" % (filepath, str(e)), file=sys.stderr)
            return None
        else:
            return h.hexdigest()

    all_paths = []
    for path in args.paths:
        if '*' in path or '?' in path:
            all_paths.extend(glob.glob(path))
        else:
            all_paths.append(path)

    hash2file = {}
    file2hash = {}

    def traverse(filepath, level=0):
        if os.path.isfile(filepath):
            if filepath not in file2hash:
                verbose("hashing '%s' .. " % filepath, end='')
                h = hashfile(filepath)
                verbose(h)
                if h in hash2file:
                    print("duplicate: '%s' same as '%s'" % (filepath, hash2file[h][0]))
                    hash2file[h].append(filepath)
                else:
                    hash2file[h] = [filepath]
                file2hash[filepath] = h
        else:
            if level == 0 or args.recursive:
                for inner_path in glob.glob(os.path.join(filepath, '*')):
                    traverse(inner_path, level+1)

    for path in all_paths:
        verbose('CHECKING:', path)
        traverse(path)

    duplicate_groups = list()
    for h, fnames in hash2file.items():
        if len(fnames) > 1:
            duplicate_groups.append(fnames)

    if len(duplicate_groups) > 0:
        print('Found %d duplicate groups:' % len(duplicate_groups))
        for i, group in enumerate(sorted(duplicate_groups, key=len, reverse=True)):
            print('group #%d of size %d:' % (i+1, len(group)))
            print('\n'.join(group))
            print()
    else:
        print('No duplicates found')
    return 0


if __name__ == '__main__':
    sys.exit(main())
