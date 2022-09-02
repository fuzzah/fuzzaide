import pytest

from fuzzaide.tools.fuzzman.fuzzman import FuzzManager

def test_fuzzman_init():
    f = FuzzManager(args=[])
    assert f
