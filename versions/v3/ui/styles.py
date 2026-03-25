"""
VP CTRL v2 — Stylesheet global.
"""

STYLESHEET = """
/* ── Base ──────────────────────────────────────────────────────── */
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #0d1117;
}

/* ── Connection bar ─────────────────────────────────────────────── */
QFrame[class="conn-bar"] {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
}

QLineEdit {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 8px;
    color: #e6edf3;
}

QLineEdit:focus {
    border-color: #2f81f7;
}

/* ── Connect button — estado indica conexão ──────────────────────── */
/* Desconectado = vermelho */
QPushButton[class="btn-disconnected"] {
    background-color: #6e1a1a;
    color: #ffa198;
    border: 1px solid #da3633;
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: bold;
}

QPushButton[class="btn-disconnected"]:hover {
    background-color: #da3633;
    color: #ffffff;
}

/* Conectado = verde */
QPushButton[class="btn-connected"] {
    background-color: #1a4a1a;
    color: #3fb950;
    border: 1px solid #3fb950;
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: bold;
}

QPushButton[class="btn-connected"]:hover {
    background-color: #238636;
    color: #ffffff;
}

/* ── Sync button ────────────────────────────────────────────────── */
QPushButton[class="btn-sync"] {
    background-color: #1f6feb;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    padding: 6px 10px;
    font-weight: bold;
}

QPushButton[class="btn-sync"]:hover {
    background-color: #388bfd;
}

QPushButton[class="btn-sync"]:disabled {
    background-color: #21262d;
    color: #484f58;
}

/* ── Mode buttons ───────────────────────────────────────────────── */
QPushButton[class="mode-edit"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 4px 14px;
    font-weight: bold;
}

QPushButton[class="mode-edit-active"] {
    background-color: #7d4e00;
    color: #ffffff;
    border: 1px solid #bb7800;
    border-radius: 5px;
    padding: 4px 14px;
    font-weight: bold;
}

QPushButton[class="mode-play"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 4px 14px;
    font-weight: bold;
}

QPushButton[class="mode-play-active"] {
    background-color: #1a4a1a;
    color: #3fb950;
    border: 1px solid #3fb950;
    border-radius: 5px;
    padding: 4px 14px;
    font-weight: bold;
}

/* ── PIE buttons ────────────────────────────────────────────────── */
QPushButton[class="btn-pie-play"] {
    background-color: #238636;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    font-weight: bold;
}

QPushButton[class="btn-pie-play"]:hover {
    background-color: #2ea043;
}

QPushButton[class="btn-pie-stop"] {
    background-color: #6e1a1a;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    font-weight: bold;
}

QPushButton[class="btn-pie-stop"]:hover {
    background-color: #da3633;
}

/* ── Path frame ─────────────────────────────────────────────────── */
QFrame[class="path-frame"] {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
}

QFrame[class="path-cell"] {
    background-color: #0d1117;
    border: 1px solid #21262d;
    border-radius: 4px;
}

/* ── Path buttons (EDIT mode) ───────────────────────────────────── */
QPushButton[class="path-btn-edit"] {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    font-weight: bold;
}

QPushButton[class="path-btn-edit"]:hover {
    background-color: #2d333b;
    border-color: #8b949e;
}

QPushButton[class="path-btn-edit-selected"] {
    background-color: #7d4e00;
    color: #ffffff;
    border: 1px solid #bb7800;
    border-radius: 4px;
    font-weight: bold;
}

/* ── Path buttons (PLAY mode) ───────────────────────────────────── */
QPushButton[class="path-btn-play"] {
    background-color: #0f2a0f;
    color: #3fb950;
    border: 1px solid #1a3a1a;
    border-radius: 4px;
    font-weight: bold;
}

QPushButton[class="path-btn-play"]:hover {
    background-color: #1a4a1a;
    border-color: #3fb950;
}

QPushButton[class="path-btn-play-selected"] {
    background-color: #1a4a1a;
    color: #ffffff;
    border: 2px solid #3fb950;
    border-radius: 4px;
    font-weight: bold;
}

/* ── Point A/B status labels ────────────────────────────────────── */
QLabel[class="point-set"] {
    background-color: #1f6feb;
    color: #ffffff;
    border-radius: 3px;
    font-size: 10px;
    font-weight: bold;
    padding: 1px 2px;
}

QLabel[class="point-unset"] {
    background-color: #21262d;
    color: #484f58;
    border-radius: 3px;
    font-size: 10px;
    padding: 1px 2px;
}

/* ── Record buttons ─────────────────────────────────────────────── */
QPushButton[class="btn-rec-a"] {
    background-color: #6e1a1a;
    color: #ffffff;
    border: 1px solid #da3633;
    border-radius: 5px;
    font-weight: bold;
}

QPushButton[class="btn-rec-a"]:hover {
    background-color: #da3633;
}

QPushButton[class="btn-rec-b"] {
    background-color: #1a3a6e;
    color: #ffffff;
    border: 1px solid #1f6feb;
    border-radius: 5px;
    font-weight: bold;
}

QPushButton[class="btn-rec-b"]:hover {
    background-color: #1f6feb;
}

/* ── Botões A / B por path ──────────────────────────────────────── */
QPushButton[class="pt-btn-inactive"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 4px;
    font-size: 11px;
    font-weight: bold;
}
QPushButton[class="pt-btn-inactive"]:hover {
    background-color: #2d333b;
    color: #e6edf3;
}
QPushButton[class="pt-btn-active-a"] {
    background-color: #1f6feb;
    color: #ffffff;
    border: 1px solid #1f6feb;
    border-radius: 4px;
    font-size: 11px;
    font-weight: bold;
}
QPushButton[class="pt-btn-active-b"] {
    background-color: #da3633;
    color: #ffffff;
    border: 1px solid #da3633;
    border-radius: 4px;
    font-size: 11px;
    font-weight: bold;
}

/* ── REC button ─────────────────────────────────────────────────── */
QPushButton[class="btn-rec"] {
    background-color: #6e3333;
    color: #ffa198;
    border: 1px solid #f85149;
    border-radius: 4px;
    font-size: 10px;
    font-weight: bold;
}
QPushButton[class="btn-rec"]:hover {
    background-color: #f85149;
    color: #ffffff;
}
QPushButton[class="btn-rec"]:disabled {
    background-color: #3a1f1f;
    color: #555;
}

/* ── GoTo buttons ───────────────────────────────────────────────── */
QPushButton[class="btn-goto"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 5px;
    font-weight: bold;
}

QPushButton[class="btn-goto"]:hover {
    background-color: #2d333b;
    color: #e6edf3;
    border-color: #8b949e;
}

/* ── Panel header ───────────────────────────────────────────────── */
QLabel[class="panel-header"] {
    color: #8b949e;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 2px 0;
}

/* ── Sliders ────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: #30363d;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #2f81f7;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::sub-page:horizontal {
    background: #2f81f7;
    border-radius: 2px;
}

/* ── SpinBox ────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 3px 6px;
    color: #e6edf3;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #2f81f7;
}

/* ── Status bar ─────────────────────────────────────────────────── */
QStatusBar {
    background-color: #161b22;
    border-top: 1px solid #30363d;
    color: #8b949e;
    font-size: 12px;
}

/* ── Separator ──────────────────────────────────────────────────── */
QFrame[frameShape="4"] {  /* HLine */
    color: #21262d;
    max-height: 1px;
}

/* ── Free Camera button ─────────────────────────────────────────── */
QPushButton[class="btn-free-cam"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 6px 10px;
    font-weight: bold;
}

QPushButton[class="btn-free-cam"]:hover {
    background-color: #2d333b;
    color: #e6edf3;
    border-color: #8b949e;
}

QPushButton[class="btn-free-cam"]:disabled {
    background-color: #161b22;
    color: #30363d;
    border-color: #21262d;
}

QPushButton[class="btn-free-cam-active"] {
    background-color: #7d4e00;
    color: #ffffff;
    border: 1px solid #bb7800;
    border-radius: 5px;
    padding: 6px 10px;
    font-weight: bold;
}

QPushButton[class="btn-free-cam-active"]:hover {
    background-color: #a36500;
}

/* ── Perf bar ───────────────────────────────────────────────────── */
QLabel[class="perf-metric"] {
    color: #8b949e;
    font-family: "Consolas", monospace;
    font-size: 11px;
}

/* ── Log panel ──────────────────────────────────────────────────── */
QTextEdit[class="log-view"] {
    background-color: #010409;
    border: 1px solid #21262d;
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    color: #c9d1d9;
}

QPushButton[class="btn-log-clear"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 3px;
    font-size: 11px;
}

QPushButton[class="btn-log-clear"]:hover {
    background-color: #2d333b;
    color: #e6edf3;
}

QPushButton[class="btn-log-toggle"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 3px;
    font-size: 11px;
}

QPushButton[class="btn-log-toggle"]:hover {
    background-color: #2d333b;
    color: #e6edf3;
}

/* ── Launch UE5 button ──────────────────────────────────────────── */
QPushButton[class="btn-launch-ue5"] {
    background-color: #1c2a3a;
    color: #79c0ff;
    border: 1px solid #1f6feb;
    border-radius: 5px;
    padding: 6px 14px;
    font-weight: bold;
}

QPushButton[class="btn-launch-ue5"]:hover {
    background-color: #1f6feb;
    color: #ffffff;
}

QPushButton[class="btn-launch-ue5"]:disabled {
    background-color: #161b22;
    color: #444d56;
    border-color: #30363d;
}

/* ── Spout buttons ──────────────────────────────────────────────── */
QPushButton[class="btn-spout-connect"] {
    background-color: #21262d;
    color: #8b949e;
    border: 1px solid #30363d;
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
}

QPushButton[class="btn-spout-connect"]:hover {
    background-color: #2d333b;
    color: #e6edf3;
    border-color: #8b949e;
}

QPushButton[class="btn-spout-disconnect"] {
    background-color: #1a4a1a;
    color: #3fb950;
    border: 1px solid #3fb950;
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
}

QPushButton[class="btn-spout-disconnect"]:hover {
    background-color: #238636;
    color: #ffffff;
}

/* ── Path card (grid visual) ────────────────────────────────────── */
QFrame[class="path-card"] {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}

QFrame[class="path-card"]:hover {
    border-color: #8b949e;
}

/* ── Disabled ───────────────────────────────────────────────────── */
QWidget:disabled {
    color: #484f58;
}

QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
    border-color: #21262d;
}
"""
