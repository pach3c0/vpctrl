"""
VP CTRL v3 — Gerenciador de arquivos recentes.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

from PyQt6.QtCore import QSettings

SETTINGS_ORG = "VPCtrl"
SETTINGS_APP = "VPCtrlV3"
MAX_RECENT = 10


class RecentFilesManager:
    def __init__(self):
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)

    def get_recent(self) -> list[dict]:
        """Retorna lista de {path, name} dos arquivos recentes (existentes)."""
        raw = self._settings.value("recent_files", [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = []
        # Filtra arquivos que ainda existem
        result = []
        for item in raw:
            if isinstance(item, dict) and Path(item.get("path", "")).exists():
                result.append(item)
        return result

    def add(self, file_path: str, name: str):
        """Adiciona (ou move para o topo) um arquivo na lista de recentes."""
        recent = self.get_recent()
        # Remove entrada existente com mesmo path
        recent = [r for r in recent if r["path"] != file_path]
        recent.insert(0, {"path": file_path, "name": name})
        recent = recent[:MAX_RECENT]
        self._settings.setValue("recent_files", json.dumps(recent))

    def remove(self, file_path: str):
        """Remove um arquivo da lista de recentes."""
        recent = [r for r in self.get_recent() if r["path"] != file_path]
        self._settings.setValue("recent_files", json.dumps(recent))

    def clear(self):
        self._settings.remove("recent_files")
