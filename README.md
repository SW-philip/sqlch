# sqlch

**sqlch** is a headless radio and streaming control toolkit with a clean
CLI, a growing TUI, and a strong bias toward reproducibility.

It's designed to sit comfortably in Unix pipelines, window manager
setups, and declarative systems (especially NixOS), while remaining
usable as a standalone Python application.

This project is also an experiment in *human--machine co-development*:
using an LLM as a systems-level collaborator, not a code vending
machine.

------------------------------------------------------------------------

## What sqlch is

-   A **CLI-first** radio / stream orchestrator
-   A **Python application**, not a monolith
-   A **reproducible artifact** (builds cleanly via PEP 517 and Nix)
-   A place where **metadata, playback, and control** are treated as
    separate concerns

------------------------------------------------------------------------

## What sqlch is *not*

-   Not a GUI-first media player
-   Not a Spotify clone
-   Not a "just works on my machine" script bundle
-   Not dependent on global Python state

------------------------------------------------------------------------

## Architecture (high level)

    sqlch/
    ├── cli/        # Argument parsing, commands, UX surface
    ├── core/       # Playback, discovery, library, metadata
    ├── tui/        # Textual-based interface (optional layer)
    └── tools/      # Repo hygiene, linting, sanity checks

Key principles:

-   **One import root** (`sqlch.*`)
-   **Explicit boundaries** between CLI, core logic, and UI
-   **No hidden globals**
-   **No implicit environment assumptions**

------------------------------------------------------------------------

## Installation

### NixOS (recommended)

`sqlch` is designed to be built as a proper Nix package, producing a
wrapped executable with isolated dependencies and no pollution of system
Python.

### Python (development / venv)

``` bash
git clone https://github.com/SW-philip/sqlch
cd sqlch
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

------------------------------------------------------------------------

## Usage

``` bash
sqlch play <id|name|index|url>
sqlch status
sqlch pause
sqlch stop
```

Library management:

``` bash
sqlch list
sqlch info <id>
sqlch add <url>
sqlch edit <id>
sqlch rm <id>
```

Discovery:

``` bash
sqlch search <query>
sqlch preview <index|url>
sqlch import <stations.json>
```

------------------------------------------------------------------------

## Appendix: Why this exists

`sqlch` exists because a lot of software quietly collapses under its own
assumptions.

Modern tooling optimizes for immediacy: fast demos, permissive
environments, "it works locally." That approach holds until
reproducibility, packaging, or cross-machine consistency matter---at
which point the cracks appear all at once.

This project was built to push against that tendency. Sometimes gently.
Sometimes with a crowbar.

At the surface, `sqlch` is a small, composable tool for controlling
radio streams. Underneath, it's a record of what happens when you keep
asking "wait, *why* does this work?"---often days *after* realizing the
fix was a single line you could have written before you tore everything
down.

### How it actually started

This didn't begin as a systems project. It began as a UX complaint.

I wanted the discovery and polish of **GNOME Radio** with the
unobtrusive, background-friendly behavior of **radiotray-ng**. One felt
modern and curated. The other respected the desktop and stayed out of
the way. Neither did both, and neither wanted to be customized.

At the time, I had essentially **no formal development experience**.
What I did have was a strong sense of what *felt right* as a user---and
a growing impatience with being told certain tradeoffs were "just how it
is."

So instead of choosing one and living with it, I started pulling at the
threads.

### X-antagonistic (a working philosophy)

Much of this was built on a Microsoft Surface Pro 7+, running NixOS, on
Hyprland. This was intentional.

Years ago, I read something---half-remembered, probably
simplified---about X11 being overly permissive or security-leaky. I
didn't fully understand the implications, but the reaction was immediate
and stubborn: *nope*.

That moment turned into what I think of as **X-antagonistic
development**: an instinct to apply pressure to any layer of the stack
that assumes trust by default, treats opacity as normal, or relies on
historical inertia.

Running Nix on a Surface with Hyprland is not efficient. It *is*
clarifying.

### On build loops and delayed clarity

Progress on this project often looked like discovering the same mistake
at higher and higher levels of abstraction.

Some of the cleanest fixes arrived days *after* a full teardown. That's
frustrating. It's also instructive.

New systems create friction. Friction exposes assumptions. Old systems
often feel stable because they've trained you not to look too closely.

`sqlch` exists because I kept looking too closely.

### On AI-assisted development

An LLM was used extensively throughout this project---not as an
autopilot, but as a collaborator that refuses to share local context.

The value wasn't speed. It was pressure.

The software here isn't AI-authored; it's software that survived
sustained questioning.

### What this project optimizes for

-   Explicit contracts over convenience
-   Reproducibility over cleverness
-   Understanding over velocity

If this project is useful, it's not because it solves a large problem.
It's because it documents what happens when someone starts with a UX
instinct, refuses inherited constraints, and learns the system by
pushing directly on its weakest assumptions.

### Epilogue

I didn't know how Python packaging really worked.
I didn't know what Nix would and would not tolerate.
I didn't know how many things "worked" only because nothing was
checking.

I know those things now.

That's progress.
