"""
VP CTRL v3 — Tela de boas-vindas (New / Open / Recent).
"""
from __future__ import annotations
import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QFileDialog, QDialog, QFormLayout,
    QLineEdit, QDialogButtonBox, QMessageBox, QApplication,
)
from PyQt6.QtGui import QFont

from core.recent_files import RecentFilesManager
from data.project import VPProject
from config.settings import PROJECTS_DIR

logger = logging.getLogger(__name__)


class WelcomeScreen(QWidget):
    """Tela inicial — emite project_opened(VPProject) quando pronto."""
    project_opened = pyqtSignal(object)  # VPProject

    def __init__(self):
        super().__init__()
        self._recent = RecentFilesManager()
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        self.setWindowTitle("VP CTRL v3.0")
        self.setMinimumSize(680, 460)
        self.resize(680, 460)
        self.setStyleSheet(self._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(90)
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(40, 20, 40, 16)
        h_layout.setSpacing(4)

        title = QLabel("VP CTRL")
        title.setObjectName("appTitle")
        subtitle = QLabel("Virtual Production Controller")
        subtitle.setObjectName("appSubtitle")

        h_layout.addWidget(title)
        h_layout.addWidget(subtitle)
        root.addWidget(header)

        # ── Body ──────────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Left panel — actions
        left = QFrame()
        left.setObjectName("leftPanel")
        left.setFixedWidth(200)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(20, 30, 20, 20)
        left_layout.setSpacing(8)

        lbl = QLabel("Start")
        lbl.setObjectName("sectionLabel")
        left_layout.addWidget(lbl)

        btn_new = QPushButton("  New Project")
        btn_new.setObjectName("actionBtn")
        btn_new.setFixedHeight(36)
        btn_new.clicked.connect(self._on_new)
        left_layout.addWidget(btn_new)

        btn_open = QPushButton("  Open Project…")
        btn_open.setObjectName("actionBtn")
        btn_open.setFixedHeight(36)
        btn_open.clicked.connect(self._on_open)
        left_layout.addWidget(btn_open)

        left_layout.addStretch()

        body.addWidget(left)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setObjectName("divider")
        body.addWidget(div)

        # Right panel — recents
        right = QWidget()
        right.setObjectName("rightPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 24, 24, 24)
        right_layout.setSpacing(4)

        lbl2 = QLabel("Recent")
        lbl2.setObjectName("sectionLabel")
        right_layout.addWidget(lbl2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self._recent_container = QWidget()
        self._recent_container.setStyleSheet("background: transparent;")
        self._recent_layout = QVBoxLayout(self._recent_container)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(2)
        self._recent_layout.addStretch()

        scroll.setWidget(self._recent_container)
        right_layout.addWidget(scroll)

        body.addWidget(right, 1)
        root.addLayout(body, 1)

        self._populate_recent()

    def _populate_recent(self):
        # Remove widgets anteriores (exceto o stretch)
        while self._recent_layout.count() > 1:
            item = self._recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        import os
        recent = self._recent.get_recent()
        if not recent:
            lbl = QLabel("No recent projects.")
            lbl.setObjectName("emptyLabel")
            self._recent_layout.insertWidget(0, lbl)
        else:
            for i, entry in enumerate(recent):
                exists = os.path.isfile(entry["path"])
                btn = _RecentItem(entry["name"], entry["path"], valid=exists)
                btn.clicked_path.connect(self._open_path)
                self._recent_layout.insertWidget(i, btn)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_new(self):
        dlg = _NewProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, host, ue5_path = dlg.values()

        # Verifica nome duplicado
        save_dir = PROJECTS_DIR / _slugify(name)
        save_path = save_dir / f"{_slugify(name)}.vpctrl"
        if save_path.exists():
            resp = QMessageBox.question(
                self, "Projeto já existe",
                f"Já existe um projeto com o nome '{name}'.\n\n"
                "Deseja sobrescrever?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            if resp != QMessageBox.StandardButton.Yes:
                return

        project = VPProject.new(name=name, host=host, ue5_project_path=ue5_path)
        try:
            project.save(str(save_path))
            self._recent.add(str(save_path), name)
            logger.info("Novo projeto criado: %s — UE5: %s — Host: %s", save_path, ue5_path, host)
            self.project_opened.emit(project)
        except Exception as e:
            logger.error("Erro ao criar projeto: %s — %s", save_path, e)
            QMessageBox.critical(self, "Erro ao criar projeto",
                f"Não foi possível criar o projeto:\n{e}")

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Projeto", str(PROJECTS_DIR),
            "VP CTRL Project (*.vpctrl);;All Files (*)"
        )
        if path:
            self._open_path(path)

    def _open_path(self, path: str):
        import os

        if not os.path.isfile(path):
            resp = QMessageBox.question(
                self, "Arquivo não encontrado",
                f"O projeto não foi encontrado em:\n{path}\n\n"
                "Deseja procurar o arquivo em outro local?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            self._recent.remove(path)
            self._populate_recent()
            logger.warning("Projeto não encontrado: %s — removido dos recentes", path)
            if resp == QMessageBox.StandardButton.Yes:
                new_path, _ = QFileDialog.getOpenFileName(
                    self, "Localizar Projeto", str(PROJECTS_DIR),
                    "VP CTRL Project (*.vpctrl);;All Files (*)"
                )
                if new_path:
                    self._open_path(new_path)
            return

        try:
            project = VPProject.load(path)
        except ValueError as e:
            logger.error("Projeto corrompido: %s — %s", path, e)
            QMessageBox.critical(self, "Projeto corrompido",
                f"O arquivo está corrompido e não pode ser aberto:\n{path}\n\n{e}")
            self._recent.remove(path)
            self._populate_recent()
            return
        except Exception as e:
            logger.error("Erro ao abrir projeto: %s — %s", path, e)
            QMessageBox.critical(self, "Erro ao abrir projeto",
                f"Não foi possível abrir o projeto:\n{path}\n\n{e}")
            return

        # Avisa se pasta UE5 não existe (não bloqueia)
        if project.ue5_project_path and not os.path.isdir(project.ue5_project_path):
            logger.warning("Pasta UE5 não encontrada: %s", project.ue5_project_path)
            QMessageBox.warning(self, "Pasta UE5 não encontrada",
                f"A pasta do projeto UE5 configurada não foi encontrada:\n"
                f"{project.ue5_project_path}\n\n"
                "Configure o caminho correto em File → Project Settings.")

        self._recent.add(path, project.name)
        logger.info("Projeto aberto: %s — %s", project.name, path)
        self.project_opened.emit(project)

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def _stylesheet(self) -> str:
        return """
        WelcomeScreen {
            background-color: #1e1e1e;
        }
        #header {
            background-color: #252526;
            border-bottom: 1px solid #3c3c3c;
        }
        #appTitle {
            color: #ffffff;
            font-size: 22px;
            font-weight: bold;
        }
        #appSubtitle {
            color: #888888;
            font-size: 12px;
        }
        #leftPanel {
            background-color: #252526;
        }
        #rightPanel {
            background-color: #1e1e1e;
        }
        #divider {
            color: #3c3c3c;
        }
        #sectionLabel {
            color: #cccccc;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        #actionBtn {
            background-color: #2d2d2d;
            color: #cccccc;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            text-align: left;
            padding-left: 8px;
            font-size: 13px;
        }
        #actionBtn:hover {
            background-color: #094771;
            color: #ffffff;
            border-color: #0078d4;
        }
        #emptyLabel {
            color: #555555;
            font-size: 12px;
        }
        """


class _RecentItem(QFrame):
    clicked_path = pyqtSignal(str)

    def __init__(self, name: str, path: str, valid: bool = True):
        super().__init__()
        self._path = path
        self.setObjectName("recentItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self.setStyleSheet("""
            #recentItem { background: transparent; border-radius: 4px; }
            #recentItem:hover { background-color: #2a2d2e; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        name_color = "#cccccc" if valid else "#8b4343"
        prefix = "" if valid else "⚠ "
        name_lbl = QLabel(f"{prefix}{name}")
        name_lbl.setStyleSheet(f"color: {name_color}; font-size: 13px;")

        path_lbl = QLabel(path)
        path_lbl.setStyleSheet("color: #666666; font-size: 10px;")
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        layout.addWidget(name_lbl)
        layout.addWidget(path_lbl)

        if not valid:
            self.setToolTip("Arquivo não encontrado — clique para procurar")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_path.emit(self._path)
        super().mousePressEvent(event)


class _NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        form.setSpacing(10)
        form.setContentsMargins(20, 20, 20, 20)

        self._name = QLineEdit("Novo Projeto")
        self._host = QLineEdit("127.0.0.1")

        # Projeto UE5 — obrigatório, com botão Browse
        ue5_row = QHBoxLayout()
        self._ue5_path = QLineEdit()
        self._ue5_path.setPlaceholderText("Selecione a pasta raiz do projeto UE5…")
        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._browse_ue5)
        ue5_row.addWidget(self._ue5_path)
        ue5_row.addWidget(btn_browse)

        self._lbl_ue5_warn = QLabel("⚠ Obrigatório — selecione a pasta do projeto UE5")
        self._lbl_ue5_warn.setStyleSheet("color: #da3633; font-size: 11px;")
        self._lbl_ue5_warn.hide()

        form.addRow("Nome:", self._name)
        form.addRow("UE5 Host:", self._host)
        form.addRow("Projeto UE5 *:", ue5_row)
        form.addRow("", self._lbl_ue5_warn)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _browse_ue5(self):
        from PyQt6.QtWidgets import QFileDialog as _FD
        folder = _FD.getExistingDirectory(self, "Selecionar Pasta do Projeto UE5", "")
        if folder:
            self._ue5_path.setText(folder)
            self._lbl_ue5_warn.hide()

    def _on_accept(self):
        import os
        from pathlib import Path
        path = self._ue5_path.text().strip()
        if not path or not os.path.isdir(path):
            self._lbl_ue5_warn.setText("⚠ Obrigatório — selecione a pasta do projeto UE5")
            self._lbl_ue5_warn.show()
            return
        # Verifica se existe .uproject na pasta
        uprojects = list(Path(path).glob("*.uproject"))
        if not uprojects:
            self._lbl_ue5_warn.setText("⚠ Pasta não contém um projeto UE5 válido (.uproject)")
            self._lbl_ue5_warn.show()
            return
        self._lbl_ue5_warn.hide()
        self.accept()

    def values(self) -> tuple[str, str, str]:
        return (
            self._name.text().strip() or "Novo Projeto",
            self._host.text().strip() or "127.0.0.1",
            self._ue5_path.text().strip(),
        )


def _slugify(name: str) -> str:
    """Converte nome em slug seguro para uso como nome de pasta/arquivo."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "_", s)
    return s or "projeto"
