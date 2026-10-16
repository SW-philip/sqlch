"""Pure rectangle math for docking the Library/Discover windows to Now
Playing. No GTK: positions are layer-shell margins in monitor pixels."""

from typing import NamedTuple

# .popup-window carries ~12px of transparent shadow margin between two
# adjacent cards; overlapping the surfaces by 8px leaves a ~4px visual gap.
DOCK_GAP = -8
SNAP_DIST = 20


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def moved(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)


def _v_overlap(a: Rect, b: Rect, slack: int = 0) -> bool:
    return a.y < b.bottom + slack and a.bottom > b.y - slack


def _h_overlap(a: Rect, b: Rect, slack: int = 0) -> bool:
    return a.x < b.right + slack and a.right > b.x - slack


def _side_adjacent(a: Rect, b: Rect, gap: int, tol: int) -> bool:
    return _v_overlap(a, b) and (
        abs(a.x - (b.right + gap)) <= tol or abs(a.right - (b.x - gap)) <= tol)


def _stacked(a: Rect, b: Rect, gap: int, tol: int) -> bool:
    return _h_overlap(a, b) and (
        abs(a.y - (b.bottom + gap)) <= tol or abs(a.bottom - (b.y - gap)) <= tol)


def touches(a: Rect, b: Rect, gap: int = DOCK_GAP, tol: int = 2) -> bool:
    return _side_adjacent(a, b, gap, tol) or _stacked(a, b, gap, tol)


def _pick(best, d, dist):
    if abs(d) <= dist and (best is None or abs(d) < abs(best)):
        return d
    return best


def snap(rect: Rect, others: list[Rect], dist: int = SNAP_DIST,
         gap: int = DOCK_GAP) -> Rect:
    """Snap each axis independently to the nearest candidate edge within
    `dist`. X first; top/bottom alignment only counts against windows that
    are side-adjacent after the X move, so a window can't align to something
    it isn't next to."""
    dx = None
    for o in others:
        if _v_overlap(rect, o, dist):
            dx = _pick(dx, o.right + gap - rect.x, dist)
            dx = _pick(dx, o.x - gap - rect.right, dist)
        if _h_overlap(rect, o, dist):
            dx = _pick(dx, o.x - rect.x, dist)
            dx = _pick(dx, o.right - rect.right, dist)
    rect = rect.moved(dx or 0, 0)

    dy = None
    for o in others:
        if _h_overlap(rect, o, dist):
            dy = _pick(dy, o.bottom + gap - rect.y, dist)
            dy = _pick(dy, o.y - gap - rect.bottom, dist)
        if _side_adjacent(rect, o, gap, dist):
            dy = _pick(dy, o.y - rect.y, dist)
            dy = _pick(dy, o.bottom - rect.bottom, dist)
    return rect.moved(0, dy or 0)


def clamp(rect: Rect, mon_w: int, mon_h: int) -> Rect:
    x = max(0, min(rect.x, mon_w - rect.w))
    y = max(0, min(rect.y, mon_h - rect.h))
    return Rect(x, y, rect.w, rect.h)


def default_dock(np_rect: Rect, items: list[tuple[str, int]],
                 gap: int = DOCK_GAP) -> dict[str, Rect]:
    out: dict[str, Rect] = {}
    edge = np_rect.x
    for name, w in items:
        edge = edge - gap - w
        out[name] = Rect(edge, np_rect.y, w, np_rect.h)
    return out
