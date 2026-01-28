import os
import sys
import json
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from core import player, library, discover


HELP = """sqlch — radio + metadata orchestrator

Usage:
  sqlch status
  sqlch play <id|name|index|url>
  sqlch play-last
  sqlch pause
  sqlch stop

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


def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print(HELP)
        return

    if len(sys.argv) < 2:
        print(player.status_string())
        return

    cmd = sys.argv[1]

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
        if len(sys.argv) < 3:
            print("Usage: sqlch play <id|name|index|url>", file=sys.stderr)
            sys.exit(1)

        arg = sys.argv[2]

        # numeric index from last search
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

        # saved station
        station = library.find_station(arg)
        if station:
            player.play_station(station)
            return

        # raw URL
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

    # ---------------- library ----------------

    if cmd == "list":
        stations = library.list_stations()
        if not stations:
            print("No stations saved.")
            return

        for st in stations:
            print(f"{st['id']:20} {st['name']}")
        return

    if cmd == "info":
        if len(sys.argv) < 3:
            print("Usage: sqlch info <station-id>", file=sys.stderr)
            sys.exit(1)

        st = library.find_station(sys.argv[2])
        if not st:
            print("Station not found.", file=sys.stderr)
            sys.exit(1)

        print(json.dumps(st, indent=2))
        return

    if cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: sqlch add <url>", file=sys.stderr)
            sys.exit(1)

        url = sys.argv[2]
        name = urlparse(url).netloc or url

        st = library.add_station(name=name, url=url)
        print(f"Added station: {st['id']}")
        return

    if cmd == "edit":
        if len(sys.argv) < 3:
            print("Usage: sqlch edit <station-id>", file=sys.stderr)
            sys.exit(1)

        st = library.find_station(sys.argv[2])
        if not st:
            print("Station not found.", file=sys.stderr)
            sys.exit(1)

        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"

        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            json.dump(st, tf, indent=2)
            tf.flush()
            subprocess.call([editor, tf.name])

        edited = json.loads(Path(tf.name).read_text())
        edited["id"] = st["id"]  # immutable
        library.update_station(st["id"], edited)

        print(f"Updated station: {st['id']}")
        return

    if cmd == "rm":
        if len(sys.argv) < 3:
            print("Usage: sqlch rm <station-id>", file=sys.stderr)
            sys.exit(1)

        if library.remove_station(sys.argv[2]):
            print("Removed.")
        else:
            print("Station not found.", file=sys.stderr)
            sys.exit(1)
        return

    # ---------------- discovery ----------------

    if cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: sqlch search <query>", file=sys.stderr)
            sys.exit(1)

        results = discover.search(" ".join(sys.argv[2:]))
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
        return

    if cmd == "preview":
        if len(sys.argv) < 3:
            print("Usage: sqlch preview <index|url>", file=sys.stderr)
            sys.exit(1)

        arg = sys.argv[2]
        if arg.isdigit():
            results = discover.load_last_search()
            idx = int(arg) - 1
            if not results or idx < 0 or idx >= len(results):
                print("Preview index out of range.", file=sys.stderr)
                sys.exit(1)
            player.preview(results[idx]["url"])
        else:
            player.preview(arg)
        return

    print(f"Unknown command: {cmd}", file=sys.stderr)
    sys.exit(1)
