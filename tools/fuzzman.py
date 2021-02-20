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

SET_G1 = b"\x1b)0"   # /* Set G1 for box drawing    */
RESET_G1 = b"\x1b)B" # /* Reset G1 to ASCII         */
bSTART = b"\x0e"     # /* Enter G1 drawing mode     */
bSTOP = b"\x0f"      # /* Leave G1 drawing mode     */

bSTG = bSTART + cGRA


class StreamingProcess:

    def __init__(self, name='', cmd=None, env=None, verbose=False):
        if cmd is None:
            raise SyntaxError("Can't create SteamingProcess without 'cmd' parameter")

        self.name = name
        self.cmd  = cmd
        self.env  = env
        self.verbose = verbose
        self.proc = None
        self.comm_thread = None

        self.buffer = deque(maxlen=100)
        self.lock   = Lock()

        self._stop  = Event()
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
            raise RuntimeError("Can't call SteamingProcess.start without 'cmd' parameter")

        args = shlex.split(cmd)
        self.waited_for_child = False

        if self.proc is None or self.proc.poll() is not None:
            self.env.update(env)

            if resume:
                self.env.update({"AFL_AUTORESUME": "1"})
                try:
                    path_idx = args.index("-i") + 1
                except ValueError:
                    sys.exit("Failed to restart instance '%s': no '-i' option passed" % (cmd,))
                args[path_idx] = "-"
                
            try:
                self.proc = Popen(args, shell=False, stdout=PIPE, env=self.env)
            except SubprocessError:
                print("Wasn't able to start process with command '%s'" % (cmd,), file=sys.stderr)
                return False
        
        if self.comm_thread is None:
            self.comm_thread = Thread(target=self.__communicate_thread)
            self.comm_thread.start()
            if not self.comm_thread.is_alive():
                print("Wasn't able to start communication thread. Stopping process", file=sys.stderr)
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
                print("\tCommunication thread is still running.. Thread: ", self.comm_thread)

        if self.proc.poll() is None:
            if force:
                print("Killing instance '%s' (pid %d)" % (self.cmd, self.proc.pid), file=sys.stderr)
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
            self._restarts -= 5 # failed attempts to restart are cooling down over time
            if self._restarts < 0:
                self._restarts = 0
        else:
            self._restarts += 10
            if self._restarts > 29: # three failed restarts in a row -> give up
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
            print("[!]\tCommunication thread is not running. Realtime output not available", file=sys.stderr)
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

    def start(self, env={}):
        args = self.args

        if args.instances < 1:
            args.instances = 1
        
        if shutil.which(args.fuzzer_binary) is None:
            sys.exit("File %s is not found so it cannot be used as fuzzer" % args.fuzzer_binary)

        if shutil.which(args.program[0]) is None:
            sys.exit("File %s is not found so it cannot be tested" % args.program[0])

        if not os.path.exists(args.input_dir):
            try:
                os.makedirs(args.input_dir, exist_ok=True)
            except OSError:
                sys.exit("Can't create input directory %s" % args.input_dir)
        elif not os.path.isdir(args.input_dir):
            sys.exit("Can't use %s as input directory" % args.input_dir)
        
        if len(glob.glob(os.path.join(args.input_dir,'*'))) < 1:
            path = os.path.join(args.input_dir,'1')
            print("Creating simple input corpus: %s" % path)
            try:
                with open(path, 'w') as f:
                    f.write('12345')
            except OSError:
                sys.exit("Wasn't able to create input corpus")

        if args.cleanup:
            if os.path.isdir(args.output_dir):
                print("Removing directory '%s'" % args.output_dir)
                try:
                    shutil.rmtree(args.output_dir, ignore_errors=True)
                except shutil.Error:
                    sys.exit("Wasn't able to remove output directory '%s'" % args.output_dir)

        for i in range(args.instances):
            dictionary = ''
            
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

            cmd = args.fuzzer_binary + " -i " + args.input_dir + " -o " + args.output_dir + " " + \
                  "-m " + args.memory_limit + dictionary + " " + role + " " + worker_name + power_schedule
            
            if args.more_args:
                cmd += " " + args.more_args
            cmd += " -- " + " ".join(args.program)

            worker_env = os.environ.copy()
            worker_env["AFL_FORCE_UI"] = "1"
            worker_env.update(env)

            print("Starting worker #%d {%s}: %s" % (i + 1, worker_name, cmd))
            self.procs.append(StreamingProcess(name=worker_name, cmd=cmd, env=worker_env, verbose=args.verbose))

    def stop(self, grace_sig=signal.SIGINT):
        print("Stopping processes")

        if len(self.procs) < 1:
            return

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

    def display_next_status_screen(self):
        if len(self.procs) < 1:
            print("No status screen to show")
            return
        elif len(self.procs) == 1:
            self.lastshown = 0

        # helper for drawing workaround on linux with fancy boxes mode
        mqj = b"mqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqj"

        instance = self.procs[self.lastshown]
        if instance.proc.poll() is None:  # process is still running
            sys.stdout.buffer.write(CURSOR_HIDE)
            for _ in range(100):
                data = instance.get_output(24)
                if not self.args.no_drawing_workaround and len(data) > 0:
                    data[0] = data[0].replace(mqj, b'')

                for line in data:
                    sys.stdout.buffer.write(line)

                if not self.args.no_drawing_workaround and len(data) > 0:
                    sys.stdout.buffer.write(SET_G1 + bSTG + mqj + bSTOP + cRST + RESET_G1)

                sleep(0.05)
            sys.stdout.buffer.write(CURSOR_SHOW)
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
                sys.stdout.buffer.write(line)
            sleep(5.0)

        sys.stdout.buffer.write(bSTOP + cRST + RESET_G1 + CURSOR_SHOW)

        if len(self.procs) > 0:
            self.lastshown += 1
            self.lastshown %= len(self.procs)

    def get_fuzzer_stats(self, output_dir, idx, instance):
        """
        Form dictionary from fuzzer_stats file of given fuzzer instance
        """
        if instance.name is None or len(instance.name) < 1:
            print("Wasn't able to get stats of instance #%d because somehow it has no name" % (idx,), file=sys.stderr)
            return None

        stats_file_path = os.path.join(output_dir, instance.name, 'fuzzer_stats')
        if not os.path.isfile(stats_file_path):
            print("Wasn't able to get stats of instance %s because somehow it has no fuzzer_stats file" % (
                instance.name,), file=sys.stderr)
            return None

        try:
            with open(stats_file_path, 'rt') as f:
                data = f.read()
        except OSError:
            print("Wasn't able to get stats of instance %s because of fail to open '%s'" % (
                instance.name, stats_file_path), file=sys.stderr)
            return None

        if data is None:
            print("Wasn't able to get data of instance %s because its fuzzer_stats file '%s' is empty" % (
                instance.name, stats_file_path), file=sys.stderr)
            return None

        stats = dict()
        for line in data.split("\n"):
            if ':' in line:
                k, v = line.split(':')
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

    def job_status_check(self, no_paths_time_substr=None):
        """
        Enumerate fuzzer_stats files, print stats, return True if stopping required
        """

        output_dir = self.args.output_dir
        if output_dir is None or len(output_dir) < 1:
            return False
        
        newest_path_stamp  = 0
        newest_hang_stamp  = 0
        newest_crash_stamp = 0

        sum_paths   = 0
        sum_hangs   = 0
        sum_crashes = 0

        for idx, instance in enumerate(self.procs, start=1):
            stats = self.get_fuzzer_stats(output_dir, idx, instance)

            if stats is None:
                continue
            
            if instance.proc.poll():
                status = 'NOT '
            else:
                status = ''
            
            print("Worker " + instance.name + " is " + status + "running")
            crashes = int(stats.get("unique_crashes", 0))
            hangs   = int(stats.get("unique_hangs", 0))
            paths_total = int(stats.get("paths_total", 0))
            paths_found = int(stats.get("paths_found", 0))

            sum_crashes += crashes
            sum_hangs   += hangs
            sum_paths   += paths_total

            print("\tcrashes: %d, hangs: %d, paths total: %d" % (crashes, hangs, paths_total))
            print("\tpaths discovered: %d (%.2f%% of total paths)" % (paths_found, 100.0 * paths_found / paths_total))

            newest_path_stamp  = self.update_stat_timestamp(stats, "last_path", newest_path_stamp)
            newest_hang_stamp  = self.update_stat_timestamp(stats, "last_hang", newest_hang_stamp)
            newest_crash_stamp = self.update_stat_timestamp(stats, "last_crash", newest_crash_stamp)

        if newest_path_stamp == 0:
            return False
        
        print("\nStats of this fuzzing job:")

        now = int(datetime.now().timestamp())

        newest_path_delta = now - newest_path_stamp
        newest_path_fmt = self.format_seconds(newest_path_delta)
        print("  Paths: %d. Last new path: %s ago" % (sum_paths, newest_path_fmt))

        if sum_hangs > 0:
            delta = now - newest_hang_stamp
            seconds_fmt = self.format_seconds(delta)
            print("  Hangs: %d. Last new hang: %s ago" % (sum_hangs, seconds_fmt))
        else:
            print("  Hangs: 0")
        
        if sum_crashes > 0:
            delta = now - newest_crash_stamp
            seconds_fmt = self.format_seconds(delta)
            print("Crashes: %d. Last new crash: %s ago" % (sum_crashes, seconds_fmt))
        else:
            print("Crashes: 0")

        # now decide if we need to stop
        if no_paths_time_substr is not None:
            if no_paths_time_substr.isnumeric:
                if int(no_paths_time_substr) <= newest_path_delta:
                    return True
            elif no_paths_time_substr in newest_path_fmt:
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
                ["Set memory limit of 10 kilobytes, cleanup output directory", "-m 10K -C ./myapp"],
                ["Pass additional agruments to fuzzer", '--more-args "-p fast" ./myapp @@'],
                ["Run 4 instances and specify in/out directories",
                 "-n 4 -i ../inputs/for_myapp -o ../outputs/myapp ./myapp @@"],
                ["Specify non-default fuzzer", "--fuzzer-binary ~/git/fuzzer/obliterator ./myapp"],
                ["Specify non-default fuzzer in path", "--fuzzer-binary py-afl-fuzz ./myapp"],
                ["Stop if there were no new paths (across all fuzzers) in 1 hour and 5 minutes",
                 '--no-paths-stop "1 hrs, 5 min" ./myapp'],
                ["Same as in previous example", '--no-paths-stop "1 hrs, 5" ./myapp'],
                ["Same as in previous example, time measured in seconds", '--no-paths-stop 3900 ./myapp']
            ]
            for action, cmd in examples:
                self.print_example(action, cmd)


