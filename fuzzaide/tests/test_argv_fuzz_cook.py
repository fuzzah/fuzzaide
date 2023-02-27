from typing import List

import pytest
from pytest import CaptureFixture

from fuzzaide.tools.argv_fuzz_cook import main

testdata = [
    (["1", "2", "hello"], "1\x002\x00hello\x00\x00"),
    (["-c", "1", "2", "hello"], "'1\\x002\\x00hello\\x00\\x00'\n"),
    (["1", "-c", "2", "hello"], "1\x00-c\x002\x00hello\x00\x00"),
]


@pytest.mark.parametrize("argv, expected", testdata)
def test_argv_fuzz_cook_main(argv: List[str], expected: str, capsys: CaptureFixture):
    main(argv)
    captured = capsys.readouterr()
    assert captured.out == expected
