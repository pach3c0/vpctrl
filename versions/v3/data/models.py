"""
VP CTRL v2 — Modelos de dados locais.
Representa o estado dos paths independente do UE5.
"""
from __future__ import annotations
import json
import math
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from config.settings import APPDATA_DIR, PATHS_FILE, NUM_PATHS

logger = logging.getLogger(__name__)


@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class Quat:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    def to_euler_degrees(self) -> Vec3:
        """Converte quaternion para Euler (Pitch, Yaw, Roll) em graus."""
        x, y, z, w = self.x, self.y, self.z, self.w

        # Roll (X)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))

        # Pitch (Y)
        sinp = 2 * (w * y - z * x)
        if abs(sinp) >= 1:
            pitch = math.degrees(math.copysign(math.pi / 2, sinp))
        else:
            pitch = math.degrees(math.asin(sinp))

        # Yaw (Z)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.degrees(math.atan2(siny_cosp, cosy_cosp))

        return Vec3(x=pitch, y=yaw, z=roll)


@dataclass
class CameraPoint:
    location: Vec3 = field(default_factory=Vec3)
    rotation: Quat = field(default_factory=Quat)
    focal_length: float = 35.0
    focus_distance: float = 1000.0
    is_set: bool = False  # True quando foi gravado pelo usuário


@dataclass
class PathData:
    index: int = 0
    name: str = ""
    duration: float = 2.0
    point_a: CameraPoint = field(default_factory=CameraPoint)
    point_b: CameraPoint = field(default_factory=CameraPoint)

    def __post_init__(self):
        if not self.name:
            self.name = f"PATH {self.index + 1}"

    @property
    def is_configured(self) -> bool:
        return self.point_a.is_set and self.point_b.is_set


@dataclass
class AppState:
    """Estado completo do app — persistido em JSON."""
    paths: list[PathData] = field(default_factory=list)
    last_host: str = "127.0.0.1"
    version: str = "2.0"

    def __post_init__(self):
        if not self.paths:
            self.paths = [PathData(index=i) for i in range(NUM_PATHS)]

    # ------------------------------------------------------------------
    # Serialização
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        def serialize(obj):
            if isinstance(obj, (Vec3, Quat, CameraPoint, PathData, AppState)):
                return {k: serialize(v) for k, v in asdict(obj).items()}
            if isinstance(obj, list):
                return [serialize(i) for i in obj]
            return obj
        return serialize(self)

    @classmethod
    def from_dict(cls, d: dict) -> AppState:
        paths = []
        for pd in d.get("paths", []):
            pa = pd.get("point_a", {})
            pb = pd.get("point_b", {})
            paths.append(PathData(
                index=pd.get("index", 0),
                name=pd.get("name", ""),
                duration=pd.get("duration", 2.0),
                point_a=CameraPoint(
                    location=Vec3(**pa.get("location", {})),
                    rotation=Quat(**pa.get("rotation", {})),
                    focal_length=pa.get("focal_length", 35.0),
                    focus_distance=pa.get("focus_distance", 1000.0),
                    is_set=pa.get("is_set", False),
                ),
                point_b=CameraPoint(
                    location=Vec3(**pb.get("location", {})),
                    rotation=Quat(**pb.get("rotation", {})),
                    focal_length=pb.get("focal_length", 35.0),
                    focus_distance=pb.get("focus_distance", 1000.0),
                    is_set=pb.get("is_set", False),
                ),
            ))
        # Garante sempre NUM_PATHS paths
        while len(paths) < NUM_PATHS:
            paths.append(PathData(index=len(paths)))
        return cls(
            paths=paths[:NUM_PATHS],
            last_host=d.get("last_host", "127.0.0.1"),
            version=d.get("version", "2.0"),
        )

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def save(self):
        try:
            APPDATA_DIR.mkdir(parents=True, exist_ok=True)
            PATHS_FILE.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            logger.debug("AppState salvo em %s", PATHS_FILE)
        except Exception as e:
            logger.error("Erro ao salvar AppState: %s", e)

    @classmethod
    def load(cls) -> AppState:
        try:
            if PATHS_FILE.exists():
                data = json.loads(PATHS_FILE.read_text(encoding="utf-8"))
                state = cls.from_dict(data)
                logger.info("AppState carregado de %s", PATHS_FILE)
                return state
        except Exception as e:
            logger.warning("Erro ao carregar AppState: %s — usando defaults", e)
        return cls()

    # ------------------------------------------------------------------
    # Sync com UE5
    # ------------------------------------------------------------------

    def update_from_ue5(self, ue5_paths: list[dict]):
        """
        Atualiza os paths locais com dados vindos do UE5 (array Paths).
        Preserva nomes customizados.
        """
        key_point_a = None
        key_point_b = None
        key_focal_a = None
        key_focus_a = None
        key_focal_b = None
        key_focus_b = None
        key_duration = None

        # Descobre as chaves reais (têm sufixo UUID no UE5)
        if ue5_paths:
            sample = ue5_paths[0]
            for k in sample:
                kl = k.lower()
                if "pointa" in kl or "point_a" in kl:
                    key_point_a = k
                elif "pointb" in kl or "point_b" in kl:
                    key_point_b = k
                elif "focallengtha" in kl or "focal_length_a" in kl:
                    key_focal_a = k
                elif "focaldistancea" in kl or "focusdistancea" in kl or "focus_distance_a" in kl:
                    key_focus_a = k
                elif "focallengthb" in kl or "focal_length_b" in kl:
                    key_focal_b = k
                elif "focaldistanceb" in kl or "focusdistanceb" in kl or "focus_distance_b" in kl:
                    key_focus_b = k
                elif "duration" in kl:
                    key_duration = k

        for i, ue5_path in enumerate(ue5_paths):
            if i >= NUM_PATHS:
                break
            pd = self.paths[i]
            pd.duration = float(ue5_path.get(key_duration, pd.duration) or pd.duration)

            def parse_point(ue5_transform: dict, focal: float, focus: float) -> CameraPoint:
                if not ue5_transform:
                    return CameraPoint()
                rot = ue5_transform.get("Rotation", {})
                loc = ue5_transform.get("Translation", {})
                q = Quat(
                    x=rot.get("X", 0), y=rot.get("Y", 0),
                    z=rot.get("Z", 0), w=rot.get("W", 1),
                )
                v = Vec3(x=loc.get("X", 0), y=loc.get("Y", 0), z=loc.get("Z", 0))
                has_data = not (v.x == 0 and v.y == 0 and v.z == 0 and focal == 0)
                return CameraPoint(
                    location=v, rotation=q,
                    focal_length=float(focal or 35.0),
                    focus_distance=float(focus or 1000.0),
                    is_set=has_data,
                )

            if key_point_a:
                pd.point_a = parse_point(
                    ue5_path.get(key_point_a, {}),
                    ue5_path.get(key_focal_a, 35.0),
                    ue5_path.get(key_focus_a, 1000.0),
                )
            if key_point_b:
                pd.point_b = parse_point(
                    ue5_path.get(key_point_b, {}),
                    ue5_path.get(key_focal_b, 35.0),
                    ue5_path.get(key_focus_b, 1000.0),
                )

        logger.info("AppState atualizado com %d paths do UE5", len(ue5_paths))
        self.save()
