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

from PyQt5.QtCore import QRectF, QSize, Qt, QTimer
from PyQt5.QtGui import (
    QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient,
)
from PyQt5.QtWidgets import (
    QAbstractButton, QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel,
    QVBoxLayout, QWidget,
)

STATE_FILE = "/var/lib/tplink-led/mode"
ICON = os.path.join(os.path.dirname(os.path.realpath(__file__)), "tplink-rgb.png")
REPAIR_CMD = "sudo ./install.sh   (see README.md)"

FONT_FAMILIES = ["Inter", "Ubuntu Sans", "Cantarell", "Noto Sans", "DejaVu Sans"]

# Palette
BG = "#0D1117"
SURFACE = "#161B22"
SURFACE_HOVER = "#1C232C"
BORDER = "#262D37"
TEXT = "#E6EDF3"
MUTED = "#8B949E"
ACCENT = QColor("#22D3EE")
OK = "#3FB950"
ERROR_BG = "#2A1517"
ERROR_TEXT = "#F2A7A7"
NOTE_TEXT = "#7EE0F0"

# (sysfs value, title, description)
CHOICES = [
    ("auto", "Follow Wi-Fi", "Steady when connected, breathing when not"),
    ("2", "Steady", "Always lit"),
    ("1", "Breathing", "Slow pulse"),
    ("0", "Off", "Light stays off"),
]

# driver mode -> what the base shows (TP-Link firmware)
EFFECTS = {0: "Off", 1: "Breathing", 2: "Steady", 3: "Steady"}


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


def wifi_connected(node):
    """Whether the card's own interface (not other adapters) is associated."""
    for net in glob.glob(os.path.join(os.path.dirname(node), "net", "*")):
        try:
            with open(os.path.join(net, "operstate")) as f:
                return f.read().strip() == "up"
        except OSError:
            continue
    return False


def pick_font_family():
    available = set(QFontDatabase().families())
    for family in FONT_FAMILIES:
        if family in available:
            return family
    return QApplication.font().family()


def font(size, weight=QFont.Normal, spacing=None):
    f = QFont(QApplication.font())
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing is not None:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


