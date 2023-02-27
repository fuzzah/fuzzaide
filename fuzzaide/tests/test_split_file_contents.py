from typing import List, Optional

import pytest
from pytest_mock import MockerFixture

from fuzzaide.common.exception import FuzzaideException
from fuzzaide.tools.split_file_contents import (
    get_bytes_from_value_with_suffix,
    Config,
    get_config,
)

MOCK_COMMON_PATH = "fuzzaide.tools.split_file_contents."

testdata = [
    ("0", 0),
    ("-0", 0),
    ("-1", -1),
    ("1", 1),
    ("1k", 1024),
    ("15k", 15 * 1024),
    ("0k", 0),
    ("-23k", -23 * 1024),
    ("1m", 1024 * 1024),
    ("7g", 7 * 1024 * 1024 * 1024),
]


@pytest.mark.parametrize("x, expected", testdata)
def test_value_with_suffix(x: str, expected: int) -> None:
    assert get_bytes_from_value_with_suffix(x) == expected


bad_testdata = [
    "-",
    "k",
    "1x",
]


@pytest.mark.parametrize("x", bad_testdata)
def test_value_with_suffix_raises(x: str) -> None:
    with pytest.raises(FuzzaideException):
        get_bytes_from_value_with_suffix(x)


good_argv = [
    (
        ["-i", __file__, "-s", "3"],
        Config(
            is_dry_run=False,
            log_level=20,
            num_equal_parts=0,
            output_prefix="",
            filepath=__file__,
            filesize=30,
            names=[],
            maxsize=3,
        ),
    ),
    (
        ["-i", __file__, "-v", "-s", "10", "--output-prefix", "test/"],
        Config(
            is_dry_run=False,
            log_level=10,
            num_equal_parts=0,
            output_prefix="test/",
            filepath=__file__,
            filesize=30,
            names=[],
            maxsize=10,
        ),
    ),
    (
        ["-i", __file__, "-D", "-e", "5", "--output-prefix", "test_"],
        Config(
            is_dry_run=True,
            log_level=10,
            num_equal_parts=5,
            output_prefix="test_",
            filepath=__file__,
            filesize=30,
            names=[],
            maxsize=0,
        ),
    ),
    (
        [
            "-i",
            __file__,
            "-D",
            "-e",
            "7",
            "--names",
            "1,2,3,4,5,6,7",
            "--output-prefix",
            "test_",
        ],
        Config(
            is_dry_run=True,
            log_level=10,
            num_equal_parts=7,
            output_prefix="test_",
            filepath=__file__,
            filesize=30,
            names=["1", "2", "3", "4", "5", "6", "7"],
            maxsize=0,
        ),
    ),
]


@pytest.mark.parametrize("argv, config", good_argv)
def test_parse_args(argv: List[str], config: Config, mocker: MockerFixture) -> None:
    mocker.patch(MOCK_COMMON_PATH + "os.path.isfile", return_value=True)
    mocker.patch(MOCK_COMMON_PATH + "os.path.getsize", return_value=30)

    assert get_config(argv) == config


bad_argv = [
    (
        ["-i", __file__, "-D", "-e", "5", "--output-prefix", "test_"],
        False,  # isfile
        30,
        None,
    ),
    (["-i", __file__, "-D", "-e", "5"], True, 0, None),  # getsize => 0
    (["-i", __file__, "-D", "-e", "5"], True, 30, OSError),  # getsize => OSError
    (
        [
            "-i",
            __file__,
            "-D",
            "-e",
            "5",
            "--names",
            "1,2,3",  # wrong number of names provided, 5 expected
        ],
        True,
        30,
        None,
    ),
]


@pytest.mark.parametrize(
    "argv, isfile_retval, getsize_retval, getsize_exception", bad_argv
)
def test_parse_args_raises(
    argv: List[str],
    isfile_retval: bool,
    getsize_retval: int,
    getsize_exception: Optional[Exception],
    mocker: MockerFixture,
) -> None:
    mocker.patch(MOCK_COMMON_PATH + "os.path.isfile", return_value=isfile_retval)
    mocker.patch(
        MOCK_COMMON_PATH + "os.path.getsize",
        return_value=getsize_retval,
        side_effect=getsize_exception,
    )

    with pytest.raises(FuzzaideException):
        get_config(argv)
