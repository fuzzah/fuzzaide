from typing import List

from fuzzaide.tools.fuzzman.fuzzman import FuzzManager
from fuzzaide.common.exception import FuzzaideException

import os
import logging

log = logging.getLogger(__name__)

import pytest
from pytest_mock import MockerFixture

extract = FuzzManager.extract_complex_mode_params
adjust = FuzzManager.adjust_complex_mode_params

OS_PATH_MOCK_PATH = "fuzzaide.tools.fuzzman.fuzzman.os.path"
WHICH_MOCK_PATH = "fuzzaide.tools.fuzzman.fuzzman.which"

testdata_extract_parse = [
    # fmt: off
    (["a/p"], "p", [[None, "a/p", None, False]]),
    (["a/p:0"], "p", [[None, "a/p", 0, False]]),
    (["a/p:1"], "p", [[None, "a/p", 1, False]]),
    (["a/p:5%"], "p", [[None, "a/p", 5.0, True]]),
    (["a/p:255%"], "p", [[None, "a/p", 255.0, True]]),
    (["a/p", "b/p"], "p", [[None, "a/p", None, False], [None, "b/p", None, False]]),
    (["basic:a/p", "asan:b/p"], "p", [["basic", "a/p", None, False], ["asan", "b/p", None, False]]),
    (["basic:a/p", "asan:b/p:1"], "p", [["basic", "a/p", None, False], ["asan", "b/p", 1, False]]),
    (["basic:a/p", "asan:b/p:15%"], "p", [["basic", "a/p", None, False], ["asan", "b/p", 15, True]]),
    (["basic:a/p", "b/p:13"], "p", [["basic", "a/p", None, False], [None, "b/p", 13, False]]),
    (["a/p", "asan:b/p:15%", "ubsan:c/p:10%"], "p", [[None, "a/p", None, False], ["asan", "b/p", 15, True], ["ubsan", "c/p", 10, True]]),
    (["a/p:89", "asan:b/p:15%", "ubsan:c/p:10%"], "p", [[None, "a/p", 89, False], ["asan", "b/p", 15, True], ["ubsan", "c/p", 10, True]]),
    (["a/p:89.5%", "asan:b/p:15%", "ubsan:c/p:10%"], "p", [[None, "a/p", 89.5, True], ["asan", "b/p", 15, True], ["ubsan", "c/p", 10, True]]),
    # fmt: on
]


@pytest.mark.parametrize("builds, program, expected", testdata_extract_parse)
def test_extract_complex_mode_params_parse(
    builds: List[str],
    program: str,
    expected: List,
    mocker: MockerFixture,
) -> None:
    mocker.patch(OS_PATH_MOCK_PATH + ".isfile", return_value=True)
    mocker.patch(OS_PATH_MOCK_PATH + ".isdir", return_value=False)
    mocker.patch(WHICH_MOCK_PATH, lambda x: x)
    assert extract(user_builds=builds, program=program, verbose=True) == expected


testdata_extract_files_dirs_invalid = [
    # fmt: off
    (False, False, False, "--builds should point EITHER to directories OR to binaries"),
    (False, False, True, "--builds should point EITHER to directories OR to binaries"),
    (True, True, False, "--builds should point EITHER to directories OR to binaries"),
    (True, True, True, "--builds should point EITHER to directories OR to binaries"),
    (True, False, False, "Error in --builds argument: file .*? not found so it cannot be tested"),
    # fmt: on
]


@pytest.mark.parametrize(
    "all_files, all_dirs, exists, exception_str", testdata_extract_files_dirs_invalid
)
def test_extract_complex_mode_params_files_dirs_invalid(
    all_files: bool,
    all_dirs: bool,
    exists: bool,
    exception_str: str,
    mocker: MockerFixture,
) -> None:
    mocker.patch(OS_PATH_MOCK_PATH + ".isfile", return_value=all_files and not all_dirs)
    mocker.patch(OS_PATH_MOCK_PATH + ".isdir", return_value=all_dirs and not all_files)
    mocker.patch(WHICH_MOCK_PATH, lambda x: exists and x or None)
    builds = ["a/p", "b/p"]
    program = "p"
    with pytest.raises(FuzzaideException) as e:
        extract(user_builds=builds, program=program, verbose=True)
    assert e.match(exception_str)


testdata_extract_files_dirs_ok = [
    # fmt: off
    (False, True, True),
    (True, False, True),
    # fmt: on
]


@pytest.mark.parametrize("all_files, all_dirs, exists", testdata_extract_files_dirs_ok)
def test_extract_complex_mode_params_files_dirs_ok(
    all_files: bool,
    all_dirs: bool,
    exists: bool,
    mocker: MockerFixture,
) -> None:
    files_not_dirs = all_files and not all_dirs
    dirs_not_files = all_dirs and not all_files

    # NOTE: Two files -> four checks,
    # but actually the number of checks is 3 if the first one returns False
    # due to the fact we're using all().
    # Hence, side effect requires 3 values instead of 4
    mocker.patch(
        OS_PATH_MOCK_PATH + ".isfile", side_effect=[files_not_dirs, True, True]
    )
    mocker.patch(OS_PATH_MOCK_PATH + ".isdir", return_value=dirs_not_files)
    mocker.patch(WHICH_MOCK_PATH, lambda x: exists and x or None)
    builds = ["a/p", "b/p"]
    program = "p"
    assert extract(user_builds=builds, program=program, verbose=True)
