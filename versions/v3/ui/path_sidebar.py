"""
VP CTRL v3 — Path sidebar.
Mostra Focal e Focus do ponto ativo (A ou B).
Troca de ponto via load_path(index, point).
Exibe thumbnails path{n}a.png e path{n}b.png da pasta de screenshots UE5.
"""
import logging
import os
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSlider, QFrame,
    QDialog, QSizePolicy,
)

from core.http_client import (
    set_path_field_async, set_property_http_async,
)
from data.models import AppState

logger = logging.getLogger(__name__)

_DEBOUNCE_MS = 80

THUMB_DIR = (
    r"C:\Users\ricar\Documents\Unreal Projects\VP_PachecoV5"
    r"\Saved\Screenshots\WindowsEditor"
)
THUMB_W, THUMB_H = 200, 112   # 16:9


class _SliderRow(QWidget):
    """Label + slider + spinbox com debounce."""
    value_changed = pyqtSignal(float)

    def __init__(self, label: str, mn: float, mx: float, val: float,
                 decimals: int = 1, step: float = 1.0, scale: int = 10):
        super().__init__()
        self._mn = mn
        self._mx = mx
        self._scale = scale
        self._blocking = False

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._flush)
        self._pending: float | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(72)
        lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(int(mn * scale), int(mx * scale))
        self._slider.setValue(int(val * scale))
        layout.addWidget(self._slider, 1)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(mn, mx)
        self._spin.setDecimals(decimals)
        self._spin.setSingleStep(step)
        self._spin.setValue(val)
        self._spin.setFixedWidth(82)
        layout.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.editingFinished.connect(self._on_spin)

    def value(self) -> float:
        return self._spin.value()

    def setValue(self, v: float):
        self._blocking = True
        v = max(self._mn, min(self._mx, v))
        self._spin.setValue(v)
        self._slider.setValue(int(v * self._scale))
        self._blocking = False

    def _on_slider(self, iv: int):
        if self._blocking:
            return
        v = iv / self._scale
        self._blocking = True
        self._spin.setValue(v)
        self._blocking = False
        self._pending = v
        self._debounce.start()

    def _on_spin(self):
        if self._blocking:
            return
        v = self._spin.value()
        self._blocking = True
        self._slider.setValue(int(v * self._scale))
        self._blocking = False
        self._pending = v
        self._debounce.start()

    def _flush(self):
        if self._pending is not None:
            self.value_changed.emit(self._pending)
            self._pending = None


