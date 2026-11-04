"""Drop-position arithmetic for the Playlist pane, kept free of GTK."""


def insert_index(mids: list[float], y: float) -> int:
    """Which gap a drop at y lands in, among rows with vertical midpoints
    `mids` (gap 0 is above the first row)."""
    for i, mid in enumerate(mids):
        if y < mid:
            return i
    return len(mids)


def move_target(src: int, drop: int) -> int:
    """The `to` for playqueue.move when dragging row `src` into gap `drop`.
    Gaps are numbered with the dragged row still in the list, move() counts
    after it has been taken out."""
    return drop - 1 if drop > src else drop
