# TP-Link Archer TBE550E antenna light for Linux

Free, open-source control of the light on the TP-Link Archer TBE550E (BE9300
Wi-Fi 7 PCIe, MediaTek MT7927) magnetic antenna base. TP-Link only ships this on
Windows.

- **Driver patch** for the `mt7925e` Wi-Fi driver: drives the antenna light the
  same way the Windows driver does.
- **Desktop app** to choose the light effect, with no root password needed.
- **udev integration** that remembers your choice across reboots.

Not affiliated with TP-Link or MediaTek.

## What you get

| Option | Light |
|---|---|
| Follow Wi-Fi (default) | steady when connected, breathing when not, like Windows |
| Steady | always lit |
| Breathing | slow pulse |
| Off | off |

The colour and the touch switch on the base (tap for on/off, hold about 2 s
for the next colour) are handled by the base itself and work as on Windows.
The computer cannot set the colour.

## Requirements

- TP-Link Archer TBE550E (PCI `14c3:7927`, subsystem `105b:e104`).
- The [mediatek-mt7927-dkms](https://github.com/jetm/mediatek-mt7927-dkms)
  driver, which adds MT7927 support to Linux. This patch applies on top of it.
- **TP-Link's Wi-Fi firmware** (WM build 20250606). That driver extracts it
  from the TP-Link/MediaTek Windows driver package by default. Other firmware
  builds can switch the light on and off but cannot make it steady.
- Python 3 with PyQt5 for the app (`sudo apt install python3-pyqt5`).

## Install

### 1. Driver

Copy the patch into a checkout of mediatek-mt7927-dkms and build its package
as usual. Its build applies every `mt7927-wifi-*.patch` in the top directory.

```
git clone https://github.com/jetm/mediatek-mt7927-dkms.git
cp patches/mt7927-wifi-20-add-tplink-tbe550e-led-support.patch mediatek-mt7927-dkms/
cd mediatek-mt7927-dkms
./build-deb.sh                      # Debian/Ubuntu; Arch: makepkg -si
sudo dpkg -i mediatek-mt7927-dkms_*_all.deb
```

If the patch number 20 is already taken upstream, rename the file to the next
free number.

After a reboot the kernel log should show:

```
mt7925e 0000:05:00.0: TP-Link Archer TBE550E RGB LED initialized (GPIO pin1=53, pin2=54)
```

### 2. App and udev integration

```
sudo ./install.sh
```

Then open **TBE550E Antenna Light** from the app menu, or run
`tplink-rgb-control`. To uninstall: `sudo ./install.sh --remove`.

## Command line

The driver exposes `tplink_led_mode` on the card's PCI device:

```
cat /sys/bus/pci/devices/*/tplink_led_mode
echo 2    > /sys/bus/pci/devices/0000:05:00.0/tplink_led_mode   # steady
echo auto > /sys/bus/pci/devices/0000:05:00.0/tplink_led_mode   # follow Wi-Fi
```

Values: `0` off, `1` breathing, `2` steady, `3` steady (alternate), `auto`.
The app saves your choice in `/var/lib/tplink-led/mode`, and
`/usr/lib/tplink-led/restore` applies it whenever the driver loads.

Module parameters (`mt7925_common`):

| Parameter | Default | Meaning |
|---|---|---|
| `tplink_led` | -1 | -1 auto-detect, 0 disable, 1 force on |
| `tplink_led_pin1`, `tplink_led_pin2` | -1 | override GPIO pins (default 53, 54) |
| `tplink_led_debug` | 0 | log the firmware's reply to each LED command; set at runtime only |

## Troubleshooting

- **App says the driver is not loaded:** check `dmesg | grep TP-Link` for the
  line above, then rebuild and reinstall the patched driver.
- **App says it has no permission:** run `sudo ./install.sh` again, then
  reboot.
- **Light breathes but never goes steady:** check the firmware build with
  `dmesg | grep "WM Firmware"`. It must be `20250606201037`.
- **Light is off:** tap the logo on the antenna base; the base keeps its own
  on/off state.

## How it works

See [docs/reverse-engineering.md](docs/reverse-engineering.md) for the command
format, the GPIO pins, and what each mode does on real hardware.

## Licence

BSD-3-Clause-Clear, the same licence as the mt76 driver files the patch
changes. See [LICENSE](LICENSE).
