def format_seconds_afl_like(seconds: int) -> str:
    """
    Returns time in AFL-like format: "1 days, 2 hrs, 34 min, 56 sec"
    NOTE: the result will not contain days, hours, or minutes if they are 0, e.g.:
        2 hrs, 34 min, 56 sec   # 0 days
        34 min, 56 sec          # 0 days, 0 hours
        56 sec                  # 0 days, 0 hours, 0 minutes
    """

    if seconds < 60:
        return "%d sec" % (seconds,)

    s = seconds % 60
    m = (seconds // 60) % 60
    h = (seconds // 3600) % 24
    d = seconds // 86400

    if d > 0:
        return "%d days, %d hrs, %d min, %d sec" % (d, h, m, s)

    if h > 0:
        return "%d hrs, %d min, %d sec" % (h, m, s)

    if m > 0:
        return "%d min, %d sec" % (m, s)

    return "%d sec" % (s,)


def format_big_stat_number(number: int) -> str:
    """
    Convert a possibly big number to a string like "1.1K", "1.23M", or "1.2345B"
    Values below 1000 are returned as is, without any special formatting.
    """

    if number < 1000:
        return str(number)

    suffix = {
        1_000_000_000: ("B", 4),
        1_000_000: ("M", 2),
        1000: ("K", 1),
    }
    for divisor, (letter, places) in suffix.items():
        if number >= divisor:
            fmt = f"%.{places}f{letter}"
            return fmt % (float(number) / divisor,)

    return str(number)
