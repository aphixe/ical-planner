# iCal-ish Python Day Planner (PySide6) — v3.9
# New in v3.9
# - Focus/center on current date & time at launch.
# - "Go to current time" button above mini calendar.
# - Mini calendar: small dot on "today" (top-right), colored ring on selected day.
# - Preferences dialog now grouped in left-side tabs; added Mini Calendar colors.
# - Keeps previous features: zoom, snap, zebra grid, 12/24h, minute-synced now line,
#   image attach/replace/cleanup, daily rules, weekly duplicates, locking, overlap prevention.

from __future__ import annotations
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field, replace
from copy import deepcopy
from pathlib import Path
import csv
import configparser
import uuid
import sys
import subprocess
import json

from PySide6.QtCore import Qt, QRect, QRectF, QSize, QDate, QTime, QTimer, QPoint, QDateTime, QUrl
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QAction, QFontMetrics, QPixmap, QImage,
    QShortcut, QKeySequence
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QScrollArea, QCalendarWidget,
    QDockWidget, QToolBar, QComboBox, QSlider, QLabel, QMenu, QDialog,
    QDialogButtonBox, QGridLayout, QPushButton, QMessageBox, QSpinBox, QCheckBox,
    QHBoxLayout, QLineEdit, QTimeEdit, QGroupBox, QFileDialog, QTabWidget,
    QToolButton, QRubberBand, QListWidget, QListWidgetItem
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

APP_DIR = Path(__file__).resolve().parent
PREF_PATH = APP_DIR / "pref.ini"
DATA_PATH = APP_DIR / "data.csv"
RULES_PATH = APP_DIR / "rules.csv"
UPLOAD_DIR = APP_DIR / "uploads"
HISTORY_PATH = APP_DIR / "history.csv"

BASE_PX_PER_MIN = 3.0  # "100%" equals old 300% zoom density


def ensure_uploads():
    try:
        UPLOAD_DIR.mkdir(exist_ok=True)
    except Exception:
        pass


def qcolor_to_hex(c: QColor) -> str:
    return c.name(QColor.NameFormat.HexRgb)


def hex_to_qcolor(s: str, fallback: str = "#000000") -> QColor:
    c = QColor(s)
    if not c.isValid():
        c = QColor(fallback)
    return c


