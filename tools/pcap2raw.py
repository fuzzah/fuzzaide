#!/usr/bin/env python3

import os
import sys
import glob
import argparse
from hashlib import sha1


try:
    from scapy.all import rdpcap
except:
    sys.exit("Please install scapy: python3 -m pip install -U scapy --user")


class ArgumentParserWithExamples(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        argparse.ArgumentParser.__init__(self, *args, **kwargs)
        self.examples = []

    def add_example(self, info, command):
        self.examples.append([info, command])

    def add_examples(self, examples):
        for example in examples:
            self.examples.append(example)

    def print_help(self, show_examples=True):
        argparse.ArgumentParser.print_help(self)
        if show_examples and len(self.examples) > 0:
            print()
            print("Invocation examples:")
            for action, cmd in self.examples:
                print(action + ": \n\t" + sys.argv[0] + " " + cmd)


def main():
    parser = ArgumentParserWithExamples(
        description="%(prog)s - tool to extract raw packets from pcap files"
    )
    parser.add_argument(
        "-i",
        "--input",
        help="pattern(s) to search for pcap files to be processed",
        required=True,
        metavar="PATTERN",
        nargs="*",
    )
    output_args = parser.add_mutually_exclusive_group(required=True)
    output_args.add_argument("-o", "--output-dir", help="output directory")
    output_args.add_argument(
        "-C",
        "--cstring",
        help="print raw bytes of packets as C-strings",
        action="store_true",
    )
    parser.add_argument(
        "-r",
        "-R",
        "--recursive",
        help="also look for files in subdirectories",
        action="store_true",
    )
    parser.add_argument(
        "-F",
        "--filter",
        help='QUOTED comma separated list of filters for recursive searches, default: "*.cap,*.pcap,*.pcapng"',
        default="*.cap,*.pcap,*.pcapng",
    )

    parser.add_argument(
        "--prefix",
        help="prefix for names of created files (empty by default)",
        default="",
    )
    parser.add_argument(
        "--suffix",
        help="suffix for names of created files (empty by default)",
        default="",
    )
    parser.add_argument(
        "--ext",
        help="extension for names of created files (empty by default)",
        default="",
    )

    parser.add_argument(
        "-a",
        "-A",
        "--allow-duplicates",
        help="don't check if same packet was processed already",
        action="store_true",
    )

    parser.add_argument(
        "-v", "--verbose", help="print more messages", action="store_true"
    )
    parser.add_argument(
        "-D", "--dry-run", help="don't perform any disk writes", action="store_true"
    )

    parser.add_example(
        "Read packets from one file and display them as C-strings", "-i http.pcap -C"
    )
    parser.add_example(
        "Same, but save packets to files ./out/http1.raw, ./out/http2.raw, etc",
        "-i http.pcap --prefix http --ext raw -o ./out",
    )
    parser.add_example(
        "Recursively extract packets from all cap, pcap and pcapng files in input dir",
        "-r -i input/ -o ./out",
    )
    parser.add_example(
        "Specify custom match pattern", '-r -i input/ --filter "*" -o ./out'
    )
    parser.add_example(
        "Recursively extract packets from cap, pcap and pcapng in multiple input dirs",
        "-r -i in1/ in2/ in3/ -o ./out",
    )
    parser.add_example(
        "Perform non-recursive, but pattern-matching scan",
        '-i "./dir/*http*.*cap*" -o ./out',
    )
    parser.add_example(
        "Perform recursive, pattern-matching scan (pattern should match directories)",
        '-ri "./dir/pcaps-*" -o ./out',
    )

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

    if "." in args.prefix + args.suffix + args.ext:
        sys.exit("please don't use dots (.) in file name prefix, suffix or extension")

    if len(args.ext) > 0:
        args.ext = "." + args.ext

    verbose = print if args.verbose or args.dry_run else lambda *a, **k: None

    if args.output_dir is not None:
        if os.path.exists(args.output_dir):
            if not os.path.isdir(args.output_dir):
                sys.exit(
                    "Path '%s' exists, but cannot be used as output directory"
                    % (args.output_dir,)
                )
            verbose(
                "Output directory exists: '%s'" % (args.output_dir,), file=sys.stderr
            )
        else:
            verbose(
                "Creating output directory '%s'" % (args.output_dir,), file=sys.stderr
            )
            if not args.dry_run:
                try:
                    os.makedirs(args.output_dir)
                except Exception as e:
                    sys.exit(
                        "Wasn't able to create output directory '%s' : %s"
                        % (args.output_dir, str(e))
                    )

    filters = [f for f in args.filter.split(",")]
    filters = sorted(filter(lambda f: len(f) > 0, set(filters)))

    if len(filters) < 1:
        print('WARNING: using filter "*"', file=sys.stderr)
        filters = ["*"]

    verbose("Using filters: %s" % (", ".join(filters),))

    all_paths = []

    for path in set(args.input):
        if "*" in path or "?" in path:
            all_paths.extend(glob.glob(path))
        else:
            all_paths.append(path)

    used_hashes = set()

    def get_next_path():
        path = args.output_dir
        while os.path.exists(path):
            get_next_path.last_number += 1
            path = os.path.join(
                args.output_dir,
                args.prefix + str(get_next_path.last_number) + args.suffix + args.ext,
            )
        return path

    get_next_path.last_number = 0

    def traverse(filepath, level=0):
        num_processed = 0
        if os.path.isfile(filepath):
            verbose("Reading '%s' .. " % (filepath,), file=sys.stderr)

            try:
                packets = rdpcap(filepath)
            except Exception as e:
                print(
                    "WARNING: wasn't able to read '%s': %s" % (filepath, str(e)),
                    file=sys.stderr,
                )
                return num_processed

            s = len(packets)
            if s < 1:
                print("WARNING: empty pcap, nothing to do", file=sys.stderr)
                return num_processed

            if args.cstring:
                for p in packets:
                    raw = bytes(p)
                    h = sha1(raw)
                    if args.allow_duplicates or h not in used_hashes:
                        used_hashes.add(h)
                        num_processed += 1
                        raw = "".join("\\x%02X" % byte for byte in raw)
                        print('"' + raw + '",')

            else:
                for i, p in enumerate(packets):
                    raw = bytes(p)
                    h = sha1(raw)
                    if args.allow_duplicates or h not in used_hashes:
                        used_hashes.add(h)
                        fname = get_next_path()
                        verbose(
                            "Saving packet #%d to %s" % (i + 1, fname), file=sys.stderr
                        )
                        if args.dry_run:
                            num_processed += 1
                            continue

                        try:
                            with open(fname, "wb") as f:
                                f.write(raw)
                        except Exception as e:
                            print(
                                "Wasn't able to save packet #"
                                + str(i + 1)
                                + " to file "
                                + fname,
                                file=sys.stderr,
                            )
                        else:
                            num_processed += 1
        else:
            verbose("Checking directory", filepath, file=sys.stderr)
            if level == 0 or args.recursive:
                if args.recursive:
                    for filter in filters:
                        for inner_path in glob.glob(os.path.join(filepath, filter)):
                            num_processed += traverse(inner_path, level + 1)
                else:
                    for inner_path in glob.glob(os.path.join(filepath, "*")):
                        num_processed += traverse(inner_path, level + 1)

        return num_processed

    processed = sum(traverse(path) for path in all_paths)
    if args.cstring:
        print("Packets displayed: %d" % (processed,), file=sys.stderr)
    else:
        print("Packets saved: %d" % (processed,), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
