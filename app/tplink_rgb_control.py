#!/usr/bin/env python3
"""
TP-Link Archer TBE550E antenna light control for Linux.

Talks to the mt7925e driver's sysfs node (tplink_led_mode): 0 = off,
1 = breathing, 2 = steady (steady needs the TP-Link Wi-Fi firmware). Colour
and the touch switch are handled by the antenna base itself.
The chosen mode is saved to /var/lib/tplink-led/mode and restored by udev each
time the driver loads.
"""

import glob
import math
import os
import sys

from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QColor, QIcon, QPainter, QRadialGradient, QPen
from PyQt5.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

STATE_FILE = "/var/lib/tplink-led/mode"
ICON = os.path.join(os.path.dirname(os.path.realpath(__file__)), "tplink-rgb.png")
REPAIR_CMD = "sudo ./install.sh  (see README.md in the tplink-tbe550e-linux repo)"

CYAN = QColor("#22D3EE")

# (sysfs value, title, description)
CHOICES = [
    ("auto", "Follow Wi-Fi", "Steady when connected, breathing when not"),
    ("2", "Steady", "Always lit, no breathing"),
    ("1", "Breathing", "Slow pulse"),
    ("0", "Off", "Light stays off"),
]

# driver mode -> what the base shows (TP-Link firmware)
EFFECTS = {0: "off", 1: "breathing", 2: "steady", 3: "steady"}

STYLE = """
QWidget#root { background: #0F141C; }
QLabel { color: #E5E7EB; }
QLabel#title { font-size: 15pt; font-weight: 700; color: #FFFFFF; }
QLabel#subtitle { color: #8B95A5; }
QLabel#status { color: #8B95A5; }
QLabel#error { color: #FCA5A5; }
QLabel#choice { font-weight: 600; color: #F3F4F6; background: transparent; }
QLabel#choicedesc { color: #8B95A5; font-size: 9pt; background: transparent; }
QPushButton {
    background: #171E29; border: 1px solid #263041; border-radius: 10px;
    padding: 0; text-align: left; color: #E5E7EB;
}
QPushButton:hover { border-color: #3B4A60; }
QPushButton:checked { background: #0E2A33; border: 1px solid #22D3EE; }
QPushButton:disabled { color: #4B5563; }
"""


def led_node():
    """Path of the tplink_led_mode node, or None if the driver lacks it."""
    nodes = glob.glob("/sys/bus/pci/devices/*/tplink_led_mode")
    return nodes[0] if nodes else None


def read_state(node):
    """Return (mode, is_auto) as reported by the driver."""
    with open(node) as f:
        text = f.read()
    mode = 0
    for line in text.splitlines():
        if line.startswith("mode:"):
            mode = int(line.split()[1])
    return mode, "[auto]" in text


def wifi_state(node):
    """SSID-less summary of the card's own interface (not other adapters)."""
    for net in glob.glob(os.path.join(os.path.dirname(node), "net", "*")):
        try:
            with open(os.path.join(net, "operstate")) as f:
                up = f.read().strip() == "up"
        except OSError:
            continue
        name = os.path.basename(net)
        return f"{name}: {'connected' if up else 'not connected'}"
    return "Wi-Fi interface not found"


class Preview(QWidget):
    """Antenna glow: dark (off), pulsing (breathing) or constant (steady)."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(150)
        self.effect = "off"
        self.phase = 0.0
        self.timer = QTimer(self, interval=40, timeout=self._tick)
        self.timer.start()

    def set_effect(self, effect):
        self.effect = effect
        self.update()

    def _tick(self):
        self.phase = (self.phase + 0.04) % (2 * math.pi)
        if self.effect == "breathing":
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = 52
        if self.effect != "off":
            level = 1.0
            if self.effect == "breathing":
                level = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self.phase))
            glow = QRadialGradient(cx, cy, r * 1.4)
            c = QColor(CYAN)
            c.setAlphaF(0.55 * level)
            glow.setColorAt(0.45, c)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(cx - r * 1.4, cy - r * 1.4, r * 2.8, r * 2.8))
            ring = QColor(CYAN)
            ring.setAlphaF(0.4 + 0.6 * level)
        else:
            ring = QColor("#2A3342")
        p.setBrush(QColor("#0B0F15"))
        p.setPen(QPen(ring, 5))
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("TBE550E Antenna Light")
        if os.path.exists(ICON):
            self.setWindowIcon(QIcon(ICON))
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel("Antenna Light", objectName="title")
        subtitle = QLabel("TP-Link Archer TBE550E", objectName="subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.preview = Preview()
        layout.addWidget(self.preview)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for value, name, desc in CHOICES:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setMinimumHeight(64)
            inner = QVBoxLayout(btn)
            inner.setContentsMargins(16, 10, 16, 10)
            inner.setSpacing(2)
            for text, obj in ((name, "choice"), (desc, "choicedesc")):
                lbl = QLabel(text, objectName=obj)
                lbl.setWordWrap(True)
                lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
                inner.addWidget(lbl)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, v=value: self.apply(v))
            self.group.addButton(btn)
            self.buttons[value] = btn
            layout.addWidget(btn)

        line = QFrame(frameShape=QFrame.HLine)
        line.setStyleSheet("color: #263041;")
        layout.addWidget(line)

        self.status = QLabel(objectName="status")
        self.error = QLabel(objectName="error")
        self.error.setWordWrap(True)
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        layout.addWidget(self.error)

        self.refresh()
        QTimer(self, interval=2000, timeout=self.refresh).start()

    def show_error(self, text):
        self.error.setText(text)

    def apply(self, value):
        node = led_node()
        if not node:
            self.show_error("The LED driver is not loaded. Fix with:\n" + REPAIR_CMD)
            self.refresh()
            return
        try:
            with open(node, "w") as f:
                f.write(value)
        except PermissionError:
            self.show_error("No permission to change the light. Fix once with:\n" + REPAIR_CMD)
            self.refresh()
            return
        except OSError as e:
            self.show_error(f"The driver rejected the change: {e.strerror}")
            self.refresh()
            return

        try:
            with open(STATE_FILE, "w") as f:
                f.write(value + "\n")
            self.show_error("")
        except OSError:
            self.show_error("Applied, but not saved for next boot. Fix once with:\n" + REPAIR_CMD)
        self.refresh()

    def refresh(self):
        node = led_node()
        if not node:
            for btn in self.buttons.values():
                btn.setEnabled(False)
            self.preview.set_effect("off")
            self.status.setText("LED driver not loaded")
            return
        try:
            mode, is_auto = read_state(node)
        except (OSError, ValueError, IndexError):
            self.status.setText("Could not read the LED state")
            return

        for btn in self.buttons.values():
            btn.setEnabled(True)
        current = "auto" if is_auto else str(mode)
        btn = self.buttons.get(current)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        # pin2 high (modes 1 and 3) is what turns the base light on
        effect = EFFECTS.get(mode, "off")
        self.preview.set_effect(effect)
        self.status.setText(f"Light {effect}  ·  {wifi_state(node)}")


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("TBE550E Antenna Light")
    win = Window()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
