# -*- coding: utf-8 -*-

# file    :  common/fs_utils.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from __future__ import print_function

import os

try:
    from shutil import which
except:
    def _access_check(fn, mode):
        return os.path.exists(fn) and os.access(fn, mode) and not os.path.isdir(fn)

    def which(cmd, mode=os.F_OK | os.X_OK):
        """
        Partial implementation as in Python3
        """
        if os.path.dirname(cmd):
            if _access_check(cmd, mode):
                return cmd
            return None

        path = os.environ.get("PATH", None)
        if path is None:
            return None

        path = path.split(os.pathsep)

        seen = set()
        for dir in path:
            normdir = os.path.normcase(dir)
            if normdir in seen:
                continue
            seen.add(normdir)
            name = os.path.join(dir, cmd)
            if _access_check(name, mode):
                return name
        return None
