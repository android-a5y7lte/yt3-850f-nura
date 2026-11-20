#!/bin/sh
# YT3-850F: put all our fixes back on top of the last working image
# (Actions run 44260772922). Run as: sudo sh yt3-restore.sh
set -u
REPO=android-a5y7lte/yt3-850f-nura
REL=https://github.com/$REPO/releases/download
KERNEL=kernel-audio-20261119-2121           # audio + sensors, pre-GPU
GSOFT=gnome-software-arm32fix-20261119-2115
PHOSH=phosh-pinlen-20261120-0820
REF=${1:-main}

[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
W=/tmp/yt3-restore; rm -rf $W; mkdir -p $W; cd $W

step() { echo; echo "=== $*"; }

step "1/7 Block the new systemd 262 (images with it don't boot)"
SDV=$(apk info -v systemd 2>/dev/null | head -1 | sed 's/^systemd-//')
echo "installed systemd: $SDV"
[ -n "$SDV" ] && apk add --no-interactive "systemd=$SDV" >/dev/null && echo "systemd pinned to $SDV"

step "2/7 Download our packages"
wget -q $REL/$KERNEL/linux-postmarketos-qcom-msm8916-6.12.1-r100.apk || echo "kernel download FAILED"
wget -q -O gs.json "https://api.github.com/repos/$REPO/releases/tags/$GSOFT"
for u in $(grep -o '"browser_download_url": *"[^"]*\.apk"' gs.json | cut -d'"' -f4); do wget -q "$u"; done
wget -q -O ph.json "https://api.github.com/repos/$REPO/releases/tags/$PHOSH"
for u in $(grep -o '"browser_download_url": *"[^"]*\.apk"' ph.json | cut -d'"' -f4 | grep -E '/(phosh|libphosh|phosh-schemas|phosh-systemd|phosh-portalsconf|phosh-lang)-99990'); do wget -q "$u"; done
ls -1 *.apk

step "3/7 Install kernel, App Store fix, new Phosh"
apk add --allow-untrusted --force-overwrite --no-interactive ./linux-postmarketos-qcom-msm8916-*.apk && echo "kernel OK"
apk add --allow-untrusted --force-overwrite --no-interactive ./gnome-software*.apk && echo "App Store fix OK"
if apk add --allow-untrusted --force-overwrite --no-interactive ./phosh-99990*.apk ./libphosh-99990*.apk ./phosh-schemas-99990*.apk ./phosh-systemd-99990*.apk ./phosh-portalsconf-99990*.apk ./phosh-lang-99990*.apk; then
  echo "new Phosh OK"
else
  echo "new Phosh needs newer system packages - skipped, the old Phosh stays (tell Claude)"
fi

step "4/7 Our config files (audio UCM, sensors, brightness, haptics, zram, RAM Plus, weather)"
wget -q -O repo.tgz "https://codeload.github.com/$REPO/tar.gz/$REF" || { echo "repo download FAILED"; exit 1; }
tar -xzf repo.tgz
SRC=$(ls -d yt3-850f-nura-*)
for d in common audio; do
  ( cd "$SRC/mods/$d" && tar -cf - --exclude=./etc/NetworkManager . ) | tar -xf - -C / --no-same-owner
done
chown -R root:root /usr/local /etc/systemd /etc/udev /etc/modprobe.d /etc/sysctl.d /etc/environment.d 2>/dev/null
chmod 755 /usr/local/bin/yt3-*
rm -f /etc/modules-load.d/yt3-gpu.conf
mkdir -p /etc/udev/hwdb.d /etc/udev/rules.d
udevadm hwdb --update 2>/dev/null; udevadm control --reload 2>/dev/null

step "5/7 Services"
systemctl daemon-reload
for s in yt3-zram.service yt3-swapfile.service yt3-weather.timer; do systemctl enable "$s" >/dev/null 2>&1 && echo "enabled $s"; done
systemctl mask systemd-oomd.service systemd-oomd.socket >/dev/null 2>&1

step "6/7 Remove LTE / modem stuff (Wi-Fi tablet)"
apk del --no-interactive lpa-gtk 2>/dev/null
systemctl mask ModemManager.service >/dev/null 2>&1 && echo "ModemManager masked"
for u in mmsd-tng.service vvmd.service cellbroadcastd.service; do systemctl --global mask "$u" >/dev/null 2>&1; done

step "7/7 Browser: Firefox out, Epiphany in"
apk add --no-interactive epiphany >/dev/null 2>&1 && echo "Epiphany installed"
apk del --no-interactive firefox-esr firefox >/dev/null 2>&1 && echo "Firefox removed"

echo
echo "Done. Now run (as user, no sudo):"
echo "  gsettings set mobi.phosh.shell.plugins status-icons \"['camera-status-icon', 'netspeed-status-icon', 'weather-status-icon']\""
echo "then: sudo reboot"
