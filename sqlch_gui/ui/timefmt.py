import time


def format_duration(seconds) -> str:
    if not seconds or seconds <= 0:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def format_date(ts) -> str:
    """Calendar day of an epoch timestamp. yt-dlp's approximate dates sit on
    UTC midnight, so localtime would show the previous day west of Greenwich."""
    if not isinstance(ts, (int, float)) or ts <= 0:
        return ""
    t = time.gmtime(ts)
    return f"{time.strftime('%b', t)} {t.tm_mday}, {t.tm_year}"
