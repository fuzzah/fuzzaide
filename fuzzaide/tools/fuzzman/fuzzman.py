#!/usr/bin/env python3

# file    :  fuzzman.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from typing import Tuple, List, Union, Iterable, Dict, Optional

import os
import sys
import glob
import shutil
import signal
import argparse
from pprint import pprint
from time import sleep, time
from dataclasses import dataclass
from multiprocessing import cpu_count

from fuzzaide.common import which
from fuzzaide.common.exception import FuzzaideException
from fuzzaide.common.fuzz_stats import is_afl_fuzzer_stats_old, get_afl_stat_name
from .args import get_launch_args
from .running_process import RunningAFLProcess, TimeoutExpired
from .const import *


@dataclass
class BuildSpecType:
    """
    Settings for one build.
    Used to store data parsed from the --builds argument.
    """

    name: Optional[str]
    path: str
    count: Optional[Union[int, float]]
    is_percent: bool
    calc_percent: float = 0.0
    original_order: int = 0


class FuzzManager:
    """
    Literally GOD-class that needs a ton of rework :(
    Responsible for:
        1. Generating fuzzer commands for different run modes (normal, --builds, --cmd-file)
        2. Running commands
        3. Monitoring and restarting of commands
        4. Statistics counting
        5. Desicion making on termination of fuzzing job

    Limitations:
        1. Only AFL, AFL++ supported
        2. Only interactive output mode supported
    """

    def __init__(self, args: argparse.Namespace):
        self.procs = list()
        self.last_shown_screen_idx = 0
        self.args = args
        self.waited_for_child = False
        self.start_time = int(time())
        self.cores_specified = False
        self.num_from_file = 0

    @staticmethod
    def extract_instance_count_or_exit(amount: str) -> Tuple[Union[int, float], bool]:
        """
        Gets number of instances from strings like "5", "10%" or "66.6%".
        Returns: (value, is_percent)
        """

        count = 0
        perc = amount.endswith("%")
        try:
            if perc:
                count = float(amount.split("%", 1)[0])
            else:
                count = int(amount)
        except ValueError:
            sys.exit(
                "Error in --builds argument: '%s' is not convertible to number of instances (examples: 3, 66.6%%)"
                % (amount,)
            )

        return count, perc

    @staticmethod
    def extract_complex_mode_params(
        user_builds: Iterable[str], program: str, verbose: bool = False
    ) -> List[BuildSpecType]:
        """
        Iterate over --builds arguments and extract group name, path, number/percent of cpu cores.
        Raises FuzzaideException on errors.
        """

        params: List[BuildSpecType] = []
        for build_spec in user_builds:
            bspec = FuzzManager.extract_one_spec_complex_params(build_spec)
            params.append(bspec)

        if verbose:
            print("Params of --builds: ")
            pprint(params)

        all_dirs = all(os.path.isdir(p.path) for p in params)
        all_bins = all(os.path.isfile(p.path) for p in params)

        if not all_dirs and not all_bins:
            raise FuzzaideException(
                "--builds should point EITHER to directories OR to binaries"
            )

        # build directories provided -> each one should contain binary with same app name
        if all_dirs:
            for i, p in enumerate(params):
                prog_path = os.path.normpath(os.path.join(p.path, program))
                if not os.path.isfile(prog_path):
                    raise FuzzaideException(
                        "Error in --builds argument: directory '%s' does not contain '%s' (path checked: '%s')"
                        % (p.path, program, prog_path)
                    )
                params[i].path = prog_path

            return params

        # exact binaries specified (full or partial paths or in PATH)
        for i, p in enumerate(params):
            if which(p.path) is None:
                raise FuzzaideException(
                    "Error in --builds argument: file %s not found so it cannot be tested"
                    % (p.path,)
                )

        return params

    @staticmethod
    def extract_one_spec_complex_params(build_spec: str) -> BuildSpecType:
        """
        XXX: this comment
        Parse one `build_spec` string, return [name: str | None, path: str, count: int | float | None, is_percent: bool | None].
        Raises FuzzaideException on errors.
        """
        bspec = build_spec.split(":")  # 0:1:2 -> NAME:PATH:N[%]
        num_spec_parts = len(bspec)
        name = None
        path = None
        count = None
        perc = False
        if num_spec_parts == 1:
            path = bspec[0]
        elif num_spec_parts == 2:
            if "%" in bspec[1] or bspec[1].isnumeric():
                path = bspec[0]
                count, perc = FuzzManager.extract_instance_count_or_exit(bspec[1])
            else:
                name = bspec[0]
                path = bspec[1]
        elif num_spec_parts == 3:
            name = bspec[0]
            path = bspec[1]
            count, perc = FuzzManager.extract_instance_count_or_exit(bspec[2])
        else:
            raise FuzzaideException(
                "Error in --builds argument: format of one build is [NAME:]<dir/bin path>[:N[%]] (examples: -h/--help)"
            )

        if path.startswith("~"):
            path = os.path.expanduser(path)

        # return [name, path, count, perc]
        return BuildSpecType(name=name, path=path, count=count, is_percent=perc)

    @staticmethod
    def adjust_complex_mode_params(
        params: List[BuildSpecType],
        num_instances: int,
        were_cores_specified: bool,
        verbose: bool = False,
    ) -> List[BuildSpecType]:
        """
        For complex mode (--builds). Converts percent ratios to number of instances
        and makes sure that each build is used at least once.
        params is a list of 4-item lists: name, path, count/percent, is_percent.
        Raises FuzzaideException on errors.
        """

        # sum percents as specified by user
        percsum = 0.0
        for p in params:
            if p.count is not None and p.is_percent:
                percsum += p.count

        # normalize percents to 100 if required
        if percsum > 100.0:
            if verbose:
                print(
                    "Info: sum of percents in --builds is %.2f%% which is not 100%%. Will proportionally adjust it"
                    % (percsum,)
                )
            for p in params:
                if p.is_percent:
                    p.count = (p.count or 0.0) * 100.0 / percsum
            percsum = 100.0

        # count builds without number or percent of cores specified
        count_none = sum(1 for p in params if p.count is None)

        if count_none > 0:
            # set percents for builds without cores specified
            for p in params:
                if p.count is None:
                    p.count = (100.0 - percsum) / count_none
                    p.is_percent = True

        sum_cores_exact = sum(p.count or 0 for p in params if not p.is_percent)
        number_of_free_cores = num_instances - sum_cores_exact
        if number_of_free_cores < 0 or (number_of_free_cores == 0 and percsum > 0.0):
            raise FuzzaideException(
                "Error in --builds argument: not enough processor cores to fit desired configuration"
            )

        if percsum > 0.0:
            for p in params:
                # make 1 core for builds specified as percent
                if p.is_percent and (
                    p.count <= 0.0 or number_of_free_cores * p.count / 100.0 < 1
                ):
                    p.count = 1
                    p.is_percent = False

        # final normalization of percents
        percsum: float = sum(p.count or 0.0 for p in params if p.is_percent)
        if percsum != 0.0 and percsum != 100.0:
            for p in params:
                if p.is_percent:
                    p.count = p.count * 100.0 / percsum
            percsum = 100.0

        sum_cores_exact = sum(p.count or 0 for p in params if not p.is_percent)
        number_of_free_cores = num_instances - sum_cores_exact
        if number_of_free_cores < 0 or (number_of_free_cores == 0 and percsum > 0.0):
            raise FuzzaideException(
                "Error in --builds argument: not enough processor cores to fit desired configuration"
            )

        # convert all the rest percent ratios to number of cores
        if percsum > 0.0:
            for i, p in enumerate(params):
                if p.is_percent:
                    p.calc_percent = p.count
                    p.count = 0
                else:
                    p.calc_percent = 0.0
                p.original_order = i

            core_percent = 100.0 / number_of_free_cores
            while True:  # TODO: there must be a better way :(
                params = sorted(params, key=lambda p: -p.calc_percent)
                for p in params:
                    if p.calc_percent <= 0.0:
                        continue
                    p.calc_percent -= core_percent
                    percsum -= core_percent
                    p.count += 1
                    if percsum <= core_percent:
                        break
                if percsum <= core_percent:
                    break

            for p in params:
                p.is_percent = False

            # sanity check
            not_enough_cores = any(p.count < 1 for p in params)
            if not_enough_cores:
                raise FuzzaideException(
                    "Error in --builds argument: not enough processor cores to fit all the specified builds"
                )

            number_of_used_cores = sum(p.count or 0 for p in params)
            if number_of_used_cores != num_instances:
                if verbose:
                    print(
                        "Math in fuzzman is janky! Fixing error with delta of %d cores"
                        % (number_of_used_cores - num_instances,)
                    )
                params = sorted(params, key=lambda p: -p.calc_percent)
                params[0].count -= number_of_used_cores - num_instances
                if verbose:
                    pprint(params)

                number_of_used_cores = sum(p.count or 0 for p in params)
                if number_of_used_cores != num_instances:
                    raise FuzzaideException(
                        "Math in fuzzman is really janky! Error with delta of %d cores! "
                        "Please create an issue with verbose run screenshot.\nFor now you may want to specify different percent/amount of cores"
                        % (number_of_used_cores - num_instances,)
                    )

            params = sorted(params, key=lambda p: p.original_order)

        number_of_used_cores = sum(p.count or 0 for p in params)
        if were_cores_specified and number_of_used_cores != num_instances:
            raise FuzzaideException(
                "Error in --builds argument: less cores specified in --builds (%d) than in -n (%d)"
                % (number_of_used_cores, num_instances)
            )

        if verbose:
            print(
                "Using %d cores out of total %d available in OS"
                % (number_of_used_cores, cpu_count())
            )

        return params

    def load_custom_cmds(self, path: str) -> List[List[str]]:
        """
        Load custom fuzzer commands from file specified by path.
        Returns list of commands to run instead of fuzzman-generated commands.
        Each element in result list is [worker_name: str, command: str]
        """

        cmds = []
        if not os.path.isfile(path):
            sys.exit("Error: file '%s' doesn't exist or it's not a file" % path)

        with open(path, "rt") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if len(line) < 1 or line[0] == "#":
                continue

            cmd = line.split(":")
            if len(cmd) != 2:
                sys.exit(
                    "Error: bad command in file %s: %s\nCorrect format:\n  name : command"
                    % (path, line)
                )

            worker = []
            for s in cmd:
                s = s.strip()
                if len(s) < 1:
                    sys.exit(
                        "Error: empty worker name or command in file %s: %s\nCorrect format:\n  name : command"
                        % (path, line)
                    )

                worker.append(s)

            if self.args.verbose:
                print("Loaded custom command %s" % (*worker,))

            cmds.append(worker)

        # some sanity checks
        if len(cmds) < 1:
            sys.exit("Error: custom commands file doesn't contain any commands to run")

        unique_names = set(name for name, _ in cmds)
        if len(unique_names) < len(cmds):
            sys.exit("Error: custom commands file shouldn't contain duplicate names")

        if not self.args.cmd_file_allow_duplicates:
            unique_cmds = set(cmd for _, cmd in cmds)
            if len(unique_cmds) < len(cmds):
                sys.exit(
                    "Error: custom commands file shouldn't contain duplicate commands (use --cmd-file-allow-duplicates to override)"
                )

        if self.cores_specified and self.args.instances != len(cmds):
            sys.exit(
                "Error: you have specified number of cores = %d but custom commands file %s contains %d commands"
                % (self.args.instances, path, len(cmds))
            )

        return cmds

    def start(self, env: Optional[Dict[str, str]] = None) -> None:
        """
        Start instances either in normal mode, complex mode (--builds) or custom commands mode (--cmd-file).
        Exits the program on errors.
        """

        if self.args.instances is None:
            self.cores_specified = False
            self.args.instances = cpu_count()
        else:
            self.cores_specified = True

        args = self.args

        if args.instances < 1:
            args.instances = 1

        if which(args.fuzzer_binary) is None:
            sys.exit(
                "File %s not found so it cannot be used as fuzzer" % args.fuzzer_binary
            )

        if not os.path.exists(args.input_dir):
            try:
                os.makedirs(args.input_dir)
            except OSError:
                sys.exit("Can't create input directory %s" % args.input_dir)
        elif not os.path.isdir(args.input_dir):
            sys.exit("Can't use %s as input directory" % args.input_dir)

        if len(glob.glob(os.path.join(args.input_dir, "*"))) < 1:
            path = os.path.join(args.input_dir, "1")
            if args.verbose:
                print("Creating simple input corpus: %s" % path)
            try:
                with open(path, "w") as f:
                    f.write("12345")
            except OSError:
                sys.exit("Wasn't able to create input corpus")

        if args.cleanup and os.path.isdir(args.output_dir):
            print("Removing directory '%s'" % args.output_dir, file=sys.stderr)
            try:
                shutil.rmtree(args.output_dir, ignore_errors=True)
            except shutil.Error:
                sys.exit(
                    "Wasn't able to remove output directory '%s'" % args.output_dir
                )

        if args.cmd_file is not None:
            custom_cmds = self.load_custom_cmds(args.cmd_file)
            for i, (worker_name, cmd) in enumerate(custom_cmds):
                worker_env = os.environ.copy()
                worker_env["AFL_FORCE_UI"] = "1"
                if env is not None:
                    worker_env.update(env)

                print("Starting worker #%d {%s}: %s" % (i + 1, worker_name, cmd))
                self.procs.append(
                    RunningAFLProcess(
                        name=worker_name,
                        groupname="custom",
                        cmd=cmd,
                        env=worker_env,
                        verbose=args.verbose,
                    )
                )
            self.start_time = int(time())
            return

        complex_mode = args.builds is not None and len(args.builds) > 0

        params = []
        used_builds = []
        if complex_mode:
            try:
                params = self.extract_complex_mode_params(
                    user_builds=args.builds,
                    program=args.program[0],
                    verbose=args.verbose,
                )
                if args.verbose:
                    print('"Raw" params:')
                    pprint(params)

                params = self.adjust_complex_mode_params(
                    params=params,
                    num_instances=args.instances,
                    were_cores_specified=self.cores_specified,
                    verbose=args.verbose,
                )
                if args.verbose:
                    print("Adjusted params:")
                    pprint(params)
            except FuzzaideException as e:
                sys.exit(f"Error: {e}")

            for name, path, num_cores in params:
                used_builds.extend([[name, path]] * num_cores)
        else:  # normal run mode
            if which(args.program[0]) is None:
                sys.exit("File %s not found so it cannot be tested" % args.program[0])
            used_builds = [[None, args.program[0]]] * args.instances

        if args.verbose:
            print("Builds in use:")
            pprint(used_builds)

        # TODO: maybe split this method for basic and complex modes?
        if args.dump_cmd_file:
            print("# Fuzzer commands for use with --cmd-file option of fuzzman")

        for i, (groupname, path) in enumerate(used_builds):
            dictionary = ""

            if i == 0:
                role = "-M"
                worker_name = "m"
                if args.dict:
                    dictionary = " -x " + args.dict

            else:
                role = "-S"
                worker_name = "s"

            power_schedule = " -p explore" if i % 2 == 0 else " -p fast"

            worker_name += str(i + 1)

            if args.no_power_schedules:
                power_schedule = ""

            cmd = (
                args.fuzzer_binary
                + " -i "
                + args.input_dir
                + " -o "
                + args.output_dir
                + " -m "
                + args.memory_limit
                + dictionary
                + " "
                + role
                + " "
                + worker_name
                + power_schedule
            )

            if args.more_args:
                cmd += " " + args.more_args
            cmd += " -- " + path + " " + " ".join(args.program[1:])

            if args.dump_cmd_file:
                worker_env = dict()
            else:
                worker_env = os.environ.copy()
                worker_env["AFL_FORCE_UI"] = "1"

            if env is not None:
                worker_env.update(env)

            cmd = cmd.strip()

            if args.dump_cmd_file:
                wenv = " ".join(k + "=" + v for k, v in worker_env.items())
                if len(wenv) > 0:
                    print("%s : env %s %s" % (worker_name, wenv, cmd))
                else:
                    print("%s : %s" % (worker_name, cmd))
            else:
                print("Starting worker #%d {%s}: %s" % (i + 1, worker_name, cmd))
                self.procs.append(
                    RunningAFLProcess(
                        name=worker_name,
                        groupname=groupname,
                        cmd=cmd,
                        env=worker_env,
                        verbose=args.verbose,
                    )
                )

        if args.dump_cmd_file:
            sys.exit(0)

        self.start_time = int(time())

    def stop(self, grace_sig=signal.SIGINT) -> None:
        """
        Stop all fuzzer workers
        """

        if len(self.procs) < 1:
            return

        if self.args.dump_screens:
            print("Dumping status screens")
            self.dump_status_screens()
        else:
            print("Stopping processes")

        self.job_status_check(onlystats=True)

        for proc in self.procs:
            proc.stop(grace_sig=grace_sig)

        term_wait = 1.0
        if self.args.verbose:
            print("Waiting %.1f seconds to check for leftover processes" % (term_wait,))
        sleep(term_wait)

        for proc in self.procs:
            proc.stop(force=True)
        self.procs = []

    def health_check(self) -> bool:
        """
        Check if fuzzer workers are still running, also print each worker status
        """

        if len(self.procs) < 1:
            return False

        print("Checking status of workers")
        num_ok = sum(1 for proc in self.procs if proc.health_check())

        print("%d/%d workers report OK status" % (num_ok, len(self.procs)))
        return num_ok > 0

    def display_next_status_screen(self, outfile=sys.stdout, static_dump=False) -> None:
        """
        Show interactive status screen of one fuzzer for approximately 5 seconds
        """

        if len(self.procs) < 1:
            print("No status screen to show")
            return

        if len(self.procs) == 1:
            self.last_shown_screen_idx = 0

        outbuf = getattr(outfile, "buffer", outfile)

        # helper for drawing workaround on linux with fancy boxes mode
        mqj = b"mqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqj"

        instance = self.procs[self.last_shown_screen_idx]
        if self.is_process_still_running(instance.proc):
            outbuf.write(CURSOR_HIDE)
            if static_dump:
                num_dumps = 1
            else:
                num_dumps = 100

            for _ in range(num_dumps):
                data = instance.get_output(24)
                need_drawing_workaround = not self.args.no_drawing_workaround and len(
                    data
                )

                if need_drawing_workaround:
                    data[0] = data[0].replace(mqj, b"")

                for line in data:
                    outbuf.write(line)

                if need_drawing_workaround:
                    outbuf.write(SET_G1 + bSTG + mqj + bSTOP + cRST + RESET_G1)

                if not static_dump:
                    sleep(0.05)
            outbuf.write(CURSOR_SHOW)
        else:  # process is not running
            if not self.waited_for_child:
                try:
                    instance.proc.wait(3.0)  # wait to prevent zombie-processes
                except TimeoutExpired:
                    pass  # timeout waiting: hanged process?
                else:
                    self.waited_for_child = True

            data = instance.get_output(29)
            for line in data:
                outbuf.write(line)
            if not static_dump:
                sleep(5.0)

        outbuf.write(bSTOP + cRST + RESET_G1 + CURSOR_SHOW)

        if len(self.procs) > 0:
            self.last_shown_screen_idx += 1
            self.last_shown_screen_idx %= len(self.procs)

    @staticmethod
    def is_process_still_running(proc) -> bool:
        return proc.poll() is None

    def dump_status_screens(self, outfile=sys.stdout) -> None:
        """
        Print status screens of all fuzzer instances
        """

        self.last_shown_screen_idx = 0
        outbuf = getattr(outfile, "buffer", outfile)
        for _ in self.procs:
            outbuf.write(
                b"\n" * 40
            )  # messy "workaround" for overlapping status screens (tmux, etc)
            self.display_next_status_screen(outfile=outfile, static_dump=True)

        outbuf.write(b"\n\n")

    def get_fuzzer_stats(
        self, output_dir: str, idx: int, instance
    ) -> Optional[Dict[str, str]]:
        """
        Form a dictionary from fuzzer_stats file of given fuzzer instance
        """

        if instance.name is None or len(instance.name) < 1:
            print(
                "Wasn't able to get stats of instance #%d because somehow it has no name"
                % (idx,),
                file=sys.stderr,
            )
            return None

        stats_file_path = os.path.join(output_dir, instance.name, "fuzzer_stats")
        if not os.path.isfile(stats_file_path):
            print(
                "Wasn't able to get stats of instance %s because somehow it has no fuzzer_stats file"
                % (instance.name,),
                file=sys.stderr,
            )
            return None

        try:
            with open(stats_file_path, "rt") as f:
                data = f.readlines()
        except OSError:
            print(
                "Wasn't able to get stats of instance %s because of fail to open '%s'"
                % (instance.name, stats_file_path),
                file=sys.stderr,
            )
            return None

        if data is None:
            print(
                "Wasn't able to get data of instance %s because its fuzzer_stats file '%s' is empty"
                % (instance.name, stats_file_path),
                file=sys.stderr,
            )
            return None

        stats = dict()
        for line in data:
            if ":" not in line:
                continue

            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            stats[k] = v

        if len(stats) < 1:
            return None

        return stats

    @staticmethod
    def update_stat_timestamp(
        stats_dict: Dict[str, Union[int, str, float]],
        stat_name: str,
        saved_newest_stamp: int,
    ) -> int:
        """
        Use this method to update last (newest) path (crash, hang, etc) timestamp.
        Example: newest_path_stamp = update_stat_timestamp(stats, "last_path", newest_path_stamp)
        """

        stamp = stats_dict.get(stat_name)

        if stamp is None:
            return saved_newest_stamp

        try:
            stamp = int(stamp)
        except ValueError:
            return saved_newest_stamp

        if stamp > saved_newest_stamp:
            return stamp

        return saved_newest_stamp

    @staticmethod
    def format_seconds(seconds: int) -> str:
        """
        Returns time in AFL-like format: days, hrs, min, sec
        """

        s = seconds % 60
        m = (seconds // 60) % 60
        h = (seconds // 3600) % 24
        d = seconds // 86400

        if d > 0:
            return "%d days, %d hrs, %d min, %d sec" % (d, h, m, s)
        elif h > 0:
            return "%d hrs, %d min, %d sec" % (h, m, s)
        elif m > 0:
            return "%d min, %d sec" % (m, s)

        return "%d sec" % (s,)

    def job_status_check(self, onlystats=False) -> bool:
        """
        Enumerate fuzzer_stats files, print stats, return True if stopping required
        """

        output_dir = self.args.output_dir
        if output_dir is None or len(output_dir) < 1:
            return False

        newest_path_stamp = 0
        newest_hang_stamp = 0
        newest_crash_stamp = 0

        sum_execs = 0
        sum_paths = 0
        sum_hangs = 0
        sum_crashes = 0
        sum_restarts = 0

        use_old_style = None

        for idx, instance in enumerate(self.procs, start=1):
            stats = self.get_fuzzer_stats(output_dir, idx, instance)

            if not stats:
                continue

            if use_old_style is None:
                use_old_style = is_afl_fuzzer_stats_old(stats)
                if use_old_style is None:
                    continue

            crashes = int(
                stats.get(get_afl_stat_name("unique_crashes", use_old_style), 0)
            )
            hangs = int(stats.get(get_afl_stat_name("unique_hangs", use_old_style), 0))
            paths_total = int(
                stats.get(get_afl_stat_name("paths_total", use_old_style), 0)
            )
            paths_found = int(
                stats.get(get_afl_stat_name("paths_found", use_old_style), 0)
            )

            sum_restarts += instance.total_restarts
            sum_crashes += crashes
            sum_hangs += hangs
            sum_paths += paths_total
            sum_execs += int(stats.get("execs_done", 0))

            if not onlystats:
                if instance.proc.poll():
                    status = "NOT "
                else:
                    status = ""

                if instance.groupname is not None:
                    print(
                        "Worker %s of group %s is %srunning"
                        % (instance.name, instance.groupname, status)
                    )
                else:
                    print("Worker %s is %srunning" % (instance.name, status))

                print(
                    "\tcrashes: %d, hangs: %d, paths total: %d"
                    % (crashes, hangs, paths_total)
                )
                print(
                    "\tpaths discovered: %d (%.2f%% of total paths)"
                    % (paths_found, 100.0 * paths_found / (paths_total or 1))
                )

            newest_path_stamp = self.update_stat_timestamp(
                stats, get_afl_stat_name("last_path", use_old_style), newest_path_stamp
            )
            newest_hang_stamp = self.update_stat_timestamp(
                stats, get_afl_stat_name("last_hang", use_old_style), newest_hang_stamp
            )
            newest_crash_stamp = self.update_stat_timestamp(
                stats,
                get_afl_stat_name("last_crash", use_old_style),
                newest_crash_stamp,
            )

        print("\nStats of this fuzzing job:")
        job_duration = int(time()) - self.start_time
        print("Duration: %s" % (self.format_seconds(job_duration),))

        if newest_path_stamp == 0:
            if not onlystats:
                print("\nNo more stats to display (yet)")
            return False

        e = float(sum_execs)
        c = ""
        if e >= 1000000000:
            e /= 1000000000
            c = "B"
        elif e >= 1000000:
            e /= 1000000
            c = "M"
        elif e >= 1000:
            e /= 1000
            c = "K"

        if len(c) > 0:
            if c == "B":
                print("   Execs: %.4f%c" % (e, c))
            else:
                print("   Execs: %.2f%c" % (e, c))
        else:
            print("   Execs: %.0f" % (e,))

        now = int(time())

        newest_path_delta = now - newest_path_stamp
        newest_path_fmt = self.format_seconds(newest_path_delta)
        print("   Paths: %d.\tLast new path: %s ago" % (sum_paths, newest_path_fmt))

        if sum_hangs > 0:
            delta = now - newest_hang_stamp
            seconds_fmt = self.format_seconds(delta)
            print("   Hangs: %d.\tLast new hang: %s ago" % (sum_hangs, seconds_fmt))
        else:
            print("   Hangs: 0")

        if sum_crashes > 0:
            delta = now - newest_crash_stamp
            seconds_fmt = self.format_seconds(delta)
            print(" Crashes: %d.\tLast new crash: %s ago" % (sum_crashes, seconds_fmt))
        else:
            print(" Crashes: 0")

        if sum_restarts > 0:
            print("Fuzzer restarts: %d" % (sum_restarts,))

        # now decide if we need to stop
        if (
            self.args.no_paths_stop is not None
            and self.args.no_paths_stop <= newest_path_delta
        ):
            if (
                self.args.minimal_job_duration is not None
                and job_duration < self.args.minimal_job_duration
            ):
                return False
            return True

        return False


def main():
    args = get_launch_args()

    retcode = 7
    fuzzman = FuzzManager(args)

    stdoutbuf = getattr(sys.stdout, "buffer", sys.stdout)

    def handler(_signo, _stack_frame):
        stdoutbuf.write(bSTOP + cRST + RESET_G1 + CURSOR_SHOW)
        print()
        fuzzman.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)

    fuzzman.start()

    while True:
        stdoutbuf.write(TERM_CLEAR)
        if not fuzzman.health_check():  # this check also prints alive status of workers
            retcode = 1
            break

        sleep(5.0)
        stdoutbuf.write(TERM_CLEAR)
        fuzzman.display_next_status_screen()  # this displays fuzzer output in real time for ~5 seconds

        stdoutbuf.write(TERM_CLEAR)

        # this function displays stats and decides if we need to stop current fuzzing job
        if fuzzman.job_status_check():
            print("STOP CONDITION MET. Stopping current fuzzing job...")
            retcode = 0
            break
        sleep(5.0)

    fuzzman.stop()

    if retcode == 0:
        print("STOP CONDITION MET")

    return retcode


if __name__ == "__main__":
    sys.exit(main())
