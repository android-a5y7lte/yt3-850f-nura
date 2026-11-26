#!/bin/sh
# Install Capyloon on the YT3-850F as a second session next to Phosh.
# usage: sh install.sh /path/to/capyloon-yt3-armv7-musl.tar.xz
# Phosh stays the default; nothing of it is changed. Remove with: sh install.sh --remove
[ "$(hostname)" = "yt3-850f" ] || { echo "STOP: this is not the tablet, nothing was changed"; exit 0; }
HERE=$(cd "$(dirname "$0")" && pwd)
if [ "$1" = "--remove" ]; then
  sudo systemctl disable --now b2ghald 2>/dev/null
  sudo rm -rf /opt/capyloon /usr/share/wayland-sessions/capyloon.desktop /etc/systemd/system/b2ghald.service
  echo "Capyloon removed (your ~/.capyloon data was kept)."; exit 0
fi
T="$1"; [ -f "$T" ] || { echo "give the path of capyloon-yt3-armv7-musl.tar.xz"; exit 0; }
need=$(df -m / | awk 'NR==2{print $4}'); [ "$need" -gt 900 ] || { echo "less than 900 MB free on / ($need MB) - not installing"; exit 0; }
PK="sway libselinux gtk+3.0 dbus-glib alsa-lib libpulse libstdc++ pixman libevent font-dejavu"
core="systemd|pam|shadow|musl|busybox|apk-tools|mesa|llvm|phosh|phoc|wlroots|linux-"
up=$(apk add --simulate $PK 2>&1 | grep -iE "upgrading|purging")
if echo "$up" | grep -qiE "$core"; then echo "NOT installing (would change core packages):"; echo "$up"; exit 0; fi
sudo apk add $PK 2>&1 | tail -2
sudo tar -xJf "$T" -C / opt || { echo "unpack failed"; exit 0; }
sudo mkdir -p /opt/capyloon/yt3 /usr/share/wayland-sessions
sudo cp "$HERE/yt3-capyloon-session" "$HERE/yt3-capyloon-start" "$HERE/sway.config" /opt/capyloon/yt3/
sudo chmod +x /opt/capyloon/yt3/yt3-capyloon-session /opt/capyloon/yt3/yt3-capyloon-start
sudo cp "$HERE/capyloon.desktop" /usr/share/wayland-sessions/capyloon.desktop
printf '[Unit]\nDescription=B2G HAL daemon (Capyloon)\n\n[Service]\nExecStart=/opt/capyloon/b2ghald/b2ghald\nRestart=on-failure\n\n[Install]\nWantedBy=multi-user.target\n' | sudo tee /etc/systemd/system/b2ghald.service >/dev/null
sudo systemctl daemon-reload; sudo systemctl enable --now b2ghald 2>&1 | tail -1
echo "--- missing libraries (empty = good) ---"
for b in /opt/capyloon/b2g/b2g /opt/capyloon/b2g/libxul.so /opt/capyloon/api-daemon/api-daemon; do ldd "$b" 2>&1 | grep -i "not found\|No such" | sed "s#^#$b: #"; done
echo "Capyloon installed. Log out of Phosh and pick Capyloon on the login screen."
