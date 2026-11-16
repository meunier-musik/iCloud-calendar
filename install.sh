#!/usr/bin/env bash
# Installation von iCloud Calendar unter Ubuntu (22.10+ / 24.04 LTS empfohlen)
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Systempakete installieren (GTK4 + libadwaita) …"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    python3-gi python3-gi-cairo \
    gir1.2-gtk-4.0 gir1.2-adw-1 \
    libadwaita-1-0 shared-mime-info desktop-file-utils

echo "==> Python-Abhängigkeiten installieren …"
if [ -d .venv ]; then
    source .venv/bin/activate
else
    python3 -m venv --system-site-packages .venv
    source .venv/bin/activate
fi
pip install -r requirements.txt

echo "==> App installieren …"
pip install --no-deps -e .

ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_DIR" "$DESKTOP_DIR"
cp data/icloud-calendar.desktop "$DESKTOP_DIR/"
sed -i "s|^Exec=.*|Exec=$PWD/.venv/bin/icloud-calendar|" "$DESKTOP_DIR/icloud-calendar.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo
echo "Fertig! Starten mit:  .venv/bin/icloud-calendar"
echo "Oder über das Anwendungsmenü („Kalender“)."
