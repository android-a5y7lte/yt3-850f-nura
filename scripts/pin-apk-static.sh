#!/bin/bash
# Work around alpine/apk-tools#11231 (seen with systemd 262 on merged /usr):
#   ERROR: systemd-262.2-r0: failed to commit usr/sbin/init: No such file or directory
#   ERROR: systemd-udevd-262.2-r0: failed to commit usr/bin/udevadm: No such file or directory
# Everything else installs fine. Wrap pmbootstrap's apk.static: when those are the
# only errors, put the two files in place ourselves and report success.
set -euo pipefail
WORK="$(pmbootstrap config work | tail -1)"
[ -f "$WORK/apk.static.real" ] || sudo mv "$WORK/apk.static" "$WORK/apk.static.real"
sudo tee "$WORK/apk.static" >/dev/null <<'WRAP'
#!/bin/bash
real="$(dirname "$(readlink -f "$0")")/apk.static.real"
errf=$(mktemp)
echo "$(date +%T) $*" >> /tmp/yt3-apk-wrapper.log
# apk may print its errors on stdout, so watch both streams
"$real" "$@" 2>&1 | tee "$errf"; rc=${PIPESTATUS[0]}
if [ $rc -ne 0 ] && grep -q "failed to commit usr/\(s\)\?bin/\(init\|udevadm\)" "$errf" \
   && ! grep "ERROR" "$errf" | grep -qv "failed to commit usr/\(s\)\?bin/\(init\|udevadm\)"; then
  root=/; cache=""
  prev=""
  for a in "$@"; do
    case "$prev" in --root) root="$a";; --cache-dir) cache="$a";; esac
    prev="$a"
  done
  echo "yt3 apk wrapper: repairing init/udevadm in $root" >&2
  if [ ! -e "$root/usr/bin/init" ] && [ -e "$root/usr/lib/systemd/systemd" ]; then
    ln -sf ../lib/systemd/systemd "$root/usr/bin/init"
  fi
  if [ ! -e "$root/usr/bin/udevadm" ]; then
    pkg=$(ls -t "$cache"/systemd-udevd-[0-9]*.apk 2>/dev/null | head -1)
    if [ -n "$pkg" ]; then
      t=$(mktemp -d); tar -xzf "$pkg" -C "$t" 2>/dev/null || true
      src=$(find "$t" -path "*bin/udevadm" -type f | head -1)
      [ -n "$src" ] && install -m 755 "$src" "$root/usr/bin/udevadm"
      rm -rf "$t"
    fi
  fi
  ls -la "$root/usr/bin/init" "$root/usr/bin/udevadm" >&2 || true
  rc=0
fi
echo "  rc=$rc errors: $(grep -c ERROR "$errf")" >> /tmp/yt3-apk-wrapper.log
grep ERROR "$errf" >> /tmp/yt3-apk-wrapper.log || true
rm -f "$errf"
exit $rc
WRAP
sudo chmod 755 "$WORK/apk.static"
"$WORK/apk.static" --version
