"""
VP CTRL v3 — Configurações fixas.
O usuário não vê nem edita esses valores.
"""
import os
from pathlib import Path

# ── Versão UE5 suportada (este build só funciona com esta versão) ──────
SUPPORTED_UE_VERSION = (5, 7, 4)   # major, minor, patch

# ── UE5 Remote Control ────────────────────────────────────────────────
DEFAULT_HOST        = "127.0.0.1"
WS_PORT             = 30020
HTTP_PORT           = 30010
OSC_PORT            = 8001

# ── Blueprint (fixo — usuário deve manter esse nome no UE5) ───────────
BP_NAME             = "BP_VPB1"
BP_ACTOR_PATH       = "/Game/VprodProject/Maps/Main.Main:PersistentLevel.BP_VPB1_C_1"
PRESET_NAME         = "VPControlPreset"

# ── Dados locais ──────────────────────────────────────────────────────
APPDATA_DIR         = Path(os.environ.get("APPDATA", "~")) / "VPCtrl"
PATHS_FILE          = APPDATA_DIR / "paths.json"
PROJECTS_DIR        = Path.home() / "Documents" / "VPCtrl" / "projetos"

# ── Timings ───────────────────────────────────────────────────────────
POLLING_INTERVAL    = 500   # ms — IsMoving
RECONNECT_INTERVAL  = 3.0   # s  — WebSocket reconnect
DEBOUNCE_INTERVAL   = 50    # ms — sliders
GRAVAR_PULSE_MS     = 200   # ms — flash botão gravar

NUM_PATHS           = 8

# ── Câmeras — Media Capture BlackMagic ────────────────────────────────
MEDIA_OUTPUT_ASSET  = "/Game/NewBlackmagicMediaOutput.NewBlackmagicMediaOutput"
CAMERA_ACTORS       = {
    1: "CineCameraActor_4",   # VPCtrl_Camera1
    2: "CineCameraActor_5",   # VPCtrl_Camera2
    3: "CineCameraActor_1",   # VPCtrl_Camera3
}
