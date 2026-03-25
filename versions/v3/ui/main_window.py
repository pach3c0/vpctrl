"""
VP CTRL v3 — Main window.
"""
import logging
import threading
from PyQt6.QtCore import Qt, QTimer, QSettings, pyqtSlot, pyqtSignal, QMetaObject
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QStatusBar, QLineEdit, QPushButton,
    QApplication, QMenuBar, QMenu, QFileDialog, QMessageBox,
)
from PyQt6.QtGui import QCloseEvent, QAction, QKeySequence

from core.websocket_client import WebSocketThread
from core.ue5_api import get_property
from core.http_client import (
    fetch_paths, ue5_begin_play,
    warm_cache, ue5_pilot_actor, ue5_eject_pilot,
    check_ue5_version, check_plugins, REQUIRED_PLUGINS,
)
from config.settings import SUPPORTED_UE_VERSION
from core.recent_files import RecentFilesManager
from config.settings import DEFAULT_HOST, WS_PORT, POLLING_INTERVAL, PROJECTS_DIR
from data.models import AppState
from data.project import VPProject
from ui.camera_panel import CameraPanel
from ui.log_panel import LogPanel
from ui.perf_panel import PerfPanel

logger = logging.getLogger(__name__)

SETTINGS_ORG = "VPCtrl"
SETTINGS_APP = "VPCtrlV3"


