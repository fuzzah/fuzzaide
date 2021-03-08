#!/usr/bin/env python3

# file    :  fuzzman.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

import os
import sys
import glob
import shlex
import shutil
import signal
import argparse
from time import sleep
from pprint import pprint
from datetime import datetime
from collections import deque
from threading import Thread, Lock, Event
from subprocess import Popen, PIPE, TimeoutExpired, SubprocessError

# some terminal constants from AFL

cGRA = b"\x1b[1;90m"
cRST = b"\x1b[0m"

TERM_CLEAR = b"\x1b[H\x1b[2J"
cEOL = b"\x1b[0K"
CURSOR_HIDE = b"\x1b[?25l"
CURSOR_SHOW = b"\x1b[?25h"

SET_G1 = b"\x1b)0"  # /* Set G1 for box drawing    */
RESET_G1 = b"\x1b)B"  # /* Reset G1 to ASCII         */
bSTART = b"\x0e"  # /* Enter G1 drawing mode     */
bSTOP = b"\x0f"  # /* Leave G1 drawing mode     */

bSTG = bSTART + cGRA


class StreamingProcess:
    def __init__(self, name="", groupname="", cmd=None, env=None, verbose=False):
        if cmd is None:
            raise SyntaxError("Can't create SteamingProcess without 'cmd' parameter")

        self.name = name
        self.groupname = groupname
        self.cmd = cmd
        self.env = env
        self.verbose = verbose
        self.proc = None
        self.comm_thread = None

        self.buffer = deque(maxlen=100)
        self.lock = Lock()

        self._stop = Event()
        self.waited_for_child = False

        self._restarts = 0
        self.total_restarts = 0

        self.start()

    def __communicate_thread(self):
        while True:
            data = self.proc.stdout.readline()
            if data is None:
                break

            if self._stop.is_set():
                break  # leave communication thread

            self.lock.acquire()
            self.buffer.append(data)
            self.lock.release()

    def start(self, resume=False, env={}):
        cmd = self.cmd

        if cmd is None:
            raise RuntimeError(
                "Can't call SteamingProcess.start without 'cmd' parameter"
            )

        args = shlex.split(cmd)
        self.waited_for_child = False

        if self.proc is None or self.proc.poll() is not None:
            self.env.update(env)

            if resume:
                self.env.update({"AFL_AUTORESUME": "1"})
                try:
                    path_idx = args.index("-i") + 1
                except ValueError:
                    sys.exit(
                        "Failed to restart instance '%s': no '-i' option passed"
                        % (cmd,)
                    )
                args[path_idx] = "-"

            try:
                self.proc = Popen(args, shell=False, stdout=PIPE, env=self.env)
            except SubprocessError:
                print(
                    "Wasn't able to start process with command '%s'" % (cmd,),
                    file=sys.stderr,
                )
                return False

        if self.comm_thread is None:
            self.comm_thread = Thread(target=self.__communicate_thread)
            self.comm_thread.start()
            if not self.comm_thread.is_alive():
                print(
                    "Wasn't able to start communication thread. Stopping process",
                    file=sys.stderr,
                )
                self.stop()
                return False
        return True

    def get_output(self, num_lines=100):
        if num_lines > 100:
            num_lines = 100
        self.lock.acquire()
        lines = list(self.buffer)[-num_lines:] if len(self.buffer) > 0 else list()
        self.lock.release()
        return lines

    def stop(self, force=False, grace_sig=signal.SIGINT):

        if self.comm_thread is not None and self.comm_thread.is_alive():
            self._stop.set()
            self.comm_thread.join(3.0)
            if self.comm_thread.is_alive():
                print(
                    "\tCommunication thread is still running.. Thread: ",
                    self.comm_thread,
                )

        if self.proc.poll() is None:
            if force:
                print(
                    "Killing instance '%s' (pid %d)" % (self.cmd, self.proc.pid),
                    file=sys.stderr,
                )
                self.proc.send_signal(signal.SIGKILL)
                self.proc.wait()
            else:
                # print("Gracefully stopping instance '%s' (pid %d)" % (self.cmd,self.proc.pid))
                self.proc.send_signal(grace_sig)
                try:
                    self.proc.wait(3.0)
                except TimeoutExpired:
                    pass

    def health_check(self):
        if self.cmd is None:
            print('[!] Instance "unknown": never started', file=sys.stderr)
            return False

        quality = 2
        print("[i] Instance '%s' status:" % self.cmd)
        if self.proc and self.proc.poll() is None:
            print("\tRunning. Process Id: %d" % self.proc.pid)
            self._restarts -= 5  # failed attempts to restart are cooling down over time
            if self._restarts < 0:
                self._restarts = 0
        else:
            self._restarts += 10
            if self._restarts > 29:  # three failed restarts in a row -> give up
                print("[!]\tNot running, gave up on restarting", file=sys.stderr)
                quality = 0
            else:
                print("[!]\tNot running, restarting.. ", file=sys.stderr)
                self.total_restarts += 1
                quality -= 1
                self.start(resume=True)

        if self.comm_thread and self.comm_thread.is_alive():
            if self.verbose:
                print("\tCommunication thread is running. Thread:", self.comm_thread)
        else:
            print(
                "[!]\tCommunication thread is not running. Realtime output not available",
                file=sys.stderr,
            )
            quality -= 1

        if quality < 1:
            print("[!]\tInstance is not working", file=sys.stderr)
        elif self.verbose:
            if quality > 1:
                print("\tInstance seems to be working normally")
            elif quality == 1:
                print("\tInstance working without realtime output report")

        return quality > 0


