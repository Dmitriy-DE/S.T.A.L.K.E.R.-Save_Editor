#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
DESK="$HOME/.local/share/applications/stalker2-cloud-save-editor.desktop"
mkdir -p "$(dirname "$DESK")"
cat > "$DESK" <<EOD
[Desktop Entry]
Type=Application
Name=STALKER 2 Cloud Save Editor (Experimental)
Comment=Edit STALKER 2 saves locally or in Steam Cloud
Exec=$DIR/run.sh
Terminal=false
Categories=Game;Utility;
EOD
chmod +x "$DESK"
echo "Установлен ярлык: $DESK"
