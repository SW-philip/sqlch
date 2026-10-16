"""Pure rectangle math for docking the Library/Discover windows to Now
Playing. No GTK: positions are pixels in the shared output-sized overlay."""

from typing import NamedTuple

# .popup-window carries ~12px of transparent shadow margin between two
# adjacent cards; overlapping the surfaces by 8px leaves a ~4px visual gap.
DOCK_GAP = -8
SNAP_DIST = 20
SNAP_IN = 24     # magnet pulls a dragged card in from this far
BREAK_OUT = 40   # and releases it only past this, so a held snap doesn't flutter


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


def _dx(rect: Rect, others: list[Rect], dist: int, gap: int):
    dx = None
    for o in others:
        if _v_overlap(rect, o, dist):
            dx = _pick(dx, o.right + gap - rect.x, dist)
            dx = _pick(dx, o.x - gap - rect.right, dist)
        if _h_overlap(rect, o, dist):
            dx = _pick(dx, o.x - rect.x, dist)
            dx = _pick(dx, o.right - rect.right, dist)
    return dx


def _dy(rect: Rect, others: list[Rect], dist: int, gap: int):
    dy = None
    for o in others:
        if _h_overlap(rect, o, dist):
            dy = _pick(dy, o.bottom + gap - rect.y, dist)
            dy = _pick(dy, o.y - gap - rect.bottom, dist)
        if _side_adjacent(rect, o, gap, dist):
            dy = _pick(dy, o.y - rect.y, dist)
            dy = _pick(dy, o.bottom - rect.bottom, dist)
    return dy


def snap(rect: Rect, others: list[Rect], dist: int = SNAP_DIST,
         gap: int = DOCK_GAP) -> Rect:
    """Snap each axis independently to the nearest candidate edge within
    `dist`. X first; top/bottom alignment only counts against windows that
    are side-adjacent after the X move, so a window can't align to something
    it isn't next to."""
    rect = rect.moved(_dx(rect, others, dist, gap) or 0, 0)
    return rect.moved(0, _dy(rect, others, dist, gap) or 0)


class Magnet(NamedTuple):
    """Held snapped coordinate per axis; None = free on that axis."""
    x: int | None
    y: int | None


def magnet(raw: Rect, others: list[Rect], held: Magnet,
           snap_in: int = SNAP_IN, break_out: int = BREAK_OUT,
           gap: int = DOCK_GAP) -> tuple[Rect, Magnet, bool]:
    """Live drag snap with hysteresis. Returns (rect to show, new held state,
    clicked). An axis already held stays put until raw is more than
    `break_out` away; otherwise it snaps to the nearest candidate within
    `snap_in`. `clicked` is True when an axis enters or changes snapped
    coordinate. The wider break-out keeps a snapped card from jittering."""
    clicked = False
    hx = held.x
    if hx is not None and abs(raw.x - hx) <= break_out:
        x = hx
    else:
        dx = _dx(raw, others, snap_in, gap)
        x = raw.x if dx is None else raw.x + dx
        hx = None if dx is None else x
        clicked = hx is not None and hx != held.x
    rect = Rect(x, raw.y, raw.w, raw.h)

    hy = held.y
    if hy is not None and abs(raw.y - hy) <= break_out:
        y = hy
    else:
        dy = _dy(rect, others, snap_in, gap)
        y = raw.y if dy is None else raw.y + dy
        hy = None if dy is None else y
        clicked = clicked or (hy is not None and hy != held.y)
    return Rect(x, y, raw.w, raw.h), Magnet(hx, hy), clicked


def held_at(rect: Rect, others: list[Rect], gap: int = DOCK_GAP,
            tol: int = 2) -> Magnet:
    """Axes on which a resting rect already sits snapped, to seed a drag
    that starts there: a nudge then neither clicks nor escapes before
    BREAK_OUT."""
    hx = hy = None
    for o in others:
        if _side_adjacent(rect, o, gap, tol):
            hx = rect.x
            if abs(rect.y - o.y) <= tol or abs(rect.bottom - o.bottom) <= tol:
                hy = rect.y
        if _stacked(rect, o, gap, tol):
            hy = rect.y
            if abs(rect.x - o.x) <= tol or abs(rect.right - o.right) <= tol:
                hx = rect.x
    return Magnet(hx, hy)


def screen_edge_rects(area_w: int, area_h: int, margin: int = 12,
                      gap: int = DOCK_GAP) -> list[Rect]:
    """Usable-area edges as ordinary Rects, so magnet needs no edge pass.
    Each is a slab lying outside the area whose inner face sits at
    margin - gap, so the flush rule (a.x = b.right + gap, etc.) leaves
    exactly `margin` px of clearance. Slabs span only margin..area-margin
    along their edge so alignment candidates also keep the margin, and are
    thick so their far faces never become alignment candidates."""
    pad = 4096
    inner = margin - gap
    return [
        Rect(inner - pad, margin, pad, area_h - 2 * margin),            # left
        Rect(area_w - inner, margin, pad, area_h - 2 * margin),         # right
        Rect(margin, inner - pad, area_w - 2 * margin, pad),            # top
        Rect(margin, area_h - inner, area_w - 2 * margin, pad),         # bottom
    ]


def attached_to(np: Rect, rects: dict[str, Rect], gap: int = DOCK_GAP,
                tol: int = 2) -> set[str]:
    """Names connected to NP through a chain of touching neighbours."""
    found: set[str] = set()
    frontier = [np]
    while frontier:
        cur = frontier.pop()
        for name, r in rects.items():
            if name not in found and touches(r, cur, gap, tol):
                found.add(name)
                frontier.append(r)
    return found


def group_left_room(np: Rect, attached: list[Rect]) -> int:
    """How far left of NP its attached windows reach: NP's x must stay at
    least this, or the leftmost one gets clamped on top of NP."""
    return max([0] + [np.x - r.x for r in attached])


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


def pack(np_rect: Rect, items: list[tuple[str, int]], placed: list[Rect],
         gap: int = DOCK_GAP) -> dict[str, Rect]:
    """Like default_dock, but a slot that would collide with an already
    positioned window is skipped by moving the edge left past it. Slots
    flush with a neighbour (overlapping by -gap) don't count as a collision."""
    out: dict[str, Rect] = {}
    edge = np_rect.x
    for name, w in items:
        while True:
            cand = Rect(edge - gap - w, np_rect.y, w, np_rect.h)
            hit = next((p for p in placed
                        if _v_overlap(cand, p) and _h_overlap(cand, p, gap)), None)
            if hit is None:
                break
            edge = hit.x
        out[name] = cand
        edge = cand.x
    return out
