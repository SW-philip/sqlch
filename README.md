# sqlch

**sqlch** is a headless radio and streaming control toolkit with a clean
CLI, a growing TUI, and a strong bias toward reproducibility.

It is designed to sit comfortably in Unix pipelines, window manager
setups, and declarative systems (especially NixOS), while remaining
usable as a standalone Python application.

------------------------------------------------------------------------

## TUI Preview

![SQLCH Textual TUI](assets/sqlch-tui.png)

Textual-based TUI for discovery and preview, backed by the same core
used by the CLI.

------------------------------------------------------------------------

## What sqlch is

-   A **CLI-first** radio and stream orchestrator
-   A **Python application**, not a monolithic media player
-   A **reproducible artifact** (builds cleanly via PEP 517 and Nix)
-   A system where **metadata, playback, and control** are separate
    concerns

------------------------------------------------------------------------

## What sqlch is not

-   Not a GUI-first media player
-   Not a Spotify clone
-   Not a grab bag of scripts tied to one machine
-   Not dependent on global Python state

------------------------------------------------------------------------

## Architecture (high level)

``` text
sqlch/
├── cli/        # Argument parsing, commands, UX surface
├── core/       # Playback, discovery, library, metadata
├── tui/        # Textual-based interface (optional layer)
└── tools/      # Repo hygiene, linting, sanity checks
```

Design principles:

-   **Single import root** (`sqlch.*`)
-   **Explicit boundaries** between CLI, core logic, and UI
-   **No hidden globals**
-   **No implicit environment assumptions**

------------------------------------------------------------------------

## Installation

### Nix (recommended)

`sqlch` is packaged as a Nix flake and can be built or run directly,
without touching system Python.

#### Run directly from GitHub (no clone required)

``` bash
nix run github:SW-philip/sqlch -- --help
```

Running without arguments is equivalent to:

``` bash
sqlch status
```

This is the simplest way to try `sqlch` on any Nix-enabled system.

------------------------------------------------------------------------

#### From a local checkout

``` bash
git clone https://github.com/SW-philip/sqlch
cd sqlch
nix build
./result/bin/sqlch --help
```

Or run directly:

``` bash
nix run -- --help
```

------------------------------------------------------------------------

#### Consume as a flake input

``` nix
inputs.sqlch.url = "github:SW-philip/sqlch";
```

Then add it to your environment:

``` nix
environment.systemPackages = [
  inputs.sqlch.packages.x86_64-linux.default
];
```

The Nix build produces a wrapped executable with isolated dependencies
and no reliance on global Python state.

------------------------------------------------------------------------

### Python (development / virtualenv)

For development or non-Nix environments:

``` bash
git clone https://github.com/SW-philip/sqlch
cd sqlch
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs `sqlch` in editable mode using the project's
`pyproject.toml`.

------------------------------------------------------------------------

## Usage

Basic playback:

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

Discovery and preview:

``` bash
sqlch search <query>
sqlch preview <index|url>
sqlch import <stations.json>
```

------------------------------------------------------------------------

## Notes on development

AI-assisted tools were used during development as critical
collaborators, not as automated code generators. The emphasis was on
pressure-testing design decisions, interfaces, and assumptions rather
than accelerating output.

The result is a small system that prioritizes clarity, separation of
concerns, and predictable behavior over feature breadth.
