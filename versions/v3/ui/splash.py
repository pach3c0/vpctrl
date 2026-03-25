"""
VP CTRL v3 — Splash screen (3 segundos).
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QSplashScreen, QLabel, QVBoxLayout, QWidget
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont


def make_splash() -> QSplashScreen:
    # Cria pixmap escuro 480×240
    pix = QPixmap(480, 240)
    pix.fill(QColor("#0d1117"))

    painter = QPainter(pix)

    # Título
    font_title = QFont("Segoe UI", 32, QFont.Weight.Bold)
    painter.setFont(font_title)
    painter.setPen(QColor("#2f81f7"))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "VP CTRL")

    # Subtítulo
    font_sub = QFont("Segoe UI", 11)
    painter.setFont(font_sub)
    painter.setPen(QColor("#8b949e"))
    painter.drawText(
        pix.rect().adjusted(0, 80, 0, 0),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "Virtual Production Control  v3.0"
    )

    # Tag UE version
    font_ue = QFont("Segoe UI", 9)
    painter.setFont(font_ue)
    painter.setPen(QColor("#3fb950"))
    painter.drawText(
        pix.rect().adjusted(0, 110, 0, 0),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        "Unreal Engine 5.7.4"
    )

    # Rodapé
    font_foot = QFont("Segoe UI", 9)
    painter.setFont(font_foot)
    painter.setPen(QColor("#484f58"))
    painter.drawText(
        pix.rect().adjusted(0, 0, 0, -16),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
        "Starting…"
    )

    painter.end()

    splash = QSplashScreen(pix, Qt.WindowType.WindowStaysOnTopHint)
    splash.setEnabled(False)
    return splash
