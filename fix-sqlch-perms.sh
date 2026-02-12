#!/usr/bin/env bash
set -euo pipefail

TARGET="$HOME/sqlch"

if [ ! -d "$TARGET" ]; then
  echo "Directory not found: $TARGET"
  exit 1
fi

echo "Fixing ownership of $TARGET"
sudo chown -R "$USER:users" "$TARGET"

echo "Fixing directory permissions"
find "$TARGET" -type d -exec chmod 755 {} \;

echo "Fixing file permissions"
find "$TARGET" -type f -exec chmod 644 {} \;

echo "Making scripts executable"
find "$TARGET" -type f -name "*.sh" -exec chmod +x {} \;

echo "Done."
