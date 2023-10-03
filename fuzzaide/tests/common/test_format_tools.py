import pytest

from fuzzaide.common import format_tools as ft


@pytest.mark.parametrize(
    "seconds, str_seconds",
    [
        (0, "0 sec"),
        (1, "1 sec"),
        (-999, "-999 sec"),
        (-1, "-1 sec"),
        (-59, "-59 sec"),
        (-60, "-60 sec"),
        (-61, "-61 sec"),
        (59, "59 sec"),
        (60, "1 min, 0 sec"),
        (61, "1 min, 1 sec"),
        (79, "1 min, 19 sec"),
        (180, "3 min, 0 sec"),
        (59 * 60 + 59, "59 min, 59 sec"),
        (60 * 60, "1 hrs, 0 min, 0 sec"),
        (60 * 60 + 59 * 60 + 59, "1 hrs, 59 min, 59 sec"),
        (23 * 60 * 60 + 59 * 60 + 59, "23 hrs, 59 min, 59 sec"),
        (24 * 60 * 60, "1 days, 0 hrs, 0 min, 0 sec"),
        (999 * 24 * 60 * 60, "999 days, 0 hrs, 0 min, 0 sec"),
    ],
)
def test_format_seconds_afl_like(seconds: int, str_seconds: str) -> None:
    assert ft.format_seconds_afl_like(seconds) == str_seconds


@pytest.mark.parametrize(
    "number, str_number",
    [
        (0, "0"),
        (-1, "-1"),
        (-100000, "-100000"),
        (-999_999_999_999, "-999999999999"),
        (100, "100"),
        (1000, "1.0K"),
        (1001, "1.0K"),
        (1049, "1.0K"),
        (1050, "1.1K"),
        (1949, "1.9K"),
        (1999, "2.0K"),
        (5_432_111, "5.43M"),
        (599_432_111, "599.43M"),
        (999_432_111, "999.43M"),
        (999_532_111, "999.53M"),
        (999_555_555, "999.56M"),
        (999_999_999, "1000.00M"),
        (1_999_944_444, "1.9999B"),
        (1_999_954_444, "2.0000B"),
        (999_999_944_444, "999.9999B"),
        (9_999_999_944_444, "9999.9999B"),
        (999_999_999_944_444, "999999.9999B"),
    ],
)
def test_format_big_stat_number(number: int, str_number: str) -> None:
    assert ft.format_big_stat_number(number) == str_number
