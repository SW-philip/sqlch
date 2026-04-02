"""sqlch-enrich: print enriched track metadata as JSON on stdout."""
import json
import sys


def main():
    if len(sys.argv) != 3:
        print(json.dumps({"error": "usage: sqlch-enrich <artist> <track>"}))
        sys.exit(1)
    artist, track = sys.argv[1], sys.argv[2]
    from sqlch.core.enrich import enrich_track
    print(json.dumps(enrich_track(artist, track)))
