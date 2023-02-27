# file    :  tools/fuzzman/args.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

import sys
import argparse
from multiprocessing import cpu_count

from fuzzaide.common import FuzzaideArgumentParser


def get_launch_args():
    parser = create_argument_parser()

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    check_args_for_common_mistakes(args)

    return args


def create_argument_parser():
    parser = FuzzaideArgumentParser(
        description="%(prog)s - your humble assistant to automate and manage fuzzing tasks",
        epilog="developed and tested by fuzzah for using with AFL++",
    )
    add_args_to_parser(parser)
    add_examples_to_parser(parser)

    return parser


def add_args_to_parser(parser):
    parser.add_argument(
        "program",
        nargs=argparse.REMAINDER,
        metavar="...",
        help="program with its arguments (example: ./myapp --file @@)",
    )
    parser.add_argument(
        "-n",
        "--instances",
        help="number of fuzzer instances to start (default: cpu count {%d})"
        % cpu_count(),
        default=None,
        type=int,
    )
    parser.add_argument(
        "-i", "--input-dir", help="input directory (default: ./in)", default="./in"
    )
    parser.add_argument(
        "-o", "--output-dir", help="output directory (default: ./out)", default=None
    )
    parser.add_argument(
        "-x",
        "--dict",
        help="dictionary for main instance (default: none)",
        default=None,
    )
    parser.add_argument(
        "-m",
        "--memory-limit",
        help="assign memory limit to each fuzzer instance (default: none)",
        default="none",
    )
    parser.add_argument(
        "--builds",
        nargs="+",
        metavar="[NAME:]<dir/bin path>[:N[%]]",
        help="specify multiple binaries for fuzzing and number or percent of cores to use"
        "(default: fuzz only one binary provided as the last argument)",
        default=None,
    )
    parser.add_argument(
        "--cmd-file",
        help="read custom fuzzer commands from file (incompatible with --builds)",
        default=None,
    )
    parser.add_argument(
        "--cmd-file-allow-duplicates",
        help="allow duplicate commands (but not names!) in --cmd-file argument",
        action="store_true",
    )
    parser.add_argument(
        "-C",
        "--cleanup",
        help="delete output directory before starting (default: don't delete)",
        action="store_true",
    )
    parser.add_argument(
        "-P",
        "--no-power-schedules",
        help="don't pass -p option to fuzzer (default: pass -p exploit for main instance, pass -p "
        "seek for secondary instances)",
        action="store_true",
    )
    parser.add_argument(
        "-W",
        "--no-drawing-workaround",
        help="disable linux G1 drawing workaround (default: workaround enabled)",
        action="store_true",
    )
    parser.add_argument(
        "--more-args",
        metavar="ARGS",
        help="additional arguments for fuzzer, added last (default: no arguments)",
        default=None,
    )
    parser.add_argument(
        "--fuzzer-binary",
        metavar="PATH",
        help="name or full path to fuzzer binary (default: afl-fuzz)",
        default="afl-fuzz",
    )
    parser.add_argument(
        "--no-paths-stop",
        metavar="N",
        help="stop fuzzing job if no new paths have been found in the last N seconds (default: don't stop)",
        default=None,
        type=int,
    )
    parser.add_argument(
        "--minimal-job-duration",
        metavar="N",
        help="don't stop fuzzing job earlier than N seconds from start (default: stop if --no-paths-stop specified)",
        default=None,
        type=int,
    )
    parser.add_argument(
        "--dump-screens",
        help="dump all status screens on job stop (default: don't dump)",
        action="store_true",
    )
    parser.add_argument(
        "--dump-cmd-file",
        help="dump fuzzer commands to put in file for --cmd-file)",
        action="store_true",
    )
    parser.add_argument(
        "-v", "--verbose", help="print more messages", action="store_true"
    )


def add_examples_to_parser(parser):
    examples = [
        ["Fuzz ./myapp using all CPU cores until stopped by Ctrl+C", "./myapp"],
        [
            "Set memory limit of 10 kilobytes, cleanup output directory",
            "-m 10K -C -- ./myapp",
        ],
        [
            "Pass additional agruments to fuzzer",
            '--more-args "-p fast" ./myapp @@',
        ],
        [
            "Run 4 instances and specify in/out directories",
            "-n 4 -i ../inputs/for_myapp -o ../outputs/myapp ./myapp @@",
        ],
        [
            "Specify non-default fuzzer",
            "--fuzzer-binary ~/git/fuzzer/obliterator -- ./myapp",
        ],
        [
            "Specify non-default fuzzer in path",
            "--fuzzer-binary py-afl-fuzz ./myapp",
        ],
        [
            "Stop if no new paths have been discovered across all fuzzers "
            "in the last 1 hour and 5 minutes (which is 3900 seconds)",
            "--no-paths-stop 3900 -- ./myapp",
        ],
        [
            "Same as above but make sure that fuzzing job runs for at least 8 hours "
            "(which is 28800 seconds)",
            "--minimal-job-duration 28800 --no-paths-stop 3900 ./myapp",
        ],
        [
            "Simultaneously fuzz multiple builds of the same application "
            "(app in PATH: 2 cores, app_asan: 1 core, app_laf: all the remaining cores)",
            "--builds app:2 /full_path/app_asan:1 ../relative_path/app_laf -- ./app",
        ],
        [
            r"Fuzz multiple builds in different dirs "
            r"(~/dir_asan/test: 1 core, ~/dir_basic/test: 30% of the remaining cores, ~/dir_laf/test: all the remaining cores)",
            r"--builds ~/dir_basic:30% ~/dir_asan/:1 ~/dir_laf -- ./test @@",
        ],
        [
            r"Fuzz multiple builds giving them some build/group names (./app_laf will use 100%-50%-10% = 40% of available cores)",
            r"--builds basic:./app:10% something:./app2:50% addr:./app_asan:1 UB:./app_ubsan:1 paths:./app_laf -- ./app @@",
        ],
        [
            "Run fuzzer commands from file job.fzm instead of commands generated by fuzzman "
            "(format of each line is name:command, names should match fuzzer dirs in output dir)",
            "-o out/ --cmd-file job.fzm",
        ],
    ]
    parser.set_examples(examples)


def check_args_for_common_mistakes(args):
    if args.cmd_file is None:
        t_len = len(args.program)
        if t_len < 1 or (args.program[0] == "--" and t_len < 2):
            sys.exit(
                "Error: you didn't specify PROGRAM you want to run. See examples: -h/--help"
            )

        if args.program[0] == "--":
            del args.program[0]

    if args.no_paths_stop and args.no_paths_stop < 1:
        sys.exit(
            "Error: bad value used for --no-paths-stop. You should specify number of seconds "
            "(e.g. --no-paths-stop 600)"
        )

    if args.minimal_job_duration and args.minimal_job_duration < 1:
        sys.exit(
            "Error: bad value used for --minimal-job-duration. You should specify number of seconds "
            "(e.g. --minimal-job-duration 3600)"
        )

    if args.cmd_file:
        if args.builds:
            sys.exit("Error: options --builds and --cmd-file are not compatible")

        if args.dump_cmd_file:
            sys.exit("Error: options --cmd-file and --dump-cmd-file are not compatible")

        if args.output_dir is None:
            sys.exit("Error: output dir must be specified for use with --cmd-file")

    if args.output_dir is None:
        args.output_dir = "./out"
