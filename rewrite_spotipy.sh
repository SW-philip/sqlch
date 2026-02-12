#!/usr/bin/env bash
set -euo pipefail

FILE="$HOME/sqlch/sqlch/core/spoti.py"

if [ ! -f "$FILE" ]; then
  echo "spoti.py not found at $FILE"
  exit 1
fi

echo "Backing up original file..."
cp "$FILE" "$FILE.bak.$(date +%s)"

echo "Rewriting cache section..."

awk '
BEGIN { replaced=0 }
/^CACHE_DIR =/ {
    print "# --- Nix-safe lazy cache handling ---"
    print "_CACHE_DIR = None"
    print ""
    print "def _cache_dir():"
    print "    global _CACHE_DIR"
    print "    if _CACHE_DIR is None:"
    print "        base = os.environ.get(\"XDG_CACHE_HOME\")"
    print "        if not base:"
    print "            base = str(Path.home() / \".cache\")"
    print "        _CACHE_DIR = Path(base) / \"sqlch\""
    print "        _CACHE_DIR.mkdir(parents=True, exist_ok=True)"
    print "    return _CACHE_DIR"
    print ""
    print "def _track_cache(): return _cache_dir() / \"spotify_tracks.json\""
    print "def _artist_cache(): return _cache_dir() / \"spotify_artists.json\""
    print "def _token_cache(): return _cache_dir() / \"spotify_token.json\""
    replaced=1
    skip=1
    next
}
/^CACHE_DIR\.mkdir/ { next }
skip && NF==0 { skip=0; next }
!skip { print }
END {
    if (replaced==0) {
        print "WARNING: CACHE_DIR block not found."
    }
}
' "$FILE" > "$FILE.tmp"

mv "$FILE.tmp" "$FILE"

echo "Rewrite complete."
