"""
VP CTRL v3 — Camera panel.
Grid 4x2 de cards + sidebar lateral com sliders do path ativo.
EDIT: clique na thumb A/B → GoTo. REC grava.
PLAY: clique no card → dispara OSC trigger.
"""
import logging
import os
import threading
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMetaObject
from PyQt6.QtGui import QPixmap, QPixmapCache
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QDoubleSpinBox,
    QScrollArea, QDialog, QSlider, QSizePolicy, QLineEdit,
)

from core.http_client import (
    set_path_field_async, fetch_paths, warm_cache,
)
from core.osc_client import (
    osc_trigger_path, osc_set_active_path,
    osc_goto_a, osc_goto_b, osc_record_a, osc_record_b,
    osc_focal_a, osc_focal_b, osc_focus_a, osc_focus_b, osc_duration,
)
from PyQt6.QtCore import QRect, QSize, QPoint
from PyQt6.QtWidgets import QLayout, QLayoutItem
from data.models import AppState
from config.settings import GRAVAR_PULSE_MS

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Flow Layout — quebra linha automaticamente conforme largura disponível
# ──────────────────────────────────────────────────────────────────────────────

class _FlowLayout(QLayout):
    """Layout que distribui widgets em linhas, quebrando conforme a largura."""

    def __init__(self, parent=None, h_spacing=8, v_spacing=8):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items: list = []

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self): return self._h_spacing
    def verticalSpacing(self):   return self._v_spacing
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True

    def heightForWidth(self, width: int) -> int:
        return self._layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._layout(rect, test_only=False)

    def sizeHint(self):     return self.minimumSize()
    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def count(self): return len(self._items)
    def itemAt(self, index):
        if 0 <= index < len(self._items): return self._items[index]
    def takeAt(self, index):
        if 0 <= index < len(self._items): return self._items.pop(index)

    def _layout(self, rect: QRect, test_only: bool) -> int:
        x, y = rect.x(), rect.y()
        row_h = 0
        for item in self._items:
            w = item.widget()
            hint = item.sizeHint()
            next_x = x + hint.width()
            if next_x > rect.right() and x > rect.x():
                x = rect.x()
                y += row_h + self._v_spacing
                next_x = x + hint.width()
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._h_spacing
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y()

THUMB_DIR = ""   # definido em runtime via CameraPanel.set_thumb_dir()
THUMB_W, THUMB_H = 200, 113   # 16:9

_ACTIVE_POINT: dict[int, str] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Thumb button
# ──────────────────────────────────────────────────────────────────────────────

