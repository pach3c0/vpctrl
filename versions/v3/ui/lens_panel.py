"""
VP CTRL v2 — Painel de lente (modo EDIT).
FocalLengthOverride e FocusDistanceOverride controlam a câmera ao vivo.
Visível apenas em modo EDIT — esconde em PLAY.
"""
import logging
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QSpinBox, QFrame,
)

from core.http_client import set_property_http_async

logger = logging.getLogger(__name__)


class LensPanel(QWidget):
    send_message = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._host = "127.0.0.1"

        self._debounce_fl = QTimer()
        self._debounce_fl.setSingleShot(True)
        self._debounce_fl.setInterval(80)
        self._debounce_fl.timeout.connect(self._flush_fl)

        self._debounce_fd = QTimer()
        self._debounce_fd.setSingleShot(True)
        self._debounce_fd.setInterval(80)
        self._debounce_fd.timeout.connect(self._flush_fd)

        self._pending_fl: float | None = None
        self._pending_fd: float | None = None

        self._build_ui()

    def set_host(self, host: str):
        self._host = host

    def set_path_index(self, index: int):
        pass

    def set_play_mode(self, playing: bool):
        self.setVisible(not playing)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        lbl_header = QLabel("LENS  —  live adjustment (Override)")
        lbl_header.setProperty("class", "panel-header")
        root.addWidget(lbl_header)

        # Focal Length Override
        fl_row = QHBoxLayout()
        fl_row.setSpacing(8)
        fl_row.addWidget(QLabel("Focal (mm):"))
        self._fl_slider = self._make_slider(10, 300, 35)
        self._fl_spin = self._make_spin(10, 300, 35, " mm")
        self._fl_slider.valueChanged.connect(self._fl_slider_changed)
        self._fl_spin.editingFinished.connect(self._fl_spin_changed)
        fl_row.addWidget(self._fl_slider, 1)
        fl_row.addWidget(self._fl_spin)
        root.addLayout(fl_row)

        # Focus Distance Override
        fd_row = QHBoxLayout()
        fd_row.setSpacing(8)
        fd_row.addWidget(QLabel("Focus (cm):"))
        self._fd_slider = self._make_slider(10, 50000, 500)
        self._fd_spin = self._make_spin(10, 50000, 500, " cm")
        self._fd_slider.valueChanged.connect(self._fd_slider_changed)
        self._fd_spin.editingFinished.connect(self._fd_spin_changed)
        fd_row.addWidget(self._fd_slider, 1)
        fd_row.addWidget(self._fd_spin)
        root.addLayout(fd_row)

    def _make_slider(self, mn, mx, val):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(mn, mx)
        s.setValue(val)
        return s

    def _make_spin(self, mn, mx, val, suffix):
        s = QSpinBox()
        s.setRange(mn, mx)
        s.setValue(val)
        s.setFixedWidth(80)
        s.setSuffix(suffix)
        return s

    # ------------------------------------------------------------------
    # Focal Length
    # ------------------------------------------------------------------

    def _fl_slider_changed(self, v: int):
        self._fl_spin.blockSignals(True)
        self._fl_spin.setValue(v)
        self._fl_spin.blockSignals(False)
        self._pending_fl = float(v)
        self._debounce_fl.start()

    def _fl_spin_changed(self):
        v = self._fl_spin.value()
        self._fl_slider.blockSignals(True)
        self._fl_slider.setValue(v)
        self._fl_slider.blockSignals(False)
        self._pending_fl = float(v)
        self._debounce_fl.start()

    def _flush_fl(self):
        if self._pending_fl is not None:
            set_property_http_async(self._host, "FocalLengthOverride", self._pending_fl)
            logger.debug("Lens SET FocalLengthOverride=%.1f", self._pending_fl)
            self._pending_fl = None

    # ------------------------------------------------------------------
    # Focus Distance
    # ------------------------------------------------------------------

    def _fd_slider_changed(self, v: int):
        self._fd_spin.blockSignals(True)
        self._fd_spin.setValue(v)
        self._fd_spin.blockSignals(False)
        self._pending_fd = float(v)
        self._debounce_fd.start()

    def _fd_spin_changed(self):
        v = self._fd_spin.value()
        self._fd_slider.blockSignals(True)
        self._fd_slider.setValue(v)
        self._fd_slider.blockSignals(False)
        self._pending_fd = float(v)
        self._debounce_fd.start()

    def _flush_fd(self):
        if self._pending_fd is not None:
            set_property_http_async(self._host, "FocusDistanceOverride", self._pending_fd)
            logger.debug("Lens SET FocusDistanceOverride=%.1f", self._pending_fd)
            self._pending_fd = None