class _ThumbLabel(QLabel):
    """QLabel clicável que abre a imagem em tamanho maior."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""
        self.setFixedSize(THUMB_W, THUMB_H)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background:#161b22; border:1px solid #30363d; color:#484f58; font-size:11px;"
        )
        self.setText("sem imagem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def load(self, filepath: str):
        self._path = filepath
        if os.path.isfile(filepath):
            px = QPixmap(filepath).scaled(
                THUMB_W, THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(px)
            self.setText("")
        else:
            self.setPixmap(QPixmap())
            self.setText("sem imagem")

    def mousePressEvent(self, event):
        if self._path and os.path.isfile(self._path):
            dlg = QDialog(self)
            dlg.setWindowTitle(os.path.basename(self._path))
            dlg.setWindowFlags(
                Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint
            )
            lbl = QLabel(dlg)
            px = QPixmap(self._path)
            screen = self.screen().availableGeometry()
            max_w = int(screen.width() * 0.8)
            max_h = int(screen.height() * 0.8)
            lbl.setPixmap(
                px.scaled(max_w, max_h,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(4, 4, 4, 4)
            lay.addWidget(lbl)
            dlg.adjustSize()
            dlg.exec()
        super().mousePressEvent(event)


class PathSidebar(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._host = "127.0.0.1"
        self._path_index = 0
        self._point = "a"   # ponto ativo: "a" ou "b"
        self._loading = False

        self.setFixedWidth(420)
        self._build_ui()

    def set_host(self, host: str):
        self._host = host

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 0, 0, 0)
        root.setSpacing(8)

        # Título: "PATH 1 — POINT A"
        self._lbl_title = QLabel("PATH 1  —  POINT A")
        self._lbl_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #e6edf3; padding: 2px 0;"
        )
        root.addWidget(self._lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Thumbnails A e B
        thumb_row = QHBoxLayout()
        thumb_row.setSpacing(6)

        col_a = QVBoxLayout()
        col_a.setSpacing(2)
        lbl_a = QLabel("POINT A")
        lbl_a.setStyleSheet("color:#1f6feb; font-size:10px; font-weight:bold;")
        lbl_a.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_a = _ThumbLabel()
        col_a.addWidget(lbl_a)
        col_a.addWidget(self._thumb_a)
        thumb_row.addLayout(col_a)

        col_b = QVBoxLayout()
        col_b.setSpacing(2)
        lbl_b = QLabel("POINT B")
        lbl_b.setStyleSheet("color:#da3633; font-size:10px; font-weight:bold;")
        lbl_b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_b = _ThumbLabel()
        col_b.addWidget(lbl_b)
        col_b.addWidget(self._thumb_b)
        thumb_row.addLayout(col_b)

        root.addLayout(thumb_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        # Focal Length
        self._fl = _SliderRow("Focal (mm)", 10, 300, 35,
                              decimals=1, step=1.0, scale=10)
        self._fl.value_changed.connect(self._send_focal)
        root.addWidget(self._fl)

        # Focus Distance
        self._fd = _SliderRow("Focus (cm)", 10, 50000, 500,
                              decimals=0, step=10.0, scale=1)
        self._fd.value_changed.connect(self._send_focus)
        root.addWidget(self._fd)

        root.addStretch()

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_path(self, index: int, point: str = None):
        """Carrega path e opcionalmente muda o ponto ativo."""
        self._path_index = index
        if point is not None:
            self._point = point

        pd = self._state.paths[index]
        pt_name = "POINT A" if self._point == "a" else "POINT B"
        color = "#1f6feb" if self._point == "a" else "#da3633"
        self._lbl_title.setText(f"{pd.name}  —  {pt_name}")
        self._lbl_title.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {color}; padding: 2px 0;"
        )

        cp = pd.point_a if self._point == "a" else pd.point_b
        self._loading = True
        self._fl.setValue(cp.focal_length)
        self._fd.setValue(cp.focus_distance)
        self._loading = False

        # Recarrega thumbnails
        n = index + 1
        self._thumb_a.load(os.path.join(THUMB_DIR, f"path{n}a.png"))
        self._thumb_b.load(os.path.join(THUMB_DIR, f"path{n}b.png"))

    # ------------------------------------------------------------------
    # Send to UE5
    # ------------------------------------------------------------------

    def _send_focal(self, v: float):
        if self._loading:
            return
        pt = self._state.paths[self._path_index]
        field = "focal_a" if self._point == "a" else "focal_b"
        if self._point == "a":
            pt.point_a.focal_length = v
        else:
            pt.point_b.focal_length = v
        set_path_field_async(self._host, self._path_index, field, v)
        set_property_http_async(self._host, "FocalLengthOverride", v)
        logger.debug("PATH %d %s focal → %.1f", self._path_index + 1, self._point.upper(), v)

    def _send_focus(self, v: float):
        if self._loading:
            return
        pt = self._state.paths[self._path_index]
        field = "focus_a" if self._point == "a" else "focus_b"
        if self._point == "a":
            pt.point_a.focus_distance = v
        else:
            pt.point_b.focus_distance = v
        set_path_field_async(self._host, self._path_index, field, v)
        set_property_http_async(self._host, "FocusDistanceOverride", v)
        logger.debug("PATH %d %s focus → %.0f", self._path_index + 1, self._point.upper(), v)
