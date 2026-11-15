# How the TBE550E antenna light works

Notes from reading the TP-Link/MediaTek Windows driver and testing on real
hardware. Addresses refer to `mtkwecx.sys` from
`DRV_WiFi_MTK_MT7925_MT7927_TP_W11_64_V5603998_20250709R.zip`.

## Which LED scheme the card uses

The Windows driver supports two LED schemes, chosen by the registry value
`OemLedMode` (default 0, no LED control). The INF maps the TBE550E
(`PCI\VEN_14C3&DEV_7927&SUBSYS_E104105B`) to `MTK7927_MODE1.ndi`, which adds
`LedCust2.reg`:

```
[LedCust2.reg]
HKR,,OemLedMode,0,"2"
```

`OemLedMode=2` selects the TP-Link GPIO functions `nicUniCmdTPLinkGpioEnable`
(0x1400d01c4) and `nicUniCmdTPLinkGpioLedCtrl` (0x1400d0594).
`OemLedMode=1` selects a different scheme (`nicUniCmdLedGpio*`) used by
other OEM cards.

## GPIO pins

The LED functions read the pins from two bytes in the adapter structure,
`adapter+0x14669a6` and `adapter+0x14669a7`, and skip LED control if either is 0.
They are filled by copying the 0x11a-byte MT7927 chip profile at `0x14024cab0`
to `adapter+0x1466957`. The chip profile init writes `0x3635` at profile offset
0x4f, so:

- pin1 = 0x35 = 53
- pin2 = 0x36 = 54

## Command

Unified MCU command, CID `0x2a`, set, no response wait (the same send flags
the driver uses for other set commands such as `0x2c`). 12-byte payload:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | pin |
| 1 | 3 | reserved |
| 4 | 2 | TLV tag: 0 = enable pin, 1 = set value |
| 6 | 2 | TLV length = 8 |
| 8 | 1 | value |
| 9 | 3 | reserved |

On init the driver enables both pins (tag 0, value 1), then sets a mode by
sending tag 1 to pin1 and pin2:

| Mode | pin1 value | pin2 value | Windows uses it for |
|---|---|---|---|
| 0 | 1 | 1 | not connected |
| 1 | 1 | 3 | connected |
| 2 | 3 | 1 | MLO / 320 MHz variants |
| 3 | 3 | 3 | MLO / 320 MHz variants |

With `tplink_led_debug=1` the firmware acknowledges every command with an event
whose first byte is `0x2a` followed by zeros.

## What the light does (observed)

With the TP-Link-shipped firmware (WM build 20250606201037):

| Mode | Light |
|---|---|
| 0 | off |
| 1 | breathing |
| 2 | steady |
| 3 | steady |

With a 2026 firmware build (WM 20260414134255) modes 2 and 3 do not give a
steady light (2 = off, 3 = breathing), so steady needs the TP-Link firmware.

The colour, and turning the light on/off by touching the logo on the base
(tap = on/off, hold ~2 s = next colour), are handled by the base itself. The
Windows driver contains no touch or colour handling, and nothing on the host
can set a colour.

TP-Link documents the Windows behaviour as: blinking when not connected,
solid when connected, colour spectrum on multi-band MLO connections, off when
the adapter is disabled
([TP-Link KB 412908](https://community.tp-link.com/en/home/kb/detail/412908)).
A colour-spectrum effect has not been observed from Linux yet.

## Pitfalls found along the way

- Sending LED commands on every BSS change while associating coincided with
  frequent WPA 4-way handshake timeouts (reason 15) on the TP-Link firmware.
  The patch skips redundant updates.
- sysfs-triggered commands must wake the chip first (`mt792x_mutex_acquire`),
  or they can be dropped while it is in power save.
- The driver creates the LED sysfs nodes in its init work, after the PCI
  `bind` uevent, so udev rules must also act on the wlan interface `add` event.
