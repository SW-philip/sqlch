def scroll_offset(t: float, overflow: float, speed: float = 25.0,
                  pause: float = 1.2) -> float:
    """Marquee position at time t: hold, travel to the far end, hold, travel back."""
    if overflow <= 0:
        return 0.0
    travel = overflow / speed
    phase = t % (2 * (pause + travel))
    if phase < pause:
        return 0.0
    phase -= pause
    if phase < travel:
        return phase * speed
    phase -= travel
    if phase < pause:
        return overflow
    phase -= pause
    return max(0.0, overflow - phase * speed)
