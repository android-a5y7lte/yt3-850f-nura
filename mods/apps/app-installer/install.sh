#!/bin/sh
# Install the App Installer helper on the YT3-850F tablet.
[ "$(hostname)" = "yt3-850f" ] || { echo "STOP: this is not the tablet"; exit 0; }
B="$1"
mkdir -p ~/.local/bin ~/.local/share/applications
wget -q -O ~/.local/bin/apps "$B/apps" || { echo "download failed"; exit 0; }
chmod +x ~/.local/bin/apps
# desktop entry: open it in a terminal. Try common terminals at launch time.
printf '[Desktop Entry]\nType=Application\nName=App Installer\nComment=Find and install apps\nIcon=system-software-install\nCategories=System;\nX-Purism-FormFactor=Workstation;Mobile;\nExec=sh -c "for t in kgx gnome-console gnome-terminal foot alacritty xterm; do command -v $t >/dev/null && exec $t -e %s/.local/bin/apps; done; %s/.local/bin/apps"\n' "$HOME" "$HOME" > ~/.local/share/applications/eco.nura.AppInstaller.desktop
echo "App Installer ready. Open it from the app grid, or run 'apps' in the Console."