class _ThumbBtn(QLabel):
    clicked = pyqtSignal()

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._img_path = ""
        self._color = color
        self._active = False
        self.setFixedSize(THUMB_W, THUMB_H)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_empty()

    def _set_empty(self):
        self.setText("sem imagem")
        self.setStyleSheet(
            f"background:#0d1117; border:1px solid #30363d; border-radius:5px; color:#484f58; font-size:10px;"
        )

    def load(self, filepath: str):
        self._img_path = filepath
        if os.path.isfile(filepath):
            QPixmapCache.remove(filepath)
            px = QPixmap(filepath).scaled(
                THUMB_W, THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(px)
            self.setText("")
        else:
            self.clear()
            self._set_empty()
        self._refresh_border()

    def set_active(self, active: bool):
        self._active = active
        self._refresh_border()

    def _refresh_border(self):
        has_img = self._img_path and os.path.isfile(self._img_path)
        base = "background:#0d1117; border-radius:5px;"
        if not has_img:
            base += " color:#484f58; font-size:10px;"
        if self._active:
            self.setStyleSheet(f"{base} border: 2px solid {self._color};")
        else:
            self.setStyleSheet(f"{base} border: 1px solid #30363d;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self._img_path and os.path.isfile(self._img_path):
                dlg = QDialog(self)
                dlg.setWindowTitle(os.path.basename(self._img_path))
                dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
                lbl = QLabel(dlg)
                px = QPixmap(self._img_path)
                screen = self.screen().availableGeometry()
                lbl.setPixmap(px.scaled(
                    int(screen.width() * 0.8), int(screen.height() * 0.8),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                lay = QVBoxLayout(dlg)
                lay.setContentsMargins(4, 4, 4, 4)
                lay.addWidget(lbl)
                dlg.adjustSize()
                dlg.exec()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# Slider row
# ──────────────────────────────────────────────────────────────────────────────

class _SliderRow(QWidget):
    value_changed = pyqtSignal(float)

    def __init__(self, label: str, mn: float, mx: float, val: float,
                 decimals: int = 1, step: float = 1.0, scale: int = 10):
        super().__init__()
        self._mn = mn; self._mx = mx; self._scale = scale
        self._blocking = False
        self._debounce = QTimer(); self._debounce.setSingleShot(True)
        self._debounce.setInterval(80)
        self._debounce.timeout.connect(self._flush)
        self._pending = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(68)
        lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        lay.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(int(mn * scale), int(mx * scale))
        self._slider.setValue(int(val * scale))
        lay.addWidget(self._slider, 1)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(mn, mx)
        self._spin.setDecimals(decimals)
        self._spin.setSingleStep(step)
        self._spin.setValue(val)
        self._spin.setFixedWidth(78)
        lay.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.editingFinished.connect(self._on_spin)

    def value(self): return self._spin.value()

    def setValue(self, v: float):
        self._blocking = True
        v = max(self._mn, min(self._mx, v))
        self._spin.setValue(v)
        self._slider.setValue(int(v * self._scale))
        self._blocking = False

    def _on_slider(self, iv):
        if self._blocking: return
        v = iv / self._scale
        self._blocking = True; self._spin.setValue(v); self._blocking = False
        self._pending = v; self._debounce.start()

    def _on_spin(self):
        if self._blocking: return
        v = self._spin.value()
        self._blocking = True; self._slider.setValue(int(v * self._scale)); self._blocking = False
        self._pending = v; self._debounce.start()

    def _flush(self):
        if self._pending is not None:
            self.value_changed.emit(self._pending)
            self._pending = None


# ──────────────────────────────────────────────────────────────────────────────
# Path Card — compacto, sem sliders inline
# ──────────────────────────────────────────────────────────────────────────────

class _PathCard(QFrame):
    goto_a       = pyqtSignal(int)
    goto_b       = pyqtSignal(int)
    record       = pyqtSignal(int)
    trigger      = pyqtSignal(int)
    name_changed = pyqtSignal(int, str)  # index, novo nome

    def __init__(self, index: int, state: AppState):
        super().__init__()
        self._index = index
        self._state = state
        self._play_mode = False
        self.setProperty("class", "path-card")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Header
        header = QHBoxLayout()
        header.setSpacing(4)

        self._lbl_name = QLabel(self._state.paths[self._index].name)
        self._lbl_name.setStyleSheet("font-weight:bold; font-size:12px; color:#c9d1d9;")
        self._lbl_name.setCursor(Qt.CursorShape.IBeamCursor)
        self._lbl_name.mouseDoubleClickEvent = self._start_rename
        header.addWidget(self._lbl_name)

        self._edit_name = QLineEdit()
        self._edit_name.setStyleSheet(
            "font-weight:bold; font-size:12px; color:#c9d1d9; "
            "background:#0d1117; border:1px solid #1f6feb; border-radius:3px; padding:0 2px;"
        )
        self._edit_name.setFixedHeight(20)
        self._edit_name.hide()
        self._edit_name.editingFinished.connect(self._finish_rename)
        self._edit_name.installEventFilter(self)
        header.addWidget(self._edit_name)

        header.addStretch()
        self._lbl_status = QLabel("Ready")
        self._lbl_status.setStyleSheet("font-size:10px; color:#8b949e;")
        header.addWidget(self._lbl_status)
        root.addLayout(header)

        # Thumbnails lado a lado
        thumbs = QHBoxLayout()
        thumbs.setSpacing(4)

        col_a = QVBoxLayout(); col_a.setSpacing(1)
        lbl_a = QLabel("A")
        lbl_a.setStyleSheet("color:#1f6feb; font-size:9px; font-weight:bold;")
        lbl_a.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_a = _ThumbBtn("#1f6feb")
        self._thumb_a.clicked.connect(lambda: self._on_thumb("a"))
        col_a.addWidget(lbl_a)
        col_a.addWidget(self._thumb_a)
        thumbs.addLayout(col_a)

        col_b = QVBoxLayout(); col_b.setSpacing(1)
        lbl_b = QLabel("B")
        lbl_b.setStyleSheet("color:#da3633; font-size:9px; font-weight:bold;")
        lbl_b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_b = _ThumbBtn("#da3633")
        self._thumb_b.clicked.connect(lambda: self._on_thumb("b"))
        col_b.addWidget(lbl_b)
        col_b.addWidget(self._thumb_b)
        thumbs.addLayout(col_b)

        root.addLayout(thumbs)

        # REC button (visível só em EDIT)
        self._btn_rec = QPushButton("● REC")
        self._btn_rec.setProperty("class", "btn-rec")
        self._btn_rec.setFixedHeight(22)
        self._btn_rec.clicked.connect(lambda: self.record.emit(self._index))
        root.addWidget(self._btn_rec)

        self._load_thumbs()

    def _on_thumb(self, pt: str):
        if self._play_mode:
            self.trigger.emit(self._index)
        else:
            if pt == "a": self.goto_a.emit(self._index)
            else:         self.goto_b.emit(self._index)

    # ------------------------------------------------------------------
    def set_play_mode(self, play: bool):
        self._play_mode = play
        self._btn_rec.setVisible(not play)
        self._update_status()

    def set_active(self, active: bool, point: str = "a"):
        self._thumb_a.set_active(active and point == "a")
        self._thumb_b.set_active(active and point == "b")
        self._update_status()

    def _update_status(self):
        pt = _ACTIVE_POINT.get(self._index)
        if pt == "a" and not self._play_mode:
            self._lbl_status.setText("● A")
            self._lbl_status.setStyleSheet("font-size:10px; color:#1f6feb; font-weight:bold;")
        elif pt == "b" and not self._play_mode:
            self._lbl_status.setText("● B")
            self._lbl_status.setStyleSheet("font-size:10px; color:#da3633; font-weight:bold;")
        else:
            self._lbl_status.setText("Ready")
            self._lbl_status.setStyleSheet("font-size:10px; color:#8b949e;")

    def _load_thumbs(self):
        n = self._index + 1
        self._thumb_a.load(os.path.join(THUMB_DIR, f"path{n}a.png"))
        self._thumb_b.load(os.path.join(THUMB_DIR, f"path{n}b.png"))

    def reload_thumb(self, pt: str):
        """Recarrega só a thumb A ou B do disco."""
        n = self._index + 1
        if pt == "a":
            self._thumb_a.load(os.path.join(THUMB_DIR, f"path{n}a.png"))
        else:
            self._thumb_b.load(os.path.join(THUMB_DIR, f"path{n}b.png"))

    def refresh(self):
        self._load_thumbs()
        self._update_status()

    def pulse_rec(self):
        self._btn_rec.setEnabled(False)
        QTimer.singleShot(GRAVAR_PULSE_MS, self._restore_rec)

    def _restore_rec(self):
        self._btn_rec.setProperty("class", "btn-rec")
        self._btn_rec.style().unpolish(self._btn_rec)
        self._btn_rec.style().polish(self._btn_rec)
        self._btn_rec.setEnabled(True)

    # ------------------------------------------------------------------
    # Rename inline
    # ------------------------------------------------------------------

    def _start_rename(self, _event=None):
        self._edit_name.setText(self._lbl_name.text())
        self._lbl_name.hide()
        self._edit_name.show()
        self._edit_name.selectAll()
        self._edit_name.setFocus()

    def _finish_rename(self):
        name = self._edit_name.text().strip()
        if not name:
            name = f"PATH {self._index + 1:02d}"
        self._lbl_name.setText(name)
        self._edit_name.hide()
        self._lbl_name.show()
        self._state.paths[self._index].name = name
        self._state.save()
        self.name_changed.emit(self._index, name)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._edit_name and event.type() == QEvent.Type.KeyPress:
            from PyQt6.QtCore import Qt as _Qt
            if event.key() == _Qt.Key.Key_Escape:
                self._edit_name.hide()
                self._lbl_name.show()
                return True
        return super().eventFilter(obj, event)


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar com sliders do path ativo
# ──────────────────────────────────────────────────────────────────────────────

class _ActiveSidebar(QWidget):
    focal_changed = pyqtSignal(int, str, float)
    focus_changed = pyqtSignal(int, str, float)
    dur_changed   = pyqtSignal(int, float)

    def __init__(self, state: AppState):
        super().__init__()
        self._state = state
        self._index = 0
        self._point = "a"
        self._loading = False
        self.setFixedWidth(300)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 0, 0, 0)
        root.setSpacing(8)

        self._lbl_title = QLabel("PATH 1 — A")
        self._lbl_title.setStyleSheet("font-size:13px; font-weight:bold; color:#e6edf3; padding:2px 0;")
        root.addWidget(self._lbl_title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Duration
        dur_row = QHBoxLayout(); dur_row.setSpacing(6)
        dur_row.addWidget(QLabel("Duration:"))
        self._dur_spin = QDoubleSpinBox()
        self._dur_spin.setRange(0.1, 60.0)
        self._dur_spin.setSingleStep(0.1)
        self._dur_spin.setDecimals(1)
        self._dur_spin.setSuffix("s")
        self._dur_spin.setFixedWidth(70)
        self._dur_timer = QTimer(); self._dur_timer.setSingleShot(True)
        self._dur_timer.setInterval(300)
        self._dur_timer.timeout.connect(self._flush_dur)
        self._dur_spin.valueChanged.connect(lambda _: self._dur_timer.start())
        dur_row.addWidget(self._dur_spin)
        dur_row.addStretch()
        root.addLayout(dur_row)

        # Focal / Focus
        self._sl_focal = _SliderRow("Focal (mm)", 10, 300, 35, decimals=1, step=1.0, scale=10)
        self._sl_focal.value_changed.connect(self._on_focal)
        root.addWidget(self._sl_focal)

        self._sl_focus = _SliderRow("Focus (cm)", 10, 50000, 500, decimals=0, step=10.0, scale=1)
        self._sl_focus.value_changed.connect(self._on_focus)
        root.addWidget(self._sl_focus)

        root.addStretch()

    def load(self, index: int, point: str):
        self._index = index
        self._point = point
        pd = self._state.paths[index]
        color = "#1f6feb" if point == "a" else "#da3633"
        pt_label = "POINT A" if point == "a" else "POINT B"
        self._lbl_title.setText(f"{pd.name}  —  {pt_label}")
        self._lbl_title.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{color}; padding:2px 0;"
        )
        cp = pd.point_a if point == "a" else pd.point_b
        self._loading = True
        self._sl_focal.setValue(cp.focal_length)
        self._sl_focus.setValue(cp.focus_distance)
        self._dur_spin.setValue(pd.duration)
        self._loading = False

    def _flush_dur(self):
        if not self._loading:
            self.dur_changed.emit(self._index, self._dur_spin.value())

    def _on_focal(self, v: float):
        if not self._loading:
            self.focal_changed.emit(self._index, self._point, v)

    def _on_focus(self, v: float):
        if not self._loading:
            self.focus_changed.emit(self._index, self._point, v)


# ──────────────────────────────────────────────────────────────────────────────
# Camera Panel
# ──────────────────────────────────────────────────────────────────────────────

class CameraPanel(QWidget):
    send_message      = pyqtSignal(dict)
    path_selected     = pyqtSignal(int)
    play_mode_changed = pyqtSignal(bool)
    toggle_pilot      = pyqtSignal()

    def __init__(self, state: AppState):
        super().__init__()
        self._state = state
        self._host  = "127.0.0.1"
        self._play_mode     = False
        self._selected_path = 0
        self._free_cam_active = False
        self._cards: list[_PathCard] = []
        self._build_ui()

    def set_host(self, host: str):
        self._host = host

    def set_thumb_dir(self, thumb_dir: str):
        global THUMB_DIR
        THUMB_DIR = thumb_dir
        for card in self._cards:
            card.refresh()

    def set_free_cam_enabled(self, enabled: bool):
        self._btn_free_cam.setEnabled(enabled)
        if not enabled:
            self._free_cam_active = False
            self._btn_free_cam.setText("Free Camera")
            self._btn_free_cam.setProperty("class", "btn-free-cam")
            self._btn_free_cam.style().unpolish(self._btn_free_cam)
            self._btn_free_cam.style().polish(self._btn_free_cam)

    @property
    def free_cam_active(self): return self._free_cam_active

    @property
    def selected_path(self): return self._selected_path

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── Mode bar ──────────────────────────────────────────────────
        mode_bar = QHBoxLayout(); mode_bar.setSpacing(8)

        self._btn_edit = QPushButton("■  EDIT")
        self._btn_edit.setProperty("class", "mode-edit-active")
        self._btn_edit.setFixedHeight(34)
        self._btn_edit.clicked.connect(self._set_edit_mode)
        mode_bar.addWidget(self._btn_edit)

        self._btn_play = QPushButton("▶  PLAY")
        self._btn_play.setProperty("class", "mode-play")
        self._btn_play.setFixedHeight(34)
        self._btn_play.clicked.connect(self._set_play_mode)
        mode_bar.addWidget(self._btn_play)

        self._btn_free_cam = QPushButton("Free Camera")
        self._btn_free_cam.setProperty("class", "btn-free-cam")
        self._btn_free_cam.setFixedHeight(34)
        self._btn_free_cam.clicked.connect(self._on_free_cam_clicked)
        self._btn_free_cam.setEnabled(False)
        mode_bar.addWidget(self._btn_free_cam)

        mode_bar.addStretch()
        root.addLayout(mode_bar)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # ── Main area: flow grid + sidebar ───────────────────────────
        main_row = QHBoxLayout(); main_row.setSpacing(0)

        # Container com FlowLayout dentro de ScrollArea vertical
        flow_container = QWidget()
        self._flow = _FlowLayout(flow_container, h_spacing=8, v_spacing=8)
        flow_container.setLayout(self._flow)

        for i in range(8):
            card = _PathCard(i, self._state)
            card.goto_a.connect(self._on_goto_a)
            card.goto_b.connect(self._on_goto_b)
            card.record.connect(self._on_record)
            card.trigger.connect(self._on_trigger)
            card.name_changed.connect(self._on_name_changed)
            self._cards.append(card)
            self._flow.addWidget(card)

        scroll = QScrollArea()
        scroll.setWidget(flow_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        main_row.addWidget(scroll, 1)

        # Sidebar lateral direita
        self._sidebar = _ActiveSidebar(self._state)
        self._sidebar.focal_changed.connect(self._on_focal_changed)
        self._sidebar.focus_changed.connect(self._on_focus_changed)
        self._sidebar.dur_changed.connect(self._on_dur_changed)
        main_row.addWidget(self._sidebar)

        root.addLayout(main_row, 1)

        # Marca primeiro card ativo
        _ACTIVE_POINT[0] = "a"
        self._cards[0].set_active(True, "a")
        self._sidebar.load(0, "a")

    # ------------------------------------------------------------------
    # Free Camera
    # ------------------------------------------------------------------

    def _on_free_cam_clicked(self):
        self._free_cam_active = not self._free_cam_active
        if self._free_cam_active:
            self._btn_free_cam.setText("⚠ Piloting OFF")
            self._btn_free_cam.setProperty("class", "btn-free-cam-active")
        else:
            self._btn_free_cam.setText("Free Camera")
            self._btn_free_cam.setProperty("class", "btn-free-cam")
        self._btn_free_cam.style().unpolish(self._btn_free_cam)
        self._btn_free_cam.style().polish(self._btn_free_cam)
        self.toggle_pilot.emit()

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _set_edit_mode(self):
        self._play_mode = False
        self._update_mode_buttons()
        for card in self._cards:
            card.set_play_mode(False)
        pt = _ACTIVE_POINT.get(self._selected_path, "a")
        self._cards[self._selected_path].set_active(True, pt)
        self._sidebar.setVisible(True)
        self.play_mode_changed.emit(False)

    def _set_play_mode(self):
        self._play_mode = True
        self._update_mode_buttons()
        for card in self._cards:
            card.set_play_mode(True)
        self._sidebar.setVisible(False)
        self.play_mode_changed.emit(True)

    def _update_mode_buttons(self):
        if self._play_mode:
            self._btn_edit.setProperty("class", "mode-edit")
            self._btn_play.setProperty("class", "mode-play-active")
        else:
            self._btn_edit.setProperty("class", "mode-edit-active")
            self._btn_play.setProperty("class", "mode-play")
        for btn in (self._btn_edit, self._btn_play):
            btn.style().unpolish(btn); btn.style().polish(btn)

    # ------------------------------------------------------------------
    # GoTo A / B
    # ------------------------------------------------------------------

    def _on_goto_a(self, index: int):
        self._select_path(index, "a")
        osc_set_active_path(self._host, index)
        osc_goto_a(self._host)
        logger.info("OSC GoTo A → path=%d", index + 1)

    def _on_goto_b(self, index: int):
        self._select_path(index, "b")
        osc_set_active_path(self._host, index)
        osc_goto_b(self._host)
        logger.info("OSC GoTo B → path=%d", index + 1)

    def _select_path(self, index: int, pt: str):
        prev = self._selected_path
        if prev != index:
            self._cards[prev].set_active(False, _ACTIVE_POINT.get(prev, "a"))
        self._selected_path = index
        _ACTIVE_POINT[index] = pt
        self._cards[index].set_active(True, pt)
        self._sidebar.load(index, pt)
        self.path_selected.emit(index)

    # ------------------------------------------------------------------
    # PLAY trigger
    # ------------------------------------------------------------------

    def _on_trigger(self, index: int):
        self._selected_path = index
        osc_trigger_path(self._host, index)
        logger.info("OSC trigger path=%d", index + 1)

    # ------------------------------------------------------------------
    # Record
    # ------------------------------------------------------------------

    def _on_record(self, index: int):
        pt = _ACTIVE_POINT.get(index, "a")
        osc_set_active_path(self._host, index)
        if pt == "a": osc_record_a(self._host)
        else:         osc_record_b(self._host)
        logger.info("OSC RECORD %s → path=%d", pt.upper(), index + 1)
        self._cards[index].pulse_rec()
        QTimer.singleShot(1500, lambda: self._reload_thumb(index, pt))

    def _on_name_changed(self, index: int, name: str):
        """Atualiza sidebar se o path renomeado for o ativo."""
        if index == self._selected_path:
            pt = _ACTIVE_POINT.get(index, "a")
            self._sidebar.load(index, pt)
        logger.debug("Path %d renomeado: %s", index + 1, name)

    def _reload_thumb(self, index: int, pt: str):
        """Recarrega só a thumbnail gravada, sem depender do HTTP."""
        self._cards[index].reload_thumb(pt)

    def _auto_sync(self):
        host = self._host

        def _do():
            paths = fetch_paths(host)
            if paths:
                self._state.update_from_ue5(paths)
                warm_cache(host)
                QMetaObject.invokeMethod(
                    self, "_on_auto_sync_done",
                    Qt.ConnectionType.QueuedConnection
                )

        threading.Thread(target=_do, daemon=True).start()

    def _on_auto_sync_done(self):
        for card in self._cards:
            card.refresh()
        pt = _ACTIVE_POINT.get(self._selected_path, "a")
        self._sidebar.load(self._selected_path, pt)
        logger.debug("Auto-sync completo após Record")

    # ------------------------------------------------------------------
    # Duration / Focal / Focus
    # ------------------------------------------------------------------

    def _on_dur_changed(self, index: int, value: float):
        self._state.paths[index].duration = value
        osc_duration(self._host, value)

    def _on_focal_changed(self, index: int, pt: str, v: float):
        pd = self._state.paths[index]
        if pt == "a":
            pd.point_a.focal_length = v
            osc_focal_a(self._host, v)
        else:
            pd.point_b.focal_length = v
            osc_focal_b(self._host, v)

    def _on_focus_changed(self, index: int, pt: str, v: float):
        pd = self._state.paths[index]
        if pt == "a":
            pd.point_a.focus_distance = v
            osc_focus_a(self._host, v)
        else:
            pd.point_b.focus_distance = v
            osc_focus_b(self._host, v)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh_from_state(self):
        for card in self._cards:
            card.refresh()
        pt = _ACTIVE_POINT.get(self._selected_path, "a")
        self._sidebar.load(self._selected_path, pt)

    def set_is_moving(self, moving: bool):
        pass

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        key = event.key()
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_8:
            idx = key - Qt.Key.Key_1
            if self._play_mode: self._on_trigger(idx)
            else:               self._on_goto_a(idx)
        else:
            super().keyPressEvent(event)
