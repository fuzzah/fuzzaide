# -*- coding: utf-8 -*-

# file    :  tests/test_import.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from __future__ import print_function, absolute_import

import os
import sys
import glob

import pytest

# TODO: find a better way to check runability of scripts
@pytest.mark.skip(reason="modules importing is inconsistent for installed and not installed packages")
@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_tools_importable():
    """
    try to load all the .py files in fuzzaide.tools
    """

    import imp

    from fuzzaide import tools
    from fuzzaide.tools import fuzz_webview, fuzzman

    modules = (tools, fuzz_webview, fuzzman)

    script_dirs = map(lambda m: os.path.dirname(m.__file__), modules)
    for script_dir in script_dirs:
        for script_path in glob.glob(os.path.join(script_dir, "*.py")):
            fname = os.path.basename(script_path)
            if not fname.startswith("__"):
                imp.load_source(fname, script_path)

