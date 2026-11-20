#!/bin/bash
# Workaround for alpine/apk-tools#11231: a fresh install of systemd 262 fails to
# commit usr/sbin/init and usr/bin/udevadm, but reinstalling (upgrade path) works.
# Usage: preinstall-systemd.sh <chroot dir name> <arch>   e.g. buildroot_armv7 armv7
set -uo pipefail
WORK="$(pmbootstrap config work | tail -1)"
ROOT="$WORK/chroot_$1"; ARCH="$2"
APK=(sudo "$WORK/apk.static" --no-progress --root "$ROOT" --arch "$ARCH"
     --cache-dir "$WORK/cache_apk_$ARCH"
     --repository "$WORK/packages/systemd-edge" --repository "$WORK/packages/edge")
echo "== first install (expected to report commit errors)"
"${APK[@]}" add --no-interactive systemd systemd-udevd 2>&1 | grep -E "ERROR|OK:" || true
echo "== repair via reinstall"
"${APK[@]}" fix --reinstall --no-interactive systemd systemd-udevd 2>&1 | grep -E "ERROR|OK:"
"${APK[@]}" fix --reinstall --no-interactive systemd systemd-udevd >/dev/null 2>&1 && echo "systemd repaired OK" || { echo "repair still failing"; exit 1; }
sudo ls -la "$ROOT/usr/bin/init" "$ROOT/usr/bin/udevadm"
