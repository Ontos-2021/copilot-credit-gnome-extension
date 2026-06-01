#!/usr/bin/env bash
set -euo pipefail

uuid="copilot-credit@local"
src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dst_dir="$HOME/.local/share/gnome-shell/extensions/$uuid"

mkdir -p "$dst_dir"
cp "$src_dir/extension.js" "$dst_dir/extension.js"
cp "$src_dir/metadata.json" "$dst_dir/metadata.json"
cp "$src_dir/stylesheet.css" "$dst_dir/stylesheet.css"
cp "$src_dir/copilot-helper.py" "$dst_dir/copilot-helper.py"
chmod +x "$dst_dir/copilot-helper.py"

current="$(gsettings get org.gnome.shell enabled-extensions || true)"
python3 - "$uuid" "$current" <<'PY'
import ast
import subprocess
import sys

uuid = sys.argv[1]
current = sys.argv[2] or "[]"
try:
    items = ast.literal_eval(current)
except Exception:
    items = []
if uuid not in items:
    items.append(uuid)
subprocess.check_call(["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(items)])
PY

echo "Installed $uuid to $dst_dir"
echo "Log out and log back in for GNOME Shell to discover it."
