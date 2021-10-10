#!/usr/bin/env python
# -*- coding: utf-8 -*-

# file    :  appverif-minimize.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from __future__ import print_function

import os
import re
import sys
import glob
import shutil
import argparse
from xml.sax.saxutils import unescape as sax_unescape


def main():

    parser = argparse.ArgumentParser(
        description="%(prog)s - tool to minimize AppVerifier XML logs and corresponding WinAFL test cases",
        epilog="*sigh* fuzzing on Windows has always been a mess...",
    )
    parser.add_argument(
        "-l",
        "--logs-in",
        "--xml-in",
        metavar="LOGS_PATH",
        help="path to directory with AppVerifier XML logs",
        required=True,
    )
    parser.add_argument(
        "-c",
        "--cases-in",
        "--have-cases",
        metavar="CASES_PATH",
        help="optional path to directory with corresponsing WinAFL test cases",
        default=None,
    )

    parser.add_argument(
        "-L",
        "--logs-out",
        metavar="MINIMIZED_LOGS_PATH",
        help="path where to save minimized AppVerifier XML logs",
        default=None,
    )
    parser.add_argument(
        "-C",
        "--cases-out",
        metavar="MINIMIZED_CASES_PATH",
        help="path where to save minimized cases (-c required)",
        default=None,
    )

    parser.add_argument(
        "--trace-head",
        metavar="NUM_LINES",
        help="only detect similarities in first NUM_LINES lines of stack traces (use with care)",
        type=int,
        default=None,
    )
    parser.add_argument(
        "-f",
        "--force",
        help="allow saving to non-empty directories and overwriting existing files (-ff to cleanup existing files)",
        action="count",
        default=0,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help='show discovered groups (enabled if "out" params omitted)',
        action="store_true",
    )

    if len(sys.argv) < 2:
        parser.print_help()
        return 0

    args = parser.parse_args()

    if not args.logs_out and not args.cases_out:
        args.verbose = True  # no output dirs: just print what we found

    verbose = print if args.verbose else lambda *_a, **_k: None

    if args.cases_out and not args.cases_in:
        sys.exit("You have specified --cases-out without --cases-in!")

    def are_paths_same(src, dst):
        if src == dst:
            return True

        if os.name == "nt":
            src = os.path.normcase(src)
            dst = os.path.normcase(dst)

        if os.path.normpath(src) == os.path.normpath(dst):
            return True

        return False

    if not os.path.isdir(args.logs_in):
        sys.exit("Directory doesn't exist: %s" % (args.logs_in,))

    if args.logs_out and are_paths_same(args.logs_in, args.logs_out):
        sys.exit("ERROR: --logs-in and --logs-out point to the same directory!")

    if args.cases_in:
        if not os.path.isdir(args.cases_in):
            sys.exit("Directory doesn't exist: %s" % (args.cases_in,))
        if args.cases_out and are_paths_same(args.cases_in, args.cases_out):
            sys.exit("ERROR: --cases-in and --cases-out point to the same directory!")

    def prep_output_dir(path):
        try_create = False
        if os.path.exists(path):
            if os.path.isdir(path):
                if not os.listdir(path):  # empty dir exists
                    return True
                elif args.force > 1:  # cleanup allowed
                    try:
                        shutil.rmtree(path)
                    except:
                        print(
                            "Wasn't able to remove directory '%s'" % (path,),
                            file=sys.stderr,
                        )
                        return False
                    try_create = True
                elif args.force < 1:
                    print(
                        "Directory '%s' already exists and contains some files. Use -f to continue anyway or -ff to also get rid of existing files"
                        % (path,),
                        file=sys.stderr,
                    )
                    return False
                else:
                    return True  # overwriting allowed
            else:
                print(
                    "Can't create directory '%s' because this is a file" % (path,),
                    file=sys.stderr,
                )
                return False
        else:
            try_create = True

        if try_create:
            try:
                os.makedirs(path, exist_ok=True)
            except:
                print("Wasn't able to create directory '%s'" % (path,), file=sys.stderr)
                return False
            else:
                return True

        return False

    if args.logs_out:
        if not prep_output_dir(args.logs_out):
            sys.exit("Wasn't able to prepare output directory for minimized logs")

    if args.cases_out:
        if not prep_output_dir(args.cases_out):
            sys.exit("Wasn't able to prepare output directory for minimized cases")

    re_caseid = re.compile(r"^.*id\D+(\d+).*?$")
    re_logid = re.compile(r"^.*\.(\d+)\.dat\.xml$")

    def get_case_id(casename):
        caseid = re_caseid.search(casename)
        if not caseid:
            return None
        caseid = int(caseid.group(1))
        return caseid

    def get_log_id(logname):
        logid = re_logid.search(logname)
        if not logid:
            return None
        logid = int(logid.group(1))
        return logid

    # typical name: notepad.exe.97.dat.xml
    logfnames = sorted(
        glob.glob(os.path.join(args.logs_in, "*.dat.xml")), key=lambda x: get_log_id(x)
    )

    if len(logfnames) < 1:
        sys.exit("No files in given directory %s!" % (args.logs_in,))

    if args.cases_in:
        # typical name: id_000097_00_EXCEPTION_ACCESS_VIOLATION
        casefnames = sorted(
            glob.glob(os.path.join(args.cases_in, "id*")), key=lambda x: get_case_id(x)
        )

        if len(casefnames) < 1:
            sys.exit("No files in given directory %s!" % (args.cases_in,))

        ## unused (yet?) code
        # def case2logname(casename, lognames):
        #     caseid = get_case_id(casename)

        #     if caseid is None:
        #         return None

        #     for logname in lognames:
        #         logid = get_log_id(logname)
        #         if logid is None:
        #             continue

        #         if logid == caseid:
        #             return logname

        #     return None

        def log2casename(logname, casenames):
            logid = get_log_id(logname)

            if logid is None:
                return None

            for casename in casenames:
                caseid = get_case_id(casename)
                if caseid is None:
                    continue

                if caseid == logid:
                    return casename

            return None

    else:
        casefnames = []

        # unused (yet?) code
        # def case2logname(_casename,_lognames):
        #     return None

        def log2casename(_logname, _casenames):
            return None

    re_traces = re.compile(
        r' Severity="(.*?)".*?<avrf:message>(.*?)</avrf:message>.*?<avrf:stackTrace>(.*?)</avrf:stackTrace>',
        re.MULTILINE | re.DOTALL,
    )

    def extract_traces(logfname, headsize=None):
        try:
            with open(logfname, "rt") as f:
                data = f.read()
        except:
            print("Wasn't able to read file %s" % (logfname,), file=sys.stderr)
            return None

        traces = re_traces.findall(data)
        if len(traces) < 1:
            verbose("INFO: file %s contains no stack traces" % (logfname,))
            return None
        traces = list(
            map(
                lambda t: "Application Verifier " + t[0] + ": " + t[1] + "\n" + t[2],
                traces,
            )
        )

        if headsize is not None:
            traces = list(
                map(lambda t: "\n".join(t.split("\n")[0 : headsize + 1]), traces)
            )

        return traces

    trace2log = dict()
    log2trace = dict()

    for logfname in logfnames:
        if args.cases_in:
            if log2casename(logfname, casefnames) is None:
                print(
                    "WARNING: case file for %s is missing because file with corresponding id wasn't found in %s"
                    % (logfname, args.cases_in),
                    file=sys.stderr,
                )

        traces = extract_traces(logfname, args.trace_head)
        if traces is not None:
            for trace in traces:
                if trace in trace2log:
                    trace2log[trace].append(logfname)
                else:
                    trace2log[trace] = [logfname]

            log2trace[logfname] = traces

    if len(trace2log) < 1:
        print("No stack traces found (at ALL). Nothing to do.")
        return 0

    def format_trace(trace):
        trace = sax_unescape(trace)
        trace = trace.replace("<avrf:trace>", "")
        trace = trace.replace("</avrf:trace>", "")
        trace = trace.split("\n")
        trace = map(lambda s: s.strip(), trace)
        trace = filter(lambda s: len(s) > 0, trace)
        trace = map(lambda s: "\t" + s, trace)
        return "\n".join(trace)

    def check_and_copy(fname, dst):
        """
        Tries to copy file fname to dst with respect to args.force
        This function exits with sys.exit to prevent unwanted behavior
        """
        destfpath = os.path.join(dst, os.path.basename(fname))
        if args.force < 1 and os.path.exists(destfpath):
            sys.exit(
                "ERROR: file '%s' already exists. Use -f to allow overwriting existing files"
                % (destfpath,)
            )
        try:
            shutil.copy(fname, destfpath)
        except:
            return False

        return True

    def copy_any_casefile(lognames):
        """
        This function enumerates log names to search for corresponding case file.
        If file was found, tries to copy it to path args.cases_out and returns copied case file name.
        If file wasn't found or couldn't be copied, returns None
        """
        res = None
        for logname in lognames:
            casename = log2casename(logname, casefnames)
            if casename is None:
                continue

            if check_and_copy(casename, args.cases_out):
                res = casename
                break

        return res

    print("Unique stack traces found: %d" % (len(trace2log)))

    # In this obscure loop we save our log and case files while printing our minimized groups
    for i, (trace, lognames) in enumerate(trace2log.items()):
        verbose("\nGroup %d (files: %d): " % (i + 1, len(lognames)))

        copied_log_name = None
        if args.logs_out:  # need to save one log file
            for logname in lognames:
                if check_and_copy(logname, args.logs_out):
                    copied_log_name = logname
                    break

            if copied_log_name is None:
                print(
                    "WARNING: wasn't able to copy any one log file for group %d!"
                    % (i + 1,),
                    file=sys.stderr,
                )

        if (
            args.cases_in is None
        ):  # no --cases-in, just print AppVerifier logs in same group
            verbose("\n".join(lognames))
        else:
            for logname in lognames:
                casename = log2casename(logname, casefnames)
                if casename is None:
                    verbose("<case file not found for %s>" % (logname,))
                else:
                    verbose(casename)

        verbose("\nStack trace of group %d (files are listed above):" % (i + 1,))
        verbose(format_trace(trace))

        if args.cases_out:  # need to save one case file
            copied_case_name = None
            casefile_renamed_to = None
            if (
                copied_log_name is None
            ):  # no log file was copied, just copy ANY case file
                copied_case_name = copy_any_casefile(lognames)
            else:
                # find and copy MATCHING case file for copied log file
                casename = log2casename(copied_log_name, casefnames)

                if casename is not None:  # corresponding file was found
                    if check_and_copy(casename, args.cases_out):
                        copied_case_name = casename
                    else:
                        # we'll need to copy another case file from group and rename it
                        print(
                            "WARNING: wasn't able to copy %s to %s"
                            % (casename, args.cases_out),
                            file=sys.stderr,
                        )

                if (
                    copied_case_name is None
                ):  # corresponding file wasn't found or couldn't be copied
                    copied_case_name = copy_any_casefile(lognames)

                    if copied_case_name is not None:
                        # we just copied some other file from the same group, try renaming it
                        srcfpath = os.path.join(
                            args.cases_out, os.path.basename(copied_case_name)
                        )
                        casefile_renamed_to = (
                            srcfpath + "___FOR_LOG_" + str(get_log_id(copied_log_name))
                        )
                        renamed = False
                        if not os.path.exists(casefile_renamed_to):
                            try:
                                shutil.move(srcfpath, casefile_renamed_to)
                                renamed = True
                            except:
                                pass

                        if renamed:
                            print(
                                "INFO: renamed file %s to %s to match log file"
                                % (srcfpath, casefile_renamed_to)
                            )
                        else:
                            print(
                                "WARNING: case file %s is for %s log file"
                                % (srcfpath, copied_log_name),
                                file=sys.stderr,
                            )

            if copied_case_name is None:
                print(
                    "WARNING: giving up on trying to find and copy test case for group %d. You can review -v output and manually copy required file"
                    % (i + 1,),
                    file=sys.stderr,
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
