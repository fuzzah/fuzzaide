#!/usr/bin/env python3

# file    :  dupmanage.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

import os
import sys
import glob
import shutil
import hashlib
import argparse
import itertools


def main():
    parser = argparse.ArgumentParser(
        description="%(prog)s - search and manage files with duplicate contents",
        epilog="Note: to use wildcards on huge amount of files you can quote your pattern\
                                     and btw ALWAYS BE CAREFUL WITH WHAT YOU TYPE. NO WARRANTY. NO REFUNDS",
    )
    parser.add_argument(
        "-v", "--verbose", help="print more messages", action="store_true"
    )

    parser.add_argument(
        "-D", "--dry-run", help="don't perform any disk writes", action="store_true"
    )

    parser.add_argument(
        "-r",
        "-R",
        "--recursive",
        help="also check files in subdirectories",
        action="store_true",
    )
    parser.add_argument(
        "-s", "--display-hashes", help="also display hashes", action="store_true"
    )

    parser.add_argument(
        "-H",
        "--hash",
        metavar="name",
        help="hash function to use, default is sha1",
        default="sha1",
    )
    parser.add_argument(
        "-L",
        "--list-hashes",
        help="list supported hash algorithms",
        action="store_true",
    )

    parser.add_argument(
        "-o", "--output-dir", help="output directory for actions MOVE and COPY"
    )
    parser.add_argument(
        "-a",
        "--append",
        help="hash files that already exist in output dir",
        action="store_true",
    )

    parser.add_argument(
        "-P",
        "--preserve-names",
        help="don't rename files, just copy to output directory (false by default) (this will overwrite files on name collision)",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--prefix",
        help="prefix for names of copied/moved files (empty by default)",
        default="",
    )
    parser.add_argument(
        "--suffix",
        help="suffix for names of copied/moved files (empty by default)",
        default="",
    )
    parser.add_argument(
        "--ext", help="resulting file extension (empty by default)", default=""
    )

    parser.add_argument(
        "action",
        help="desired action",
        choices=["list", "ls", "copy", "cp", "move", "mv", "delete", "rm"],
    )

    parser.add_argument(
        "type",
        help="type of files to perform action on",
        choices=["unique", "u", "uniq", "duplicates", "d", "dup", "mixed", "mix", "m"],
    )

    parser.add_argument(
        "paths",
        metavar="<dir/file pattern>",
        help="files and directories to check",
        nargs="*",
        default=[os.path.join(".", "*")],
    )

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    if "-L" in sys.argv:
        print("Sorted list of available file hashing algorithms:", file=sys.stderr)
        print(", ".join(sorted(hashlib.algorithms_available)), file=sys.stderr)
        return 0

    args = parser.parse_args()

    verbose = print if args.verbose else lambda *a, **k: None

    if len(args.prefix + args.suffix + args.ext) > 0 and args.preserve_names:
        sys.exit(
            "Names preserving (-P) is incompatible with custom file name prefix, suffix and extension"
        )

    action_map = {"ls": "list", "cp": "copy", "mv": "move", "rm": "delete"}
    args.action = action_map.get(args.action, args.action)

    if args.append or args.action in ("move", "copy"):  # need output directory
        if args.output_dir is None:
            sys.exit(
                "Please specify output directory (-o) for use with --append option or MOVE and COPY actions"
            )

        if os.path.exists(args.output_dir):
            if not os.path.isdir(args.output_dir):
                sys.exit(
                    "Path '%s' exists, but cannot be used as output directory"
                    % (args.output_dir,)
                )
        else:
            verbose(
                "Trying to create directory '%s'" % (args.output_dir,), file=sys.stderr
            )
            if not args.dry_run:
                try:
                    os.makedirs(args.output_dir)
                except Exception as e:
                    sys.exit(
                        "Wasn't able to create output directory '%s' : %s"
                        % (args.output_dir, str(e))
                    )

    if args.append and args.action == "delete":
        sys.exit("Error: append option is incompatible with delete action")

    type_map = {
        "u": "unique",
        "uniq": "unique",
        "d": "duplicates",
        "dup": "duplicates",
        "m": "mixed",
        "mix": "mixed",
    }
    args.type = type_map.get(args.type, args.type)

    try:
        hashlib.new(args.hash)
    except ValueError:
        sys.exit("Can't use hash function '%s'" % args.hash)

    def hashfile(filepath, blocksize=2 ** 23):  # read by 8 megabytes
        if not os.path.isfile(filepath):
            return None
        h = hashlib.new(args.hash)
        try:
            with open(filepath, "rb") as f:
                while True:
                    data = f.read(blocksize)
                    if not data:
                        break
                    h.update(data)
        except Exception as e:
            print(
                "Wasn't able to check file '%s': %s" % (filepath, str(e)),
                file=sys.stderr,
            )
            return None
        else:
            return h.hexdigest()

    all_paths = []
    if args.append:
        all_paths.append(args.output_dir)

    for path in args.paths:
        if "*" in path or "?" in path:
            all_paths.extend(glob.glob(path))
        else:
            all_paths.append(path)

    hash2file = {}
    file2hash = {}

    def traverse(filepath, level=0):
        if os.path.isfile(filepath):
            if filepath not in file2hash:
                verbose("hashing '%s' .. " % filepath, end="", file=sys.stderr)
                h = hashfile(filepath)
                verbose(h, file=sys.stderr)
                if h is not None:
                    if h in hash2file:
                        verbose(
                            "duplicate: '%s' is same as '%s'"
                            % (filepath, hash2file[h][0]),
                            file=sys.stderr,
                        )
                        hash2file[h].append(filepath)
                    else:
                        hash2file[h] = [filepath]
                    file2hash[filepath] = h
        else:
            if level == 0 or args.recursive:
                for inner_path in glob.glob(os.path.join(filepath, "*")):
                    traverse(inner_path, level + 1)

    for path in all_paths:
        verbose("CHECKING:", path, file=sys.stderr)
        traverse(path)

    if args.action == "list":
        if args.display_hashes:

            def action(fname):
                print(file2hash[fname] + ";" + fname)

        else:

            def action(fname):
                print(fname)

    elif args.action == "delete":
        if args.dry_run:

            def action(fname):
                verbose("delete '%s'" % (fname,))

        else:

            def action(fname):
                verbose("delete '%s'" % (fname,))
                try:
                    shutil.rmtree(fname)
                except Exception as e:
                    print(
                        "WARNING: Wasn't able to delete file '%s' : %s"
                        % (fname, str(e)),
                        file=sys.stderr,
                    )

    else:  # action = copy | move
        if "/" in args.prefix + args.suffix + args.ext:
            sys.exit("can't use / in output file name prefix, suffix or extension")

        if "." in args.prefix + args.suffix + args.ext:
            sys.exit(
                "please don't use dots (.) in file name prefix, suffix or extension"
            )

        if len(args.ext) > 0:
            args.ext = "." + args.ext

        if args.preserve_names:
            verbose(
                "Will preserve file names (files with matching names may be overwritten)",
                file=sys.stderr,
            )

            def get_next_path(oldname):
                return os.path.join(args.output_dir, os.path.basename(oldname))

        else:
            verbose(
                "Will generate unique names, pattern: '"
                + args.prefix
                + "<number>"
                + args.suffix
                + args.ext
                + "', example: '"
                + args.prefix
                + "42"
                + args.suffix
                + args.ext
                + "'",
                file=sys.stderr,
            )

            def get_next_path(oldname):
                get_next_path.last_number += 1
                path = os.path.join(
                    args.output_dir,
                    args.prefix
                    + str(get_next_path.last_number)
                    + args.suffix
                    + args.ext,
                )
                while os.path.exists(path):
                    get_next_path.last_number += 1
                    path = os.path.join(
                        args.output_dir,
                        args.prefix
                        + str(get_next_path.last_number)
                        + args.suffix
                        + args.ext,
                    )
                return path

            get_next_path.last_number = 0

        if args.dry_run:

            def action(fname):
                newpath = get_next_path(fname)
                print(
                    "%s '%s' to '%s'" % (args.action, fname, newpath), file=sys.stderr
                )

        else:
            if args.action == "copy":
                operation = shutil.copy
            else:
                operation = shutil.move

            def action(fname):
                newpath = get_next_path(fname)
                print("%s '%s' to '%s'" % (args.action, fname, newpath))
                try:
                    operation(fname, newpath)
                except Exception as e:
                    print(
                        "WARNING: Wasn't able to %s file '%s' : %s"
                        % (args.action, fname, str(e)),
                        file=sys.stderr,
                    )

    files = hash2file.values()

    if args.type == "unique":
        files = filter(lambda a: len(a) == 1, files)
    elif args.type == "duplicates":
        files = filter(lambda a: len(a) > 1, files)
    else:
        files = map(lambda a: [a[0]], files)

    files = itertools.chain.from_iterable(files)
    if args.type == "duplicates":
        files = sorted(files, key=lambda name: (file2hash.get(name, "UNKNOWN"), name))
    else:
        files = sorted(files)

    matching_files = 0
    if len(files) > 0:
        if args.append:
            abs_out = os.path.abspath(args.output_dir)
            for fname in files:
                fpath = os.path.join(abs_out, os.path.basename(fname))
                if os.path.exists(fpath) and os.path.samefile(
                    fpath, os.path.abspath(fname)
                ):
                    continue  # don't process files that are already in output_dir
                action(fname)
                matching_files += 1
        else:
            for fname in files:
                action(fname)
            matching_files = len(files)

    if matching_files > 0:
        print("Matching files: %d" % (matching_files,), file=sys.stderr)
    else:
        print("No files to %s" % (args.action,), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
