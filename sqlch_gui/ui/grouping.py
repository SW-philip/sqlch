"""Grouping for a source pane's sort pill: pure, no Gtk. group() turns show
items into ("header", text, depth) and ("item", item, tag) rows."""

MODES = ("source", "genre", "az")
LABELS = {"source": "SOURCE", "genre": "GENRE", "az": "A–Z"}
OTHER = "Other"


def next_mode(mode: str, modes=MODES) -> str:
    return modes[(modes.index(mode) + 1) % len(modes)] if mode in modes else modes[0]


def _str(value) -> str:
    # Items come from external directories: a title or genre can be an int, a dict or None.
    return value if isinstance(value, str) else ""


def _title(item) -> str:
    return _str(item.get("title")).casefold()


def _genre(item) -> str:
    return _str(item.get("genre")) or OTHER


def _by_genre(items, depth, tag) -> list:
    rows = []
    for g in sorted({_genre(i) for i in items}, key=lambda g: (g == OTHER, g.casefold())):
        rows.append(("header", g, depth))
        rows += [("item", i, tag(i)) for i in sorted(items, key=_title) if _genre(i) == g]
    return rows


def group(items, mode, providers=None) -> list:
    providers = providers or {}

    def shorts(i):
        return "·".join(providers.get(p, {}).get("short", p) for p in i.get("providers") or [])

    if mode == "az":
        return [("item", i, _str(i.get("genre"))) for i in sorted(items, key=_title)]
    if mode == "genre":
        return _by_genre(items, 0, shorts)
    seen = {p for i in items for p in i.get("providers") or []}
    order = [p for p in providers if p in seen] + sorted(seen - set(providers))
    rows = []
    for p in order:
        rows.append(("header", providers.get(p, {}).get("title", p.upper()), 0))
        rows += _by_genre([i for i in items if p in (i.get("providers") or [])], 1, lambda i: "")
    loose = [i for i in items if not i.get("providers")]
    if loose:
        rows.append(("header", OTHER.upper(), 0))
        rows += _by_genre(loose, 1, lambda i: "")
    return rows
