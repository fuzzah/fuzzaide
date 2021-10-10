import os
import sys
import glob

import pytest


# imp module is deprecated in python3
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_tools_importable():
    """
    try to load all the .py files in fuzzaide.tools
    """

    import imp

    from fuzzaide import tools

    scripts_dir = os.path.dirname(tools.__file__)
    for script_path in glob.glob(os.path.join(scripts_dir, "*.py")):
        fname = os.path.basename(script_path)
        if not fname.startswith("__"):
            imp.load_source(fname, script_path)
