#!/bin/sh
# Installs YT Player into the user's home on the YT3-850F. Run as the normal user.
[ "$(hostname)" = "yt3-850f" ] || { echo "STOP: this is not the tablet, nothing was changed"; exit 0; }
BASE="$1"
core="systemd|pam|shadow|musl|busybox|apk-tools|mesa|llvm|gtk|phosh|phoc|wlroots|linux-"
if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null; then
  up=$(apk add --simulate py3-gobject3 2>&1 | grep -iE "upgrading|purging")
  if echo "$up" | grep -qiE "$core"; then echo "NOT installing py3-gobject3, it would change core packages:"; echo "$up"; exit 0; fi
  sudo apk add py3-gobject3 2>&1 | tail -1
fi
python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk; print('GTK for Python: OK')" || { echo "GTK for Python is still missing"; exit 0; }
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps ~/.config/mpv
wget -q -O ~/.local/bin/yt-player "$BASE/yt-player.py" || { echo "download failed"; exit 0; }
wget -q -O ~/.local/share/icons/hicolor/scalable/apps/eco.nura.YtPlayer.svg "$BASE/eco.nura.YtPlayer.svg"
chmod +x ~/.local/bin/yt-player
[ -f ~/.config/mpv/mpv.conf ] || printf 'fs=yes\nprofile=fast\nytdl-format=bestvideo[height<=360][vcodec^=avc1]+bestaudio/best[height<=360]\n' > ~/.config/mpv/mpv.conf
rm -f ~/.local/share/applications/yt-player.desktop
printf '[Desktop Entry]\nType=Application\nName=YT Player\nComment=Search and play videos\nExec=%s/.local/bin/yt-player\nIcon=eco.nura.YtPlayer\nCategories=AudioVideo;\nStartupNotify=true\nX-Purism-FormFactor=Workstation;Mobile;\n' "$HOME" > ~/.local/share/applications/eco.nura.YtPlayer.desktop
echo "YT Player installed. Open it from the app grid."