class FuzzManager:
    def __init__(self, args):
        self.procs = list()
        self.lastshown = 0
        self.args = args
        self.waited_for_child = False
        self.start_time = int(datetime.now().timestamp())
        self.cores_specified = False

    def extract_instance_count(self, s):
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
        except:
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
                if "%" in bi[1] or bi[1].isnumeric():
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
            if path is not None:
                if path.startswith('~'):
                    path = os.path.expanduser(path)
                params.append([name, path, count, perc])

        all_dirs = all(os.path.isdir(p) for _, p, _, _ in params)
        all_bins = all(os.path.isfile(p) for _, p, _, _ in params)

        pprint(params)

        if (
            all_dirs
        ):  # build directories provided -> each one should contain binary with same app name
            for i, (_, p, _, _) in enumerate(params):
                path = os.path.normpath(os.path.join(p, args.program[0]))
                if not os.path.isfile(path):
                    sys.exit(
                        "Error in --builds argument: directory '%s' does not contain '%s' (path checked: '%s')"
                        % (p, args.program[0], path)
                    )
                params[i][1] = path
        elif all_bins:  # exact binaries specified (full or partial paths or in PATH)
            for i, (_, p, _, _) in enumerate(params):
                if shutil.which(p) is None:
                    sys.exit(
                        "Error in --builds argument: file %s not found so it cannot be tested"
                        % (p,)
                    )
        else:
            sys.exit(
                "Error: --builds should point EITHER to directories OR to binaries"
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
                % (used_cores, os.cpu_count())
            )

        return params

    def start(self, env={}):
        if self.args.instances is None:
            self.cores_specified = False
            self.args.instances = os.cpu_count()
        else:
            self.cores_specified = True

        args = self.args

        if args.instances < 1:
            args.instances = 1

        if shutil.which(args.fuzzer_binary) is None:
            sys.exit(
                "File %s not found so it cannot be used as fuzzer" % args.fuzzer_binary
            )

        if not os.path.exists(args.input_dir):
            try:
                os.makedirs(args.input_dir, exist_ok=True)
            except OSError:
                sys.exit("Can't create input directory %s" % args.input_dir)
        elif not os.path.isdir(args.input_dir):
            sys.exit("Can't use %s as input directory" % args.input_dir)

        if len(glob.glob(os.path.join(args.input_dir, "*"))) < 1:
            path = os.path.join(args.input_dir, "1")
            print("Creating simple input corpus: %s" % path)
            try:
                with open(path, "w") as f:
                    f.write("12345")
            except OSError:
                sys.exit("Wasn't able to create input corpus")

        if args.cleanup and os.path.isdir(args.output_dir):
            print("Removing directory '%s'" % args.output_dir)
            try:
                shutil.rmtree(args.output_dir, ignore_errors=True)
            except shutil.Error:
                sys.exit(
                    "Wasn't able to remove output directory '%s'" % args.output_dir
                )

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
            if shutil.which(args.program[0]) is None:
                sys.exit("File %s not found so it cannot be tested" % args.program[0])
            used_builds = [[None, args.program[0]]] * args.instances

        if args.verbose:
            print("Builds in use:")
            pprint(used_builds)

        # TODO: maybe split this method for basic and complex modes?

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

            worker_env = os.environ.copy()
            worker_env["AFL_FORCE_UI"] = "1"
            worker_env.update(env)

            print("Starting worker #%d {%s}: %s" % (i + 1, worker_name, cmd))
            self.procs.append(
                StreamingProcess(
                    name=worker_name,
                    groupname=groupname,
                    cmd=cmd,
                    env=worker_env,
                    verbose=args.verbose,
                )
            )
        self.start_time = int(datetime.now().timestamp())

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
        # print("Waiting %.1f seconds to check for leftover processes" % (term_wait,))
        sleep(term_wait)

        for proc in self.procs:
            proc.stop(force=True)
        self.procs = []

    def health_check(self):
        if len(self.procs) < 1:
            return False

        num_ok = 0
        print("Checking status of workers")
        for proc in self.procs:
            if proc.health_check():
                num_ok += 1

        print("%d/%d workers report OK status" % (num_ok, len(self.procs)))
        return num_ok > 0

    def display_next_status_screen(self, outfile=sys.stdout, dump=False):
        if len(self.procs) < 1:
            print("No status screen to show")
            return
        elif len(self.procs) == 1:
            self.lastshown = 0

        # helper for drawing workaround on linux with fancy boxes mode
        mqj = b"mqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqj"

        instance = self.procs[self.lastshown]
        if instance.proc.poll() is None:  # process is still running
            outfile.buffer.write(CURSOR_HIDE)
            if dump:
                num_dumps = 1
            else:
                num_dumps = 100

            for _ in range(num_dumps):
                data = instance.get_output(24)
                if not self.args.no_drawing_workaround and len(data) > 0:
                    data[0] = data[0].replace(mqj, b"")

                for line in data:
                    outfile.buffer.write(line)

                if not self.args.no_drawing_workaround and len(data) > 0:
                    outfile.buffer.write(SET_G1 + bSTG + mqj + bSTOP + cRST + RESET_G1)

                if not dump:
                    sleep(0.05)
            outfile.buffer.write(CURSOR_SHOW)
        else:  # process is not running
            if not self.waited_for_child:
                try:
                    instance.proc.wait(3.0)  # wait to prevent zombie-processes
                except TimeoutExpired:
                    pass  # timeout waiting: process hung?
                else:
                    self.waited_for_child = True

            data = instance.get_output(29)
            for line in data:
                outfile.buffer.write(line)
            if not dump:
                sleep(5.0)

        sys.stdout.buffer.write(bSTOP + cRST + RESET_G1 + CURSOR_SHOW)

        if len(self.procs) > 0:
            self.lastshown += 1
            self.lastshown %= len(self.procs)

    def dump_status_screens(self, outfile=sys.stdout):
        self.lastshown = 0
        for _ in self.procs:
            # outfile.buffer.write(TERM_CLEAR)
            outfile.buffer.write(b"\n" * 40)
            self.display_next_status_screen(outfile=outfile, dump=True)

        outfile.buffer.write(b"\n\n")

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
        job_duration = int(datetime.now().timestamp()) - self.start_time
        print("Duration: %s" % (self.format_seconds(job_duration),))

        if newest_path_stamp == 0:
            if not onlystats:
                print("\nNo more stats to display (yet)")
            return False

        e = float(sum_execs)
        c = ""
        if e >= 1_000_000_000:
            e /= 1_000_000_000
            c = "B"
        elif e >= 1_000_000:
            e /= 1_000_000
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

        now = int(datetime.now().timestamp())

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


class FuzzmanArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        argparse.ArgumentParser.__init__(self, *args, **kwargs)

    def print_example(self, action="", cmd=""):
        print(action + ": \n\t" + sys.argv[0] + " " + cmd)

    def print_help(self, examples=True):
        argparse.ArgumentParser.print_help(self)
        if examples:
            print()
            print("Invocation examples:")
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
                    "--builds app:2 /full_path/app_asan:1 ../relative_path/app_laf -- ./myapp",
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
            ]
            for action, cmd in examples:
                self.print_example(action, cmd)


def main():
    parser = FuzzmanArgumentParser(
        description="%(prog)s - your humble assistant to automate and manage fuzzing tasks",
        epilog="developed and tested by fuzzah for using with AFL++",
    )
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
        % os.cpu_count(),
        default=None,
        type=int,
    )
    parser.add_argument(
        "-i", "--input-dir", help="input directory (default: ./in)", default="./in"
    )
    parser.add_argument(
        "-o", "--output-dir", help="output directory (default: ./out)", default="./out"
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
        "-v", "--verbose", help="print more messages", action="store_true"
    )
    # TODO:
    # -c cmplog binary

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

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

    retcode = 7
    fuzzman = FuzzManager(args)

    def handler(_signo, _stack_frame):
        sys.stdout.buffer.write(bSTOP + cRST + RESET_G1 + CURSOR_SHOW)
        print()
        fuzzman.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)

    fuzzman.start()

    while True:
        sys.stdout.buffer.write(TERM_CLEAR)
        if not fuzzman.health_check():  # this check also prints alive status of workers
            retcode = 1
            break

        sleep(5.0)
        sys.stdout.buffer.write(TERM_CLEAR)
        fuzzman.display_next_status_screen()  # this displays fuzzer output in real time for ~5 seconds

        sys.stdout.buffer.write(TERM_CLEAR)

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