class Preview(QWidget):
    """Antenna base seen from above: dark (off), pulsing or constant glow."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(170)
        self.effect = "Off"
        self.phase = 0.0
        self.timer = QTimer(self, interval=33, timeout=self._tick)
        self.timer.start()

    def set_effect(self, effect):
        if effect != self.effect:
            self.effect = effect
            self.update()

    def _tick(self):
        self.phase = (self.phase + 0.035) % (2 * math.pi)
        if self.effect == "Breathing":
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = 50

        level = 0.0
        if self.effect == "Steady":
            level = 1.0
        elif self.effect == "Breathing":
            level = 0.2 + 0.8 * (0.5 + 0.5 * math.sin(self.phase))

        if level:
            glow = QRadialGradient(cx, cy, r * 1.7)
            c = QColor(ACCENT)
            c.setAlphaF(0.45 * level)
            glow.setColorAt(0.55, c)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(cx - r * 1.7, cy - r * 1.7, r * 3.4, r * 3.4))

        # base body
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0A0D12"))
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

        # light ring
        ring = QColor(ACCENT) if level else QColor("#2B333E")
        if level:
            ring.setAlphaF(0.35 + 0.65 * level)
        p.setPen(QPen(ring, 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - r + 2, cy - r + 2, 2 * r - 4, 2 * r - 4))

        # touch logo area
        p.setPen(QPen(QColor("#3A4350"), 1.5))
        p.drawEllipse(QRectF(cx - 9, cy - 9, 18, 18))


class ChoiceRow(QAbstractButton):
    """Settings-style radio row: indicator, title and description."""

    HEIGHT = 60

    def __init__(self, title, desc, first, last):
        super().__init__()
        self.title, self.desc = title, desc
        self.first, self.last = first, last
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        # keyboard focus only, so a mouse click doesn't leave a focus ring
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedHeight(self.HEIGHT)
        self.title_font = font(10.5, QFont.DemiBold)
        self.desc_font = font(9.5)

    def sizeHint(self):
        return QSize(380, self.HEIGHT)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())

        # row background, rounded only on the outer corners of the group
        if self.underMouse() and self.isEnabled():
            path = QPainterPath()
            rad = 10
            path.addRoundedRect(rect, rad, rad)
            if not self.first:
                path.addRect(QRectF(rect.left(), rect.top(), rect.width(), rad))
            if not self.last:
                path.addRect(QRectF(rect.left(), rect.bottom() - rad, rect.width(), rad))
            p.fillPath(path.simplified(), QColor(SURFACE_HOVER))

        if not self.last:
            p.setPen(QPen(QColor(BORDER), 1))
            p.drawLine(int(rect.left() + 52), int(rect.bottom()), int(rect.right()), int(rect.bottom()))

        # radio indicator
        cy = rect.center().y()
        ind = QRectF(20, cy - 9, 18, 18)
        enabled = self.isEnabled()
        if self.isChecked():
            p.setPen(QPen(ACCENT, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(ind)
            p.setPen(Qt.NoPen)
            p.setBrush(ACCENT)
            p.drawEllipse(ind.adjusted(4.5, 4.5, -4.5, -4.5))
        else:
            p.setPen(QPen(QColor("#4A5260"), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(ind)

        if self.hasFocus() and self.isEnabled():
            p.setPen(QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 90), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(ind.adjusted(-4, -4, 4, 4))

        # text
        p.setPen(QColor(TEXT if enabled else MUTED))
        p.setFont(self.title_font)
        p.drawText(QRectF(52, 10, rect.width() - 64, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setPen(QColor(MUTED))
        p.setFont(self.desc_font)
        p.drawText(QRectF(52, 31, rect.width() - 64, 20), Qt.AlignLeft | Qt.AlignVCenter, self.desc)


class Pill(QLabel):
    """Small status badge with a coloured dot."""

    def set_state(self, text, color):
        self.setText(f"<span style='color:{color}'>●</span>&nbsp; {text}")


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("TBE550E Antenna Light")
        if os.path.exists(ICON):
            self.setWindowIcon(QIcon(ICON))
        self.setFixedWidth(460)
        self.setStyleSheet(f"""
            QWidget#root {{ background: {BG}; }}
            QLabel {{ color: {TEXT}; background: transparent; }}
            QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
            QLabel#pill {{
                color: {MUTED}; background: {SURFACE}; border: 1px solid {BORDER};
                border-radius: 11px; padding: 3px 10px;
            }}
            QLabel#error {{
                color: {ERROR_TEXT}; background: {ERROR_BG}; border: 1px solid #4A2226;
                border-radius: 8px; padding: 10px 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(0)

        # header
        header = QHBoxLayout()
        header.setSpacing(12)
        if os.path.exists(ICON):
            icon = QLabel()
            dpr = self.devicePixelRatioF()
            pix = QPixmap(ICON).scaled(int(40 * dpr), int(40 * dpr), Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)  # sharp on HiDPI screens
            icon.setPixmap(pix)
            header.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Antenna Light")
        title.setFont(font(15, QFont.DemiBold))
        subtitle = QLabel("TP-Link Archer TBE550E")
        subtitle.setFont(font(9.5))
        subtitle.setStyleSheet(f"color: {MUTED};")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.pill = Pill(objectName="pill")
        self.pill.setFont(font(9, QFont.Medium))
        header.addWidget(self.pill, alignment=Qt.AlignVCenter)
        layout.addLayout(header)
        layout.addSpacing(18)

        # preview card
        preview_card = QFrame(objectName="card")
        pv = QVBoxLayout(preview_card)
        pv.setContentsMargins(16, 8, 16, 14)
        pv.setSpacing(0)
        self.preview = Preview()
        pv.addWidget(self.preview)
        self.effect_lbl = QLabel(alignment=Qt.AlignCenter)
        self.effect_lbl.setFont(font(10.5, QFont.DemiBold))
        self.effect_sub = QLabel(alignment=Qt.AlignCenter)
        self.effect_sub.setFont(font(9))
        self.effect_sub.setStyleSheet(f"color: {MUTED};")
        pv.addWidget(self.effect_lbl)
        pv.addSpacing(2)
        pv.addWidget(self.effect_sub)
        layout.addWidget(preview_card)
        layout.addSpacing(22)

        # options
        section = QLabel("LIGHT EFFECT")
        section.setFont(font(8.5, QFont.DemiBold, spacing=1.2))
        section.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(section)
        layout.addSpacing(8)

        options_card = QFrame(objectName="card")
        ov = QVBoxLayout(options_card)
        ov.setContentsMargins(1, 1, 1, 1)
        ov.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for i, (value, name, desc) in enumerate(CHOICES):
            row = ChoiceRow(name, desc, first=i == 0, last=i == len(CHOICES) - 1)
            row.clicked.connect(lambda _, v=value: self.apply(v))
            self.group.addButton(row)
            self.buttons[value] = row
            ov.addWidget(row)
        layout.addWidget(options_card)
        layout.addSpacing(12)

        hint = QLabel("Colour and on/off are also controlled by touching the logo on "
                      "the antenna base (hold for the next colour).")
        hint.setWordWrap(True)
        hint.setFont(font(9))
        hint.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(hint)
        layout.addSpacing(12)

        self.error = QLabel(objectName="error")
        self.error.setWordWrap(True)
        self.error.setFont(font(9.5))
        self.error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error.hide()
        layout.addWidget(self.error)

        self.note = QLabel()
        self.note.setFont(font(9))
        self.note.setStyleSheet(f"color: {NOTE_TEXT};")
        self.note.hide()
        layout.addWidget(self.note)
        self.note_timer = QTimer(self, singleShot=True, interval=2500, timeout=self.note.hide)

        layout.addStretch()

        self.refresh()
        QTimer(self, interval=2000, timeout=self.refresh).start()

    def show_error(self, text):
        self.error.setText(text)
        self.error.setVisible(bool(text))
        self.adjustSize()

    def show_note(self, text):
        self.note.setText(text)
        self.note.show()
        self.note_timer.start()

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
            self.show_note("✓  Saved. It will be restored at startup.")
        except OSError:
            self.show_error("Applied, but not saved for next boot. Fix once with:\n" + REPAIR_CMD)
        self.refresh()

    def refresh(self):
        node = led_node()
        if not node:
            for btn in self.buttons.values():
                btn.setEnabled(False)
            self.preview.set_effect("Off")
            self.effect_lbl.setText("Driver not loaded")
            self.effect_sub.setText("The TBE550E LED driver was not found")
            self.pill.set_state("Unavailable", MUTED)
            return
        try:
            mode, is_auto = read_state(node)
        except (OSError, ValueError, IndexError):
            self.effect_lbl.setText("Could not read the light state")
            self.effect_sub.setText("")
            return

        for btn in self.buttons.values():
            btn.setEnabled(True)
        current = "auto" if is_auto else str(mode)
        btn = self.buttons.get(current)
        if btn and not btn.isChecked():
            btn.setChecked(True)

        effect = EFFECTS.get(mode, "Off")
        self.preview.set_effect(effect)
        self.effect_lbl.setText(effect)
        self.effect_sub.setText("Following Wi-Fi" if is_auto else "Manual")
        if wifi_connected(node):
            self.pill.set_state("Connected", OK)
        else:
            self.pill.set_state("Not connected", MUTED)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("TBE550E Antenna Light")  # also the X11 WM_CLASS
    app.setDesktopFileName("tplink-rgb-control")  # match the launcher icon
    base = QFont(pick_font_family())
    base.setPointSizeF(10)
    base.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(base)
    win = Window()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
