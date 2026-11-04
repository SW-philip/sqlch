"""Hover text for list rows. Pure functions: no GTK, so they test anywhere."""

from .timefmt import format_date, format_duration

DESCRIPTION_MAX = 300


def _freq(v) -> float:
    try:
        return float(str(v or "0").split()[0])
    except (ValueError, IndexError):
        return 0.0


def item_tooltip(item: dict) -> str | None:
    title = item.get("title")
    if not title:
        return None
    meta = " · ".join(x for x in (item.get("artist"), item.get("album"),
                                  format_date(item.get("date")),
                                  format_duration(item.get("duration"))) if x)
    lines = [title] + ([meta] if meta else [])
    desc = item.get("description")
    if desc and item.get("kind") != "folder":
        if len(desc) > DESCRIPTION_MAX:
            desc = desc[:DESCRIPTION_MAX - 1].rstrip() + "…"
        return "\n".join(lines) + "\n\n" + desc
    return "\n".join(lines)


def station_tooltip(station: dict, live_text: str = "") -> str:
    lines = [station.get("name") or "",
             f"{station.get('group') or 'Unsorted'} · {_freq(station.get('frequency')):.1f}"]
    if live_text:
        lines.append(live_text)
    return "\n".join(lines)
