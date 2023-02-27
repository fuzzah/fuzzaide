#!/usr/bin/env python3

# file    :  split-dir-contents.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

import os
import sys
import math
import glob
import shutil
import argparse


def indexed_iter_by_n(collection, n):
    idx = 0
    for i in range(0, len(collection), n):
        yield idx, collection[i : i + n]
        idx += 1


def main():
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
        help="dry run to show you what would happen",
        action="store_true",
    )
    parser.add_argument(
        "-A", "--all", help="also copy hidden files", action="store_true"
    )
    parser.add_argument(
        "-v", "--verbose", help="verbose output", action="count", default=0
    )

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

    verbose = print if args.verbose > 0 else lambda *a, **k: None
    verbose2 = print if args.verbose > 1 else lambda *a, **k: None

    def warning(a):
        print(a, file=sys.stderr)

    if args.dry_run:
        print("THIS IS DRY-RUN, NO ACTUAL WRITE OPERATIONS ARE MADE")
        if args.move:

            def process_file(filepath, destination):
                fname = os.path.basename(filepath)
                if os.path.exists(os.path.join(destination, fname)):
                    if args.force > 1:
                        verbose2("[DRY-RUN] Moving]", filepath, "to", destination)
                    else:
                        warning(
                            "Not moving file %s because same name is used in destination directory %s (-ff to "
                            "overwrite)" % (filepath, destination)
                        )
                else:
                    verbose2("[DRY-RUN] Moving", filepath, "to", destination)

        else:

            def process_file(filepath, destination):
                fname = os.path.basename(filepath)
                if (
                    not os.path.exists(os.path.join(destination, fname))
                    or args.force > 1
                ):
                    print("[DRY-RUN] Copying", filepath, "to", destination)
                else:
                    warning(
                        "Not moving file %s because same name is used in destination directory %s (-ff to "
                        "overwrite)" % (filepath, destination)
                    )

    else:
        if args.move:

            def process_file(filepath, destination):
                fname = os.path.basename(filepath)
                if os.path.exists(os.path.join(destination, fname)):
                    if args.force > 1:
                        verbose2("Moving", filepath, "to", destination)
                        shutil.copy(filepath, destination)
                        os.remove(filepath)
                    else:
                        warning(
                            "Not moving file %s because same name is used in destination directory %s (-ff to "
                            "overwrite)" % (filepath, destination)
                        )
                else:
                    verbose2("Moving", filepath, "to", destination)
                    shutil.move(filepath, destination)

        else:

            def process_file(filepath, destination):
                fname = os.path.basename(filepath)
                if (
                    not os.path.exists(os.path.join(destination, fname))
                    or args.force > 1
                ):
                    verbose2("Copying", filepath, "to", destination)
                    shutil.copy(filepath, destination)
                else:
                    warning(
                        "Not copying file %s because same name is used in destination directory %s (-ff to "
                        "overwrite)" % (filepath, destination)
                    )

    def process_chunk(filepaths, destination):
        verbose("Processing", len(filepaths), "files, destination:", destination)

        if not os.path.exists(destination):
            if args.dry_run:
                print("[DRY-RUN] Creating directory", destination)
            else:
                verbose2("Creating directory", destination)
                try:
                    os.makedirs(destination)
                except OSError as e:
                    print(
                        "Wasn't able to create directory ",
                        destination,
                        ":",
                        sep="",
                        file=sys.stderr,
                    )
                    sys.exit(e)

        if os.path.isdir(destination):
            if os.listdir(destination):
                if args.force > 0:
                    warning(
                        "Directory already exists and contains some files: %s. CONTINUING due to --force"
                        % destination
                    )
                else:
                    sys.exit(
                        "Directory already exists and contains some files: %s.\n"
                        "You can:\n\t1) use (some other) --output-prefix\n"
                        "\t2) manually clean up your files\n"
                        "\t3) specify -f or --force to allow copying to non-empty directories"
                        % destination
                    )
        else:
            if not args.dry_run:
                raise OSError("Can't access path %s as directory" % destination)

        for filepath in filepaths:
            process_file(filepath, destination)

    if not os.path.isdir(args.input_dir):
        sys.exit("This doesn't seem like existing directory: %s" % args.input_dir)

    if args.output_prefix == "":
        if args.input_dir == "." or args.input_dir == "./":
            args.output_prefix = "split_chunk"
        else:
            args.output_prefix = args.input_dir + "_chunk"

    filenames = glob.glob(os.path.join(args.input_dir, "*"))
    if args.all:
        filenames.extend(glob.glob(os.path.join(args.input_path, ".*")))

    filenames = sorted(filter(lambda path: os.path.isfile(path), filenames))
    if len(filenames) < 1:
        warning("No files to process. Leaving")
        return 0

    if args.chunk_size < 1:
        sys.exit("Chunk size (NUMFILES) should be more than 0")

    num_dirs = math.ceil(1.0 * len(filenames) / args.chunk_size)

    message = "%d files from %s to %s" % (
        len(filenames),
        args.input_dir,
        args.output_prefix + "0",
    )

    if num_dirs > 1:
        message += "-%s" % (args.output_prefix + str(num_dirs - 1))

    if args.move:
        verbose("Will MOVE", message)
    else:
        verbose("Will COPY", message)

    for dirnum, filepaths in indexed_iter_by_n(filenames, args.chunk_size):
        try:
            process_chunk(filepaths, args.output_prefix + str(dirnum))
        except OSError as e:
            if args.force < 1:
                sys.exit(e)
            else:
                warning(e)

    verbose("Work complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
