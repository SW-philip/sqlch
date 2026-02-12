import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from sqlch.core import player, library, discover


HELP = """sqlch — radio + metadata orchestrator

Usage:
  sqlch status
  sqlch play <id|name|index|url>
  sqlch play-last
  sqlch pause
  sqlch stop
  sqlch tui

Library:
  sqlch list
  sqlch info <id>
  sqlch add <url>
  sqlch edit <id>
  sqlch rm <id>

Discovery:
  sqlch search <query>
  sqlch preview <index|url>
  sqlch import <stations.json>
"""


# ------------------------------------------------------------
# Entry
# ------------------------------------------------------------

def main():
    argv = sys.argv[1:]

    if not argv:
        print(player.status_string())
        return

    if argv[0] in ("-h", "--help", "help"):
        print(HELP)
        return

    cmd, *args = argv

    # TUI is a mode, not a side script
    if cmd == "tui":
        from sqlch.tui.app import main as tui_main
        tui_main()
        return

    dispatch_command(cmd, args)


# ------------------------------------------------------------
# Command dispatch
# ------------------------------------------------------------

def dispatch_command(cmd: str, args: list[str]) -> None:
    # ---------------- basic controls ----------------

    if cmd == "status":
        print(player.status_string())
        return

    if cmd == "stop":
        player.stop()
        return

    if cmd == "pause":
        player.pause()
        return

    if cmd == "play-last":
        player.start_last()
        return

    # ---------------- play ----------------

    if cmd == "play":
        play_cmd(args)
        return

    # ---------------- library ----------------

    if cmd == "list":
        list_cmd()
        return

    if cmd == "info":
        info_cmd(args)
        return

    if cmd == "add":
        add_cmd(args)
        return

    if cmd == "edit":
        edit_cmd(args)
        return

    if cmd == "rm":
        rm_cmd(args)
        return

    # ---------------- discovery ----------------

    if cmd == "search":
        search_cmd(args)
        return

    if cmd == "preview":
        preview_cmd(args)
        return

    print(f"Unknown command: {cmd}", file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------
# Command implementations
# ------------------------------------------------------------

def play_cmd(args: list[str]) -> None:
    if not args:
        print("Usage: sqlch play <id|name|index|url>", file=sys.stderr)
        sys.exit(1)

    arg = args[0]

    if arg.isdigit():
        results = discover.load_last_search()
        idx = int(arg) - 1

        if not results or idx < 0 or idx >= len(results):
            print("Play index out of range.", file=sys.stderr)
            sys.exit(1)

        st = results[idx]

        station = library.add_station(
            name=st.get("name") or "unknown",
            url=st.get("url"),
            tags=(st.get("tags") or "").split(",")
            if isinstance(st.get("tags"), str)
            else st.get("tags") or [],
            source={
                "type": "search",
                "origin": "radio-browser",
                "country": st.get("country"),
                "codec": st.get("codec"),
                "bitrate": st.get("bitrate"),
            },
            allow_existing=True,
        )

        player.play_station(station)
        return

    station = library.find_station(arg)
    if station:
        player.play_station(station)
        return

    if "://" in arg:
        station = library.add_station(
            name=urlparse(arg).netloc or arg,
            url=arg,
            source={"type": "adhoc", "origin": "cli"},
            allow_existing=True,
        )
        player.play_station(station)
        return

    print(f"Could not resolve station: {arg}", file=sys.stderr)
    sys.exit(1)


def list_cmd() -> None:
    stations = library.list_stations()
    if not stations:
        print("No stations saved.")
        return

    for st in stations:
        print(f"{st['id']:20} {st['name']}")


def info_cmd(args: list[str]) -> None:
    if not args:
        print("Usage: sqlch info <station-id>", file=sys.stderr)
        sys.exit(1)

    st = library.find_station(args[0])
    if not st:
        print("Station not found.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(st, indent=2))


def add_cmd(args: list[str]) -> None:
    if not args:
        print("Usage: sqlch add <url>", file=sys.stderr)
        sys.exit(1)

    url = args[0]
    name = urlparse(url).netloc or url
    st = library.add_station(name=name, url=url)

    print(f"Added station: {st['id']}")


def edit_cmd(args: list[str]) -> None:
    if not args:
        print("Usage: sqlch edit <station-id>", file=sys.stderr)
        sys.exit(1)

    st = library.find_station(args[0])
    if not st:
        print("Station not found.", file=sys.stderr)
        sys.exit(1)

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"

    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
        json.dump(st, tf, indent=2)
        tf.flush()
        subprocess.call([editor, tf.name])

    edited = json.loads(Path(tf.name).read_text())
    edited["id"] = st["id"]
    library.update_station(st["id"], edited)

    print(f"Updated station: {st['id']}")


def rm_cmd(args: list[str]) -> None:
    if not args:
        print("Usage: sqlch rm <station-id>", file=sys.stderr)
        sys.exit(1)

    if library.remove_station(args[0]):
        print("Removed.")
    else:
        print("Station not found.", file=sys.stderr)
        sys.exit(1)


def search_cmd(args: list[str]) -> None:
    if not args:
        print("Usage: sqlch search <query>", file=sys.stderr)
        sys.exit(1)

    results = discover.search(" ".join(args))
    discover.save_last_search(results)

    if not results:
        print("No results.")
        return

    for i, st in enumerate(results, 1):
        country = st.get("country") or "-"
        codec = st.get("codec") or "-"
        bitrate = f"{st['bitrate']}kbps" if st.get("bitrate") else "-"
        url = st.get("url") or "-"

        print(
            f"[{i:2}] {st.get('name', 'Unknown')}\n"
            f"     {country} | {codec} {bitrate}\n"
            f"     url: {url}\n"
        )


def preview_cmd(args: list[str]) -> None:
    if not args:
        print("Usage: sqlch preview <index|url>", file=sys.stderr)
        sys.exit(1)

    arg = args[0]
    if arg.isdigit():
        results = discover.load_last_search()
        idx = int(arg) - 1
        if not results or idx < 0 or idx >= len(results):
            print("Preview index out of range.", file=sys.stderr)
            sys.exit(1)
        player.preview(results[idx]["url"])
    else:
        player.preview(arg)
