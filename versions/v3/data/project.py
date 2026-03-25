"""
VP CTRL v3 — Modelo de projeto (.vpctrl).
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import NUM_PATHS, PROJECTS_DIR
from data.models import AppState, PathData

logger = logging.getLogger(__name__)


@dataclass
class VPProject:
    name: str = "Novo Projeto"
    host: str = "127.0.0.1"
    ue5_project_path: str = ""
    paths: list[PathData] = field(default_factory=list)
    file_path: str = ""  # caminho do .vpctrl no disco (não serializado)

    def __post_init__(self):
        if not self.paths:
            self.paths = [PathData(index=i) for i in range(NUM_PATHS)]

    @property
    def thumb_dir(self) -> str:
        if not self.ue5_project_path:
            return ""
        return str(Path(self.ue5_project_path) / "Saved" / "Screenshots" / "WindowsEditor")

    # ------------------------------------------------------------------
    # Serialização
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        state = AppState(paths=self.paths, last_host=self.host)
        d = state.to_dict()
        return {
            "name": self.name,
            "host": self.host,
            "ue5_project_path": self.ue5_project_path,
            "paths": d["paths"],
            "version": "3.0",
        }

    @classmethod
    def from_dict(cls, d: dict, file_path: str = "") -> VPProject:
        state = AppState.from_dict(d)
        return cls(
            name=d.get("name", "Projeto"),
            host=d.get("host", d.get("last_host", "127.0.0.1")),
            ue5_project_path=d.get("ue5_project_path", ""),
            paths=state.paths,
            file_path=file_path,
        )

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def save(self, path: str | None = None):
        target = Path(path or self.file_path)
        if not target.suffix:
            target = target.with_suffix(".vpctrl")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.file_path = str(target)
            logger.info("Projeto salvo: %s", target)
        except Exception as e:
            logger.error("Erro ao salvar projeto: %s", e)
            raise

    @classmethod
    def load(cls, file_path: str) -> VPProject:
        p = Path(file_path)
        data = json.loads(p.read_text(encoding="utf-8"))
        project = cls.from_dict(data, file_path=str(p))
        logger.info("Projeto carregado: %s", p)
        return project

    @classmethod
    def new(cls, name: str, host: str, ue5_project_path: str) -> VPProject:
        return cls(name=name, host=host, ue5_project_path=ue5_project_path)