def save_png_square_256(src_path: Path) -> Optional[str]:
    """Load an image, center-crop to square, downscale to 256x256, save to uploads/, return relative path."""
    try:
        img = QImage(str(src_path))
        if img.isNull():
            return None
        w, h = img.width(), img.height()
        side = min(w, h)
        x = (w - side) // 2
        y = (h - side) // 2
        cropped = img.copy(x, y, side, side)
        scaled = cropped.scaled(256, 256, Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        UPLOAD_DIR.mkdir(exist_ok=True)
        name = f"{uuid.uuid4().hex}.png"
        out_path = UPLOAD_DIR / name
        scaled.save(str(out_path), "PNG")
        return str(Path("uploads") / name)
    except Exception:
        return None


@dataclass
class Prefs:
    # Timeline / grid
    day_background: QColor = field(default_factory=lambda: QColor("#F8F9FB"))
    hour_line: QColor = field(default_factory=lambda: QColor("#C8CDD4"))
    halfhour_line: QColor = field(default_factory=lambda: QColor("#DCE0E6"))
    gutter_text: QColor = field(default_factory=lambda: QColor("#787C82"))
    gutter_minor_text: QColor = field(default_factory=lambda: QColor("#9AA0A6"))
    snap_text: QColor = field(default_factory=lambda: QColor("#82878C"))
    # Zebra hours
    zebra_even: QColor = field(default_factory=lambda: QColor("#FFFFFF"))
    zebra_odd:  QColor = field(default_factory=lambda: QColor("#F3F5FA"))
    # Now line + box
    now_line: QColor = field(default_factory=lambda: QColor("#FF3B30"))
    now_box_fill: QColor = field(default_factory=lambda: QColor("#FFF2F2"))
    now_box_text: QColor = field(default_factory=lambda: QColor("#FF3B30"))
    now_box_border: QColor = field(default_factory=lambda: QColor("#FF3B30"))
    # Events
    event_default: QColor = field(default_factory=lambda: QColor("#4879C5"))
    event_border:  QColor = field(default_factory=lambda: QColor("#1E1E1E"))
    header_text:  QColor = field(default_factory=lambda: QColor("#FFFFFF"))
    upcoming_bar: QColor = field(default_factory=lambda: QColor("#FF9F0A"))
    upcoming_bar_bg: QColor = field(default_factory=lambda: QColor("#FFF7E6"))
    upcoming_bar_bg_opacity: int = 40  # percent 0-100
    # Mini calendar
    cal_today_dot: QColor = field(default_factory=lambda: QColor("#34C759"))   # Apple green
    cal_selected_ring: QColor = field(default_factory=lambda: QColor("#007AFF"))  # iOS blue
    # UI options
    time_24h: bool = True
    zoom_percent: int = 100
    time_snap_enabled: bool = True
    time_size_minutes: int = 30
    smart_scale_enabled: bool = False
    magnetic_mode: bool = False
    notify_sound_path: str = ""

    def as_color_dict(self) -> Dict[str, str]:
        return {
            "day_background": qcolor_to_hex(self.day_background),
            "hour_line": qcolor_to_hex(self.hour_line),
            "halfhour_line": qcolor_to_hex(self.halfhour_line),
            "gutter_text": qcolor_to_hex(self.gutter_text),
            "gutter_minor_text": qcolor_to_hex(self.gutter_minor_text),
            "snap_text": qcolor_to_hex(self.snap_text),
            "zebra_even": qcolor_to_hex(self.zebra_even),
            "zebra_odd":  qcolor_to_hex(self.zebra_odd),
            "now_line": qcolor_to_hex(self.now_line),
            "now_box_fill": qcolor_to_hex(self.now_box_fill),
            "now_box_text": qcolor_to_hex(self.now_box_text),
            "now_box_border": qcolor_to_hex(self.now_box_border),
            "event_default": qcolor_to_hex(self.event_default),
            "event_border":  qcolor_to_hex(self.event_border),
            "header_text":   qcolor_to_hex(self.header_text),
            "upcoming_bar":  qcolor_to_hex(self.upcoming_bar),
            "upcoming_bar_bg": qcolor_to_hex(self.upcoming_bar_bg),
            "cal_today_dot": qcolor_to_hex(self.cal_today_dot),
            "cal_selected_ring": qcolor_to_hex(self.cal_selected_ring),
        }

    def as_ui_dict(self) -> Dict[str, str]:
        return {
            "time_24h": "1" if self.time_24h else "0",
            "zoom_percent": str(int(self.zoom_percent)),
            "upcoming_bar_bg_opacity": str(int(self.upcoming_bar_bg_opacity)),
            "notify_sound_path": self.notify_sound_path,
            "time_snap_enabled": "1" if self.time_snap_enabled else "0",
            "time_size_minutes": str(int(self.time_size_minutes)),
            "smart_scale_enabled": "1" if self.smart_scale_enabled else "0",
            "magnetic_mode": "1" if self.magnetic_mode else "0",
        }

    @classmethod
    def from_config(cls, path: Path) -> "Prefs":
        cfg = configparser.ConfigParser()
        if not path.exists():
            p = cls()
            p.save(path)
            return p
        cfg.read(path)
        sec = cfg["colors"] if "colors" in cfg else {}
        ui  = cfg["ui"]     if "ui"     in cfg else {}

        def get_color(name: str, default_hex: str) -> QColor:
            return hex_to_qcolor(sec.get(name, default_hex), default_hex)

        def get_bool(key: str, default: bool) -> bool:
            raw = ui.get(key, "1" if default else "0").strip().lower()
            return raw in ("1", "true", "yes", "on")

        def get_int(key: str, default: int) -> int:
            try:
                return int(ui.get(key, str(default)))
            except Exception:
                return default
        def get_str(key: str, default: str) -> str:
            return ui.get(key, default)

        size_minutes = get_int("time_size_minutes", -1)
        if size_minutes <= 0:
            size_minutes = get_int("time_snap_minutes", 30)

        return cls(
            day_background=get_color("day_background", "#F8F9FB"),
            hour_line=get_color("hour_line", "#C8CDD4"),
            halfhour_line=get_color("halfhour_line", "#DCE0E6"),
            gutter_text=get_color("gutter_text", "#787C82"),
            gutter_minor_text=get_color("gutter_minor_text", "#9AA0A6"),
            snap_text=get_color("snap_text", "#82878C"),
            zebra_even=get_color("zebra_even", "#FFFFFF"),
            zebra_odd=get_color("zebra_odd",  "#F3F5FA"),
            now_line=get_color("now_line", "#FF3B30"),
            now_box_fill=get_color("now_box_fill", "#FFF2F2"),
            now_box_text=get_color("now_box_text", "#FF3B30"),
            now_box_border=get_color("now_box_border", "#FF3B30"),
            event_default=get_color("event_default", "#4879C5"),
            event_border=get_color("event_border", "#1E1E1E"),
            header_text=get_color("header_text", "#FFFFFF"),
            upcoming_bar=get_color("upcoming_bar", "#FF9F0A"),
            upcoming_bar_bg=get_color("upcoming_bar_bg", "#FFF7E6"),
            cal_today_dot=get_color("cal_today_dot", "#34C759"),
            cal_selected_ring=get_color("cal_selected_ring", "#007AFF"),
            time_24h=get_bool("time_24h", True),
            zoom_percent=max(50, min(500, get_int("zoom_percent", 100))),
            upcoming_bar_bg_opacity=max(0, min(100, get_int("upcoming_bar_bg_opacity", 40))),
            notify_sound_path=get_str("notify_sound_path", "").strip(),
            time_snap_enabled=get_bool("time_snap_enabled", True),
            time_size_minutes=max(1, size_minutes),
            smart_scale_enabled=get_bool("smart_scale_enabled", False),
            magnetic_mode=get_bool("magnetic_mode", False),
        )

    def save(self, path: Path):
        cfg = configparser.ConfigParser()
        cfg["colors"] = self.as_color_dict()
        cfg["ui"] = self.as_ui_dict()
        with path.open("w", encoding="utf-8") as f:
            cfg.write(f)


class PreferencesDialog(QDialog):
    # Grouped color keys -> (key, label)
    GROUPS = {
        "Timeline": [
            ("day_background", "Day Background"),
            ("hour_line", "Hour Grid Line"),
            ("halfhour_line", "Minor Grid Line"),
            ("gutter_text", "Gutter Hour Text"),
            ("gutter_minor_text", "Gutter Minor Text"),
            ("snap_text", "Snap/Info Text"),
            ("zebra_even", "Zebra Hour Even"),
            ("zebra_odd", "Zebra Hour Odd"),
        ],
        "Now Line & Box": [
            ("now_line", "Now Line"),
            ("now_box_fill", "Now Box Fill"),
            ("now_box_text", "Now Box Text"),
            ("now_box_border", "Now Box Border"),
        ],
        "Upcoming Reminder": [
            ("upcoming_bar", "Line/Text Color"),
            ("upcoming_bar_bg", "Bubble Background"),
        ],
        "Events": [
            ("event_default", "Default Event Fill"),
            ("event_border", "Event Border"),
            ("header_text", "Event Header Text"),
        ],
        "Mini Calendar": [
            ("cal_today_dot", "Today Dot"),
            ("cal_selected_ring", "Selected Day Ring"),
        ],
    }

    def __init__(self, prefs: Prefs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self._orig_prefs = prefs if prefs is not None else Prefs()
        self._time_24h = prefs.time_24h
        self._zoom_percent = prefs.zoom_percent
        self._upcoming_bg_opacity = int(getattr(prefs, "upcoming_bar_bg_opacity", 40))
        self._notify_sound_path = getattr(prefs, "notify_sound_path", "").strip()
        self._values = prefs.as_color_dict()

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.btns: Dict[str, QPushButton] = {}
        self.swatches: Dict[str, QLabel] = {}
        self.upcoming_opacity_spin: Optional[QSpinBox] = None
        self.notify_sound_edit: Optional[QLineEdit] = None
        self.notify_test_btn: Optional[QPushButton] = None

        for tab_name, items in self.GROUPS.items():
            page = QWidget()
            grid = QGridLayout(page)
            for row, (key, label) in enumerate(items):
                grid.addWidget(QLabel(label + ":"), row, 0)
                swatch = QLabel()
                swatch.setFixedSize(22, 22)
                swatch.setStyleSheet(f"border:1px solid #888; background:{self._values[key]};")
                self.swatches[key] = swatch
                grid.addWidget(swatch, row, 1)
                b = QPushButton(self._values[key])
                b.clicked.connect(lambda _, k=key: self.pick(k))
                self.btns[key] = b
                grid.addWidget(b, row, 2)
            if tab_name == "Upcoming Reminder":
                row = len(items)
                grid.addWidget(QLabel("Bubble Opacity (%):"), row, 0)
                spin = QSpinBox()
                spin.setRange(0, 100)
                spin.setValue(self._upcoming_bg_opacity)
                grid.addWidget(spin, row, 1, 1, 2)
                self.upcoming_opacity_spin = spin
                row += 1
                grid.addWidget(QLabel("Notification Sound (MP3):"), row, 0)
                container = QWidget()
                cont_layout = QHBoxLayout(container)
                cont_layout.setContentsMargins(0, 0, 0, 0)
                sound_edit = QLineEdit(self._notify_sound_path)
                sound_edit.setReadOnly(True)
                browse_btn = QPushButton("Choose MP3…")
                browse_btn.clicked.connect(self.pick_notify_sound)
                clear_btn = QPushButton("Clear")
                clear_btn.clicked.connect(self.clear_notify_sound)
                cont_layout.addWidget(sound_edit, 1)
                cont_layout.addWidget(browse_btn)
                cont_layout.addWidget(clear_btn)
                self.notify_sound_edit = sound_edit
                grid.addWidget(container, row, 1, 1, 2)
                row += 1
                test_btn = QPushButton("🔊 Test notification")
                test_btn.clicked.connect(self.test_notification)
                self.notify_test_btn = test_btn
                grid.addWidget(test_btn, row, 1, 1, 2)
            self.tabs.addTab(page, tab_name)

        layout.addWidget(self.tabs)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def pick(self, key: str):
        start = hex_to_qcolor(self._values[key], self._values[key])
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(start, self, f"Pick color for {key}")
        if c.isValid():
            hexv = qcolor_to_hex(c)
            self._values[key] = hexv
            self.btns[key].setText(hexv)
            self.swatches[key].setStyleSheet(f"border:1px solid #888; background:{hexv};")

    def pick_notify_sound(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Choose MP3", str(APP_DIR), "Audio Files (*.mp3)")
        if not fp:
            return
        self._notify_sound_path = fp.strip()
        if self.notify_sound_edit is not None:
            self.notify_sound_edit.setText(self._notify_sound_path)

    def clear_notify_sound(self):
        self._notify_sound_path = ""
        if self.notify_sound_edit is not None:
            self.notify_sound_edit.setText("")

    def test_notification(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, "trigger_test_notification"):
            parent.trigger_test_notification(self._notify_sound_path)
        else:
            QMessageBox.information(self, "Notification Test", "Unable to trigger notification from here.")

    def result_prefs(self) -> Prefs:
        g = lambda k, d: hex_to_qcolor(self._values.get(k, d), d)
        opacity = self._upcoming_bg_opacity
        if self.upcoming_opacity_spin is not None:
            opacity = int(self.upcoming_opacity_spin.value())
        opacity = max(0, min(100, opacity))
        new_prefs = replace(self._orig_prefs)
        new_prefs.day_background = g("day_background", "#F8F9FB")
        new_prefs.hour_line = g("hour_line", "#C8CDD4")
        new_prefs.halfhour_line = g("halfhour_line", "#DCE0E6")
        new_prefs.gutter_text = g("gutter_text", "#787C82")
        new_prefs.gutter_minor_text = g("gutter_minor_text", "#9AA0A6")
        new_prefs.snap_text = g("snap_text", "#82878C")
        new_prefs.zebra_even = g("zebra_even", "#FFFFFF")
        new_prefs.zebra_odd = g("zebra_odd",  "#F3F5FA")
        new_prefs.now_line = g("now_line", "#FF3B30")
        new_prefs.now_box_fill = g("now_box_fill", "#FFF2F2")
        new_prefs.now_box_text = g("now_box_text", "#FF3B30")
        new_prefs.now_box_border = g("now_box_border", "#FF3B30")
        new_prefs.event_default = g("event_default", "#4879C5")
        new_prefs.event_border = g("event_border", "#1E1E1E")
        new_prefs.header_text = g("header_text", "#FFFFFF")
        new_prefs.upcoming_bar = g("upcoming_bar", "#FF9F0A")
        new_prefs.upcoming_bar_bg = g("upcoming_bar_bg", "#FFF7E6")
        new_prefs.upcoming_bar_bg_opacity = opacity
        new_prefs.cal_today_dot = g("cal_today_dot", "#34C759")
        new_prefs.cal_selected_ring = g("cal_selected_ring", "#007AFF")
        new_prefs.time_24h = self._time_24h
        new_prefs.zoom_percent = self._zoom_percent
        new_prefs.notify_sound_path = self._notify_sound_path
        return new_prefs


class HistoryDialog(QDialog):
    def __init__(self, entries: List[dict], on_clear=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("History")
        self.setModal(True)
        self._entries = entries or []
        self.selected_index: Optional[int] = None
        self._on_clear = on_clear

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select an action to restore:"))

        self.list_widget = QListWidget()
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.list_widget)

        self._rebuild_list()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.restore_btn = buttons.addButton("Restore", QDialogButtonBox.ButtonRole.AcceptRole)
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._accept_selection)
        self.clear_btn = buttons.addButton("Clear", QDialogButtonBox.ButtonRole.ActionRole)
        self.clear_btn.clicked.connect(self._handle_clear)
        self.clear_btn.setEnabled(bool(self._entries))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _rebuild_list(self):
        self.list_widget.clear()
        for idx, entry in enumerate(reversed(self._entries)):
            real_index = entry.get("_history_index")
            if real_index is None:
                real_index = len(self._entries) - 1 - idx
            timestamp = entry.get("timestamp") or ""
            action = entry.get("action") or "Change"
            date = entry.get("date") or ""
            text = f"{timestamp} — {action}"
            if date:
                text += f" ({date})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, real_index)
            self.list_widget.addItem(item)
        self.restore_btn = getattr(self, "restore_btn", None)
        if self.restore_btn is not None:
            self.restore_btn.setEnabled(False)

    def _on_selection_changed(self):
        has_selection = bool(self.list_widget.selectedItems())
        self.restore_btn.setEnabled(has_selection)

    def _accept_selection(self):
        items = self.list_widget.selectedItems()
        if not items:
            return
        item = items[0]
        self.selected_index = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _handle_clear(self):
        if self._on_clear is None:
            return
        new_entries = self._on_clear() or []
        self._entries = new_entries
        self._rebuild_list()
        self.clear_btn.setEnabled(bool(self._entries))


class WeeklyPatternPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        grid = QGridLayout()
        self.checks: Dict[int, QCheckBox] = {}
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, name in enumerate(names, start=1):
            cb = QCheckBox(name)
            self.checks[i] = cb
            grid.addWidget(cb, 0 if i <= 4 else 1, (i - 1) % 4)
        v.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(QLabel("Weeks forward:"))
        self.spin = QSpinBox(); self.spin.setRange(1, 52); self.spin.setValue(4)
        row.addWidget(self.spin); row.addStretch(1)
        v.addLayout(row)
    def weekdays(self) -> List[int]: return [d for d, cb in self.checks.items() if cb.isChecked()]
    def weeks(self) -> int: return int(self.spin.value())


class EventEditDialog(QDialog):
    """Edit event/rule; supports weekly duplicates, convert to daily rule, notifications, and image attach/clear."""
    def __init__(self, title: str, color_hex: str, start_min: int, end_min: int, is_rule: bool,
                 time_24h: bool, image_rel: Optional[str], notify_offset: int, tag: str = "",
                 existing_tags: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Event")
        self.setModal(True)
        self._is_rule = is_rule
        self._time_24h = time_24h
        self._color_hex = color_hex
        self._image_rel = image_rel  # "uploads/uuid.png" or None
        self._notify_offset = max(0, int(notify_offset or 0))
        cleaned_tags: List[str] = []
        if existing_tags:
            seen: Set[str] = set()
            for t in existing_tags:
                t_clean = (t or "").strip()
                if not t_clean or t_clean in seen:
                    continue
                seen.add(t_clean)
                cleaned_tags.append(t_clean)
        self._existing_tags = sorted(cleaned_tags, key=lambda s: s.lower())
        self._tag_placeholder = "Choose existing tag…"
        self._tag_combo: Optional[QComboBox] = None

        v = QVBoxLayout(self)

        # Title
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit(title)
        title_row.addWidget(self.title_edit)
        v.addLayout(title_row)

        # Tag field (optional)
        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Tag:"))
        self.tag_edit = QLineEdit(tag or "")
        self.tag_edit.setPlaceholderText("Optional label")
        tag_row.addWidget(self.tag_edit)
        v.addLayout(tag_row)

        # Existing tags dropdown
        tag_combo_row = QHBoxLayout()
        tag_combo_row.addWidget(QLabel("Existing tags:"))
        self._tag_combo = QComboBox()
        if self._existing_tags:
            self._tag_combo.addItem(self._tag_placeholder)
            for t in self._existing_tags:
                self._tag_combo.addItem(t)
            self._tag_combo.currentTextChanged.connect(self._apply_tag_selection)
        else:
            self._tag_combo.addItem("No tags yet")
            self._tag_combo.setEnabled(False)
        tag_combo_row.addWidget(self._tag_combo)
        v.addLayout(tag_combo_row)

        # Color
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        from PySide6.QtWidgets import QColorDialog
        self.color_btn = QPushButton("Pick Color…")
        self.color_btn.clicked.connect(self.pick_color)
        self._update_color_button()
        color_row.addWidget(self.color_btn)
        v.addLayout(color_row)

        # Time pickers
        time_box = QGroupBox("Time")
        tgrid = QGridLayout(time_box)
        self.start_edit = QTimeEdit(); self.end_edit = QTimeEdit()
        fmt = "HH:mm" if time_24h else "h:mm AP"
        self.start_edit.setDisplayFormat(fmt); self.end_edit.setDisplayFormat(fmt)
        self.start_edit.setTime(QTime(start_min // 60, start_min % 60))
        self.end_edit.setTime(QTime(end_min // 60, end_min % 60))
        tgrid.addWidget(QLabel("Start:"), 0, 0); tgrid.addWidget(self.start_edit, 0, 1)
        tgrid.addWidget(QLabel("End:"),   1, 0); tgrid.addWidget(self.end_edit,   1, 1)
        v.addWidget(time_box)

        # Notification (macOS only for now)
        notify_row = QHBoxLayout()
        notify_row.addWidget(QLabel("Notify:"))
        self.notify_combo = QComboBox()
        self.notify_options: List[tuple[str, int]] = [
            ("None", 0),
            ("5 minutes before", 5),
            ("15 minutes before", 15),
            ("20 minutes before", 20),
            ("30 minutes before", 30),
            ("45 minutes before", 45),
            ("60 minutes before", 60),
        ]
        for label, minutes in self.notify_options:
            self.notify_combo.addItem(label, minutes)
        matched_index = 0
        for idx in range(self.notify_combo.count()):
            if int(self.notify_combo.itemData(idx)) == self._notify_offset:
                matched_index = idx
                break
        self.notify_combo.setCurrentIndex(matched_index)
        if sys.platform != "darwin":
            self.notify_combo.setEnabled(False)
            self.notify_combo.setToolTip("macOS notifications only")
        notify_row.addWidget(self.notify_combo, 1)
        notify_row.addStretch(1)
        v.addLayout(notify_row)

        # Image attach/preview
        img_box = QGroupBox("Image (PNG, square recommended)")
        igrid = QGridLayout(img_box)
        self.img_preview = QLabel(); self.img_preview.setFixedSize(96, 96)
        self.img_preview.setStyleSheet("background:#eee; border:1px solid #aaa;")
        self._refresh_preview()
        btn_attach = QPushButton("Attach PNG…"); btn_attach.clicked.connect(self.attach_png)
        btn_clear  = QPushButton("Clear image"); btn_clear.clicked.connect(self.clear_image)
        igrid.addWidget(self.img_preview, 0, 0, 2, 1)
        igrid.addWidget(btn_attach, 0, 1)
        igrid.addWidget(btn_clear,  1, 1)
        v.addWidget(img_box)

        # Weekly duplicates
        weekly_box = QGroupBox("Weekly duplicates (optional)")
        self.weekly_panel = WeeklyPatternPanel()
        wb = QVBoxLayout(weekly_box); wb.addWidget(self.weekly_panel)
        v.addWidget(weekly_box)

        # Convert to daily rule
        self.make_daily_chk = QCheckBox("Convert to Daily (indefinite)")
        if is_rule:
            self.make_daily_chk.setEnabled(False); self.make_daily_chk.setToolTip("Already a daily rule")
        v.addWidget(self.make_daily_chk)

        # Buttons
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept); box.rejected.connect(self.reject)
        v.addWidget(box)

    def _refresh_preview(self):
        if self._image_rel:
            p = QPixmap(str(APP_DIR / self._image_rel))
            if not p.isNull():
                self.img_preview.setPixmap(p.scaled(self.img_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                return
        self.img_preview.setPixmap(QPixmap())

    def pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        start = hex_to_qcolor(self._color_hex, self._color_hex)
        c = QColorDialog.getColor(start, self, "Pick a color")
        if c.isValid():
            self._color_hex = qcolor_to_hex(c)
            self._update_color_button()

    def _apply_tag_selection(self, text: str):
        if not text or text == self._tag_placeholder:
            return
        self.tag_edit.setText(text)
        if self._tag_combo is not None:
            self._tag_combo.blockSignals(True)
            self._tag_combo.setCurrentIndex(0)
            self._tag_combo.blockSignals(False)

    def _update_color_button(self):
        color = hex_to_qcolor(self._color_hex, "#4879C5")
        if not color.isValid():
            color = QColor("#4879C5")
        r, g, b = color.red(), color.green(), color.blue()
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        text_color = "#000000" if luminance > 186 else "#FFFFFF"
        self.color_btn.setStyleSheet(
            f"background-color: {qcolor_to_hex(color)}; color: {text_color}; padding:6px;"
        )

    def attach_png(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Choose PNG", str(APP_DIR), "PNG Images (*.png)")
        if not fp: return
        rel = save_png_square_256(Path(fp))
        if rel:
            self._image_rel = rel
            self._refresh_preview()
        else:
            QMessageBox.warning(self, "Image Error", "Failed to load/convert that PNG.")

    def clear_image(self):
        self._image_rel = None
        self._refresh_preview()

    def result_payload(self) -> dict:
        s = self.start_edit.time(); e = self.end_edit.time()
        start_min = s.hour() * 60 + s.minute()
        end_min = e.hour() * 60 + e.minute()
        if end_min <= start_min:
            end_min = min(24 * 60, start_min + 5)
        return {
            "title": self.title_edit.text().strip(),
            "tag": self.tag_edit.text().strip(),
            "color": self._color_hex,
            "start_min": start_min,
            "end_min": end_min,
            "convert_daily": self.make_daily_chk.isChecked() and (not self._is_rule),
            "weekly_days": self.weekly_panel.weekdays(),
            "weekly_weeks": self.weekly_panel.weeks(),
            "image": self._image_rel,
            "notify_offset": int(self.notify_combo.currentData()),
        }


class TagEditorDialog(QDialog):
    def __init__(self, tags: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tag Editor")
        self.setModal(True)
        self._deleted: Set[str] = set()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a tag to remove it from every event."))
        self.list = QListWidget()
        self.list.addItems(sorted(tags, key=lambda s: s.lower()))
        self.list.currentRowChanged.connect(self._update_buttons)
        layout.addWidget(self.list)
        self.delete_btn = QPushButton("Delete selected tag")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_selected)
        layout.addWidget(self.delete_btn)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.accept)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)
        if self.list.count():
            self.list.setCurrentRow(0)
        self._update_buttons(self.list.currentRow())

    def _update_buttons(self, row: int):
        self.delete_btn.setEnabled(row is not None and row >= 0 and self.list.count() > 0)

    def _delete_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        tag = item.text().strip()
        if not tag:
            return
        confirm = QMessageBox.question(
            self,
            "Delete Tag",
            f"Delete tag “{tag}” everywhere?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        row = self.list.row(item)
        self.list.takeItem(row)
        self._deleted.add(tag)
        if self.list.count():
            self.list.setCurrentRow(min(row, self.list.count() - 1))
        else:
            self.list.clearSelection()
        self._update_buttons(self.list.currentRow())

    def removed_tags(self) -> List[str]:
        return sorted(self._deleted, key=lambda s: s.lower())

class DayView(QWidget):
    gutter = 64
    top_pad = 16
    bottom_pad = 16
    def __init__(self, parent=None, prefs: Prefs = None):
        super().__init__(parent)
        self.owner = None
        self.prefs = prefs or Prefs()
        self.px_per_min = BASE_PX_PER_MIN * (float(self.prefs.zoom_percent) / 100.0)
        self.time_size_minutes = max(1, int(getattr(self.prefs, "time_size_minutes", getattr(self.prefs, "time_snap_minutes", 30))))
        self.snap_enabled = bool(getattr(self.prefs, "time_snap_enabled", True))
        self.smart_scale_enabled = bool(getattr(self.prefs, "smart_scale_enabled", False))
        self.magnetic_mode = bool(getattr(self.prefs, "magnetic_mode", False))
        self.event_widgets: List[EventWidget] = []
        self.setMinimumWidth(420); self.setMouseTracking(True)
        self._update_height()
        self.show_now_line = False
        self.upcoming_window_minutes = 6 * 60  # show countdown indicator for events within this window
        self._cached_indicator_state: Optional[dict] = None
        self.upcoming_indicator = UpcomingIndicator(self)
        self.upcoming_indicator.hide()
        self._layout_upcoming_indicator()
        self.box_select_mode = False
        self._box_selecting = False
        self._box_select_origin: Optional[QPoint] = None
        self._box_rubber: Optional[QRubberBand] = None
        self._box_selected_widgets: Set['EventWidget'] = set()
        self._group_move_active = False
        self._group_move_start_global = 0.0
        self._group_move_last_delta = 0
        self._group_move_refs: List[Tuple['EventWidget', int, int]] = []
        self._group_move_selected: Set['EventWidget'] = set()

    def note_history_action(self, action: str):
        owner = getattr(self, "owner", None)
        if owner and hasattr(owner, "note_history_action"):
            owner.note_history_action(action)

    def minute_to_y(self, minute: int) -> int: return int(minute * self.px_per_min) + self.top_pad
    def y_to_minute(self, y: int) -> int:
        m = int(round((y - self.top_pad) / self.px_per_min)); return max(0, min(24 * 60, m))
    def time_to_str(self, t: QTime) -> str:
        if getattr(self.prefs, "time_24h", True): return f"{t.hour():02d}:{t.minute():02d}"
        suffix = "AM" if t.hour() < 12 else "PM"; h12 = t.hour() % 12 or 12; return f"{h12}:{t.minute():02d} {suffix}"
    def min_to_hhmm(self, m: int) -> str:
        h = m // 60; mi = m % 60
        if getattr(self.prefs, "time_24h", True): return f"{h:02d}:{mi:02d}"
        suffix = "AM" if h < 12 else "PM"; h12 = h % 12 or 12; return f"{h12}:{mi:02d} {suffix}"
    def _grid_step_minutes(self) -> int:
        for step in (5, 10, 15, 30, 60):
            if step * self.px_per_min >= 14: return step
        return 60
    def _update_height(self):
        total_px = int(24 * 60 * self.px_per_min) + self.top_pad + self.bottom_pad
        self.setFixedHeight(total_px)
        if hasattr(self, "upcoming_indicator"):
            self._layout_upcoming_indicator()

    def _layout_upcoming_indicator(self):
        if not hasattr(self, "upcoming_indicator"):
            return
        width = 140
        x = max(0, self.width() - width)
        self.upcoming_indicator.setGeometry(int(x), 0, int(width), self.height())
        self.upcoming_indicator.raise_()

    def _next_upcoming_start(self, current_min: int) -> Optional[int]:
        next_start: Optional[int] = None
        for ev in self.event_widgets:
            if ev.start_min > current_min:
                if next_start is None or ev.start_min < next_start:
                    next_start = ev.start_min
        return next_start

    @staticmethod
    def _format_remaining_minutes(total_min: int) -> str:
        total_min = max(0, total_min)
        h, m = divmod(total_min, 60)
        parts = []
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        if not parts:
            parts.append("0m")
        return " ".join(parts)

    def snap_step(self) -> int:
        return self.time_size_minutes if self.snap_enabled else 1

    def snap_minute(self, minute: int) -> int:
        step = self.snap_step()
        if step <= 1:
            return max(0, min(24 * 60, int(minute)))
        snapped = int(round(minute / step) * step)
        return max(0, min(24 * 60, snapped))

    def snap_delta(self, raw_minutes: float) -> int:
        step = self.snap_step()
        if step <= 1:
            return int(round(raw_minutes))
        return int(round(raw_minutes / step) * step)

    def _snap_minute_to_chunk(self, minute: int) -> int:
        chunk = max(1, self.time_size_minutes)
        snapped = int(round(minute / chunk) * chunk)
        return max(0, min(24 * 60, snapped))

    def _minutes_from_pixels(self, pixels: float) -> int:
        px = max(0.1, float(self.px_per_min))
        return max(1, int(round(pixels / px)))

    def _snap_threshold_minutes(self) -> int:
        return self._minutes_from_pixels(30.0)

    def _current_time_minute(self) -> Optional[int]:
        if not self.show_now_line:
            return None
        now = QTime.currentTime()
        return now.hour() * 60 + now.minute()

    def _now_line_snap_candidate(
        self,
        start_min: int,
        duration: int,
        exclude: Optional['EventWidget'] = None,
    ) -> Optional[Tuple[int, int, int]]:
        if not (self.magnetic_mode and self.show_now_line):
            return None
        now_min = self._current_time_minute()
        if now_min is None:
            return None
        diff = abs(start_min - now_min)
        threshold = self._minutes_from_pixels(40.0)
        if diff > threshold:
            return None
        candidate_start = now_min
        candidate_end = candidate_start + duration
        if candidate_end > 24 * 60:
            return None
        if self.overlaps_range(candidate_start, candidate_end, exclude=exclude):
            return None
        return (candidate_start, candidate_end, diff)

    def snap_block_to_neighbors(
        self,
        block: Optional['EventWidget'],
        allow_start: bool = True,
        allow_end: bool = True,
        lock_start: bool = False,
        lock_end: bool = False,
    ) -> bool:
        if block is None or not self.magnetic_mode:
            return False
        threshold = self._snap_threshold_minutes()
        duration = max(1, block.end_min - block.start_min)
        original_start = block.start_min
        original_end = block.end_min
        best: Optional[Tuple[int, int, int]] = None  # (start, end, diff)

        for ev in self.event_widgets:
            if ev is block:
                continue
            if allow_start:
                target_start = ev.end_min
                diff = abs(block.start_min - target_start)
                if diff <= threshold:
                    candidate_start = target_start
                    candidate_end = candidate_start + duration
                    if lock_start and candidate_start != original_start:
                        pass
                    elif candidate_end <= 24 * 60 and not self.overlaps_range(candidate_start, candidate_end, exclude=block):
                        if not lock_end or candidate_end == original_end:
                            if best is None or diff < best[2]:
                                best = (candidate_start, candidate_end, diff)
            if allow_end:
                target_end = ev.start_min
                diff = abs(block.end_min - target_end)
                if diff <= threshold:
                    candidate_end = target_end
                    candidate_start = candidate_end - duration
                    if lock_end and candidate_end != original_end:
                        pass
                    elif candidate_start >= 0 and not self.overlaps_range(candidate_start, candidate_end, exclude=block):
                        if not lock_start or candidate_start == original_start:
                            if best is None or diff < best[2]:
                                best = (candidate_start, candidate_end, diff)

        if allow_start:
            now_candidate = self._now_line_snap_candidate(block.start_min, duration, exclude=block)
            if now_candidate:
                candidate_start, candidate_end, diff = now_candidate
                if lock_start and candidate_start != original_start:
                    pass
                elif lock_end and candidate_end != original_end:
                    pass
                elif best is None or diff < best[2]:
                    best = now_candidate

        if best is None:
            return False
        block.start_min = best[0]
        block.end_min = best[1]
        block.update_geometry()
        return True

    def _suggest_start_for_creation(self, start_min: int, duration: int) -> int:
        if not self.magnetic_mode:
            return start_min
        threshold = self._snap_threshold_minutes()
        best_start = start_min
        best_diff: Optional[int] = None

        for ev in self.event_widgets:
            # Snap to block above (new block immediately below existing)
            candidate_start = ev.end_min
            diff = abs(start_min - candidate_start)
            if candidate_start <= start_min and diff <= threshold:
                candidate_end = candidate_start + duration
                if candidate_end <= 24 * 60 and not self.overlaps_range(candidate_start, candidate_end):
                    if best_diff is None or diff < best_diff:
                        best_start = candidate_start
                        best_diff = diff
            # Snap to block below (new block immediately above existing)
            candidate_start = ev.start_min - duration
            diff = abs(start_min - candidate_start)
            if candidate_start >= 0 and diff <= threshold:
                candidate_end = candidate_start + duration
                if candidate_end <= ev.start_min and not self.overlaps_range(candidate_start, candidate_end):
                    if best_diff is None or diff < best_diff:
                        best_start = candidate_start
                        best_diff = diff

        return best_start

    def clamp_start_to_available(self, start: int, duration: int, exclude: Optional['EventWidget']=None,
                                 exclude_set: Optional[Set['EventWidget']]=None, direction: int = 0) -> Optional[int]:
        duration = max(1, duration)
        start = max(0, min(start, 24 * 60 - duration))
        excluded: Set['EventWidget'] = set(exclude_set or [])
        if exclude is not None:
            excluded.add(exclude)

        max_iters = len(self.event_widgets) + 1
        for _ in range(max_iters):
            conflict = None
            for ev in self.event_widgets:
                if ev in excluded:
                    continue
                if max(start, ev.start_min) < min(start + duration, ev.end_min):
                    conflict = ev
                    break
            if conflict is None:
                return start

            if direction > 0:
                start = conflict.end_min
            elif direction < 0:
                start = conflict.start_min - duration
            else:
                down = conflict.end_min
                up = conflict.start_min - duration
                candidates: List[Tuple[int, int]] = []
                if 0 <= down <= 24 * 60 - duration:
                    candidates.append((abs(down - start), down))
                if up >= 0 and up <= 24 * 60 - duration:
                    candidates.append((abs(up - start), up))
                if candidates:
                    candidates.sort()
                    start = candidates[0][1]
                else:
                    return None

            start = max(0, min(start, 24 * 60 - duration))
        return None

    def _compute_indicator_state(self, current_min: int) -> Optional[dict]:
        if not self.show_now_line:
            return None
        next_start = self._next_upcoming_start(current_min)
        if next_start is None:
            return None
        diff_min = next_start - current_min
        if diff_min <= 0 or diff_min > self.upcoming_window_minutes:
            return None
        y_now = self.minute_to_y(current_min)
        y_event = self.minute_to_y(next_start)
        y_min = self.top_pad
        y_max = self.height() - self.bottom_pad
        y_now_clamped = max(y_min, min(y_now, y_max))
        y_event_clamped = max(y_min, min(y_event, y_max))
        if y_event_clamped <= y_now_clamped + 2:
            return None
        return {
            "y_now": y_now_clamped,
            "y_event": y_event_clamped,
            "text": f"Time left {self._format_remaining_minutes(diff_min)} ⏰",
        }

    def overlaps_range(self, start_min: int, end_min: int,
                       exclude: Optional['EventWidget']=None,
                       exclude_set: Optional[Set['EventWidget']]=None) -> bool:
        for ev in self.event_widgets:
            if ev is exclude:
                continue
            if exclude_set and ev in exclude_set:
                continue
            if max(start_min, ev.start_min) < min(end_min, ev.end_min):
                return True
        return False

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self.prefs.day_background)

        width_right = self.width() - 8
        band_left = self.gutter
        for hour in range(24):
            y0 = self.minute_to_y(hour*60); y1 = self.minute_to_y(hour*60+60)
            color = self.prefs.zebra_even if (hour % 2 == 0) else self.prefs.zebra_odd
            p.fillRect(QRect(band_left, y0, max(0, width_right - band_left), max(0, y1 - y0)), color)

        step = self._grid_step_minutes()
        for minute in range(0, 24 * 60 + 1, step):
            y = self.minute_to_y(minute)
            is_hour = (minute % 60 == 0)
            pen = QPen(self.prefs.hour_line if is_hour else self.prefs.halfhour_line); pen.setWidth(2 if is_hour else 1)
            p.setPen(pen); p.drawLine(self.gutter, y, self.width() - 8, y)
            if is_hour:
                p.setPen(QPen(self.prefs.gutter_text)); p.setFont(QFont("Segoe UI", 9))
                p.drawText(8, y + 4, self.min_to_hhmm(minute))
            else:
                p.setPen(QPen(self.prefs.gutter_minor_text)); p.setFont(QFont("Segoe UI", 8))
                p.drawText(8, y + 3, self.min_to_hhmm(minute))

        p.setPen(QPen(self.prefs.snap_text)); p.setFont(QFont("Segoe UI", 8))
        size_text = f"{self.time_size_minutes} min"
        snap_text = "On" if self.snap_enabled else "Off"
        p.drawText(self.width() - 260, 12, f"Time Size: {size_text}  |  Snap: {snap_text}  |  Zoom: {int(self.px_per_min/BASE_PX_PER_MIN*100)}%")

        indicator_state: Optional[dict] = None
        if self.show_now_line:
            now = QTime.currentTime()
            m = now.hour()*60 + now.minute()
            y = self.minute_to_y(m)
            p.setPen(QPen(self.prefs.now_line, 2)); p.drawLine(self.gutter, y, self.width() - 8, y)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            box_font = QFont("Segoe UI", 9, QFont.Weight.Medium); p.setFont(box_font)
            txt = self.time_to_str(now); fm = QFontMetrics(box_font)
            pad_x, pad_y = 8, 4; rect_w = fm.horizontalAdvance(txt)+pad_x*2; rect_h = fm.height()+pad_y*2
            usable_left = self.gutter; usable_right = self.width() - 8
            rect_x = int(usable_left + (usable_right-usable_left)//2 - rect_w/2); rect_y = int(y - rect_h/2)
            p.setPen(QPen(self.prefs.now_box_border, 1)); p.setBrush(QBrush(self.prefs.now_box_fill))
            p.drawRoundedRect(QRect(rect_x, rect_y, rect_w, rect_h), 8, 8)
            p.setPen(QPen(self.prefs.now_box_text)); p.drawText(QRect(rect_x, rect_y, rect_w, rect_h), Qt.AlignmentFlag.AlignCenter, txt)
            indicator_state = self._compute_indicator_state(m)

        self._cached_indicator_state = indicator_state
        if hasattr(self, "upcoming_indicator"):
            should_show = indicator_state is not None
            self.upcoming_indicator.setVisible(should_show)
            if should_show:
                self._layout_upcoming_indicator()
                self.upcoming_indicator.raise_()
                self.upcoming_indicator.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for ev in self.event_widgets: ev.update_geometry()
        self._layout_upcoming_indicator()
        if hasattr(self, "upcoming_indicator"):
            self.upcoming_indicator.update()

    def add_block(self, start_min: int, duration_min: int, title: str = "", color: Optional[QColor] = None,
                  from_rule: bool = False, rule_id: Optional[str]=None, locked: bool=False,
                  image_rel: Optional[str]=None, tag: Optional[str]=None, notify_offset: int = 0,
                  record_history: bool = True) -> Optional['EventWidget']:
        duration_min = max(1, duration_min)
        start_candidate = self.clamp_start_to_available(start_min, duration_min, exclude=None, direction=0)
        if start_candidate is None:
            if self.owner:
                self.owner.flash_status("No room for new event here", warn=True)
            return None
        start_min = start_candidate
        end_min = start_min + duration_min
        if self.overlaps_range(start_min, end_min):
            if self.owner: self.owner.flash_status("Time occupied — cannot create here", warn=True)
            return None
        color = color or self.prefs.event_default
        block = EventWidget(self, start_min, end_min, title, color, from_rule=from_rule,
                            rule_id=rule_id, locked=locked, image_rel=image_rel,
                            tag=tag, notify_offset=notify_offset)
        block.set_box_selected(False)
        block.set_mouse_transparent(self.box_select_mode and block not in self._box_selected_widgets)
        block.show()
        self.event_widgets.append(block)
        self._refresh_widget_transparency()
        self.update()
        if record_history:
            self.note_history_action("Add block")
        return block

    def delete_block(self, block: 'EventWidget'):
        if block in self.event_widgets:
            if block.locked:
                if self.owner: self.owner.flash_status("Event is locked", warn=True)
                return
            self.note_history_action("Delete block")
            old_img = block.image_rel
            if block in self._box_selected_widgets:
                new_sel = set(self._box_selected_widgets)
                new_sel.discard(block)
                self._update_box_selection(new_sel)
            self.event_widgets.remove(block); block.deleteLater(); self.on_block_changed(None)
            if self.owner and old_img:
                self.owner.try_delete_image_if_unreferenced(old_img)
            self._refresh_widget_transparency()

    def clear_blocks(self):
        self._update_box_selection(set())
        for b in self.event_widgets: b.deleteLater()
        self.event_widgets.clear()
        self.update()

    def set_box_select_mode(self, enabled: bool):
        enabled = bool(enabled)
        if self.box_select_mode == enabled:
            return
        self.box_select_mode = enabled
        if not enabled:
            self._cancel_group_move()
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self._cancel_box_selection()
            self._update_box_selection(set())
            self.unsetCursor()
        self._refresh_widget_transparency()

    def _ensure_rubber_band(self):
        if self._box_rubber is None:
            self._box_rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def _cancel_box_selection(self):
        self._box_selecting = False
        self._box_select_origin = None
        if self._box_rubber is not None:
            self._box_rubber.hide()
        self._cancel_group_move()

    def _update_box_selection(self, new_selection: Set['EventWidget']):
        if new_selection == self._box_selected_widgets:
            return
        remove = self._box_selected_widgets - new_selection
        add = new_selection - self._box_selected_widgets
        for w in remove:
            w.set_box_selected(False)
        for w in add:
            w.set_box_selected(True)
        self._box_selected_widgets = new_selection
        self._notify_box_selection_changed()

    def _notify_box_selection_changed(self):
        if self.owner is None or not hasattr(self.owner, "on_box_selection_changed"):
            return
        total_minutes = 0
        for w in self._box_selected_widgets:
            total_minutes += max(1, w.end_min - w.start_min)
        try:
            self.owner.on_box_selection_changed(len(self._box_selected_widgets), total_minutes)
        except Exception:
            pass
        self._refresh_widget_transparency()

    def _apply_box_selection(self, rect: QRect):
        rect = rect.normalized()
        if rect.width() < 4 and rect.height() < 4:
            widget = self.childAt(rect.topLeft())
            selection: Set['EventWidget'] = set()
            if isinstance(widget, EventWidget):
                selection.add(widget)
        else:
            selection = {w for w in self.event_widgets if rect.intersects(w.geometry())}
        self._update_box_selection(selection)

    def clear_box_selection(self):
        self._update_box_selection(set())

    def _start_group_move(self, start_global_y: float) -> bool:
        selected = set(self._box_selected_widgets)
        if not selected:
            return False
        if any(w.locked for w in selected):
            if self.owner:
                self.owner.flash_status("Locked events cannot move", warn=True)
            return False
        self._group_move_active = True
        self._group_move_start_global = float(start_global_y)
        self._group_move_last_delta = 0
        self._group_move_refs = [(w, w.start_min, w.end_min) for w in selected]
        self._group_move_selected = selected
        self._box_selecting = False
        if self._box_rubber is not None:
            self._box_rubber.hide()
        for w in selected:
            w.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        return True

    def start_group_move_by_widget(self, widget: 'EventWidget', start_global_y: float) -> bool:
        if widget not in self._box_selected_widgets:
            return False
        return self._start_group_move(start_global_y)

    def _update_group_move(self, current_global_y: float):
        if not self._group_move_active:
            return
        delta_px = float(current_global_y) - self._group_move_start_global
        raw_minutes = delta_px / self.px_per_min
        delta_minutes = self.snap_delta(raw_minutes)
        if delta_minutes == self._group_move_last_delta:
            return
        new_positions: List[Tuple[EventWidget, int, int]] = []
        for w, start, end in self._group_move_refs:
            duration = end - start
            new_start = start + delta_minutes
            new_end = end + delta_minutes
            if new_start < 0 or new_end > 24 * 60:
                return
            new_positions.append((w, new_start, new_end))
        excludes = self._group_move_selected
        for w, new_start, new_end in new_positions:
            if self.overlaps_range(new_start, new_end, exclude_set=excludes):
                return
        for w, new_start, new_end in new_positions:
            w.start_min = new_start
            w.end_min = new_end
            w.update_geometry()
        self._group_move_last_delta = delta_minutes

    def _finish_group_move(self):
        if not self._group_move_active:
            return
        moved = self._group_move_last_delta != 0
        self._group_move_active = False
        self._group_move_refs = []
        self._group_move_selected = set()
        self._group_move_last_delta = 0
        self._group_move_start_global = 0.0
        if self.box_select_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        self._refresh_widget_transparency()
        if moved:
            self.on_block_changed(None)

    def _cancel_group_move(self):
        if not self._group_move_active:
            return
        self._group_move_active = False
        self._group_move_refs = []
        self._group_move_selected = set()
        self._group_move_last_delta = 0
        self._group_move_start_global = 0.0
        if self.box_select_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        self._refresh_widget_transparency()

    def _refresh_widget_transparency(self):
        if not self.box_select_mode:
            for ev in self.event_widgets:
                ev.set_mouse_transparent(False)
            return
        selected = self._box_selected_widgets
        for ev in self.event_widgets:
            ev.set_mouse_transparent(ev not in selected)

    def delete_selected_blocks(self):
        selected = set(self._box_selected_widgets)
        if not selected:
            return
        self.note_history_action("Delete selection")
        if any(w.locked for w in selected):
            if self.owner:
                self.owner.flash_status("Locked events cannot be deleted", warn=True)
            return
        self._cancel_group_move()
        from_rules = [w for w in selected if w.from_rule]
        regulars = [w for w in selected if not w.from_rule]
        for w in list(regulars):
            self.delete_block(w)
        if from_rules and self.owner:
            for w in from_rules:
                self.owner.delete_daily_rule_with_cleanup(w.rule_id)
            self.owner.load_day(self.owner.current_date)
        total_deleted = len(regulars) + len(from_rules)
        self._update_box_selection(set())
        if self.owner and total_deleted:
            self.owner.flash_status(f"Deleted {total_deleted} event{'s' if total_deleted != 1 else ''}")

    def get_selected_widgets(self) -> Set['EventWidget']:
        return set(self._box_selected_widgets)

    def finalize_single_move(self, widget: 'EventWidget', orig_start: int, orig_end: int):
        duration = max(1, widget.end_min - widget.start_min)
        if widget.start_min == orig_start and widget.end_min == orig_end:
            self.on_block_changed(widget)
            return
        direction = 1 if widget.start_min > orig_start else -1 if widget.start_min < orig_start else 0
        clamped = self.clamp_start_to_available(widget.start_min, duration, exclude=widget, direction=direction)
        if clamped is None:
            widget.start_min = orig_start
            widget.end_min = orig_end
            widget.update_geometry()
            if self.owner:
                self.owner.flash_status("Time occupied — cannot place here", warn=True)
            self.on_block_changed(widget)
            return
        widget.start_min = clamped
        widget.end_min = widget.start_min + duration
        widget.update_geometry()
        self.on_block_changed(widget)

    def on_block_changed(self, _block: Optional['EventWidget']):
        self.update()
        if self.owner is not None: self.owner.on_day_changed()

    def set_time_size(self, minutes: int):
        try:
            minutes = int(minutes)
        except Exception:
            minutes = self.time_size_minutes
        minutes = max(1, minutes)
        if minutes == self.time_size_minutes:
            return
        self.time_size_minutes = minutes
        if hasattr(self.prefs, "time_size_minutes"):
            self.prefs.time_size_minutes = int(self.time_size_minutes)
            try:
                self.prefs.save(PREF_PATH)
            except Exception:
                pass
        self.update()

    def set_snap_enabled(self, enabled: bool):
        enabled = bool(enabled)
        if self.snap_enabled == enabled:
            return
        self.snap_enabled = enabled
        if hasattr(self.prefs, "time_snap_enabled"):
            self.prefs.time_snap_enabled = bool(enabled)
            try:
                self.prefs.save(PREF_PATH)
            except Exception:
                pass
        self.update()
        self._refresh_widget_transparency()

    def set_magnetic_mode(self, enabled: bool):
        enabled = bool(enabled)
        if self.magnetic_mode == enabled:
            return
        self.magnetic_mode = enabled
        if hasattr(self.prefs, "magnetic_mode"):
            self.prefs.magnetic_mode = bool(enabled)
            try:
                self.prefs.save(PREF_PATH)
            except Exception:
                pass
        self.update()

    def set_smart_scale_enabled(self, enabled: bool):
        enabled = bool(enabled)
        if self.smart_scale_enabled == enabled:
            return
        self.smart_scale_enabled = enabled
        if hasattr(self.prefs, "smart_scale_enabled"):
            self.prefs.smart_scale_enabled = bool(enabled)
            try:
                self.prefs.save(PREF_PATH)
            except Exception:
                pass
        self.update()

    def set_prefs(self, prefs: Prefs):
        self.prefs = prefs
        self.time_size_minutes = max(1, int(getattr(prefs, "time_size_minutes", getattr(prefs, "time_snap_minutes", self.time_size_minutes))))
        self.snap_enabled = bool(getattr(prefs, "time_snap_enabled", True))
        self.smart_scale_enabled = bool(getattr(prefs, "smart_scale_enabled", False))
        self.magnetic_mode = bool(getattr(prefs, "magnetic_mode", False))
        self.set_zoom_from_percent(prefs.zoom_percent)
        for ev in self.event_widgets: ev.update_geometry()
        self.update()
        self._refresh_widget_transparency()
    def set_zoom_from_percent(self, display_percent: int):
        display_percent = max(50, min(500, int(display_percent)))
        self.prefs.zoom_percent = display_percent
        self.px_per_min = BASE_PX_PER_MIN * (display_percent / 100.0)
        self._update_height()
        for ev in self.event_widgets: ev.update_geometry()
        self.update()

    def mousePressEvent(self, e):
        if self.box_select_mode:
            if e.button() == Qt.MouseButton.LeftButton:
                pos = e.position().toPoint()
                hit = None
                for w in self._box_selected_widgets:
                    if w.geometry().contains(pos):
                        hit = w
                        break
                if hit and self._start_group_move(e.globalPosition().y()):
                    e.accept()
                else:
                    self._box_selecting = True
                    self._box_select_origin = pos
                    self._ensure_rubber_band()
                    if self._box_rubber is not None:
                        origin = self._box_select_origin or QPoint()
                        self._box_rubber.setGeometry(QRect(origin, origin))
                        self._box_rubber.show()
                    e.accept()
            else:
                super().mousePressEvent(e)
            return

        if e.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(e.position().toPoint())
            if isinstance(child, EventWidget):
                return super().mousePressEvent(e)
            base_min = self.y_to_minute(int(e.position().y()))
            start_min = self.snap_minute(base_min)
            duration = max(1, self.time_size_minutes)
            max_start = max(0, 24 * 60 - duration)
            start_min = max(0, min(start_min, max_start))
            if self.magnetic_mode:
                start_min = self._suggest_start_for_creation(start_min, duration)
            created = self.add_block(start_min, duration)
            if created:
                snapped = False
                if self.magnetic_mode:
                    snapped = self.snap_block_to_neighbors(created, allow_start=True, allow_end=False)
                    if not snapped:
                        snapped = self.snap_block_to_neighbors(created, allow_start=False, allow_end=True)
                    if not snapped:
                        snapped = self.snap_block_to_neighbors(created)
                self.on_block_changed(created if snapped else None)
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.box_select_mode and self._group_move_active:
            self._update_group_move(e.globalPosition().y())
            e.accept()
            return
        if self.box_select_mode and self._box_selecting:
            self._ensure_rubber_band()
            if self._box_rubber is not None and self._box_select_origin is not None:
                current = e.position().toPoint()
                rect = QRect(self._box_select_origin, current).normalized()
                self._box_rubber.setGeometry(rect)
                self._box_rubber.show()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.box_select_mode and self._group_move_active and e.button() == Qt.MouseButton.LeftButton:
            self._finish_group_move()
            e.accept()
            return
        if self.box_select_mode and self._box_selecting and e.button() == Qt.MouseButton.LeftButton:
            origin = self._box_select_origin or e.position().toPoint()
            end_point = e.position().toPoint()
            rect = QRect(origin, end_point)
            self._cancel_box_selection()
            self._apply_box_selection(rect)
            e.accept()
            return
        if self.box_select_mode:
            super().mouseReleaseEvent(e)
            return
        super().mouseReleaseEvent(e)


class UpcomingIndicator(QWidget):
    def __init__(self, day_view: 'DayView'):
        super().__init__(day_view)
        self.day_view = day_view
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        state = getattr(self.day_view, "_cached_indicator_state", None)
        if not state:
            return
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        line_color = QColor(self.day_view.prefs.upcoming_bar)
        bubble_bg = QColor(self.day_view.prefs.upcoming_bar_bg)
        opacity_pct = int(getattr(self.day_view.prefs, "upcoming_bar_bg_opacity", 40))
        opacity_pct = max(0, min(100, opacity_pct))
        bubble_bg.setAlpha(int(round(opacity_pct / 100.0 * 255)))

        y_now = max(0, min(self.height(), state["y_now"]))
        y_event = max(0, min(self.height(), state["y_event"]))
        if y_event <= y_now:
            return

        line_pen = QPen(line_color, 4); line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(line_pen)
        line_x = self.width() - 20
        p.drawLine(int(line_x), int(y_now), int(line_x), int(y_event))

        center_y = (y_now + y_event) / 2.0
        bubble_text = state["text"]
        bubble_font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        p.setFont(bubble_font)
        metrics = QFontMetrics(bubble_font)
        text_w = metrics.horizontalAdvance(bubble_text)
        text_h = metrics.height()
        pad_w, pad_h = 10, 6
        bubble_w = text_w + pad_w * 2
        bubble_h = text_h + pad_h * 2
        half_len = bubble_w / 2.0
        center_y = max(half_len, min(self.height() - half_len, center_y))

        p.save()
        p.translate(line_x - (bubble_h / 2.0) - 16, center_y)
        p.rotate(-90)
        rect = QRectF(-bubble_w / 2.0, -bubble_h / 2.0, bubble_w, bubble_h)
        p.setPen(QPen(line_color, 1))
        p.setBrush(QBrush(bubble_bg))
        p.drawRoundedRect(rect, 10, 10)
        p.setPen(QPen(line_color))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, bubble_text)
        p.restore()


class EventWidget(QWidget):
    HANDLE = 6
    def __init__(self, day_view: DayView, start_min: int, end_min: int, title: str = "",
                 color: Optional[QColor] = None, from_rule: bool = False, rule_id: Optional[str]=None,
                 locked: bool=False, image_rel: Optional[str]=None, tag: Optional[str]=None,
                 notify_offset: int = 0):
        super().__init__(day_view)
        self.day_view = day_view
        self.start_min = max(0, min(start_min, 24 * 60 - 1))
        self.end_min = max(self.start_min + 1, min(end_min, 24 * 60))
        self.title = title
        self.tag = (tag or "").strip()
        self.color = QColor(color or self.day_view.prefs.event_default)
        self.from_rule = from_rule
        self.rule_id = rule_id
        self.locked = locked
        self.image_rel = image_rel
        self.pixmap: Optional[QPixmap] = None
        self.notify_offset = max(0, int(notify_offset or 0))
        self._load_pixmap()
        self._box_selected = False
        self._group_dragging = False
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._drag_mode: Optional[str] = None
        self._press_global_y: float = 0.0
        self._orig_start = self.start_min; self._orig_end = self.end_min
        self._orig_duration = max(1, self._orig_end - self._orig_start)
        self.setMouseTracking(True); self.update_geometry()

    def _load_pixmap(self):
        if self.image_rel:
            p = QPixmap(str(APP_DIR / self.image_rel))
            self.pixmap = p if not p.isNull() else None
        else:
            self.pixmap = None

    def _base_chunk(self) -> int:
        return max(1, self.day_view.time_size_minutes)

    def _smart_scale_resize_bottom(self, minute_at_cursor: int):
        chunk = self._base_chunk()
        minute_at_cursor = max(self._orig_start + chunk, min(minute_at_cursor, 24 * 60))
        delta = minute_at_cursor - self._orig_end
        steps = int(delta // chunk)
        target_duration = max(chunk, self._orig_duration + steps * chunk)
        max_duration = max(chunk, ((24 * 60 - self._orig_start) // chunk) * chunk or chunk)
        target_duration = max(chunk, min(target_duration, max_duration))
        duration = target_duration
        direction = 1 if duration >= self._orig_duration else -1
        attempts = 0
        while attempts < 1000:
            duration = max(chunk, min(duration, max_duration))
            new_end = self._orig_start + duration
            if new_end > 24 * 60:
                duration -= chunk
                attempts += 1
                continue
            if not self.day_view.overlaps_range(self._orig_start, new_end, exclude=self):
                break
            duration -= chunk if direction >= 0 else -chunk
            if duration < chunk:
                duration = chunk
                break
            attempts += 1
        self.start_min = self._orig_start
        self.end_min = min(24 * 60, self._orig_start + duration)
        self.update_geometry()

    def _smart_scale_resize_top(self, minute_at_cursor: int):
        chunk = self._base_chunk()
        minute_at_cursor = max(0, min(minute_at_cursor, self._orig_end - chunk))
        delta = self._orig_start - minute_at_cursor
        steps = int(delta // chunk)
        target_duration = max(chunk, self._orig_duration + steps * chunk)
        max_duration = max(chunk, ((self._orig_end) // chunk) * chunk or chunk)
        target_duration = max(chunk, min(target_duration, max_duration))
        duration = target_duration
        direction = 1 if duration >= self._orig_duration else -1
        attempts = 0
        while attempts < 1000:
            duration = max(chunk, min(duration, max_duration))
            new_start = self._orig_end - duration
            if new_start < 0:
                duration -= chunk
                attempts += 1
                continue
            if not self.day_view.overlaps_range(new_start, self._orig_end, exclude=self):
                break
            duration -= chunk if direction >= 0 else -chunk
            if duration < chunk:
                duration = chunk
                break
            attempts += 1
        self.start_min = max(0, self._orig_end - duration)
        self.end_min = self._orig_end
        self.update_geometry()

    def set_box_selected(self, value: bool):
        if self._box_selected != value:
            self._box_selected = value
            self.update()

    def set_mouse_transparent(self, enabled: bool):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._group_dragging = False
        else:
            self._set_idle_cursor()

    def _set_idle_cursor(self):
        if self.locked:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def update_geometry(self):
        x = self.day_view.gutter + 10
        w = max(120, self.day_view.width() - x - 10)
        y = self.day_view.minute_to_y(self.start_min)
        h = max(10, self.day_view.minute_to_y(self.end_min) - y)
        self.setGeometry(QRect(x, y, w, h))
        self.update()
        self.day_view.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        fill = QColor(self.color); fill.setAlpha(180)
        border = QColor(self.day_view.prefs.event_border)
        if self.locked: border.setAlpha(180)
        p.setBrush(QBrush(fill)); p.setPen(QPen(border, 1))
        p.drawRoundedRect(rect, 6, 6)

        header_rect = QRect(rect.x() + 1, rect.y() + 1, rect.width() - 2, 22)
        header_color = QColor(self.color); header_color.setAlpha(220)
        p.fillRect(header_rect, header_color)

        # Title (emoji ok)
        p.setPen(self.day_view.prefs.header_text)
        p.setFont(QFont("Segoe UI Emoji", 9, QFont.Weight.Medium))
        base_title = (self.title or "(untitled)").strip()
        parts: List[str] = []
        if self.locked:
            parts.append("🔒")
        if self.tag:
            parts.append(f"[{self.tag}]")
        parts.append(base_title)
        left_text = " ".join(parts)
        if self.from_rule: left_text += "  ⟳"
        p.drawText(header_rect.adjusted(8, 0, -8, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   left_text)

        # Duration centered (and show remaining time when in-progress on current day)
        duration_min = max(1, self.end_min - self.start_min)
        dh, dm = divmod(duration_min, 60)
        dur_text = f"{dh}h {dm}m" if dh and dm else (f"{dh}h" if dh else f"{dm}m")

        remaining_text = ""
        if self.day_view.show_now_line:
            now = QTime.currentTime()
            current_min = now.hour() * 60 + now.minute()
            if self.start_min <= current_min < self.end_min:
                rem_min = self.end_min - current_min
                rh, rm = divmod(rem_min, 60)
                parts: List[str] = []
                if rh:
                    parts.append(f"{rh}h")
                if rm:
                    parts.append(f"{rm}m")
                if not parts:
                    parts.append("0m")
                remaining_text = f"REM {' '.join(parts)}"

        center_text = dur_text if not remaining_text else f"{dur_text}   {remaining_text}"
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        p.drawText(header_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, center_text)

        # Time range right
        time_text = f"{self.day_view.min_to_hhmm(self.start_min)} – {self.day_view.min_to_hhmm(self.end_min)}"
        p.drawText(header_rect.adjusted(8, 0, -8, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   time_text)

        # Handles
        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.drawLine(10, self.HANDLE, self.width() - 10, self.HANDLE)
        p.drawLine(10, self.height() - self.HANDLE, self.width() - 10, self.height() - self.HANDLE)

        # Attached image (top-right inside block, 16px padding). Fit if height is small.
        if self.pixmap:
            padding = 16
            available_h = max(0, self.height() - header_rect.height() - padding - 4)
            if available_h > 0:
                side = min(256, available_h)  # scale down to fit short blocks
                side = max(1, side)
                x = self.width() - padding - side
                y = header_rect.bottom() + 4
                p.drawPixmap(QRect(int(x), int(y), int(side), int(side)),
                             self.pixmap, self.pixmap.rect())

        if self._box_selected:
            highlight_pen = QPen(QColor("#007AFF"), 2, Qt.PenStyle.DashLine)
            highlight_pen.setCosmetic(True)
            p.setPen(highlight_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

    def _hover_update_cursor(self, y: float):
        magnetic = bool(getattr(self.day_view, "magnetic_mode", False))
        smart_scale = bool(getattr(self.day_view, "smart_scale_enabled", False))
        if self.locked:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
            return
        if smart_scale:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return
        if magnetic:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if y <= self.HANDLE or y >= self.height() - self.HANDLE:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, e):
        magnetic = bool(getattr(self.day_view, "magnetic_mode", False))
        smart_scale = bool(getattr(self.day_view, "smart_scale_enabled", False))
        if self.day_view.box_select_mode:
            if e.button() == Qt.MouseButton.LeftButton:
                if self in self.day_view.get_selected_widgets():
                    if self.day_view.start_group_move_by_widget(self, e.globalPosition().y()):
                        self._group_dragging = True
                        e.accept()
                    else:
                        e.ignore()
                else:
                    e.ignore()
            elif e.button() == Qt.MouseButton.RightButton:
                super().mousePressEvent(e)
            else:
                e.ignore()
            return
        if self.locked and e.button() == Qt.MouseButton.LeftButton:
            owner = getattr(self.day_view, "owner", None)
            if owner:
                owner.flash_status("Event is locked", warn=True)
            self._drag_mode = None
            self._orig_start = self.start_min; self._orig_end = self.end_min
            self._set_idle_cursor()
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self.raise_()
            y = e.position().y()
            if smart_scale:
                if y <= self.HANDLE:
                    self._drag_mode = "resize_top"; self.setCursor(Qt.CursorShape.SizeVerCursor)
                elif y >= self.height() - self.HANDLE:
                    self._drag_mode = "resize_bottom"; self.setCursor(Qt.CursorShape.SizeVerCursor)
                else:
                    self._drag_mode = None
                    self._set_idle_cursor()
                    if self.day_view.owner:
                        self.day_view.owner.statusBar().showMessage("Smart scale: use handles to resize", 1500)
                    e.accept()
                    return
            else:
                if y <= self.HANDLE: self._drag_mode = "resize_top"; self.setCursor(Qt.CursorShape.SizeVerCursor)
                elif y >= self.height() - self.HANDLE: self._drag_mode = "resize_bottom"; self.setCursor(Qt.CursorShape.SizeVerCursor)
                else: self._drag_mode = "move"; self.setCursor(Qt.CursorShape.ClosedHandCursor)
                if magnetic:
                    self._drag_mode = "move"; self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._press_global_y = e.globalPosition().y()
            self._orig_start = self.start_min; self._orig_end = self.end_min
            self._orig_duration = max(1, self._orig_end - self._orig_start)
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        magnetic = bool(getattr(self.day_view, "magnetic_mode", False))
        smart_scale = bool(getattr(self.day_view, "smart_scale_enabled", False))
        if self.day_view.box_select_mode:
            if self._group_dragging:
                self.day_view._update_group_move(e.globalPosition().y())
                e.accept()
            else:
                e.ignore()
            return
        block_size = self._base_chunk()
        snap_active = magnetic
        if self._drag_mode is None:
            self._hover_update_cursor(e.position().y()); return
        if self.locked:
            self._drag_mode = None
            self._hover_update_cursor(e.position().y())
            e.accept()
            return

        if self._drag_mode == "move":
            if smart_scale:
                e.accept()
                return
            delta_px = e.globalPosition().y() - self._press_global_y
            raw_minutes = delta_px / self.day_view.px_per_min
            delta_min = self.day_view.snap_delta(raw_minutes)
            duration = block_size
            if snap_active:
                duration = max(1, self._orig_duration)
            new_start = self._orig_start + delta_min
            direction = 1 if delta_min >= 0 else -1
            clamped = self.day_view.clamp_start_to_available(new_start, duration, exclude=self, direction=direction)
            if clamped is not None:
                self.start_min = clamped
                self.end_min = self.start_min + duration
                if snap_active:
                    snapped = False
                    if direction >= 0:
                        snapped = self.day_view.snap_block_to_neighbors(self, allow_start=True, allow_end=False)
                    else:
                        snapped = self.day_view.snap_block_to_neighbors(self, allow_start=False, allow_end=True)
                    if not snapped:
                        self.day_view.snap_block_to_neighbors(self, allow_start=True, allow_end=True)
                self.update_geometry()
            e.accept()
        else:
            day_y = self.day_view.mapFromGlobal(e.globalPosition().toPoint()).y()
            minute_at_cursor = self.day_view.y_to_minute(day_y)
            if self._drag_mode == "resize_top":
                if smart_scale:
                    self._smart_scale_resize_top(minute_at_cursor)
                else:
                    snapped = self.day_view.snap_minute(minute_at_cursor)
                    new_start = snapped
                    if magnetic:
                        now_candidate = self.day_view._now_line_snap_candidate(snapped, block_size, exclude=self)
                        if now_candidate:
                            new_start = now_candidate[0]
                    direction = -1 if new_start < self.start_min else 1 if new_start > self.start_min else 0
                    clamped = self.day_view.clamp_start_to_available(new_start, block_size, exclude=self, direction=direction)
                    if clamped is not None:
                        self.start_min = clamped
                        self.end_min = self.start_min + block_size
                        self.update_geometry()
                e.accept()
            elif self._drag_mode == "resize_bottom":
                if smart_scale:
                    self._smart_scale_resize_bottom(minute_at_cursor)
                else:
                    snapped_end = self.day_view.snap_minute(minute_at_cursor)
                    new_end = snapped_end
                    new_start = new_end - block_size
                    direction = 1 if new_end > self.end_min else -1 if new_end < self.end_min else 0
                    clamped = self.day_view.clamp_start_to_available(new_start, block_size, exclude=self, direction=direction)
                    if clamped is not None:
                        self.start_min = clamped
                        self.end_min = self.start_min + block_size
                        self.update_geometry()
                e.accept()

    def mouseReleaseEvent(self, e):
        if self.day_view.box_select_mode:
            if self._group_dragging and e.button() == Qt.MouseButton.LeftButton:
                self.day_view._finish_group_move()
                self._group_dragging = False
                e.accept()
            else:
                super().mouseReleaseEvent(e)
            return
        if self.locked and e.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = None
            self._set_idle_cursor()
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self._drag_mode == "move":
                moved = (self.start_min != self._orig_start) or (self.end_min != self._orig_end)
                if moved:
                    self.day_view.note_history_action("Move block")
                self.day_view.finalize_single_move(self, self._orig_start, self._orig_end)
            else:
                resized = (self.start_min != self._orig_start) or (self.end_min != self._orig_end)
                if resized:
                    self.day_view.note_history_action("Resize block")
                self.day_view.on_block_changed(self)
            self._drag_mode = None; self._set_idle_cursor()
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def _do_edit(self):
        owner = self.day_view.owner
        old_image = self.image_rel
        existing_tags: List[str] = []
        if owner and hasattr(owner, "known_tags"):
            try:
                existing_tags = list(owner.known_tags())
            except Exception:
                existing_tags = []
        dlg = EventEditDialog(
            title=self.title, color_hex=qcolor_to_hex(self.color),
            start_min=self.start_min, end_min=self.end_min, is_rule=self.from_rule,
            time_24h=self.day_view.prefs.time_24h, image_rel=self.image_rel,
            notify_offset=self.notify_offset, tag=self.tag, existing_tags=existing_tags, parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        payload = dlg.result_payload()
        block_size = self._base_chunk()
        start = max(0, int(payload["start_min"]))
        desired_end = max(start + 1, int(payload["end_min"]))
        end = start + block_size
        if end > 24 * 60:
            end = 24 * 60
            start = max(0, end - block_size)
        payload["start_min"] = start
        payload["end_min"] = end

        new_start, new_end = payload["start_min"], payload["end_min"]
        if self.day_view.overlaps_range(new_start, new_end, exclude=self):
            owner.flash_status("Cannot apply: overlaps another event", warn=True); return

        old_title = self.title
        old_color = qcolor_to_hex(self.color)
        old_start = self.start_min
        old_end = self.end_min
        old_image = self.image_rel
        old_notify = getattr(self, "notify_offset", 0)
        old_tag = self.tag

        self.title = payload["title"]; self.color = QColor(payload["color"])
        self.tag = payload["tag"]
        self.image_rel = payload.get("image"); self._load_pixmap()

        if self.from_rule:
            if self.rule_id and owner.update_daily_rule(
                self.rule_id, new_start, new_end, self.title,
                qcolor_to_hex(self.color), self.image_rel, payload["notify_offset"], self.tag
            ):
                owner.flash_status("Daily rule updated")
            else:
                owner.flash_status("Failed to update rule", warn=True)
            if old_image and old_image != self.image_rel:
                owner.try_delete_image_if_unreferenced(old_image)
            owner.load_day(owner.current_date)
        else:
            self.start_min, self.end_min = new_start, new_end
            self.notify_offset = int(payload["notify_offset"])
            changed = (
                self.start_min != old_start or
                self.end_min != old_end or
                self.title != old_title or
                qcolor_to_hex(self.color) != old_color or
                (self.image_rel or "") != (payload.get("image") or "") or
                self.notify_offset != old_notify or
                (self.tag or "") != (old_tag or "")
            )
            if changed:
                self.day_view.note_history_action("Edit block")
            self.update_geometry(); owner.on_day_changed()
            if old_image and old_image != self.image_rel:
                owner.try_delete_image_if_unreferenced(old_image)

        wdys = payload["weekly_days"]; weeks = payload["weekly_weeks"]
        if wdys and weeks > 0:
            added = owner.duplicate_weekly(self.start_min, self.end_min, self.title, qcolor_to_hex(self.color),
                                           wdys, weeks, image_rel=self.image_rel,
                                           notify_offset=int(payload["notify_offset"]), tag=self.tag)
            owner.flash_status(f"Created {added} weekly duplicate(s)")

        if payload["convert_daily"]:
            owner.add_daily_rule(self.start_min, self.end_min, self.title, qcolor_to_hex(self.color),
                                 locked=self.locked, image_rel=self.image_rel,
                                 notify_offset=int(payload["notify_offset"]), tag=self.tag)
            self.day_view.delete_block(self); owner.on_day_changed()
            owner.flash_status("Converted to daily rule")

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        edit_act = menu.addAction("Edit…")
        lock_act = menu.addAction("Unlock" if self.locked else "Lock (prevent move/delete)")
        menu.addSeparator()
        multi_del_act = None
        selected = self.day_view.get_selected_widgets()
        if selected and self in selected:
            label = f"Delete selected ({len(selected)})"
            multi_del_act = menu.addAction(label)
            if any(w.locked for w in selected):
                multi_del_act.setEnabled(False)
            menu.addSeparator()
        del_text = "Delete (all days)" if self.from_rule else "Delete"
        del_act = menu.addAction(del_text)
        if self.locked: del_act.setEnabled(False)
        if self.from_rule and self.day_view.owner.rule_locked(self.rule_id): del_act.setEnabled(False)

        chosen = menu.exec(e.globalPos()); owner = self.day_view.owner
        if chosen is edit_act:
            self._do_edit()
        elif chosen is lock_act:
            if self.from_rule:
                new_state = not owner.rule_locked(self.rule_id)
                owner.set_rule_locked(self.rule_id, new_state)
                owner.flash_status("Rule locked" if new_state else "Rule unlocked")
                owner.load_day(owner.current_date)
            else:
                self.locked = not self.locked; owner.on_day_changed(); self.update(); self._set_idle_cursor()
                owner.flash_status("Event locked" if self.locked else "Event unlocked")
        elif multi_del_act is not None and chosen is multi_del_act:
            self.day_view.delete_selected_blocks()
        elif chosen is del_act:
            if self.locked: owner.flash_status("Item is locked", warn=True); return
            if self.from_rule:
                owner.delete_daily_rule_with_cleanup(self.rule_id); owner.load_day(owner.current_date)
            else:
                self.day_view.delete_block(self)


class MiniCalendar(QCalendarWidget):
    """Custom painter: tiny dot on 'today', ring on selected day. Colors from Prefs."""
    def __init__(self, prefs: Prefs, parent=None):
        super().__init__(parent)
        self._prefs = prefs

    def set_prefs(self, prefs: Prefs):
        self._prefs = prefs
        self.viewport().update()

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate):
        super().paintCell(painter, rect, date)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Today dot (top-right)
        if date == QDate.currentDate():
            r = 4
            cx = rect.right() - r - 3
            cy = rect.top() + r + 3
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._prefs.cal_today_dot))
            painter.drawEllipse(QPoint(cx, cy), r, r)

        # Selected ring
        if date == self.selectedDate():
            ring_color = self._prefs.cal_selected_ring
            pen = QPen(ring_color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(4, 4, -4, -4))

        painter.restore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("iCal-ish Day Planner"); self.resize(1140, 800)
        self.prefs = Prefs.from_config(PREF_PATH)
        if getattr(self.prefs, "smart_scale_enabled", False) and getattr(self.prefs, "magnetic_mode", False):
            self.prefs.magnetic_mode = False

        self.events_by_date: Dict[str, List[dict]] = self.load_data()
        self.repeat_rules: List[dict] = self.load_rules()
        self._next_rule_id = self.compute_next_rule_id()
        self.current_date: QDate = QDate.currentDate()
        self.notification_timers: List[QTimer] = []
        self._notification_schedule_date: Optional[QDate] = None
        self.notification_player: Optional[QMediaPlayer] = None
        self.notification_audio: Optional[QAudioOutput] = None
        self._history: List[dict] = []
        self._history_index: int = -1
        self._history_freeze: bool = False
        self._history_max: int = 11  # baseline + 10 actions
        self._pending_history_action: Optional[str] = None
        self._clear_history_file()

        # Menus
        menu = self.menuBar(); edit_menu = menu.addMenu("Edit")
        pref_act = QAction("Preferences…", self); pref_act.triggered.connect(self.open_prefs)
        edit_menu.addAction(pref_act)

        # Toolbar
        tb = QToolBar("Controls", self); tb.setMovable(False); self.addToolBar(tb)
        tb.addWidget(QLabel("  Time Size: "))
        self.time_size_combo = QComboBox()
        snap_values = []
        for val in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 22, 24, 30, 60]:
            text = str(val)
            if text not in snap_values:
                snap_values.append(text)
        self.time_size_combo.addItems(snap_values)
        self.time_size_combo.setCurrentText(str(self.prefs.time_size_minutes))
        self.time_size_combo.currentTextChanged.connect(self.on_time_size_changed)
        tb.addWidget(self.time_size_combo)
        self.smart_scale_btn = QToolButton()
        self.smart_scale_btn.setText("⌛️")
        self.smart_scale_btn.setCheckable(True)
        self.smart_scale_btn.setChecked(bool(getattr(self.prefs, "smart_scale_enabled", False)))
        self.smart_scale_btn.setAutoRaise(True)
        self.smart_scale_btn.setToolTip("Toggle smart scale (resize in increments)")
        self.smart_scale_btn.toggled.connect(self.on_smart_scale_toggled)
        tb.addWidget(self.smart_scale_btn)
        self.magnetic_btn = QToolButton()
        self.magnetic_btn.setText("🧲")
        self.magnetic_btn.setCheckable(True)
        self.magnetic_btn.setChecked(bool(getattr(self.prefs, "magnetic_mode", False)))
        self.magnetic_btn.setAutoRaise(True)
        self.magnetic_btn.setToolTip("Toggle magnetic mode")
        self.magnetic_btn.toggled.connect(self.on_magnetic_toggled)
        tb.addWidget(self.magnetic_btn)
        self.snap_toggle = QToolButton()
        self.snap_toggle.setAutoRaise(True)
        self.snap_toggle.setCheckable(True)
        self.snap_toggle.toggled.connect(self.on_snap_toggle)
        tb.addWidget(self.snap_toggle)
        self.update_snap_toggle_text()

        tb.addWidget(QLabel("  Time: "))
        self.time_combo = QComboBox(); self.time_combo.addItems(["24h", "12h"])
        self.time_combo.setCurrentText("24h" if self.prefs.time_24h else "12h")
        self.time_combo.currentTextChanged.connect(self.on_time_format_changed)
        tb.addWidget(self.time_combo)
        self.box_select_btn = QToolButton()
        self.box_select_btn.setText("⏹️")
        self.box_select_btn.setCheckable(True)
        self.box_select_btn.setAutoRaise(True)
        self.box_select_btn.setToolTip("Toggle box selection tool")
        self.box_select_btn.toggled.connect(self.on_box_select_toggled)
        tb.addWidget(self.box_select_btn)
        self.history_btn = QToolButton()
        self.history_btn.setText("🗒️")
        self.history_btn.setToolTip("Show history")
        self.history_btn.clicked.connect(self.show_history_dialog)
        tb.addWidget(self.history_btn)

        tb.addWidget(QLabel("  Zoom: "))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(50); self.zoom_slider.setMaximum(500)
        self.zoom_slider.setSingleStep(5); self.zoom_slider.setPageStep(10); self.zoom_slider.setFixedWidth(220)
        self.zoom_slider.setValue(int(self.prefs.zoom_percent)); self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        tb.addWidget(self.zoom_slider); self.zoom_label = QLabel(f"{self.prefs.zoom_percent}%"); tb.addWidget(self.zoom_label)

        tb.addSeparator(); self.date_label = QLabel(); tb.addWidget(self.date_label)

        # Day view + scroll
        self.day_view = DayView(prefs=self.prefs); self.day_view.owner = self
        scroll = QScrollArea(); scroll.setWidget(self.day_view); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area = scroll
        self.setCentralWidget(scroll)
        self.day_view.set_time_size(self.prefs.time_size_minutes)
        self.day_view.set_snap_enabled(self.prefs.time_snap_enabled)
        self.day_view.set_magnetic_mode(self.prefs.magnetic_mode)
        self.day_view.set_smart_scale_enabled(self.prefs.smart_scale_enabled)
        if hasattr(self, "snap_toggle"):
            self.snap_toggle.blockSignals(True)
            self.snap_toggle.setChecked(self.prefs.time_snap_enabled)
            self.snap_toggle.blockSignals(False)
        if hasattr(self, "time_size_combo"):
            self.time_size_combo.blockSignals(True)
            self.time_size_combo.setCurrentText(str(self.prefs.time_size_minutes))
            self.time_size_combo.blockSignals(False)
        if hasattr(self, "smart_scale_btn"):
            self.smart_scale_btn.blockSignals(True)
            self.smart_scale_btn.setChecked(bool(self.prefs.smart_scale_enabled))
            self.smart_scale_btn.blockSignals(False)
        if hasattr(self, "magnetic_btn"):
            self.magnetic_btn.blockSignals(True)
            self.magnetic_btn.setChecked(bool(self.prefs.magnetic_mode))
            self.magnetic_btn.blockSignals(False)
        self.update_snap_toggle_text()
        self._init_shortcuts()

        # Calendar dock (left) with "Go to current time" button
        self.calendar_dock = QDockWidget("Mini Month", self)
        self.calendar_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        cal_container = QWidget(); v = QVBoxLayout(cal_container); v.setContentsMargins(8, 8, 8, 8)

        self.go_now_btn = QPushButton("Go to current time")
        self.go_now_btn.clicked.connect(self.go_to_now)
        v.addWidget(self.go_now_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        tag_controls_box = QWidget()
        tag_controls_layout = QVBoxLayout(tag_controls_box)
        tag_controls_layout.setContentsMargins(0, 0, 0, 0)
        tag_controls_layout.setSpacing(0)
        self.tag_editor_btn = QPushButton("Open tag editor")
        self.tag_editor_btn.clicked.connect(self.open_tag_editor)
        tag_controls_layout.addWidget(self.tag_editor_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        tag_totals_box = QWidget()
        tag_totals_layout = QVBoxLayout(tag_totals_box)
        tag_totals_layout.setContentsMargins(0, 0, 0, 0)
        tag_totals_layout.setSpacing(0)
        totals_label = QLabel("Tag totals (today):")
        totals_label.setStyleSheet("font-weight:600;")
        tag_totals_layout.addWidget(totals_label)
        self.tag_totals_list = QListWidget()
        self.tag_totals_list.setFixedWidth(240)
        self.tag_totals_list.setMaximumHeight(160)
        self.tag_totals_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        tag_totals_layout.addWidget(self.tag_totals_list)
        tag_controls_layout.addWidget(tag_totals_box, alignment=Qt.AlignmentFlag.AlignLeft)
        v.addWidget(tag_controls_box, alignment=Qt.AlignmentFlag.AlignLeft)

        self.calendar = MiniCalendar(self.prefs)
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setFixedSize(QSize(260, 240))
        self.calendar.setSelectedDate(self.current_date)
        v.addWidget(self.calendar, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.calendar_dock.setWidget(cal_container); self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.calendar_dock)

        # Signals / timers
        self.calendar.selectionChanged.connect(self.on_calendar_changed)
        self.statusBar().showMessage("Ready", 1500)
        self.now_timer = QTimer(self); self.now_timer.timeout.connect(self.update_now_line)
        self._align_now_timer()

        self.update_date_label(); self.load_day(self.current_date); self.update_now_line()

        # Center on current time at launch (after layout stabilizes)
        QTimer.singleShot(0, self.center_on_current_time)

    # --- scrolling helpers ---
    def center_on_minute(self, minute: int):
        y = self.day_view.minute_to_y(minute)
        sb = self.scroll_area.verticalScrollBar()
        target = int(y - self.scroll_area.viewport().height() / 2)
        target = max(0, min(target, sb.maximum()))
        sb.setValue(target)

    def center_on_current_time(self):
        now = QTime.currentTime()
        m = now.hour() * 60 + now.minute()
        self.center_on_minute(m)

    def go_to_now(self):
        today = QDate.currentDate()
        if self.calendar.selectedDate() != today:
            self.calendar.setSelectedDate(today)  # will trigger on_calendar_changed
        # Ensure we center after the day loads
        QTimer.singleShot(0, self.center_on_current_time)

    def _format_minutes_compact(self, minutes: int) -> str:
        minutes = max(0, int(minutes))
        h, m = divmod(minutes, 60)
        parts: List[str] = []
        if h:
            parts.append(f"{h}h")
        if m or not parts:
            parts.append(f"{m}m")
        return " ".join(parts)

    def rebuild_tag_totals(self):
        totals: Dict[str, int] = {}
        for ev in getattr(self.day_view, "event_widgets", []):
            tag = (getattr(ev, "tag", "") or "").strip()
            if not tag:
                continue
            duration = max(0, ev.end_min - ev.start_min)
            totals[tag] = totals.get(tag, 0) + duration
        items = [(tag, totals[tag]) for tag in sorted(totals.keys(), key=lambda s: s.lower())]
        if hasattr(self, "tag_totals_list"):
            self.tag_totals_list.blockSignals(True)
            self.tag_totals_list.clear()
            if not items:
                self.tag_totals_list.addItem("No tagged events today")
            else:
                for tag, minutes in items:
                    self.tag_totals_list.addItem(f"{tag}: {self._format_minutes_compact(minutes)}")
            self.tag_totals_list.blockSignals(False)

    def open_tag_editor(self):
        tags = self.known_tags()
        dlg = TagEditorDialog(tags, self)
        dlg.exec()
        removed = dlg.removed_tags()
        if not removed:
            self.flash_status("No tags deleted")
            return
        changed = self._remove_tags_from_all(set(removed))
        if changed:
            plural = "s" if len(removed) != 1 else ""
            self.flash_status(f"Tag{plural} removed")
            self.day_view.update()
            self.rebuild_tag_totals()
        else:
            self.flash_status("Tags already cleared")

    # timers
    def _align_now_timer(self):
        now = QTime.currentTime()
        ms_to_next_min = (60 - now.second()) * 1000 - now.msec()
        if ms_to_next_min <= 0: ms_to_next_min = 1000
        QTimer.singleShot(ms_to_next_min, self._start_minute_timer)
    def _start_minute_timer(self):
        self.update_now_line(); self.now_timer.start(60_000)
    def _init_shortcuts(self):
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.undo_shortcut.activated.connect(self.perform_undo)
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.redo_shortcut.activated.connect(self.perform_redo)
        self.redo_shortcut_alt = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.redo_shortcut_alt.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.redo_shortcut_alt.activated.connect(self.perform_redo)

    # toolbar actions
    def on_time_size_changed(self, text: str):
        try:
            minutes = int(text)
        except ValueError:
            minutes = self.day_view.time_size_minutes
        minutes = max(1, minutes)
        self.prefs.time_size_minutes = minutes
        if hasattr(self, "day_view"):
            self.day_view.set_time_size(minutes)
        self.statusBar().showMessage(f"Time size set to {minutes} min", 1500)
    def update_snap_toggle_text(self):
        if getattr(self, "snap_toggle", None) is None:
            return
        self.snap_toggle.setText("Snap On" if self.snap_toggle.isChecked() else "Snap Off")
    def on_snap_toggle(self, checked: bool):
        self.prefs.time_snap_enabled = bool(checked)
        self.prefs.save(PREF_PATH)
        if hasattr(self, "day_view"):
            self.day_view.set_snap_enabled(bool(checked))
        self.update_snap_toggle_text()
        msg = "Time snap enabled" if checked else "Time snap disabled"
        self.statusBar().showMessage(msg, 1500)
    def on_smart_scale_toggled(self, checked: bool):
        self.prefs.smart_scale_enabled = bool(checked)
        self.prefs.save(PREF_PATH)
        if checked and getattr(self, "magnetic_btn", None):
            self.magnetic_btn.blockSignals(True)
            self.magnetic_btn.setChecked(False)
            self.magnetic_btn.blockSignals(False)
            self.prefs.magnetic_mode = False
            if hasattr(self, "day_view"):
                self.day_view.set_magnetic_mode(False)
        if hasattr(self, "day_view"):
            self.day_view.set_smart_scale_enabled(bool(checked))
        msg = "Smart scale on" if checked else "Smart scale off"
        self.statusBar().showMessage(msg, 1500)
    def on_magnetic_toggled(self, checked: bool):
        self.prefs.magnetic_mode = bool(checked)
        self.prefs.save(PREF_PATH)
        if checked and getattr(self, "smart_scale_btn", None):
            self.smart_scale_btn.blockSignals(True)
            self.smart_scale_btn.setChecked(False)
            self.smart_scale_btn.blockSignals(False)
            self.prefs.smart_scale_enabled = False
            if hasattr(self, "day_view"):
                self.day_view.set_smart_scale_enabled(False)
        if hasattr(self, "day_view"):
            self.day_view.set_magnetic_mode(bool(checked))
        msg = "Magnetic mode on" if checked else "Magnetic mode off"
        self.statusBar().showMessage(msg, 1500)
    def on_time_format_changed(self, text: str):
        self.prefs.time_24h = (text.strip() == "24h"); self.prefs.save(PREF_PATH)
        self.day_view.set_prefs(self.prefs)
    def on_zoom_changed(self, val: int):
        self.zoom_label.setText(f"{val}%"); self.prefs.zoom_percent = int(val); self.prefs.save(PREF_PATH)
        self.day_view.set_zoom_from_percent(val)
    def on_box_select_toggled(self, checked: bool):
        if hasattr(self, "day_view"):
            self.day_view.set_box_select_mode(bool(checked))
        msg = "Box select enabled" if checked else "Box select disabled"
        self.statusBar().showMessage(msg, 1500)
    def on_box_selection_changed(self, count: int, total_minutes: int):
        if count > 0:
            label = "event" if count == 1 else "events"
            total_text = self.day_view._format_remaining_minutes(total_minutes)
            self.statusBar().showMessage(f"{count} {label} selected • {total_text} total", 2500)
        elif getattr(self, "box_select_btn", None) and self.box_select_btn.isChecked():
            self.statusBar().showMessage("No events selected", 1500)
    def _history_entries_for_dialog(self) -> List[dict]:
        display_entries: List[dict] = []
        for idx, entry in enumerate(self._history):
            if entry.get("action") == "Initial load":
                continue
            cloned = dict(entry)
            cloned["_history_index"] = idx
            display_entries.append(cloned)
        return display_entries

    def show_history_dialog(self):
        display_entries = self._history_entries_for_dialog()
        if not display_entries:
            self.statusBar().showMessage("History is empty", 1500)
            return
        dialog = HistoryDialog(display_entries, on_clear=self.clear_history_entries, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_index is not None:
            self.restore_history_entry(int(dialog.selected_index))
    def restore_history_entry(self, index: int):
        if not (0 <= index < len(self._history)):
            self.statusBar().showMessage("History entry unavailable", 1500)
            return
        snapshot = self._history[index]
        self._history_index = index
        self._history_freeze = True
        try:
            self._apply_history_snapshot(snapshot)
        finally:
            self._history_freeze = False
        self._pending_history_action = None
        label = snapshot.get("action", "History restored")
        self._write_history_file()
        self.statusBar().showMessage(f"Restored: {label}", 2000)
    def perform_undo(self):
        if self._history_index <= 0 or not self._history:
            self.statusBar().showMessage("Nothing to undo", 1500)
            return
        self._history_index -= 1
        self._history_freeze = True
        try:
            snapshot = self._history[self._history_index]
            self._apply_history_snapshot(snapshot)
        finally:
            self._history_freeze = False
        self._pending_history_action = None
        self.statusBar().showMessage("Undo complete", 1500)
    def perform_redo(self):
        if not self._history or self._history_index >= len(self._history) - 1:
            self.statusBar().showMessage("Nothing to redo", 1500)
            return
        self._history_index += 1
        self._history_freeze = True
        try:
            snapshot = self._history[self._history_index]
            self._apply_history_snapshot(snapshot)
        finally:
            self._history_freeze = False
        self._pending_history_action = None
        self.statusBar().showMessage("Redo complete", 1500)
    def clear_history_entries(self) -> List[dict]:
        self._history = []
        self._history_index = -1
        self._pending_history_action = None
        self._history_freeze = False
        self._reset_history(self.current_date)
        self.statusBar().showMessage("History cleared", 1500)
        return self._history_entries_for_dialog()

    # prefs
    def open_prefs(self):
        dlg = PreferencesDialog(self.prefs, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.prefs = dlg.result_prefs(); self.prefs.save(PREF_PATH)
            self.time_combo.setCurrentText("24h" if self.prefs.time_24h else "12h")
            self.zoom_slider.setValue(int(self.prefs.zoom_percent))
            self.day_view.set_prefs(self.prefs)
            self.calendar.set_prefs(self.prefs)
            if hasattr(self, "time_size_combo"):
                self.time_size_combo.blockSignals(True)
                self.time_size_combo.setCurrentText(str(self.prefs.time_size_minutes))
                self.time_size_combo.blockSignals(False)
            if hasattr(self, "snap_toggle"):
                self.snap_toggle.blockSignals(True)
                self.snap_toggle.setChecked(self.prefs.time_snap_enabled)
                self.snap_toggle.blockSignals(False)
            if hasattr(self, "magnetic_btn"):
                self.magnetic_btn.blockSignals(True)
                self.magnetic_btn.setChecked(bool(self.prefs.magnetic_mode))
                self.magnetic_btn.blockSignals(False)
            if hasattr(self, "smart_scale_btn"):
                self.smart_scale_btn.blockSignals(True)
                self.smart_scale_btn.setChecked(bool(self.prefs.smart_scale_enabled))
                self.smart_scale_btn.blockSignals(False)
            self.update_snap_toggle_text()
            self.day_view.set_magnetic_mode(self.prefs.magnetic_mode)
            self.day_view.set_smart_scale_enabled(self.prefs.smart_scale_enabled)

    # date helpers
    def date_key(self, qd: QDate) -> str: return qd.toString("yyyy-MM-dd")
    def update_date_label(self): self.date_label.setText(f"  Viewing: <b>{self.current_date.toString('dddd, MMM d, yyyy')}</b>")

    # calendar change
    def on_calendar_changed(self):
        self.save_day(self.current_date)
        self.current_date = self.calendar.selectedDate()
        self.update_date_label(); self.load_day(self.current_date); self.update_now_line()

    # now line
    def update_now_line(self):
        is_today = (self.current_date == QDate.currentDate())
        self.day_view.show_now_line = is_today
        self.day_view.update()
        for ev in self.day_view.event_widgets:
            ev.update()
        actual_today = QDate.currentDate()
        if self._notification_schedule_date != actual_today:
            self.refresh_notifications()

    # notifications (macOS)
    def clear_notification_timers(self):
        for t in self.notification_timers:
            try:
                t.stop()
            except Exception:
                pass
            t.deleteLater()
        self.notification_timers.clear()

    def refresh_notifications(self):
        self.clear_notification_timers()
        today = QDate.currentDate()
        self._notification_schedule_date = today
        if sys.platform != "darwin":
            return
        now = QDateTime.currentDateTime()
        key = self.date_key(today)
        scheduled: List[tuple[str, int, int, Optional[str]]] = []
        for item in self.events_by_date.get(key, []):
            try:
                start_min = int(item.get("start_min", 0))
            except Exception:
                continue
            offset = int(item.get("notify_offset", 0))
            if offset <= 0:
                continue
            image_rel = (item.get("image") or "").strip() or None
            scheduled.append((item.get("title", ""), start_min, offset, image_rel))
        for r in self.repeat_rules:
            if str(r.get("type", "")).upper() != "DAILY":
                continue
            offset = int(r.get("notify_offset", 0))
            if offset <= 0:
                continue
            try:
                start_min = int(r.get("start_min", 0))
            except Exception:
                continue
            image_rel = (r.get("image") or "").strip() or None
            scheduled.append((r.get("title", ""), start_min, offset, image_rel))

        for title, start_min, offset, image_rel in scheduled:
            if start_min < 0 or start_min >= 24 * 60:
                continue
            trigger_minute = start_min - offset
            if trigger_minute < 0:
                continue
            trigger_time = QTime(trigger_minute // 60, trigger_minute % 60)
            trigger_dt = QDateTime(today, trigger_time)
            if trigger_dt <= now:
                continue
            msecs = now.msecsTo(trigger_dt)
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda t=title, s=start_min, img=image_rel: self.show_mac_notification(t, s, img))
            timer.start(msecs)
            self.notification_timers.append(timer)

    def show_mac_notification(self, title: str, start_min: int, image_rel: Optional[str] = None,
                              sound_path: Optional[str] = None):
        if sys.platform != "darwin":
            return
        safe_start = max(0, min(24 * 60 - 1, int(start_min)))
        event_title = (title or "Upcoming event").strip() or "Upcoming event"
        time_text = self.day_view.min_to_hhmm(safe_start)
        message = f"{event_title} starts at {time_text}"
        subtitle = "iCal-ish Reminder"

        image_path: Optional[Path] = None
        if image_rel:
            candidate = Path(image_rel)
            if not candidate.is_absolute():
                candidate = APP_DIR / candidate
            if candidate.exists():
                image_path = candidate

        parts = [
            f'display notification {json.dumps(message)}',
            f'with title {json.dumps(event_title)}',
            f'subtitle {json.dumps(subtitle)}',
        ]
        if image_path is not None:
            parts.append(f'content image POSIX file {json.dumps(str(image_path))}')
        script = " ".join(parts)
        try:
            result = subprocess.run(["osascript", "-e", script], check=False)
            if result.returncode != 0:
                raise RuntimeError("osascript failed")
        except Exception:
            fallback = " ".join(parts[:3])
            try:
                subprocess.run(["osascript", "-e", fallback], check=False)
            except Exception:
                pass
        self.play_notification_sound(sound_path)
 
    def play_notification_sound(self, sound_path: Optional[str] = None):
        chosen_path = ""
        if sound_path is not None:
            chosen_path = sound_path.strip()
        else:
            chosen_path = getattr(self.prefs, "notify_sound_path", "").strip()
        if not chosen_path:
            return
        audio_file = Path(chosen_path).expanduser()
        if not audio_file.is_file():
            return
        try:
            if self.notification_player is None:
                self.notification_audio = QAudioOutput(self)
                if self.notification_audio is not None:
                    self.notification_audio.setVolume(1.0)
                self.notification_player = QMediaPlayer(self)
                self.notification_player.setAudioOutput(self.notification_audio)
            if self.notification_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.notification_player.stop()
            self.notification_player.setSource(QUrl.fromLocalFile(str(audio_file)))
            self.notification_player.play()
        except Exception:
            pass

    def trigger_test_notification(self, sound_path: str, image_rel: Optional[str] = None):
        chosen = (sound_path or "").strip()
        if not image_rel:
            today = QDate.currentDate()
            key = self.date_key(today)
            for item in self.events_by_date.get(key, []):
                rel = (item.get("image") or "").strip()
                if rel:
                    image_rel = rel
                    break
            if not image_rel:
                for r in self.repeat_rules:
                    if str(r.get("type", "")).upper() != "DAILY":
                        continue
                    rel = (r.get("image") or "").strip()
                    if rel:
                        image_rel = rel
                        break
        if sys.platform == "darwin":
            now = QTime.currentTime()
            start_min = now.hour() * 60 + now.minute()
            self.show_mac_notification(
                "Preferences Test",
                start_min,
                image_rel=image_rel,
                sound_path=chosen if chosen else None,
            )
            return
        else:
            QMessageBox.information(
                self,
                "Notification Test",
                "Toast notifications require macOS. Playing audio only.",
            )
        self.play_notification_sound(chosen if chosen else None)

    # rules (daily)
    def compute_next_rule_id(self) -> int:
        mx = 0
        for r in self.repeat_rules:
            try: mx = max(mx, int(r.get("id", 0)))
            except Exception: pass
        return mx + 1

    def add_daily_rule(self, start_min: int, end_min: int, title: str, color_hex: str, locked: bool=False,
                       image_rel: Optional[str]=None, notify_offset: int = 0, tag: str = ""):
        rid = str(self._next_rule_id); self._next_rule_id += 1
        self.repeat_rules.append({
            "id": rid, "type": "DAILY",
            "start_min": int(start_min), "end_min": int(end_min),
            "title": title, "color": color_hex, "locked": 1 if locked else 0,
            "image": image_rel or "",
            "tag": tag or "",
            "notify_offset": int(notify_offset),
        })
        self.save_rules(); self.load_day(self.current_date)

    def update_daily_rule(self, rid: Optional[str], start_min: int, end_min: int, title: str, color_hex: str,
                          image_rel: Optional[str], notify_offset: int, tag: str) -> bool:
        if rid is None: return False
        for r in self.repeat_rules:
            if str(r.get("id")) == str(rid):
                if int(r.get("locked", 0)) == 1: return False
                r["start_min"] = int(start_min); r["end_min"] = int(end_min)
                r["title"] = title; r["color"] = color_hex; r["image"] = image_rel or ""
                r["notify_offset"] = int(notify_offset); r["tag"] = tag or ""
                self.save_rules(); return True
        return False

    def delete_daily_rule(self, rid: Optional[str]) -> Optional[str]:
        if rid is None: return None
        for i, r in enumerate(self.repeat_rules):
            if str(r.get("id")) == str(rid):
                if int(r.get("locked", 0)) == 1: return None
                img = r.get("image") or None
                self.repeat_rules.pop(i); self.save_rules(); return img
        return None

    def delete_daily_rule_with_cleanup(self, rid: Optional[str]):
        img = self.delete_daily_rule(rid)
        if img: self.try_delete_image_if_unreferenced(img)

    def rule_locked(self, rid: Optional[str]) -> bool:
        if rid is None: return False
        for r in self.repeat_rules:
            if str(r.get("id")) == str(rid): return int(r.get("locked", 0)) == 1
        return False

    def set_rule_locked(self, rid: Optional[str], locked: bool):
        if rid is None: return
        for r in self.repeat_rules:
            if str(r.get("id")) == str(rid):
                r["locked"] = 1 if locked else 0; self.save_rules(); return

    def load_rules(self) -> List[dict]:
        rules: List[dict] = []
        if not RULES_PATH.exists(): return rules
        try:
            with RULES_PATH.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rtype = (row.get("type") or "").strip().upper()
                    if rtype == "DAILY":
                        try:
                            rules.append({
                                "id": row.get("id") or "0",
                                "type": "DAILY",
                                "start_min": int(row.get("start_min", 0)),
                                "end_min": int(row.get("end_min", 0)),
                                "title": row.get("title", ""),
                                "tag": row.get("tag", "") or "",
                                "color": row.get("color", "#4879C5"),
                                "locked": int(row.get("locked", "0")),
                                "image": row.get("image", ""),
                                "notify_offset": int(row.get("notify_offset", 0)),
                            })
                        except Exception:
                            continue
        except Exception as e:
            QMessageBox.warning(self, "Load Rules Error", f"Failed to load rules.csv: {e}")
        changed = False; next_id = 1
        for r in rules:
            if not r.get("id") or r.get("id") == "0":
                r["id"] = str(next_id); next_id += 1; changed = True
        if changed:
            self.repeat_rules = rules; self.save_rules()
        return rules

    def save_rules(self):
        try:
            with RULES_PATH.open("w", encoding="utf-8", newline="") as f:
                fieldnames = ["id", "type", "start_min", "end_min", "title", "tag", "color", "locked", "image", "notify_offset"]
                writer = csv.DictWriter(f, fieldnames=fieldnames); writer.writeheader()
                for r in self.repeat_rules:
                    writer.writerow({
                        "id": r.get("id", ""), "type": r.get("type", "DAILY"),
                        "start_min": r.get("start_min", 0), "end_min": r.get("end_min", 0),
                        "title": r.get("title", ""), "tag": r.get("tag", "") or "",
                        "color": r.get("color", "#4879C5"),
                        "locked": r.get("locked", 0), "image": r.get("image", ""),
                        "notify_offset": r.get("notify_offset", 0),
                    })
        except Exception as e:
            QMessageBox.warning(self, "Save Rules Error", f"Failed to save rules.csv: {e}")

    # dated persistence
    def load_data(self) -> Dict[str, List[dict]]:
        result: Dict[str, List[dict]] = {}
        if not DATA_PATH.exists(): return result
        try:
            with DATA_PATH.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = row.get("date", "")
                    if not key:
                        continue
                    if key not in result:
                        result[key] = []
                    try:
                        result[key].append({
                            "start_min": int(row.get("start_min", 0)),
                            "end_min": int(row.get("end_min", 0)),
                            "title": row.get("title", ""),
                            "tag": row.get("tag", "") or "",
                            "color": row.get("color", "#4879C5"),
                            "locked": int(row.get("locked", "0")),
                            "image": row.get("image", ""),
                            "notify_offset": int(row.get("notify_offset", 0)),
                        })
                    except Exception:
                        continue
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load data.csv: {e}")
        return result

    def save_all_data(self):
        try:
            with DATA_PATH.open("w", encoding="utf-8", newline="") as f:
                fieldnames = ["date", "start_min", "end_min", "title", "tag", "color", "locked", "image", "notify_offset"]
                writer = csv.DictWriter(f, fieldnames=fieldnames); writer.writeheader()
                for date_key, items in sorted(self.events_by_date.items()):
                    for it in items:
                        writer.writerow({
                            "date": date_key,
                            "start_min": it["start_min"], "end_min": it["end_min"],
                            "title": it.get("title", ""), "tag": it.get("tag", "") or "",
                            "color": it.get("color", "#4879C5"),
                            "locked": int(it.get("locked", 0)), "image": it.get("image", "") or "",
                            "notify_offset": int(it.get("notify_offset", 0)),
                        })
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save data.csv: {e}")

    def save_day(self, qdate: QDate):
        key = self.date_key(qdate); data = []
        for ev in self.day_view.event_widgets:
            if getattr(ev, "from_rule", False): continue
            data.append({
                "start_min": ev.start_min, "end_min": ev.end_min, "title": ev.title,
                "tag": getattr(ev, "tag", "") or "",
                "color": qcolor_to_hex(ev.color), "locked": 1 if ev.locked else 0,
                "image": ev.image_rel or "",
                "notify_offset": int(getattr(ev, "notify_offset", 0)),
            })
        self.events_by_date[key] = data; self.save_all_data()

    def load_day(self, qdate: QDate, reset_history: bool = True):
        self.day_view.clear_blocks(); key = self.date_key(qdate)
        # dated
        for item in sorted(self.events_by_date.get(key, []), key=lambda x: x["start_min"]):
            color = hex_to_qcolor(item.get("color", "#4879C5"), "#4879C5")
            self.day_view.add_block(
                item["start_min"], item["end_min"] - item["start_min"], item.get("title", ""),
                color, from_rule=False, rule_id=None, locked=bool(int(item.get("locked", 0))),
                image_rel=item.get("image") or None, tag=item.get("tag", "") or "",
                notify_offset=int(item.get("notify_offset", 0)), record_history=False
            )
        # rules
        for r in self.repeat_rules:
            if r.get("type") == "DAILY":
                color = hex_to_qcolor(r.get("color", "#4879C5"), "#4879C5")
                self.day_view.add_block(
                    r["start_min"], r["end_min"] - r["start_min"], r.get("title", ""), color,
                    from_rule=True, rule_id=str(r.get("id")), locked=bool(int(r.get("locked", 0))),
                    image_rel=r.get("image") or None, tag=r.get("tag", "") or "",
                    notify_offset=int(r.get("notify_offset", 0)), record_history=False
                )
        self.day_view.update()
        self.refresh_notifications()
        if reset_history:
            self._reset_history(qdate)
        self.rebuild_tag_totals()

    def _history_snapshot(self, qdate: Optional[QDate] = None) -> Optional[dict]:
        if not hasattr(self, "events_by_date"):
            return None
        if qdate is None:
            qdate = self.current_date
        if qdate is None:
            return None
        key = self.date_key(qdate)
        data = deepcopy(self.events_by_date.get(key, []))
        return {"date": key, "events": data}

    def _reset_history(self, qdate: Optional[QDate] = None):
        snap = self._history_snapshot(qdate)
        if snap is None:
            self._history = []
            self._history_index = -1
            self._write_history_file()
            return
        snap["action"] = "Initial load"
        snap["timestamp"] = QDateTime.currentDateTime().toString(Qt.ISODate)
        self._history = [snap]
        self._history_index = 0
        self._pending_history_action = None
        self._write_history_file()

    def note_history_action(self, action: str):
        if action:
            self._pending_history_action = action

    def _record_history(self):
        if self._history_freeze:
            return
        snap = self._history_snapshot()
        if snap is None:
            return
        action = self._pending_history_action or "Change"
        self._pending_history_action = None
        snap["action"] = action
        snap["timestamp"] = QDateTime.currentDateTime().toString(Qt.ISODate)
        if self._history_index >= 0 and self._history and snap["events"] == self._history[self._history_index].get("events"):
            return
        if self._history_index < len(self._history) - 1:
            self._history = self._history[:self._history_index + 1]
        self._history.append(snap)
        self._history_index += 1
        if len(self._history) > self._history_max:
            excess = len(self._history) - self._history_max
            del self._history[:excess]
            self._history_index = max(0, self._history_index - excess)
        self._write_history_file()

    def _apply_history_snapshot(self, snapshot: dict):
        if not snapshot:
            return
        key = snapshot.get("date")
        if not key:
            return
        self.events_by_date[key] = deepcopy(snapshot.get("events", []))
        target_date = QDate.fromString(key, "yyyy-MM-dd")
        if target_date.isValid():
            self.current_date = target_date
            if hasattr(self, "calendar"):
                try:
                    self.calendar.blockSignals(True)
                    self.calendar.setSelectedDate(target_date)
                finally:
                    self.calendar.blockSignals(False)
            self.update_date_label()
            self.load_day(target_date, reset_history=False)
        else:
            self.load_day(self.current_date, reset_history=False)
        self.save_all_data()
        self.refresh_notifications()

    def _write_history_file(self):
        entries = [entry for entry in self._history if entry.get("action") != "Initial load"]
        if not entries:
            self._clear_history_file()
            return
        entries = entries[-10:]
        try:
            with HISTORY_PATH.open("w", encoding="utf-8", newline="") as f:
                fieldnames = ["timestamp", "action", "date", "events"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for entry in entries:
                    writer.writerow({
                        "timestamp": entry.get("timestamp", ""),
                        "action": entry.get("action", ""),
                        "date": entry.get("date", ""),
                        "events": json.dumps(entry.get("events", [])),
                    })
        except Exception:
            pass

    def _clear_history_file(self):
        try:
            if HISTORY_PATH.exists():
                HISTORY_PATH.unlink()
        except Exception:
            pass


    # image ref counting / cleanup
    def count_image_references(self, rel_path: str) -> int:
        if not rel_path: return 0
        count = 0
        for items in self.events_by_date.values():
            for it in items:
                if (it.get("image") or "") == rel_path: count += 1
        for r in self.repeat_rules:
            if (r.get("image") or "") == rel_path: count += 1
        return count

    def try_delete_image_if_unreferenced(self, rel_path: Optional[str]):
        if not rel_path: return
        if self.count_image_references(rel_path) == 0:
            abs_path = APP_DIR / rel_path
            try:
                if abs_path.exists() and abs_path.is_file():
                    abs_path.unlink(); self.flash_status("Unused image file removed")
            except Exception:
                pass

    def on_day_changed(self):
        self.save_day(self.current_date)
        self.refresh_notifications()
        self.rebuild_tag_totals()
        self._record_history()

    def known_tags(self) -> List[str]:
        tags: Set[str] = set()
        for items in self.events_by_date.values():
            for it in items:
                tag = (it.get("tag") or "").strip()
                if tag:
                    tags.add(tag)
        for ev in getattr(self.day_view, "event_widgets", []):
            tag = (getattr(ev, "tag", "") or "").strip()
            if tag:
                tags.add(tag)
        for r in self.repeat_rules:
            tag = (r.get("tag") or "").strip()
            if tag:
                tags.add(tag)
        return sorted(tags, key=lambda s: s.lower())

    def _remove_tags_from_all(self, tags_to_remove: Set[str]) -> bool:
        normalized = {t.strip() for t in tags_to_remove if t and t.strip()}
        if not normalized:
            return False
        events_changed = False
        for items in self.events_by_date.values():
            for it in items:
                if (it.get("tag") or "").strip() in normalized:
                    it["tag"] = ""
                    events_changed = True
        rules_changed = False
        for r in self.repeat_rules:
            if (r.get("tag") or "").strip() in normalized:
                r["tag"] = ""
                rules_changed = True
        view_changed = False
        for ev in getattr(self.day_view, "event_widgets", []):
            if (ev.tag or "").strip() in normalized:
                ev.tag = ""
                ev.update()
                view_changed = True
        if events_changed:
            self.save_all_data()
        if rules_changed:
            self.save_rules()
        return events_changed or rules_changed or view_changed

    def duplicate_weekly(self, start_min: int, end_min: int, title: str, color_hex: str,
                          wdys: List[int], weeks: int, image_rel: Optional[str]=None,
                          notify_offset: int = 0, tag: Optional[str]=None) -> int:
        total_days = weeks * 7; added = 0
        for d in range(1, total_days + 1):
            date = self.current_date.addDays(d)
            if date.dayOfWeek() in wdys:
                if self.add_event_to_date(date, start_min, end_min, title, color_hex,
                                          image_rel=image_rel, notify_offset=notify_offset, tag=tag):
                    added += 1
        return added

    def add_event_to_date(self, qdate: QDate, start_min: int, end_min: int, title: str, color_hex: str,
                          locked: bool=False, image_rel: Optional[str]=None, notify_offset: int = 0,
                          tag: Optional[str]=None) -> bool:
        key = self.date_key(qdate)
        for it in self.events_by_date.get(key, []):
            if max(start_min, it["start_min"]) < min(end_min, it["end_min"]):
                return False
        self.events_by_date.setdefault(key, []).append({
            "start_min": start_min, "end_min": end_min, "title": title, "color": color_hex,
            "tag": tag or "",
            "locked": 1 if locked else 0, "image": image_rel or "",
            "notify_offset": int(notify_offset),
        })
        if qdate == self.current_date:
            self.day_view.add_block(start_min, end_min - start_min, title, hex_to_qcolor(color_hex),
                                    locked=locked, image_rel=image_rel, tag=tag or "",
                                    notify_offset=notify_offset,
                                    record_history=False)
            self.refresh_notifications()
        self.save_all_data(); return True

    def flash_status(self, msg: str, warn: bool = False):
        if warn: self.statusBar().setStyleSheet("color:#b00020;")
        else: self.statusBar().setStyleSheet("")
        self.statusBar().showMessage(msg, 2500)

    def closeEvent(self, e):
        try:
            self.clear_notification_timers()
            self.save_day(self.current_date); self.save_all_data(); self.save_rules()
            self._clear_history_file()
        finally:
            super().closeEvent(e)


def main():
    import sys
    ensure_uploads()
    app = QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
