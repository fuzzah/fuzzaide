# file    :  fuzz_stats.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

"""
Utility functions for fuzzer stats
"""


def is_afl_fuzzer_stats_old(stats):
    """
    Checks dictionary `stats` to detect stat names introduced in afl++ 4.00.
    Returns True, False or None.
    None is returned if `stats` dict is empty or doesn't contain checked fields.
    """

    if not stats:
        return None

    if stats.get("last_path") is not None:
        return True

    if stats.get("last_find") is not None:
        return False

    # last path/find stat is not yet present in fuzzer_stats
    return None


def get_afl_stat_name(wanted_stat_name, is_old_afl_stats):
    """
    `is_old_afl_stats` should be True or False.
    `wanted_stat_name` is stat name as in original AFL fuzzer.
    NOTE: not all stats supported. Add them as needed.
    """
    stat_style_mapping = {
        True: {  # old stats style
            "last_path": "last_path",
            "last_crash": "last_crash",
            "last_hang": "last_hang",
            "paths_found": "paths_found",
            "paths_total": "paths_total",
            "unique_crashes": "unique_crashes",
            "unique_hangs": "unique_hangs",
        },
        False: {  # stats since afl++ 4.00
            "last_path": "last_find",
            "last_crash": "last_crash",
            "last_hang": "last_hang",
            "paths_found": "corpus_found",
            "paths_total": "corpus_count",
            "unique_crashes": "saved_crashes",
            "unique_hangs": "saved_hangs",
        },
    }
    return stat_style_mapping[is_old_afl_stats][wanted_stat_name]
