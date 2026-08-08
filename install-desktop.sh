#!/usr/bin/env bash
# Install a menu launcher so you can open System Inspector from the app grid.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
DESKTOP_FILE="$APP_DIR/system-inspector.desktop"
ICON_DST="$ICON_DIR/system-inspector.png"
ICON_SRC="$ROOT/frontend/assets/logo.png"

mkdir -p "$APP_DIR" "$ICON_DIR"
chmod +x "$ROOT/SystemInspector" "$ROOT/run.sh" 2>/dev/null || true

if [[ -f "$ICON_SRC" ]]; then
  cp "$ICON_SRC" "$ICON_DST"
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=System Inspector
Comment=Scan hardware specs and live system vitals
Exec=$ROOT/SystemInspector
Icon=system-inspector
Path=$ROOT
Terminal=false
Categories=System;Monitor;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"

# Refresh menu cache when available
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" 2>/dev/null || true
fi

echo "Installed desktop launcher:"
echo "  $DESKTOP_FILE"
echo "Search your app menu for “System Inspector”, or run:"
echo "  $ROOT/SystemInspector"