def main():
    parser = FuzzmanArgumentParser(description='%(prog)s - your humble assistant to automate and manage fuzzing tasks',
                                   epilog='developed and tested by fuzzah for using with AFL++')
    parser.add_argument('program', nargs=argparse.REMAINDER, metavar='...',
                        help='program with its arguments (example: ./myapp --file @@)')

    parser.add_argument('-n', '--instances',
                        help='number of fuzzer instances to start (default: cpu count {%d})' % os.cpu_count(),
                        default=os.cpu_count(), type=int)
    parser.add_argument('-i', '--input-dir', help='input directory (default: ./in)', default='./in')
    parser.add_argument('-o', '--output-dir', help='output directory (default: ./out)', default='./out')
    parser.add_argument('-x', '--dict', help='dictionary for main instance (default: none)', default=None)
    parser.add_argument('-m', '--memory-limit', help='assign memory limit to fuzzer (default: none)', default='none')
    parser.add_argument('-C', '--cleanup', help='delete output directory before starting (default: don\'t delete)',
                        action='store_true')
    parser.add_argument('-P', '--no-power-schedules',
                        help='don\'t pass -p option to fuzzer (default: pass -p exploit for main instance, pass -p '
                             'seek for secondary instances)', action='store_true')
    parser.add_argument('-W', '--no-drawing-workaround',
                        help='disable linux G1 drawing workaround (default: workaround enabled)', action='store_true')
    parser.add_argument('--more-args', metavar='ARGS',
                        help='additional arguments for fuzzer, added last (default: no arguments)', default=None)
    parser.add_argument('--fuzzer-binary', metavar='PATH',
                        help='name or full path to fuzzer binary (default: afl-fuzz)', default='afl-fuzz')
    parser.add_argument('--no-paths-stop', metavar='TIME',
                        help='stop when time without finds (TWF) contains TIME or if TWF becomes greater than or '
                             'equal to int(TIME) (default: don\'t stop)',
                        default=None)
    parser.add_argument('-v', '--verbose', help='print more messages', action='store_true')
    # TODO:
    # -c cmplog binary

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()
    if args.program[0] == '--':
        del args.program[0]

    if len(args.program) < 1:
        print("Error: you didn't specify PROGRAM you want to run. See examples: -h/--help", file=sys.stderr)
        return 3

    if args.no_paths_stop:
        args.no_paths_stop = args.no_paths_stop.strip()
        if 'se' in args.no_paths_stop or ' s' in args.no_paths_stop:
            # TODO: rewrite it to be SHORT and INFORMATIVE
            msg = "Error: don't specify exact number of seconds in --no-paths-stop, " + parser.prog + " is not that precise."
            msg += "\n  You probably want to check if time without new paths is LONGER than '" + args.no_paths_stop + "', " \
                   "but " + parser.prog + " will search it as a substring in string like '2 days, 13 hrs, 9 min, 37 sec' "
            msg += "\n  You can specify exact number of seconds just as a number. This number will be compared to " \
                   "time without finds measured in seconds. "
            msg += "\n  For example, this command will stop fuzzing job AFTER one hour and one second: " \
                   "\n\t" + sys.argv[0] + " --no-paths-stop 3601 ./myapp"
            msg += "\nSee -h/--help for more examples"
            print(msg, file=sys.stderr)
            return 3

    fuzzman = FuzzManager(args)

    def handler(_signo, _stack_frame):
        sys.stdout.buffer.write(bSTOP + cRST + RESET_G1 + CURSOR_SHOW)
        print()
        fuzzman.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)

    fuzzman.start()

    # input("Workers are running. Press enter to start monitoring mode")

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
        if fuzzman.job_status_check(no_paths_time_substr=args.no_paths_stop):
            print("Stop condition met. Stopping current fuzzing job...")
            retcode = 0
            break
        sleep(5.0)

    fuzzman.stop()

    return retcode


if __name__ == '__main__':
    sys.exit(main())
