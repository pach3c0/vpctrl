"""
VP CTRL v2 — Spout viewport preview.
Recebe textura do UE5 via Spout (GPU shared texture, zero network).
Requer: pip install SpoutGL PyOpenGL
"""
import logging
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

logger = logging.getLogger(__name__)

# -- tenta importar SpoutGL ------------------------------------------------
try:
    import SpoutGL
    from OpenGL.GL import GL_RGBA
    _SPOUT_AVAILABLE = True
except ImportError:
    _SPOUT_AVAILABLE = False
    logger.warning("SpoutGL não encontrado — preview Spout desativado. "
                   "Execute: pip install SpoutGL PyOpenGL")


_DEFAULT_SENDER = "UE5_Viewport"
_FPS_TARGET = 30
_FRAME_MS = 1000 // _FPS_TARGET



class SpoutWidget(QWidget):
    """
    Widget de preview Spout.
    Mostra feed da viewport UE5 via textura GPU compartilhada.
    Sem custo de rede — tudo na placa de vídeo.
    """

    connected_changed = pyqtSignal(bool)

    def __init__(self, sender_name: str = _DEFAULT_SENDER, parent=None):
        super().__init__(parent)
        self._sender_name = sender_name
        self._receiver = None
        self._running = False
        self._width = 0
        self._height = 0
        self._buf = None
        self._connected = False

        self._build_ui()

        self._diag_counter = 0

        if _SPOUT_AVAILABLE:
            self._timer = QTimer(self)
            self._timer.setInterval(_FRAME_MS)
            self._timer.timeout.connect(self._grab_frame)
        else:
            self._timer = None

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        lbl = QLabel("SPOUT PREVIEW")
        lbl.setProperty("class", "panel-header")
        header.addWidget(lbl)

        self._lbl_status = QLabel("● Offline")
        self._lbl_status.setStyleSheet("color: #484f58; font-size: 11px;")
        header.addWidget(self._lbl_status)
        header.addStretch()

        self._btn_toggle = QPushButton("Connect")
        self._btn_toggle.setProperty("class", "btn-spout-connect")
        self._btn_toggle.setFixedHeight(22)
        self._btn_toggle.setFixedWidth(80)
        self._btn_toggle.clicked.connect(self._toggle)
        header.addWidget(self._btn_toggle)

        root.addLayout(header)

        self._viewport = QLabel()
        self._viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._viewport.setMinimumHeight(180)

        if not _SPOUT_AVAILABLE:
            self._viewport.setText(
                "SpoutGL not installed\npip install SpoutGL PyOpenGL"
            )
            self._viewport.setStyleSheet(
                "background-color: #010409; border: 1px solid #21262d; "
                "border-radius: 4px; color: #484f58; font-size: 12px;"
            )
        else:
            self._viewport.setText("No signal")
            self._viewport.setStyleSheet(
                "background-color: #010409; border: 1px solid #21262d; "
                "border-radius: 4px; color: #484f58; font-size: 12px;"
            )

        root.addWidget(self._viewport)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_sender_name(self, name: str):
        self._sender_name = name
        if self._running:
            self.stop()
            self.start()

    def start(self):
        if not _SPOUT_AVAILABLE:
            return
        if self._running:
            return
        try:
            self._receiver = SpoutGL.SpoutReceiver()
            ok_gl = self._receiver.createOpenGL()
            logger.info("Spout createOpenGL: %s", ok_gl)

            self._receiver.setReceiverName(self._sender_name)
            self._running = True
            self._timer.start()
            logger.info("Spout receiver iniciado — sender '%s'", self._sender_name)
        except Exception as e:
            logger.error("Spout start falhou: %s", e)

    def stop(self):
        if not _SPOUT_AVAILABLE:
            return
        self._running = False
        if self._timer:
            self._timer.stop()
        if self._receiver:
            try:
                self._receiver.releaseReceiver()
                self._receiver.closeOpenGL()
            except Exception:
                pass
            self._receiver = None
        self._set_connected(False)
        self._viewport.setPixmap(QPixmap())
        self._viewport.setText("No signal")
        logger.info("Spout receiver parado")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _toggle(self):
        if self._running:
            self.stop()
            self._btn_toggle.setText("Connect")
            self._btn_toggle.setProperty("class", "btn-spout-connect")
        else:
            self.start()
            self._btn_toggle.setText("Disconnect")
            self._btn_toggle.setProperty("class", "btn-spout-disconnect")
        self._btn_toggle.style().unpolish(self._btn_toggle)
        self._btn_toggle.style().polish(self._btn_toggle)

    def _grab_frame(self):
        if not self._running or self._receiver is None:
            return

        try:
            r = self._receiver

            # receiveImage faz tudo: conecta, espera frame, copia pixels
            # Precisa alocar buffer com tamanho do sender
            w = r.getSenderWidth()
            h = r.getSenderHeight()

            if w == 0 or h == 0:
                # Sender existe mas ainda sem tamanho — tenta receiveImage
                # com buffer mínimo para forçar a conexão
                if self._buf is None:
                    self._buf = np.zeros(4, dtype=np.uint8)
                r.receiveImage(self._buf, GL_RGBA, False, 0)
                return

            # Realoca buffer se tamanho mudou
            if w != self._width or h != self._height:
                self._width = w
                self._height = h
                self._buf = np.zeros(w * h * 4, dtype=np.uint8)
                logger.info("Spout frame size: %dx%d", w, h)

            ok = r.receiveImage(self._buf, GL_RGBA, False, 0)
            if ok:
                self._show_array(self._buf, w, h)
            else:
                if self._connected:
                    self._set_connected(False)

        except Exception as e:
            logger.warning("Spout frame error: %s", e)
            self._set_connected(False)

    def _show_array(self, arr, w: int, h: int):
        if not self._connected:
            self._set_connected(True)

        img = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        vw = self._viewport.width()
        vh = self._viewport.height()
        pix = QPixmap.fromImage(img).scaled(
            vw, vh,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._viewport.setPixmap(pix)

    def _set_connected(self, state: bool):
        if state == self._connected:
            return
        self._connected = state
        if state:
            self._lbl_status.setText(
                f"● {self._sender_name}  {self._width}×{self._height}"
            )
            self._lbl_status.setStyleSheet("color: #3fb950; font-size: 11px;")
            self._viewport.setText("")
        else:
            self._lbl_status.setText("● Waiting for sender…")
            self._lbl_status.setStyleSheet("color: #e3b341; font-size: 11px;")
        self.connected_changed.emit(state)

    def resizeEvent(self, event):
        super().resizeEvent(event)
