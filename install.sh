#!/usr/bin/env bash
# Install (or remove) the TBE550E antenna light app and udev integration.
# The LED driver patch is built separately; see README.md.
# Usage: sudo ./install.sh [--remove]
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SHARE=/usr/local/share/tplink-rgb-control
BIN=/usr/local/bin/tplink-rgb-control
DESKTOP=/usr/share/applications/tplink-rgb-control.desktop
ICONS=/usr/share/icons/hicolor
RULE=/etc/udev/rules.d/99-tplink-led.rules
RESTORE=/usr/lib/tplink-led/restore
STATE=/var/lib/tplink-led/mode

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi

if [[ "${1:-}" == "--remove" ]]; then
    rm -rf "$SHARE" "$BIN" "$DESKTOP" "$RULE" "${RESTORE%/*}" "${STATE%/*}"
    rm -f "$ICONS/scalable/apps/tplink-rgb-control.svg" "$ICONS/512x512/apps/tplink-rgb-control.png"
    gtk-update-icon-cache -q -t "$ICONS" 2>/dev/null || true
    udevadm control --reload || true
    echo "Removed. The driver patch, if installed, is untouched."
    exit 0
fi

install -Dm755 "$HERE/app/tplink_rgb_control.py" "$SHARE/tplink_rgb_control.py"
install -Dm644 "$HERE/app/tplink-rgb.png" "$SHARE/tplink-rgb.png"
ln -sf "$SHARE/tplink_rgb_control.py" "$BIN"
install -Dm644 "$HERE/app/tplink-rgb-control.desktop" "$DESKTOP"
# Themed icon, so menus, docks and desktop shortcuts all show the same one
install -Dm644 "$HERE/app/icon.svg" "$ICONS/scalable/apps/tplink-rgb-control.svg"
install -Dm644 "$HERE/app/tplink-rgb.png" "$ICONS/512x512/apps/tplink-rgb-control.png"
gtk-update-icon-cache -q -t "$ICONS" 2>/dev/null || true

install -Dm755 "$HERE/udev/tplink-led-restore" "$RESTORE"
install -Dm644 "$HERE/udev/99-tplink-led.rules" "$RULE"
# Saved mode, written by the app as the desktop user
install -d -m 0755 "${STATE%/*}"
[[ -f "$STATE" ]] || echo auto > "$STATE"
chmod 0666 "$STATE"
udevadm control --reload || true

# Apply to an already-loaded driver
found=0
for d in /sys/bus/pci/devices/*; do
    if [[ -e "$d/tplink_led_mode" ]]; then
        "$RESTORE" "$d"
        found=1
    fi
done

echo "Installed. Launch \"TBE550E Antenna Light\" from the app menu or run: tplink-rgb-control"
if [[ $found -eq 0 ]]; then
    echo "Note: the LED driver is not loaded yet. Build and install the patched driver (README.md), then reboot."
fi
