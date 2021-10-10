#!/usr/bin/env python3

# file    :  fuzz-webview.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

"""
fuzz webview: simple Flask App to aggregate and display data from fuzzer_stats files
Code here may partially overlap with fuzzman.py
"""

import os
import sys
import glob
import time
import argparse
from datetime import datetime
from threading import Thread, Lock, Event

try:
    from flask import Flask, render_template, send_from_directory
except:
    sys.exit("Please install Flask")


class StatsLoader(Thread):
    def __init__(self, dir, lock):
        super().__init__()
        self.dir = dir  # fuzzers sync dir
        self.stats = list()  # list of dicts
        self.common_stats = dict()
        self.lock = lock  # lock for self.stats
        self._stop_evt = Event()

        self.start()

    def get_fuzzer_stats(self, fname):
        """
        Form a dictionary from fuzzer_stats
        """

        try:
            with open(fname, "rt") as f:
                data = f.read()
        except OSError:
            return None

        if data is None:  # file is empty
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

    def load_stats(self):
        fuzzer_stats = "fuzzer_stats"
        filenames = glob.glob(os.path.join(self.dir, "*", fuzzer_stats))
        single_fuzzer_stats = os.path.join(self.dir, fuzzer_stats)
        if os.path.isfile(single_fuzzer_stats):
            filenames.append(single_fuzzer_stats)
        filenames = sorted(filenames)

        newest_path_stamp = 0
        newest_hang_stamp = 0
        newest_crash_stamp = 0

        sum_execs = 0
        sum_paths = 0
        sum_hangs = 0
        sum_crashes = 0

        common_stats = {}
        all_stats = []

        now = int(datetime.now().timestamp())

        for fname in filenames:
            stats = self.get_fuzzer_stats(fname)
            if stats is None:
                continue

            last_upd = int(stats.get("last_update", 0))
            if last_upd > 0:
                delta = now - last_upd
                mess = self.format_seconds(delta) + " ago"
                if delta > 90:
                    mess += " (NOT RUNNING?)"
                stats["last_update"] = mess
            all_stats.append(stats)

            crashes = int(stats.get("unique_crashes", 0))
            hangs = int(stats.get("unique_hangs", 0))
            paths_total = int(stats.get("paths_total", 0))

            sum_crashes += crashes
            sum_hangs += hangs
            sum_paths += paths_total
            sum_execs += int(stats.get("execs_done", 0))

            newest_path_stamp = self.update_stat_timestamp(
                stats, "last_path", newest_path_stamp
            )
            newest_hang_stamp = self.update_stat_timestamp(
                stats, "last_hang", newest_hang_stamp
            )
            newest_crash_stamp = self.update_stat_timestamp(
                stats, "last_crash", newest_crash_stamp
            )

        if newest_path_stamp == 0:
            return

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

        execs = "Unknown"
        if len(c) > 0:
            if c == "B":
                execs = "%.4f%c" % (e, c)
            else:
                execs = "%.2f%c" % (e, c)
        else:
            execs = "%.0f" % (e,)

        common_stats["execs"] = execs

        newest_path_delta = now - newest_path_stamp
        newest_path_fmt = self.format_seconds(newest_path_delta)

        common_stats["paths"] = sum_paths
        common_stats["last_new_path"] = newest_path_delta
        common_stats["paths_info_fmt"] = "Paths: %d.\tLast new path: %s ago" % (
            sum_paths,
            newest_path_fmt,
        )

        common_stats["hangs"] = sum_hangs

        if sum_hangs > 0:
            delta = now - newest_hang_stamp
            seconds_fmt = self.format_seconds(delta)
            common_stats["last_new_hang"] = delta
            common_stats["hangs_info_fmt"] = "Hangs: %d.\tLast new hang: %s ago" % (
                sum_hangs,
                seconds_fmt,
            )
        else:
            common_stats["last_new_hang"] = -1
            common_stats["hangs_info_fmt"] = "Hangs: 0"

        common_stats["crashes"] = sum_crashes
        if sum_crashes > 0:
            delta = now - newest_crash_stamp
            seconds_fmt = self.format_seconds(delta)
            common_stats["last_new_crash"] = delta
            common_stats[
                "crashes_info_fmt"
            ] = "Crashes: %d.\tLast new crash: %s ago" % (sum_crashes, seconds_fmt)
        else:
            common_stats["last_new_crash"] = -1
            common_stats["crashes_info_fmt"] = "Crashes: 0"

        self.lock.acquire()
        self.stats = all_stats
        self.common_stats = common_stats
        self.lock.release()

    def run(self):
        while True:
            self.load_stats()
            time.sleep(1.0)
            if self._stop_evt.is_set():
                break

    def stop(self):
        self._stop_evt.set()


class WebApp(Flask):
    def __init__(self, appname, syncdir):
        super().__init__(appname)
        self.stats_lock = Lock()
        self.stats_loader = StatsLoader(syncdir, self.stats_lock)

        @self.route("/", methods=["GET"])
        def _index():
            return self.render_index()

        @self.route("/favicon.ico")
        def _favicon():
            return send_from_directory(
                os.path.join(self.root_path, "static"),
                "favicon.ico",
                mimetype="image/x-icon",
            )

    def stop_stats_loader(self):
        self.stats_loader.stop()

    def load_stats(self):
        self.stats_lock.acquire()
        fuzz_stats = self.stats_loader.stats
        common_stats = self.stats_loader.common_stats
        self.stats_lock.release()
        return common_stats, fuzz_stats

    def render_index(self):
        now = datetime.now()
        curtime_fmt = now.strftime(r"%H:%M:%S %d.%m.%Y")
        comm_stats, fuzz_stats = self.load_stats()
        comm_stats["curtime_fmt"] = curtime_fmt
        return render_template(
            "index.html", fuzzer_stats=fuzz_stats, common_stats=comm_stats
        )


def main():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),
        description="%(prog)s - simple dashboard for AFL-like fuzzers",
        epilog="by default, listens on http://127.0.0.1:8080",
    )

    parser.add_argument(
        "-o", "--sync-dir", help="fuzzer sync directory", type=str, required=True
    )
    parser.add_argument(
        "-p", "--port", help="port to bind to", type=int, default="8080"
    )
    parser.add_argument(
        "-l", "--addr", help="address to bind to", default="127.0.0.1", type=str
    )
    parser.add_argument(
        "-v", "--verbose", help="verbose mode", action="count", default=0
    )

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

    print("Using sync dir:", args.sync_dir)
    print("Trying to start web server on http://%s:%s.." % (args.addr, args.port))

    app = WebApp(__name__, args.sync_dir)
    app.run(host=args.addr, port=args.port, debug=args.verbose > 0)
    print("\nLeaving..")
    app.stop_stats_loader()
    return 0


if __name__ == "__main__":
    sys.exit(main())
