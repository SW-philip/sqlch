"""TEMPORARY drag/relayout diagnostics, on only with SQLCH_GUI_TRACE=1."""

import os
import sys
import time

ON = os.environ.get("SQLCH_GUI_TRACE") == "1"


def trace(msg: str, *args, caller: int = 0) -> None:
    """One `[trace] <ms> msg` line on stderr, plus `caller` frames of the
    traced function's call chain; formatting only happens when on."""
    if not ON:
        return
    if args:
        msg = msg % args
    f = sys._getframe(2) if caller else None
    for _ in range(caller):
        if f is None:
            break
        msg = f"{msg} <- {f.f_code.co_name}:{f.f_lineno}"
        f = f.f_back
    print(f"[trace] {time.monotonic() * 1000:.1f} {msg}", file=sys.stderr, flush=True)
