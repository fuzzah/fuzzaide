# -*- coding: utf-8 -*-

# file    :  fuzzman.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from __future__ import print_function

import sys
import shlex
import signal
from collections import deque
from subprocess import Popen, PIPE
from threading import Thread, Lock, Event

# python2 compatibility
try:
    from subprocess import TimeoutExpired, SubprocessError
except ImportError:
    TimeoutExpired = Exception
    SubprocessError = Exception


class RunningAFLProcess:
    """
    Long-running child process of AFL-like fuzzer with interactive stdout updates.
    This class autorestarts child process up to three restart failures in a row
    """

    def __init__(self, name="", groupname="", cmd=None, env=None, verbose=False):
        if cmd is None:
            raise SyntaxError("Can't create RunningAFLProcess without 'cmd' parameter")

        self.name = name
        self.groupname = groupname
        self.cmd = cmd
        self.env = env
        self.verbose = verbose
        self.proc = None
        self.comm_thread = None

        self.buffer = deque(maxlen=100)
        self.lock = Lock()

        self.__stop = Event()
        self.waited_for_child = False

        self.__restarts = 0
        self.total_restarts = 0

        self.start()

    def __communication_thread_func(self):
        while True:
            data = self.proc.stdout.readline()
            if data is None:
                break

            if self.__stop.is_set():
                break  # leave communication thread

            self.lock.acquire()
            self.buffer.append(data)
            self.lock.release()

    def start(self, resume=False, env={}):
        cmd = self.cmd

        if cmd is None:
            raise RuntimeError(
                "Can't call RunningAFLProcess.start without 'cmd' parameter"
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
            self.comm_thread = Thread(target=self.__communication_thread_func)
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
            self.__stop.set()
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
                self.proc.send_signal(grace_sig)
                try:
                    self.proc.wait(3.0)
                except TimeoutExpired:
                    pass

    def health_check(self):
        quality = 2
        print("[i] Instance '%s' status:" % self.cmd)
        if self.proc and self.proc.poll() is None:
            print("\tRunning. Process Id: %d" % self.proc.pid)
            self.__restarts -= (
                5  # failed attempts to restart are cooling down over time
            )
            if self.__restarts < 0:
                self.__restarts = 0
        else:
            self.__restarts += 10
            if self.__restarts > 29:  # three failed restarts in a row -> give up
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