class MainWindow(QMainWindow):
    _version_checked  = pyqtSignal(bool, str, str)
    _plugins_checked  = pyqtSignal(dict, str)   # {plugin: bool}, host

    def __init__(self, project: VPProject):
        super().__init__()
        self._project = project
        self._connected = False
        self._is_moving = False
        self._ws_thread: WebSocketThread = None
        self._pending_is_moving_id: str = None
        self._recent = RecentFilesManager()

        self._qsettings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._state = AppState(paths=project.paths, last_host=project.host)

        self._version_checked.connect(self._on_version_checked)
        self._plugins_checked.connect(self._on_plugins_checked)

        self._setup_window()
        self._build_ui()
        self._apply_project()
        self._setup_polling()
        self._set_controls_enabled(False)

        # Register log handler after UI is built
        logging.getLogger().addHandler(self._log_panel.handler)

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------

    def _setup_window(self):
        self._refresh_title()
        self.setMinimumSize(700, 500)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.showMaximized()
        geom = self._qsettings.value("geometry")
        if geom:
            self.restoreGeometry(geom)

        self._build_menu()

    def _refresh_title(self):
        self.setWindowTitle(f"VP CTRL v3.0 — {self._project.name}")

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self):
        menubar = self.menuBar()

        # ── File ──────────────────────────────────────────────────────
        file_menu = menubar.addMenu("File")

        act_new = QAction("New Project…", self)
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self._on_file_new)
        file_menu.addAction(act_new)

        act_open = QAction("Open Project…", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self._on_file_open)
        file_menu.addAction(act_open)

        self._recent_menu = QMenu("Recent Files", self)
        file_menu.addMenu(self._recent_menu)
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        self._act_save = QAction("Save Project", self)
        self._act_save.setShortcut(QKeySequence("Ctrl+S"))
        self._act_save.triggered.connect(self._on_file_save)
        file_menu.addAction(self._act_save)

        self._act_save_as = QAction("Save Project As…", self)
        self._act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_save_as.triggered.connect(self._on_file_save_as)
        file_menu.addAction(self._act_save_as)

        file_menu.addSeparator()

        act_settings = QAction("Project Settings…", self)
        act_settings.triggered.connect(self._show_project_settings)
        file_menu.addAction(act_settings)

        self._act_reveal = QAction("Reveal in Explorer", self)
        self._act_reveal.triggered.connect(self._on_reveal_in_explorer)
        file_menu.addAction(self._act_reveal)

        file_menu.addSeparator()

        act_close = QAction("Close Project", self)
        act_close.triggered.connect(self._on_close_project)
        file_menu.addAction(act_close)

        file_menu.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setShortcut(QKeySequence("Alt+F4"))
        act_exit.triggered.connect(self._exit_app)
        file_menu.addAction(act_exit)

        # ── Edit ──────────────────────────────────────────────────────
        edit_menu = menubar.addMenu("Edit")

        manage_menu = QMenu("Manage Devices", self)

        act_ue5_host = QAction("UE5 Host", self)
        act_ue5_host.triggered.connect(self._show_host_settings)
        manage_menu.addAction(act_ue5_host)

        manage_menu.addSeparator()

        act_relay = QAction("VP CTRL Relay  (multi-machine)  — Em breve", self)
        act_relay.setEnabled(False)
        act_relay.setToolTip(
            "Permite controlar múltiplos Unreal Engine em máquinas diferentes.\n"
            "Recurso disponível em versão futura do VP CTRL."
        )
        manage_menu.addAction(act_relay)

        edit_menu.addMenu(manage_menu)

        # ── View ──────────────────────────────────────────────────────
        view_menu = menubar.addMenu("View")

        self._act_log = QAction("Hide Log", self)
        self._act_log.setShortcut(QKeySequence("Ctrl+L"))
        self._act_log.triggered.connect(self._toggle_log)
        view_menu.addAction(self._act_log)

        view_menu.addSeparator()

        self._act_fullscreen = QAction("Full Screen", self)
        self._act_fullscreen.setShortcut(QKeySequence("F11"))
        self._act_fullscreen.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(self._act_fullscreen)

        self._act_always_on_top = QAction("Always on Top", self)
        self._act_always_on_top.setCheckable(True)
        self._act_always_on_top.triggered.connect(self._toggle_always_on_top)
        view_menu.addAction(self._act_always_on_top)

        # ── Tools ─────────────────────────────────────────────────────
        tools_menu = menubar.addMenu("Tools")

        act_clear_log = QAction("Clear Log", self)
        act_clear_log.triggered.connect(self._on_clear_log)
        tools_menu.addAction(act_clear_log)

        act_export_log = QAction("Export Log…", self)
        act_export_log.triggered.connect(self._on_export_log)
        tools_menu.addAction(act_export_log)

        tools_menu.addSeparator()

        act_reset_thumbs = QAction("Reset Thumbnails", self)
        act_reset_thumbs.triggered.connect(self._on_reset_thumbnails)
        tools_menu.addAction(act_reset_thumbs)

        # ── Help ──────────────────────────────────────────────────────
        help_menu = menubar.addMenu("Help")

        act_docs = QAction("Documentation…", self)
        act_docs.triggered.connect(self._on_open_docs)
        help_menu.addAction(act_docs)

        act_updates = QAction("Check for Updates…", self)
        act_updates.triggered.connect(self._on_check_updates)
        help_menu.addAction(act_updates)

        help_menu.addSeparator()

        act_license = QAction("License…", self)
        act_license.triggered.connect(self._on_show_license)
        help_menu.addAction(act_license)

        help_menu.addSeparator()

        act_about = QAction("About VP CTRL…", self)
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    def _rebuild_recent_menu(self):
        import os
        self._recent_menu.clear()
        recent = self._recent.get_recent()
        if not recent:
            act = QAction("(empty)", self)
            act.setEnabled(False)
            self._recent_menu.addAction(act)
        else:
            for entry in recent:
                exists = os.path.isfile(entry["path"])
                label = f"{entry['name']}  —  {entry['path']}"
                if not exists:
                    label = f"⚠ {entry['name']}  —  {entry['path']}"
                act = QAction(label, self)
                act.setData(entry["path"])
                if not exists:
                    act.setEnabled(True)  # ainda clicável — oferece "Procurar"
                act.triggered.connect(lambda checked, p=entry["path"]: self._open_project_path(p))
                self._recent_menu.addAction(act)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 4)
        root.setSpacing(6)

        # ── Connection bar ────────────────────────────────────────────
        conn_bar = QFrame()
        conn_bar.setProperty("class", "conn-bar")
        conn_layout = QHBoxLayout(conn_bar)
        conn_layout.setContentsMargins(10, 8, 10, 8)
        conn_layout.setSpacing(8)

        # Host edit — oculto da topbar, gerenciado via Edit → Manage Devices → UE5 Host
        self._host_edit = QLineEdit()
        self._host_edit.setVisible(False)

        conn_layout.addStretch()

        self._btn_launch_ue5 = QPushButton("Launch UE5")
        self._btn_launch_ue5.setProperty("class", "btn-launch-ue5")
        self._btn_launch_ue5.setFixedWidth(110)
        self._btn_launch_ue5.clicked.connect(self._launch_ue5)
        conn_layout.addWidget(self._btn_launch_ue5)

        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setProperty("class", "btn-disconnected")
        self._btn_connect.setFixedWidth(110)
        self._btn_connect.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self._btn_connect)

        root.addWidget(conn_bar)

        # ── Perf bar ──────────────────────────────────────────────────
        self._perf_panel = PerfPanel()
        root.addWidget(self._perf_panel)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # ── Camera panel ──────────────────────────────────────────────
        self._camera_panel = CameraPanel(self._state)
        self._camera_panel.send_message.connect(self._send)
        self._camera_panel.toggle_pilot.connect(self._on_toggle_pilot)
        root.addWidget(self._camera_panel)

        # ── Log panel ─────────────────────────────────────────────────
        self._log_panel = LogPanel()
        root.addWidget(self._log_panel)

        # ── Status bar ────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("● Disconnected")
        self._status_label.setStyleSheet("color: #666666;")
        self._status_bar.addWidget(self._status_label)

        self._proj_label = QLabel()
        self._proj_label.setStyleSheet("color: #555555; font-size: 11px;")
        self._status_bar.addPermanentWidget(self._proj_label)

    def _apply_project(self):
        """Aplica os dados do projeto carregado na UI."""
        import os
        self._host_edit.setText(self._project.host)
        self._camera_panel.set_host(self._project.host)
        if self._project.thumb_dir:
            self._camera_panel.set_thumb_dir(self._project.thumb_dir)
        self._proj_label.setText(self._project.file_path or "")
        self._refresh_title()
        # Habilita Launch UE5 só se a pasta estiver configurada e existir
        ue5_ok = bool(self._project.ue5_project_path) and os.path.isdir(self._project.ue5_project_path)
        self._btn_launch_ue5.setEnabled(ue5_ok)
        self._btn_launch_ue5.setToolTip(
            "Abrir projeto no Unreal Engine" if ue5_ok
            else "Configure o caminho do projeto UE5 em File → Project Settings"
        )

    # ------------------------------------------------------------------
    # File menu actions
    # ------------------------------------------------------------------

    def _on_file_new(self):
        from ui.welcome_screen import _NewProjectDialog
        from config.settings import PROJECTS_DIR
        import re

        dlg = _NewProjectDialog(self)
        if dlg.exec():
            name, host, ue5_path = dlg.values()
            project = VPProject.new(name=name, host=host, ue5_project_path=ue5_path)
            slug = re.sub(r"[\s_-]+", "_", re.sub(r"[^\w\s-]", "", name.lower().strip())) or "projeto"
            save_path = PROJECTS_DIR / slug / f"{slug}.vpctrl"
            try:
                project.save(str(save_path))
                self._recent.add(str(save_path), name)
                self._load_project(project)
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Não foi possível criar o projeto:\n{e}")

    def _on_file_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Projeto", str(PROJECTS_DIR),
            "VP CTRL Project (*.vpctrl);;All Files (*)"
        )
        if path:
            self._open_project_path(path)

    def _open_project_path(self, path: str):
        import os
        from pathlib import Path

        # Arquivo não existe
        if not os.path.isfile(path):
            resp = QMessageBox.question(
                self, "Arquivo não encontrado",
                f"O projeto não foi encontrado em:\n{path}\n\n"
                "Deseja procurar o arquivo em outro local?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            self._recent.remove(path)
            self._rebuild_recent_menu()
            logger.warning("Projeto não encontrado: %s — removido dos recentes", path)
            if resp == QMessageBox.StandardButton.Yes:
                new_path, _ = QFileDialog.getOpenFileName(
                    self, "Localizar Projeto", str(PROJECTS_DIR),
                    "VP CTRL Project (*.vpctrl);;All Files (*)"
                )
                if new_path:
                    self._open_project_path(new_path)
            return

        try:
            project = VPProject.load(path)
        except ValueError as e:
            logger.error("Projeto corrompido: %s — %s", path, e)
            QMessageBox.critical(self, "Projeto corrompido",
                f"O arquivo de projeto está corrompido e não pode ser aberto:\n{path}\n\n{e}")
            self._recent.remove(path)
            self._rebuild_recent_menu()
            return
        except Exception as e:
            logger.error("Erro ao abrir projeto: %s — %s", path, e)
            QMessageBox.critical(self, "Erro ao abrir projeto",
                f"Não foi possível abrir o projeto:\n{path}\n\n{e}")
            return

        # Avisa se pasta UE5 configurada não existe (não bloqueia)
        if project.ue5_project_path and not os.path.isdir(project.ue5_project_path):
            logger.warning("Pasta UE5 não encontrada: %s", project.ue5_project_path)
            QMessageBox.warning(self, "Pasta UE5 não encontrada",
                f"A pasta do projeto UE5 configurada não foi encontrada:\n"
                f"{project.ue5_project_path}\n\n"
                "O projeto será aberto, mas configure o caminho correto em\n"
                "File → Project Settings.")

        self._recent.add(path, project.name)
        self._load_project(project)
        logger.info("Projeto aberto: %s — %s", project.name, path)

    def _load_project(self, project: VPProject):
        """Troca o projeto ativo sem reiniciar a janela."""
        if self._connected:
            self._disconnect()
        self._project = project
        self._state = AppState(paths=project.paths, last_host=project.host)
        self._camera_panel._state = self._state
        self._apply_project()
        self._camera_panel.refresh_from_state()
        self._rebuild_recent_menu()
        logger.info("Projeto carregado: %s", project.name)

    def _on_file_save(self):
        """Salva o projeto atual no mesmo arquivo."""
        if not self._project.file_path:
            self._on_file_save_as()
            return
        self._project.paths = self._state.paths
        try:
            self._project.save()
            logger.info("Projeto salvo: %s", self._project.file_path)
        except Exception as e:
            logger.error("Erro ao salvar projeto: %s", e)
            QMessageBox.critical(self, "Erro ao salvar",
                f"Não foi possível salvar o projeto:\n{e}")

    def _on_file_save_as(self):
        """Salva o projeto em novo arquivo/pasta."""
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Projeto Como…", str(PROJECTS_DIR),
            "VP CTRL Project (*.vpctrl)"
        )
        if not path:
            return
        if not path.endswith(".vpctrl"):
            path += ".vpctrl"
        self._project.paths = self._state.paths
        try:
            self._project.save(path)
            self._recent.add(path, self._project.name)
            self._rebuild_recent_menu()
            self._proj_label.setText(path)
            logger.info("Projeto salvo como: %s", path)
        except Exception as e:
            logger.error("Erro ao salvar projeto como: %s", e)
            QMessageBox.critical(self, "Erro ao salvar",
                f"Não foi possível salvar o projeto:\n{e}")

    def _on_reveal_in_explorer(self):
        """Abre a pasta do projeto no Windows Explorer."""
        import subprocess
        from pathlib import Path
        if not self._project.file_path:
            QMessageBox.information(self, "Reveal in Explorer",
                "Salve o projeto primeiro.")
            return
        folder = str(Path(self._project.file_path).parent)
        try:
            subprocess.Popen(["explorer", folder])
            logger.info("Explorer aberto: %s", folder)
        except Exception as e:
            logger.error("Erro ao abrir Explorer: %s", e)

    def _on_close_project(self):
        """Fecha o projeto atual e volta para a Welcome Screen."""
        if self._connected:
            resp = QMessageBox.question(
                self, "Fechar Projeto",
                "Você está conectado ao UE5.\nDeseja desconectar e fechar o projeto?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
            self._disconnect()

        # Salva antes de fechar
        self._project.paths = self._state.paths
        if self._project.file_path:
            try:
                self._project.save()
                logger.info("Projeto salvo antes de fechar: %s", self._project.name)
            except Exception as e:
                logger.warning("Erro ao salvar projeto ao fechar: %s", e)

        logger.info("Projeto fechado: %s — voltando à Welcome Screen", self._project.name)
        self._poll_timer.stop()
        self._perf_panel.stop()

        from ui.welcome_screen import WelcomeScreen
        self._welcome = WelcomeScreen()
        self._welcome.project_opened.connect(self._on_reopen_project)
        self._welcome.show()
        self.hide()

    def _on_reopen_project(self, project: VPProject):
        """Callback quando usuário abre projeto na Welcome Screen."""
        self._welcome.hide()
        self._load_project(project)
        self._poll_timer.start(POLLING_INTERVAL)
        self.show()

    # ------------------------------------------------------------------
    # Project Settings dialog
    # ------------------------------------------------------------------

    def _show_project_settings(self):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Project Settings")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)
        form.setSpacing(10)
        form.setContentsMargins(20, 20, 20, 20)

        name_edit = QLineEdit(self._project.name)
        host_edit = QLineEdit(self._project.host)

        from PyQt6.QtWidgets import QHBoxLayout as _HBox
        ue5_row = _HBox()
        ue5_edit = QLineEdit(self._project.ue5_project_path)
        ue5_edit.setPlaceholderText("Selecione a pasta raiz do projeto UE5…")
        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedWidth(70)

        def _browse():
            folder = QFileDialog.getExistingDirectory(dlg, "Selecionar Pasta do Projeto UE5", ue5_edit.text())
            if folder:
                ue5_edit.setText(folder)

        btn_browse.clicked.connect(_browse)
        ue5_row.addWidget(ue5_edit)
        ue5_row.addWidget(btn_browse)

        form.addRow("Nome:", name_edit)
        form.addRow("UE5 Host:", host_edit)
        form.addRow("Projeto UE5 *:", ue5_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            import re
            from pathlib import Path

            new_name = name_edit.text().strip() or self._project.name
            new_host = host_edit.text().strip() or DEFAULT_HOST
            new_ue5  = ue5_edit.text().strip()
            old_name = self._project.name
            old_path = self._project.file_path

            self._project.name             = new_name
            self._project.host             = new_host
            self._project.ue5_project_path = new_ue5

            # Renomeia pasta+arquivo se o nome mudou e o projeto já está salvo
            if new_name != old_name and old_path:
                old_dir  = Path(old_path).parent
                new_slug = re.sub(r"[\s_-]+", "_",
                           re.sub(r"[^\w\s-]", "", new_name.lower().strip())) or "projeto"
                new_dir  = old_dir.parent / new_slug
                new_file = new_dir / f"{new_slug}.vpctrl"
                try:
                    if new_dir != old_dir:
                        old_dir.rename(new_dir)
                        logger.info("Projeto renomeado: '%s' → '%s' (%s → %s)",
                                    old_name, new_name, old_dir, new_dir)
                    self._project.save(str(new_file))
                    self._recent.remove(old_path)
                    self._recent.add(str(new_file), new_name)
                    self._rebuild_recent_menu()
                except Exception as e:
                    logger.error("Erro ao renomear projeto: %s", e)
                    QMessageBox.warning(self, "Erro ao renomear",
                        f"Não foi possível renomear a pasta do projeto:\n{e}\n\n"
                        "O nome foi atualizado mas a pasta mantém o nome antigo.")
                    self._project.save()
            else:
                self._project.save()

            self._apply_project()
            logger.info("Project Settings salvo: nome='%s' host='%s' ue5='%s'",
                        new_name, new_host, new_ue5)

    # ------------------------------------------------------------------
    # Host settings dialog (Edit → Manage Devices)
    # ------------------------------------------------------------------

    def _show_host_settings(self):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("UE5 Host")
        dlg.setMinimumWidth(280)
        form = QFormLayout(dlg)
        host_edit = QLineEdit(self._host_edit.text())
        form.addRow("Host:", host_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = host_edit.text().strip()
            if value:
                self._host_edit.setText(value)
                self._project.host = value
                self._camera_panel.set_host(value)

    # ------------------------------------------------------------------
    # Launch UE5
    # ------------------------------------------------------------------

    def _launch_ue5(self):
        import os
        import subprocess
        from pathlib import Path as _Path

        ue5_path = self._project.ue5_project_path.strip()
        if not ue5_path or not os.path.isdir(ue5_path):
            QMessageBox.warning(
                self, "Projeto UE5 não configurado",
                "Configure o caminho do projeto UE5 em File → Project Settings."
            )
            return

        uproject_files = list(_Path(ue5_path).glob("*.uproject"))
        if not uproject_files:
            QMessageBox.warning(
                self, "Projeto UE5 inválido",
                f"Nenhum arquivo .uproject encontrado em:\n{ue5_path}"
            )
            return

        uproject = str(uproject_files[0])
        logger.info("Abrindo projeto UE5: %s", uproject)
        try:
            # Windows: abre o .uproject com o aplicativo associado (UE5 Editor)
            os.startfile(uproject)
            self._status_label.setText("● Abrindo UE5…")
            self._status_label.setStyleSheet("color: #79c0ff;")

            def _restore_status():
                if not self._connected:
                    self._status_label.setText("● Disconnected")
                    self._status_label.setStyleSheet("color: #666666;")

            QTimer.singleShot(4000, _restore_status)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao abrir UE5", str(e))
            logger.error("Erro ao abrir UE5: %s", e)

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _toggle_connection(self):
        if self._connected or self._ws_thread is not None:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        import os
        from pathlib import Path as _Path

        # 1. Verificar se o caminho do projeto UE5 está configurado
        ue5_path = self._project.ue5_project_path.strip()
        if not ue5_path:
            QMessageBox.warning(
                self, "Projeto UE5 não configurado",
                "O caminho do projeto Unreal Engine não foi definido.\n\n"
                "Acesse File → Project Settings e configure o caminho do projeto UE5."
            )
            return

        # 2. Verificar se a pasta do projeto existe
        if not os.path.isdir(ue5_path):
            QMessageBox.warning(
                self, "Projeto UE5 não encontrado",
                f"A pasta do projeto Unreal Engine não foi encontrada:\n\n"
                f"{ue5_path}\n\n"
                "Verifique se o projeto existe e se o caminho está correto em\n"
                "File → Project Settings."
            )
            return

        # 3. Verificar se existe um .uproject na pasta
        uproject_files = list(_Path(ue5_path).glob("*.uproject"))
        if not uproject_files:
            QMessageBox.warning(
                self, "Projeto UE5 inválido",
                f"Nenhum arquivo .uproject encontrado em:\n\n"
                f"{ue5_path}\n\n"
                "Selecione a pasta raiz do projeto Unreal Engine\n"
                "(que contém o arquivo .uproject)."
            )
            return

        host = self._host_edit.text().strip() or DEFAULT_HOST
        self._project.host = host
        self._camera_panel.set_host(host)
        self._btn_connect.setEnabled(False)
        self._btn_connect.setText("Please wait…")
        self._status_label.setText("● Checking UE5 version…")
        self._status_label.setStyleSheet("color: #0078d4;")

        uproject_path = self._project.ue5_project_path.strip()

        def _do_version_check():
            ok, detected = check_ue5_version(host, uproject_path)
            self._version_checked.emit(ok, detected, host)

        threading.Thread(target=_do_version_check, daemon=True).start()

    @pyqtSlot(bool, str, str)
    def _on_version_checked(self, ok: bool, detected: str, host: str):
        if not ok:
            supported = ".".join(str(x) for x in SUPPORTED_UE_VERSION)
            if detected:
                msg = (
                    f"Versão do Unreal Engine incompatível.\n\n"
                    f"Detectado:  {detected}\n"
                    f"Requerido:  {supported}\n\n"
                    f"Este build do VP CTRL só suporta UE {supported}."
                )
            else:
                msg = (
                    f"Não foi possível conectar ao Unreal Engine em '{host}'.\n\n"
                    f"Verifique:\n"
                    f"  • O UE5 está aberto\n"
                    f"  • O plugin Remote Control API está ativo\n"
                    f"  • O host está correto (File → Project Settings)\n"
                    f"  • O firewall não está bloqueando a porta 30010\n\n"
                    f"Versão requerida: UE {supported}"
                )
            QMessageBox.critical(self, "Versão UE5 Incompatível", msg)
            self._btn_connect.setEnabled(True)
            self._btn_connect.setText("Connect")
            self._status_label.setText("● Disconnected")
            self._status_label.setStyleSheet("color: #666666;")
            return

        # Versão OK — verifica plugins antes de conectar
        self._status_label.setText("● Verificando plugins…")
        self._status_label.setStyleSheet("color: #0078d4;")

        def _do_plugin_check():
            result = check_plugins(host)
            self._plugins_checked.emit(result, host)

        threading.Thread(target=_do_plugin_check, daemon=True).start()

    @pyqtSlot(dict, str)
    def _on_plugins_checked(self, result: dict, host: str):
        def _abort(title: str, msg: str):
            QMessageBox.critical(self, title, msg)
            self._btn_connect.setEnabled(True)
            self._btn_connect.setText("Connect")
            self._status_label.setText("● Disconnected")
            self._status_label.setStyleSheet("color: #666666;")

        if result.get("_host_unreachable"):
            _abort(
                "Host inacessível",
                f"Não foi possível conectar ao Unreal Engine em '{host}'.\n\n"
                f"Verifique:\n"
                f"  • O IP/host está correto\n"
                f"  • O UE5 está aberto\n"
                f"  • O Remote Control API está ativo"
            )
            return

        if not result:
            logger.warning("check_plugins: não foi possível verificar plugins")
            _abort(
                "Verificação de plugins falhou",
                "O VP CTRL não conseguiu verificar os plugins do Unreal Engine.\n\n"
                "A causa mais comum é o plugin Python desativado.\n\n"
                "Como resolver:\n"
                "  1. No UE5, acesse Edit → Plugins\n"
                "  2. Busque por 'Python Script Plugin'\n"
                "  3. Ative o plugin e reinicie o projeto UE5\n\n"
                "Após reiniciar, tente conectar novamente."
            )
            return

        missing = [p for p in REQUIRED_PLUGINS if not result.get(p, False)]
        if missing:
            names = "\n".join(f"  • {p}" for p in missing)
            _abort(
                "Plugins obrigatórios ausentes",
                f"Os seguintes plugins não estão ativos no Unreal Engine:\n\n"
                f"{names}\n\n"
                f"Ative-os em Edit → Plugins e reinicie o projeto UE5."
            )
            return

        # Plugins OK — conecta WebSocket
        url = f"ws://{host}:{WS_PORT}"
        logger.info("Plugins OK — conectando a %s", url)
        self._ws_thread = WebSocketThread(url, self)
        self._ws_thread.connected.connect(self._on_connected)
        self._ws_thread.disconnected.connect(self._on_disconnected)
        self._ws_thread.message_received.connect(self._on_message)
        self._ws_thread.start()

    def _disconnect(self):
        if self._ws_thread:
            self._ws_thread.stop()
            self._ws_thread = None
        self._on_disconnected()

    def _refresh_connect_btn(self):
        cls = "btn-connected" if self._connected else "btn-disconnected"
        self._btn_connect.setProperty("class", cls)
        self._btn_connect.style().unpolish(self._btn_connect)
        self._btn_connect.style().polish(self._btn_connect)

    @pyqtSlot()
    def _on_connected(self):
        self._connected = True
        self._btn_connect.setText("Connected")
        self._btn_connect.setEnabled(True)
        self._refresh_connect_btn()
        self._camera_panel.set_free_cam_enabled(True)
        self._set_controls_enabled(True)
        self._status_label.setText("● Starting play…")
        self._status_label.setStyleSheet("color: #0078d4;")
        logger.info("Connected to UE5")

        host = self._host_edit.text().strip() or DEFAULT_HOST

        # Inicia Viewport Play e pilota BP — depois faz sync
        ue5_begin_play(host)
        logger.info("Viewport Play iniciado")

        # Aguarda o play subir antes de pilotar e sincronizar
        QTimer.singleShot(1500, lambda: self._after_play_started(host))

        self._perf_panel.start(host)

    def _after_play_started(self, host: str):
        ue5_pilot_actor(host)
        logger.info("Viewport piloted to BP_VPB1")
        self._sync_from_ue5()

    @pyqtSlot()
    def _on_disconnected(self):
        self._connected = False
        self._btn_connect.setText("Connect")
        self._btn_connect.setEnabled(True)
        self._refresh_connect_btn()
        self._camera_panel.set_free_cam_enabled(False)
        self._set_controls_enabled(False)
        self._status_label.setText("● Disconnected")
        self._status_label.setStyleSheet("color: #666666;")
        logger.info("Disconnected from UE5")
        self._perf_panel.stop()

    @pyqtSlot(dict)
    def _on_message(self, data: dict):
        msg_id = data.get("Id")
        if msg_id and msg_id == self._pending_is_moving_id:
            self._pending_is_moving_id = None
            try:
                params = data.get("Parameters", {})
                value = params.get("IsMoving", params.get("PropertyValue", False))
                self._apply_is_moving(bool(value))
            except Exception:
                pass
            return
        logger.debug("WS message: %s", data)

    def _send(self, message: dict):
        if not self._connected or self._ws_thread is None:
            return
        self._ws_thread.send(message)

    def _set_controls_enabled(self, enabled: bool):
        self._camera_panel.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Pilot
    # ------------------------------------------------------------------

    def _on_toggle_pilot(self):
        host = self._host_edit.text().strip() or DEFAULT_HOST
        if self._camera_panel.free_cam_active:
            ue5_eject_pilot(host)
            logger.info("Free camera — viewport pilot released")
        else:
            ue5_pilot_actor(host)
            logger.info("Viewport re-piloted to BP_VPB1")

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def _sync_from_ue5(self):
        if not self._connected:
            return
        host = self._host_edit.text().strip() or DEFAULT_HOST

        def _do_sync():
            paths = fetch_paths(host)
            if paths:
                self._state.update_from_ue5(paths)
                warm_cache(host)
                QMetaObject.invokeMethod(self, "_on_sync_done", Qt.ConnectionType.QueuedConnection)
            else:
                logger.warning("Sync failed — UE5 returned no paths")

        threading.Thread(target=_do_sync, daemon=True).start()
        self._status_label.setText("● Syncing…")
        self._status_label.setStyleSheet("color: #0078d4;")

    @pyqtSlot()
    def _on_sync_done(self):
        self._camera_panel.refresh_from_state()
        self._status_label.setText("● Idle")
        self._status_label.setStyleSheet("color: #888888;")
        logger.info("Sync complete")

    # ------------------------------------------------------------------
    # Polling IsMoving
    # ------------------------------------------------------------------

    def _setup_polling(self):
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLLING_INTERVAL)
        self._poll_timer.timeout.connect(self._poll_is_moving)
        self._poll_timer.start()

    def _poll_is_moving(self):
        if not self._connected or self._ws_thread is None:
            return
        if self._pending_is_moving_id is not None:
            return
        msg = get_property("IsMoving")
        self._pending_is_moving_id = msg["Id"]
        self._ws_thread.send(msg)

    def _apply_is_moving(self, moving: bool):
        if moving == self._is_moving:
            return
        self._is_moving = moving
        self._camera_panel.set_is_moving(moving)
        if moving:
            path = self._camera_panel.selected_path
            self._status_label.setText(f"● Running PATH {path + 1}")
            self._status_label.setStyleSheet("color: #e67e00; font-weight: bold;")
        else:
            self._status_label.setText("● Idle")
            self._status_label.setStyleSheet("color: #888888;")

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        if Qt.Key.Key_1 <= event.key() <= Qt.Key.Key_8:
            self._camera_panel.keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent):
        # Confirmação se conectado
        if self._connected:
            resp = QMessageBox.question(
                self, "Encerrar VP CTRL",
                "Você está conectado ao UE5.\n\n"
                "Deseja encerrar o VP CTRL?\n"
                "O Play no UE5 será interrompido.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            if resp != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        logger.info("Encerrando VP CTRL...")

        # Desconecta e para Play no UE5
        if self._connected:
            self._disconnect()
            logger.info("Desconectado do UE5 antes de fechar")

        self._poll_timer.stop()
        self._perf_panel.stop()
        if self._ws_thread:
            self._ws_thread.stop()

        # Salva geometria
        self._qsettings.setValue("geometry", self.saveGeometry())

        # Salva projeto
        self._project.paths = self._state.paths
        if self._project.file_path:
            try:
                self._project.save()
                logger.info("Projeto salvo: %s", self._project.name)
            except Exception as e:
                logger.error("Erro ao salvar projeto no fechar: %s", e)
                resp = QMessageBox.warning(
                    self, "Erro ao salvar",
                    f"Não foi possível salvar o projeto:\n{e}\n\nDeseja encerrar mesmo assim?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
                )
                if resp != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return

        logger.info("Aplicação encerrada")
        event.accept()

    def _exit_app(self):
        self.close()

    # ------------------------------------------------------------------
    # View menu
    # ------------------------------------------------------------------

    def _toggle_log(self):
        visible = self._log_panel.isVisible()
        self._log_panel.setVisible(not visible)
        self._act_log.setText("Show Log" if visible else "Hide Log")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self._act_fullscreen.setText("Full Screen")
        else:
            self.showFullScreen()
            self._act_fullscreen.setText("Exit Full Screen")

    def _toggle_always_on_top(self, checked: bool):
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show()
        logger.info("Always on Top: %s", "ON" if checked else "OFF")

    # ------------------------------------------------------------------
    # Tools menu
    # ------------------------------------------------------------------

    def _on_clear_log(self):
        self._log_panel._clear()
        logger.info("Log limpo pelo usuário")

    def _on_export_log(self):
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Log", str(Path.home() / "vpctrl_log.txt"),
            "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            text = self._log_panel._text.toPlainText()
            Path(path).write_text(text, encoding="utf-8")
            logger.info("Log exportado: %s", path)
        except Exception as e:
            logger.error("Erro ao exportar log: %s", e)
            QMessageBox.critical(self, "Erro", f"Não foi possível exportar o log:\n{e}")

    def _on_reset_thumbnails(self):
        if not self._project.thumb_dir:
            QMessageBox.information(self, "Reset Thumbnails",
                "Nenhuma pasta de thumbnails configurada.")
            return
        resp = QMessageBox.question(
            self, "Reset Thumbnails",
            "Deseja apagar todas as thumbnails do projeto atual?\n\n"
            "Os arquivos PNG serão removidos da pasta:\n"
            f"{self._project.thumb_dir}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        import os
        from pathlib import Path
        removed = 0
        for n in range(1, 9):
            for pt in ("a", "b"):
                f = Path(self._project.thumb_dir) / f"path{n}{pt}.png"
                if f.exists():
                    try:
                        f.unlink()
                        removed += 1
                    except Exception as e:
                        logger.warning("Erro ao remover thumbnail %s: %s", f, e)
        self._camera_panel.refresh_from_state()
        logger.info("Reset thumbnails: %d arquivo(s) removido(s)", removed)

    # ------------------------------------------------------------------
    # Help menu
    # ------------------------------------------------------------------

    def _on_open_docs(self):
        import webbrowser
        webbrowser.open("https://vpctrl.com.br/docs")
        logger.info("Documentação aberta no navegador")

    def _on_check_updates(self):
        import webbrowser
        webbrowser.open("https://vpctrl.com.br/updates")
        logger.info("Página de updates aberta no navegador")

    def _on_show_license(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        from core.license_client import LicenseClient, LicenseStatus

        client = LicenseClient()
        result = client.check_license()

        status_map = {
            LicenseStatus.VALID:         ("✔ Licença ativa",          "#3fb950"),
            LicenseStatus.GRACE:         ("⚠ Modo offline (graça)",   "#e3b341"),
            LicenseStatus.EXPIRED:       ("✘ Licença expirada",        "#f85149"),
            LicenseStatus.SUSPENDED:     ("✘ Licença suspensa",        "#f85149"),
            LicenseStatus.INVALID:       ("✘ Licença inválida",        "#f85149"),
            LicenseStatus.NOT_ACTIVATED: ("✘ Não ativada nesta máquina","#f85149"),
        }
        label, color = status_map.get(result.status, ("Desconhecido", "#8b949e"))

        dlg = QDialog(self)
        dlg.setWindowTitle("Licença VP CTRL")
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(8)

        status_lbl = QLabel(label)
        status_lbl.setStyleSheet(f"font-size:14px; font-weight:bold; color:{color};")
        layout.addWidget(status_lbl)

        if result.customer_name:
            layout.addWidget(QLabel(f"Cliente: {result.customer_name}"))
        if result.message:
            msg_lbl = QLabel(result.message)
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
            layout.addWidget(msg_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)
        dlg.exec()

    def _on_about(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        from config.settings import SUPPORTED_UE_VERSION

        ue_ver = ".".join(str(x) for x in SUPPORTED_UE_VERSION)

        dlg = QDialog(self)
        dlg.setWindowTitle("About VP CTRL")
        dlg.setMinimumWidth(340)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(6)

        title = QLabel("VP CTRL")
        title.setStyleSheet("font-size:22px; font-weight:bold; color:#2f81f7;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Virtual Production Controller"))

        layout.addSpacing(8)

        for text in [
            f"Versão:           3.0",
            f"Unreal Engine:    {ue_ver}",
            f"Plataforma:       Windows",
            f"Autor:            Ricardo Pacheco",
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#8b949e; font-size:11px;")
            layout.addWidget(lbl)

        layout.addSpacing(8)

        copy_lbl = QLabel("© 2025 Ricardo Pacheco. Todos os direitos reservados.")
        copy_lbl.setStyleSheet("color:#484f58; font-size:10px;")
        copy_lbl.setWordWrap(True)
        layout.addWidget(copy_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)
        dlg.exec()
