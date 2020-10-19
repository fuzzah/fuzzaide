#!/usr/bin/env python3

# file    :  split-file-contents.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description='tool to split file equally or into blocks of size specified',
                                     epilog='this script was born thanks to extraordinary laziness of its author')

    parser.add_argument('-f', '--file', help='file to split', required=True)
    parser.add_argument('-o', '--output-prefix', help='prefix for names of output files, may start with path for -s, '
                                                      'should be output directory path for -e', default=None)

    parser.add_argument('-s', '--maxsize', help='split to blocks of MAXSIZE bytes (k/m/g suffixes supported)',
                        type=str, metavar='MAXSIZE', default=None)
    parser.add_argument('-e', '--equally', help='split to N blocks of equal size', type=int, metavar='N', default=None)
    parser.add_argument('-N', '--names', help='comma separated list of names for output files (for use with -e)',
                        default=None)

    parser.add_argument('-v', '--verbose', help='be verbose', action='count', default=0)
    parser.add_argument('-D', '--dry-run', help='perform dry run to see what would happen', action='store_true')

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

    if args.dry_run:
        print("THIS IS DRY RUN. NO WRITE OPERATIONS ARE MADE", file=sys.stderr)

    if not os.path.isfile(args.file):
        sys.exit("File is not accessible or doesn't exist: '%s'" % args.file)

    if not args.maxsize and not args.equally:
        sys.exit("You need to specify mode: -s or -e! See -h for help")

    if args.maxsize and args.equally:
        sys.exit("-s and -e are mutually exclusive!")

    if args.maxsize and args.names:
        sys.exit("-s and -N are mutually exclusive!")

    verbose = print if args.verbose > 0 else lambda *a, **k: None
    #verbose2 = print if args.verbose > 1 else lambda *a, **k: None

    if args.equally:
        num_parts = args.equally
        if num_parts < 2:
            sys.exit("No need to 'split' file into %d parts. Leaving" % num_parts)

        names = None
        if args.names:
            names = args.names.split(',')
            if len(names) != num_parts:
                sys.exit("-N param should be comma separated list of file names, count of names should match -e "
                         "argument, but now you have %d file parts and %d names!" % (num_parts, len(names)))

        fsize = os.path.getsize(args.file)
        if fsize < num_parts:
            sys.exit("File '%s' size is only %d bytes. Can't split into %d even parts" % (args.file, fsize, num_parts))

        if args.output_prefix:
            if not os.path.isdir(args.output_prefix):
                verbose("Creating directory(-ies): '%s'" % args.output_prefix)
                if not args.dry_run:
                    try:
                        os.makedirs(args.output_prefix, exist_ok=True)
                    except Exception as e:
                        print("Wasn't able to create output directory '%s'. Error follows:" % args.output_prefix,
                              file=sys.stderr)
                        sys.exit(e)
        else:
            args.output_prefix = ''

        blocksize = fsize // num_parts

        verbose("File size is %d. Splitting into %d files of %d bytes each" % (fsize, num_parts, blocksize))

        name_idx = 0
        try:
            with open(args.file, 'rb') as f:
                while True:
                    data = f.read(blocksize)
                    if not data:
                        break
                    if len(data) < blocksize:
                        break
                    if names:
                        fname = os.path.join(args.output_prefix, names[name_idx])
                    else:
                        fname = args.output_prefix + str(name_idx)
                    verbose("Writing file %s" % fname)
                    if not args.dry_run:
                        with open(fname, 'wb') as fout:
                            fout.write(data)
                    name_idx += 1
        except Exception as e:
            print("Wasn't able to process input/output files. Error follows:", file=sys.stderr)
            sys.exit(e)
    else:  # split not equally, by size
        def get_bytes(s):
            s = s.lower()
            u = s[-1]
            if u in ['k', 'm', 'g']:
                value = int(s[0:-1])
                if u == 'k':
                    value *= 1024
                elif u == 'm':
                    value *= 1024 * 1024
                elif u == 'g':
                    value *= 1024 * 1024 * 1024
                return value
            return int(s)

        if not args.output_prefix:
            args.output_prefix = args.file + '_'

        fsize = os.path.getsize(args.file)
        if fsize < 1:
            sys.exit("File '%s' is empty. Leaving" % args.file)

        blocksize = get_bytes(args.maxsize)
        verbose("File size is %d. Splitting into files of up to %d bytes in size each" % (fsize, blocksize))

        name_idx = 0
        try:
            with open(args.file, 'rb') as f:
                while True:
                    data = f.read(blocksize)
                    if not data:
                        break
                    fname = args.output_prefix + str(name_idx)
                    verbose("Writing file %s" % fname)
                    if not args.dry_run:
                        with open(fname, 'wb') as fout:
                            fout.write(data)
                    name_idx += 1
        except Exception as e:
            print("Wasn't able to process input/output files. Error follows:", file=sys.stderr)
            sys.exit(e)

    verbose("Work complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
