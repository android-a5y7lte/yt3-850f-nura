#!/bin/sh
# Install Software Lite (F-Droid-style app store) on the YT3-850F tablet.
[ "$(hostname)" = "yt3-850f" ] || { echo "STOP: this is not the tablet"; exit 0; }
B="$1"
core="systemd|pam|shadow|musl|busybox|apk-tools|mesa|llvm|gtk|phosh|phoc|wlroots|linux-"
if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null; then
  up=$(apk add --simulate py3-gobject3 2>&1 | grep -iE "upgrading|purging")
  if echo "$up" | grep -qiE "$core"; then echo "NOT installing py3-gobject3 (would change core packages):"; echo "$up"; exit 0; fi
  sudo apk add py3-gobject3 2>&1 | tail -1
fi
# pkexec is how the app installs without a terminal; note if it is missing
command -v pkexec >/dev/null || echo "note: pkexec not found - installs will fall back to the Console"
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
wget -q -O ~/.local/bin/software-lite "$B/software-lite.py" || { echo "download failed"; exit 0; }
wget -q -O ~/.local/share/icons/hicolor/scalable/apps/eco.nura.SoftwareLite.svg "$B/eco.nura.SoftwareLite.svg"
chmod +x ~/.local/bin/software-lite
printf '[Desktop Entry]\nType=Application\nName=Software Lite\nComment=Find and install apps\nExec=%s/.local/bin/software-lite\nIcon=eco.nura.SoftwareLite\nCategories=System;\nStartupNotify=true\nX-Purism-FormFactor=Workstation;Mobile;\n' "$HOME" > ~/.local/share/applications/eco.nura.SoftwareLite.desktop
echo "Software Lite installed. Open it from the app grid."
