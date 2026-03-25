"""
VP CTRL v2 — Log panel with Qt handler.
"""
import logging
import html
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QFrame
from PyQt6.QtGui import QTextCursor

LEVEL_COLORS = {
    logging.DEBUG:   "#484f58",
    logging.INFO:    "#c9d1d9",
    logging.WARNING: "#e3b341",
    logging.ERROR:   "#f85149",
    logging.CRITICAL:"#ff7b72",
}

IGNORED_LOGGERS = {"urllib3.connectionpool", "websockets.client", "websockets.server"}


class _Emitter(QObject):
    """Helper que emite sinal a partir de qualquer thread."""
    line_ready = pyqtSignal(str)


class _QtLogHandler(logging.Handler):
    def __init__(self, panel: "LogPanel"):
        super().__init__()
        self._emitter = _Emitter()
        self._emitter.line_ready.connect(panel._append_line, Qt.ConnectionType.QueuedConnection)

    def emit(self, record: logging.LogRecord):
        if record.name in IGNORED_LOGGERS:
            return
        try:
            color = LEVEL_COLORS.get(record.levelno, "#c9d1d9")
            level = record.levelname[0]
            name = record.name.split(".")[-1]
            msg = html.escape(record.getMessage())
            line = f'<span style="color:{color}"><b>[{level}]</b> <span style="color:#555d69">{name}:</span> {msg}</span>'
            self._emitter.line_ready.emit(line)
        except Exception:
            pass


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._build_ui()
        self.handler = _QtLogHandler(self)
        self.handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(6)

        lbl = QLabel("LOG")
        lbl.setProperty("class", "panel-header")
        header.addWidget(lbl)
        header.addStretch()

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setProperty("class", "btn-log-clear")
        self._btn_clear.setFixedSize(50, 20)
        self._btn_clear.clicked.connect(self._clear)
        header.addWidget(self._btn_clear)

        self._btn_toggle = QPushButton("▲ Hide")
        self._btn_toggle.setProperty("class", "btn-log-toggle")
        self._btn_toggle.setFixedSize(60, 20)
        self._btn_toggle.clicked.connect(self._toggle)
        header.addWidget(self._btn_toggle)

        root.addLayout(header)

        # Text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setProperty("class", "log-view")
        self._text.setFixedHeight(110)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self._text)

    def _toggle(self):
        self._expanded = not self._expanded
        self._text.setVisible(self._expanded)
        self._btn_toggle.setText("▲ Hide" if self._expanded else "▼ Show")

    def _clear(self):
        self._text.clear()

    def _append_line(self, line: str):
        self._text.moveCursor(QTextCursor.MoveOperation.End)
        self._text.insertHtml(line + "<br>")
        self._text.moveCursor(QTextCursor.MoveOperation.End)
        # Keep max 500 lines
        doc = self._text.document()
        while doc.blockCount() > 500:
            cursor = QTextCursor(doc.begin())
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
