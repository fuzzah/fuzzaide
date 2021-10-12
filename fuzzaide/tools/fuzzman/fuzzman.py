#!/usr/bin/env python
# -*- coding: utf-8 -*-

# file    :  fuzzman.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from __future__ import print_function

import os
import sys
import glob
import shlex
import shutil
import signal
from time import sleep, time
from pprint import pprint

from multiprocessing import cpu_count

from fuzzaide.common import isnumeric, which
from .args import get_launch_args
from .running_process import RunningAFLProcess, TimeoutExpired
from .const import *


class FuzzManager:
    def __init__(self, args):
        self.procs = list()
        self.lastshown = 0
        self.args = args
        self.waited_for_child = False
        self.start_time = int(time())
        self.cores_specified = False
        self.num_from_file = 0

    @staticmethod
    def extract_instance_count(s):
        """
        Gets number of instances from strings like "5", "10%" or "66.6%"
        """
        count = 0
        perc = s.endswith("%")
        try:
            if perc:
                count = float(s.split("%", 1)[0])
            else:
                count = int(s)
        except ValueError:
            sys.exit(
                "Error in --builds argument: '%s' is not convertible to number of instances (examples: 3, 66.6%%)"
                % (s,)
            )

        return count, perc

    def extract_complex_mode_params(self):
        args = self.args

        params = []
        for b in args.builds:
            bi = b.split(":")  # 0:1:2 -> NAME:PATH:N[%]
            n = len(bi)
            name = None
            path = None
            count = None
            perc = False
            if n == 1:
                path = bi[0]
            elif n == 2:
                if "%" in bi[1] or isnumeric(bi[1]):
                    path = bi[0]
                    count, perc = self.extract_instance_count(bi[1])
                else:
                    name = bi[0]
                    path = bi[1]
            elif n == 3:
                name = bi[0]
                path = bi[1]
                count, perc = self.extract_instance_count(bi[2])
            else:
                sys.exit(
                    "Error in --builds argument: format of one build is [NAME:]<dir/bin path>[:N[%]] (examples: -h/--help)"
                )
            
            if path.startswith("~"):
                path = os.path.expanduser(path)
            params.append([name, path, count, perc])

        if args.verbose:
            print("Params of --builds: ")
            pprint(params)

        all_dirs = all(os.path.isdir(p) for _, p, _, _ in params)
        all_bins = all(os.path.isfile(p) for _, p, _, _ in params)

        if not all_dirs and not all_bins:
            sys.exit(
                "Error: --builds should point EITHER to directories OR to binaries"
            )

        # build directories provided -> each one should contain binary with same app name
        if all_dirs:
            for i, (_, p, _, _) in enumerate(params):
                path = os.path.normpath(os.path.join(p, args.program[0]))
                if not os.path.isfile(path):
                    sys.exit(
                        "Error in --builds argument: directory '%s' does not contain '%s' (path checked: '%s')"
                        % (p, args.program[0], path)
                    )
                params[i][1] = path
            
            return params

        # exact binaries specified (full or partial paths or in PATH)
        for i, (_, p, _, _) in enumerate(params):
            if which(p) is None:
                sys.exit(
                    "Error in --builds argument: file %s not found so it cannot be tested"
                    % (p,)
                )

        return params

    def adjust_complex_mode_params(self, params):
        """
        For complex mode (--builds). Converts percent ratios to number of instances
        and makes sure that each build is used at least once.
        params is a list of 4-item lists: name, path, count/percent, is_percent
        """
        percsum = 0.0
        for _, _, count, is_perc in params:
            if count is not None and is_perc:
                percsum += count

        if percsum > 100.0:
            if self.args.verbose:
                print(
                    "Info: sum of percents in --builds is %.2f%% which is not 100%%. Will proportionally adjust it"
                    % (percsum,)
                )
            for i, (_, _, count, is_perc) in enumerate(params):
                if is_perc:
                    params[i][2] = count * 100.0 / percsum
            percsum = 100.0

        count_none = sum(1 for _, _, count, _ in params if count is None)

        if count_none > 0:
            for i, (_, _, count, _) in enumerate(params):
                if count is None:
                    params[i][2] = (100.0 - percsum) / count_none
                    params[i][3] = True

        count_exact = sum(count for _, _, count, is_perc in params if is_perc == False)
        count_free = self.args.instances - count_exact
        if count_free < 0 or (count_free == 0 and percsum > 0.0):
            sys.exit(
                "Error in --builds argument: not enough processor cores to fit desired configuration"
            )

        if percsum > 0.0:
            for i, (_, _, count, is_perc) in enumerate(params):
                if is_perc and (count <= 0.0 or count_free * params[i][2] / 100.0 < 1):
                    params[i][2] = 1
                    params[i][3] = False

        # final normalization of percents
        percsum = sum(p for _, _, p, is_perc in params if is_perc)
        if percsum != 0.0 and percsum != 100.0:
            for i, (_, _, count, is_perc) in enumerate(params):
                if is_perc:
                    params[i][2] = count * 100.0 / percsum
            percsum = 100.0

        count_exact = sum(count for _, _, count, is_perc in params if is_perc == False)
        count_free = self.args.instances - count_exact
        if count_free < 0 or (count_free == 0 and percsum > 0.0):
            sys.exit(
                "Error in --builds argument: not enough processor cores to fit desired configuration"
            )

        # convert all the rest rest percent ratios to number of cores
        if percsum > 0.0:
            for i, (_, _, p, is_perc) in enumerate(params):
                if is_perc:
                    params[i].append(p)
                    params[i][2] = 0
                else:
                    params[i].append(0.0)
                params[i].append(i)  # order

            core_percent = 100.0 / count_free
            while True:  # TODO: there must be a better way :(
                params = sorted(params, key=lambda x: -x[4])
                for i, (_, _, _, _, perc, _) in enumerate(params):
                    if perc > 0.0:
                        params[i][4] -= core_percent
                        percsum -= core_percent
                        params[i][2] += 1
                        if percsum <= core_percent:
                            break
                if percsum <= core_percent:
                    break

            used_cores = sum(c for _, _, c, _, _, _ in params)
            if used_cores != self.args.instances:
                if self.args.verbose:
                    print(
                        "Math in fuzzman is junky! Fixing error with delta of %d cores"
                        % (used_cores - self.args.instances)
                    )
                params = sorted(params, key=lambda x: -x[4])
                params[0][2] -= used_cores - self.args.instances
                if self.args.verbose:
                    pprint(params)

                used_cores = sum(c for _, _, c, _, _, _ in params)
                if used_cores != self.args.instances:
                    sys.exit(
                        "Math in fuzzman is really junky! Error with delta of %d cores! "
                        "Please create an issue with verbose run screenshot.\nFor now you may want to specify different percent/amount of cores"
                        % (used_cores - self.args.instances)
                    )

            params = sorted(params, key=lambda x: x[5])  # return original order

        params = list(
            map(lambda x: x[0:3], params)
        )  # leave only name, path and number of cores

        used_cores = sum(c for _, _, c in params)
        if self.cores_specified and used_cores != self.args.instances:
            sys.exit(
                "Error in --builds argument: less cores specified in --builds (%d) than in -n (%d)"
                % (used_cores, self.args.instances)
            )

        if self.args.verbose:
            print(
                "Using %d cores out of total %d available in OS"
                % (used_cores, cpu_count())
            )

        return params

    def load_custom_cmds(self, path):
        """
        Load custom fuzzer commands from file specified by path.
        Returns list of commands to run instead of fuzzman-generated commands.
        Each element in result list is [worker_name, command]
        """
        cmds = []
        if not os.path.isfile(path):
            sys.exit("Error: file '%s' doesn't exist or it's not a file" % path)

        with open(path, "rt") as f:
            for line in f:
                line = line.strip()
                if len(line) < 1 or line[0] == "#":
                    continue

                cmd = line.split(":", 1)
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
                    print("Loaded custom command: %s" % worker)

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

    def start(self, env={}):
        """
        Start instances either in normal mode, complex mode (--builds) or custom commands mode (--cmd-file)
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
            params = self.extract_complex_mode_params()
            if args.verbose:
                print('"Raw" params:')
                pprint(params)

            params = self.adjust_complex_mode_params(params)
            if args.verbose:
                print("Adjusted params:")
                pprint(params)

            for name, path, num_cores in params:
                used_builds.extend([[name, path]] * num_cores)
        else:
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
                power_schedule = " -p exploit"
                if args.dict:
                    dictionary = " -x " + args.dict

            else:
                role = "-S"
                worker_name = "s"
                power_schedule = " -p seek"

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

            worker_env.update(env)

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

    def stop(self, grace_sig=signal.SIGINT):
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

    def health_check(self):
        if len(self.procs) < 1:
            return False

        print("Checking status of workers")
        num_ok = sum(1 for proc in self.procs if proc.health_check())

        print("%d/%d workers report OK status" % (num_ok, len(self.procs)))
        return num_ok > 0

    def display_next_status_screen(self, outfile=sys.stdout, dump=False):
        if len(self.procs) < 1:
            print("No status screen to show")
            return
        elif len(self.procs) == 1:
            self.lastshown = 0

        outbuf = getattr(outfile, "buffer", outfile)

        # helper for drawing workaround on linux with fancy boxes mode
        mqj = b"mqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqj"

        instance = self.procs[self.lastshown]
        if instance.proc.poll() is None:  # process is still running
            outbuf.write(CURSOR_HIDE)
            if dump:
                num_dumps = 1
            else:
                num_dumps = 100

            for _ in range(num_dumps):
                data = instance.get_output(24)

                # one of the dirtiest hacks so far: make double terminal clean in python2
                # .. by sending first half of ANSI sequence "\x1b[H\x1b[2J" twice
                if sys.version_info[0] == 2:
                    data = [l.replace(TERM_CLEAR_PY2_REPLACE, TERM_CLEAR) for l in data]

                if not self.args.no_drawing_workaround and len(data) > 0:
                    data[0] = data[0].replace(mqj, b"")

                for line in data:
                    outbuf.write(line)

                if not self.args.no_drawing_workaround and len(data) > 0:
                    outbuf.write(SET_G1 + bSTG + mqj + bSTOP + cRST + RESET_G1)

                if not dump:
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
            if not dump:
                sleep(5.0)

        outbuf.write(bSTOP + cRST + RESET_G1 + CURSOR_SHOW)

        if len(self.procs) > 0:
            self.lastshown += 1
            self.lastshown %= len(self.procs)

    def dump_status_screens(self, outfile=sys.stdout):
        self.lastshown = 0
        outbuf = getattr(outfile, "buffer", outfile)
        for _ in self.procs:
            outbuf.write(b"\n" * 40)
            self.display_next_status_screen(outfile=outfile, dump=True)

        outbuf.write(b"\n\n")

    def get_fuzzer_stats(self, output_dir, idx, instance):
        """
        Form dictionary from fuzzer_stats file of given fuzzer instance
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
                data = f.read()
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
        for line in data.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                stats[k] = v
        if len(stats) < 1:
            return None
        return stats

    @staticmethod
    def update_stat_timestamp(stats_dict, stat_name, saved_newest_stamp):
        """
        Use this method to update last path (crash, hang, etc) timestamp.
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
    def format_seconds(seconds):
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

    def job_status_check(self, onlystats=False):
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

        for idx, instance in enumerate(self.procs, start=1):
            stats = self.get_fuzzer_stats(output_dir, idx, instance)

            if stats is None:
                continue

            crashes = int(stats.get("unique_crashes", 0))
            hangs = int(stats.get("unique_hangs", 0))
            paths_total = int(stats.get("paths_total", 0))
            paths_found = int(stats.get("paths_found", 0))

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
                    % (paths_found, 100.0 * paths_found / paths_total)
                )

            newest_path_stamp = self.update_stat_timestamp(
                stats, "last_path", newest_path_stamp
            )
            newest_hang_stamp = self.update_stat_timestamp(
                stats, "last_hang", newest_hang_stamp
            )
            newest_crash_stamp = self.update_stat_timestamp(
                stats, "last_crash", newest_crash_stamp
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
