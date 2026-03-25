"""
VP CTRL v3 — Entry point.
"""
import sys
import logging

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QCoreApplication, Qt, QTimer

from ui.splash import make_splash
from ui.styles import STYLESHEET
from ui.welcome_screen import WelcomeScreen
from core.license_client import LicenseClient, LicenseStatus, ActivationDialog
from data.project import VPProject

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def main():
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("VP CTRL")
    app.setOrganizationName("VPCtrl")
    app.setStyleSheet(STYLESHEET)

    # ── Licença ───────────────────────────────────────────────────────
    license_client = LicenseClient()
    result = license_client.check_license()

    if not result.is_allowed:
        result = ActivationDialog.exec_dialog()
        if not result.is_allowed:
            sys.exit(0)

    if result.status == LicenseStatus.GRACE:
        QMessageBox.warning(
            None,
            "Licença — Modo Offline",
            "Não foi possível conectar ao servidor de licenças.\n"
            "Executando em modo offline (período de graça).\n\n"
            "Conecte à internet para renovar sua licença.",
        )

    # ── Splash 3 s → Welcome screen ──────────────────────────────────
    splash = make_splash()
    splash.show()
    app.processEvents()

    _main_window_ref = []  # mantém referência forte ao MainWindow

    def _on_project_opened(project: VPProject):
        from ui.main_window import MainWindow
        welcome.hide()
        win = MainWindow(project)
        _main_window_ref.append(win)
        splash.finish(win)
        win.show()

    welcome = WelcomeScreen()

    def _launch():
        splash.finish(welcome)
        welcome.show()

    welcome.project_opened.connect(_on_project_opened)
    QTimer.singleShot(3000, _launch)

    exit_code = app.exec()

    license_client.stop_heartbeat()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
