#!/bin/bash
# Work around apk-tools 3.0.10 bug (alpine/apk-tools#11231): installs fail with
# "failed to commit usr/sbin/init / usr/bin/udevadm: No such file or directory".
# Replace pmbootstrap's apk.static with the newest 3.0.x older than 3.0.10.
set -euo pipefail
WORK="$(pmbootstrap config work | tail -1)"
tmp=$(mktemp -d)
found=""
for br in v3.24 v3.23 v3.22; do
  url="https://dl-cdn.alpinelinux.org/alpine/$br/main/x86_64"
  curl -fsSL "$url/APKINDEX.tar.gz" -o "$tmp/idx.tgz" || continue
  ver=$(tar -xzOf "$tmp/idx.tgz" APKINDEX | awk '/^P:/{p=substr($0,3)} /^V:/{if(p=="apk-tools-static") print substr($0,3)}' | head -1)
  echo "$br: apk-tools-static $ver"
  case "$ver" in
    3.0.[0-9]-r*) found="$url/apk-tools-static-$ver.apk"; break ;;
  esac
done
[ -n "$found" ] || { echo "no apk-tools-static < 3.0.10 found"; exit 1; }
curl -fsSL "$found" -o "$tmp/a.apk"
mkdir "$tmp/x" && tar -xzf "$tmp/a.apk" -C "$tmp/x" 2>/dev/null || true
bin=$(find "$tmp/x" -name apk.static -type f | head -1)
[ -n "$bin" ] || { echo "apk.static not in package"; exit 1; }
sudo install -m 755 "$bin" "$WORK/apk.static"
"$WORK/apk.static" --version
