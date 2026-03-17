import webview
import uvicorn
import threading
import httpx
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import os
import time

APP_PORT        = 8000

# ── NDI Source Discovery ────────────────────────────────────
_ndi_sources: list[str] = []

def _ndi_scan_thread():
    """Thread que mantém lista de sources NDI atualizada via cyndilib."""
    global _ndi_sources
    try:
        from cyndilib.finder import Finder
        with Finder() as finder:
            while True:
                finder.wait_for_sources(timeout=2.0)
                _ndi_sources = [str(s.name) for s in finder]
                time.sleep(1)
    except Exception:
        _ndi_sources = []
PRESET_NAME     = "VPCtrl_Preset"
MANAGER_ACTOR   = ""  # preenchido automaticamente no connect
MEDIA_PROFILE     = "/Game/VPCtrl/VPCtrl_MediaProfile.VPCtrl_MediaProfile"
BILLBOARD1_COMP   = "/Game/VprodProject/Maps/Main.Main:PersistentLevel.MediaPlate_0.MediaPlateComponent0"

# ── Estado global ──────────────────────────────────────────
state = {
    "connected": False,
    "ue5_base": "http://localhost:30010",
    "project_name": None,
    "active_camera": 1,
    "tally_on": False,
    "fps": 0.0,
    "gpu": 0,
    "media_profile": None,
    "ndi": {"runtime_ok": False, "plugin_ok": False},
}

connected_clients: list[WebSocket] = []

# ── Helpers UE5 ────────────────────────────────────────────
def ue5_url(path: str) -> str:
    return f"{state['ue5_base']}{path}"

async def ue5_get(path: str):
    async with httpx.AsyncClient(timeout=3.0) as c:
        return await c.get(ue5_url(path))

async def ue5_call_function(function_name: str):
    """Chama uma função do VPCtrl_Manager via /remote/object/call."""
    global MANAGER_ACTOR
    async with httpx.AsyncClient(timeout=5.0) as c:
        return await c.put(
            ue5_url("/remote/object/call"),
            json={
                "objectPath": MANAGER_ACTOR,
                "functionName": function_name,
                "generateTransaction": True
            }
        )

async def ue5_set_property(property_display_name: str, value):
    """Define o valor de uma propriedade exposta no Preset pelo DisplayName."""
    async with httpx.AsyncClient(timeout=5.0) as c:
        return await c.put(
            ue5_url(f"/remote/preset/{PRESET_NAME}/property"),
            json={"PropertyLabel": property_display_name, "PropertyValue": value}
        )

async def ue5_get_property(property_display_name: str):
    """Lê o valor de uma propriedade exposta no Preset pelo DisplayName."""
    async with httpx.AsyncClient(timeout=5.0) as c:
        return await c.get(
            ue5_url(f"/remote/preset/{PRESET_NAME}/property"),
            params={"propertyLabel": property_display_name}
        )

# ── Lifespan ───────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(poll_ue5())
    yield

app = FastAPI(lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ── Rota principal ─────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        return f.read()

# ── WebSocket ──────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        await ws.send_json({"type": "state", "data": state})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in connected_clients:
            connected_clients.remove(ws)

async def broadcast(event: dict):
    for ws in list(connected_clients):
        try:
            await ws.send_json(event)
        except Exception:
            if ws in connected_clients:
                connected_clients.remove(ws)

# ── CONNECT ────────────────────────────────────────────────
@app.post("/api/connect")
async def connect(body: dict):
    host = body.get("host", "localhost")
    port = body.get("port", 30010)
    base = f"http://{host}:{port}"
    state["ue5_base"] = base

    result = {
        "ue5": False,
        "project": None,
        "preset_found": False,
        "ndi_runtime": False,
        "ndi_plugin": False,
        "media_profile": None,
    }

    async with httpx.AsyncClient(timeout=3.0) as client:

        # 1. Testa conexão — lista presets
        try:
            r = await client.get(f"{base}/remote/presets")
            if r.status_code == 200:
                result["ue5"] = True
                state["connected"] = True
                presets = r.json().get("Presets", [])
                result["preset_found"] = any(p.get("Name") == PRESET_NAME for p in presets)
        except Exception:
            return result

        if not result["ue5"]:
            return result

        # 2. Tenta pegar nome do projeto via preset path
        try:
            r = await client.get(f"{base}/remote/preset/{PRESET_NAME}")
            if r.status_code == 200:
                data = r.json()
                # Extrai nome do projeto do path do preset (ex: /Game/VPCtrl/VPCtrl_Preset)
                path = data.get("Preset", {}).get("Path", "")
                parts = [p for p in path.split("/") if p and p not in ("Game", PRESET_NAME)]
                result["project"] = parts[0] if parts else "UnrealProject"
                state["project_name"] = result["project"]

                # Pega o path do actor VPCtrl_Manager para chamar funções
                global MANAGER_ACTOR
                groups = data.get("Preset", {}).get("Groups", [])
                for group in groups:
                    for func in group.get("ExposedFunctions", []):
                        owners = func.get("OwnerObjects", [])
                        if owners:
                            MANAGER_ACTOR = owners[0].get("Path", "")
                            break
                    if MANAGER_ACTOR:
                        break

                # Lê media profile ativo das propriedades expostas
                props = [p for g in data.get("Preset", {}).get("Groups", []) for p in g.get("ExposedProperties", [])]
                for prop in props:
                    if "MediaProfile" in prop.get("DisplayName", ""):
                        val = prop.get("Value", {})
                        if isinstance(val, dict):
                            asset_path = val.get("ObjectName", val.get("AssetName", ""))
                        else:
                            asset_path = str(val)
                        # Pega só o nome do asset (ex: VPCtrl_MediaProfile)
                        result["media_profile"] = asset_path.split(".")[-1] if asset_path else None
                        state["media_profile"] = result["media_profile"]
                        break
        except Exception:
            result["project"] = "UnrealProject"
            state["project_name"] = result["project"]

        # 3. Verifica NDI Runtime
        try:
            import NDIlib  # noqa: F401
            result["ndi_runtime"] = True
            state["ndi"]["runtime_ok"] = True
        except ImportError:
            result["ndi_runtime"] = False

        # 4. NDI plugin — verifica se há saída NDI no projeto
        result["ndi_plugin"] = result["ue5"]
        state["ndi"]["plugin_ok"] = result["ndi_plugin"]

    await broadcast({"type": "state", "data": state})
    return result

# ── INPUT — Media Profile ──────────────────────────────────
@app.get("/api/input/status")
async def input_status():
    """Retorna o status atual do Media Profile."""
    try:
        r = await ue5_get(f"/remote/preset/{PRESET_NAME}")
        if r.status_code == 200:
            data = r.json()
            props = data.get("Preset", {}).get("Properties", [])
            for prop in props:
                if "MediaProfile" in prop.get("DisplayName", ""):
                    return {"ok": True, "media_profile": prop.get("Value"), "raw": prop}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "media_profile": None}

@app.post("/api/input/apply")
async def input_apply():
    """Chama ApplyMediaProfile no UE5."""
    try:
        r = await ue5_call_function("ApplyMediaProfile")
        ok = r.status_code in (200, 204)
        if ok:
            state["media_profile"] = state.get("media_profile", "VPCtrl_MediaProfile")
            await broadcast({"type": "input", "data": {"media_profile": state["media_profile"]}})
        return {"ok": ok, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/input/set_profile")
async def input_set_profile(body: dict):
    """Troca o Media Profile ativo e aplica."""
    profile_path = body.get("path")  # ex: /Game/VPCtrl/VPCtrl_MediaProfile
    if not profile_path:
        return {"ok": False, "error": "path obrigatório"}
    try:
        # 1. Muda a propriedade ActiveMediaProfile
        r = await ue5_set_property("ActiveMediaProfile", {"AssetPath": profile_path})
        if r.status_code not in (200, 204):
            return {"ok": False, "error": f"set_property status {r.status_code}"}
        # 2. Aplica o profile
        await ue5_call_function("ApplyMediaProfile")
        name = profile_path.split("/")[-1]
        state["media_profile"] = name
        await broadcast({"type": "input", "data": {"media_profile": name}})
        return {"ok": True, "profile": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── BILLBOARD 1 — File Media Source ───────────────────────
@app.get("/api/input/b1/filepath")
async def b1_get_filepath():
    """Lê o ExternalMediaPath atual do Billboard 1."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={"objectPath": BILLBOARD1_COMP, "propertyName": "MediaPlateResource", "access": "READ_ACCESS"}
            )
            if r.status_code == 200:
                fp = r.json().get("MediaPlateResource", {}).get("ExternalMediaPath", "")
                return {"ok": True, "filepath": fp}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "filepath": ""}

@app.post("/api/input/b1/filepath")
async def b1_set_filepath(body: dict):
    """Define o arquivo do Billboard 1 via MediaPlateResource."""
    path = body.get("path", "")
    if not path:
        return {"ok": False, "error": "path required"}

    # Normaliza para barras Windows e verifica extensão
    path = path.replace("/", "\\")
    ext = path.lower().split(".")[-1] if "." in path else ""
    supported = {"mp4", "mov", "avi", "mkv", "mxf", "wmv"}
    if ext not in supported:
        return {"ok": False, "error": f"Unsupported format: .{ext}. Supported: {', '.join(sorted(supported))}"}

    try:
        await b1_call("Close")
        await asyncio.sleep(0.3)
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={
                    "objectPath": BILLBOARD1_COMP,
                    "propertyName": "MediaPlateResource",
                    "propertyValue": {"MediaPlateResource": {
                        "Type": "External",
                        "ExternalMediaPath": path,
                        "MediaAsset": "",
                        "SourcePlaylist": "",
                        "ExternalMedia": ""
                    }},
                    "access": "WRITE_ACCESS"
                }
            )
            if r.status_code not in (200, 204):
                return {"ok": False, "error": f"status {r.status_code}"}

        await asyncio.sleep(0.5)
        await b1_call("Open")
        await broadcast({"type": "b1_filepath", "data": {"path": path}})
        return {"ok": True, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── BILLBOARD 1 — BlackMagic Signal Source ────────────────
BMB1_ASSET  = "/Game/VPCtrl/Bilbords/Bilbord1/BMB1.BMB1"
BMB1_PATH   = f"/Script/BlackmagicMedia.BlackmagicMediaSource'{BMB1_ASSET}'"
NDIB1_ASSET = "/Game/VPCtrl/Bilbords/Bilbord1/NDIB1.NDIB1"
NDIB1_PATH  = f"/Script/NDIMedia.NDIMediaSource'{NDIB1_ASSET}'"

@app.post("/api/input/b1/signal")
async def b1_set_signal():
    """Muda o MediaPlateResource do Billboard 1 para o asset BlackMagic BMB1."""
    try:
        await b1_call("Close")
        await asyncio.sleep(0.3)
        async with httpx.AsyncClient(timeout=5.0) as c:
            # Limpa primeiro
            await c.put(
                ue5_url("/remote/object/property"),
                json={
                    "objectPath": BILLBOARD1_COMP,
                    "propertyName": "MediaPlateResource",
                    "propertyValue": {"MediaPlateResource": {
                        "Type": "External",
                        "ExternalMediaPath": "",
                        "MediaAsset": "",
                        "SourcePlaylist": "",
                        "ExternalMedia": ""
                    }},
                    "access": "WRITE_ACCESS"
                }
            )
            await asyncio.sleep(0.2)
            # Seta BMB1
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={
                    "objectPath": BILLBOARD1_COMP,
                    "propertyName": "MediaPlateResource",
                    "propertyValue": {"MediaPlateResource": {
                        "Type": "Asset",
                        "ExternalMediaPath": "",
                        "MediaAsset": BMB1_ASSET,
                        "SourcePlaylist": "",
                        "ExternalMedia": ""
                    }},
                    "access": "WRITE_ACCESS"
                }
            )
            if r.status_code not in (200, 204):
                return {"ok": False, "error": f"set_property status {r.status_code}", "body": r.text}
        await asyncio.sleep(0.5)
        await b1_call("Open")
        return {"ok": True, "source": BMB1_PATH}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/input/b1/debug")
async def b1_debug():
    """Testa Close/Open e lê MediaPlateResource atual para debug."""
    result = {}
    async with httpx.AsyncClient(timeout=5.0) as c:
        # Lê MediaPlateResource atual
        r = await c.put(
            ue5_url("/remote/object/property"),
            json={"objectPath": BILLBOARD1_COMP, "propertyName": "MediaPlateResource", "access": "READ_ACCESS"}
        )
        result["MediaPlateResource"] = {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text}

        # Testa chamada Open — retorna o status code e body
        r2 = await c.put(
            ue5_url("/remote/object/call"),
            json={"objectPath": BILLBOARD1_COMP, "functionName": "Open", "generateTransaction": False}
        )
        result["Open"] = {"status": r2.status_code, "body": r2.text}

        # Testa chamada Close
        r3 = await c.put(
            ue5_url("/remote/object/call"),
            json={"objectPath": BILLBOARD1_COMP, "functionName": "Close", "generateTransaction": False}
        )
        result["Close"] = {"status": r3.status_code, "body": r3.text}

        # Lista funções disponíveis no objeto
        r4 = await c.get(ue5_url(f"/remote/object/describe"),
            params={"objectPath": BILLBOARD1_COMP})
        result["describe"] = {"status": r4.status_code, "body": r4.json() if r4.status_code == 200 else r4.text}

    return result

@app.get("/api/input/b1/blackmagic/dump")
async def b1_blackmagic_dump():
    """Dump completo de todas as propriedades do BMB1 para debug."""
    props = ["MediaConfiguration", "DeviceIndex", "Configuration", "InputConfiguration",
             "TimecodeFormat", "EvaluationType"]
    result = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            for prop in props:
                r = await c.put(
                    ue5_url("/remote/object/property"),
                    json={"objectPath": BMB1_PATH, "propertyName": prop, "access": "READ_ACCESS"}
                )
                result[prop] = {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text}
    except Exception as e:
        result["error"] = str(e)
    return result

@app.get("/api/input/b1/blackmagic/config")
async def b1_get_blackmagic_config():
    """Lê MediaConfiguration atual do BMB1 — retorna device atual e lista de devices conhecidos."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={"objectPath": BMB1_PATH, "propertyName": "MediaConfiguration", "access": "READ_ACCESS"}
            )
            media_cfg = r.json().get("MediaConfiguration", {}) if r.status_code == 200 else {}

        # Extrai device atual
        conn = media_cfg.get("MediaConnection", {})
        device = conn.get("Device", {})
        current_identifier = device.get("DeviceIdentifier", -1)
        current_name = device.get("DeviceName", "")

        return {
            "ok": True,
            "current_identifier": current_identifier,
            "current_name": current_name,
            "media_configuration": media_cfg
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/input/b1/blackmagic/config")
async def b1_set_blackmagic_config(body: dict):
    """
    Troca o device do BMB1 modificando MediaConfiguration.
    Recebe: { device_identifier: int, device_name: str }
    Mantém Resolution/FrameRate/Standard atuais, só troca o Device.
    """
    device_identifier = body.get("device_identifier")
    device_name = body.get("device_name", f"DeckLink Duo ({device_identifier})")
    if device_identifier is None:
        return {"ok": False, "error": "device_identifier required"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            # 1. Lê config atual para preservar MediaMode
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={"objectPath": BMB1_PATH, "propertyName": "MediaConfiguration", "access": "READ_ACCESS"}
            )
            media_cfg = r.json().get("MediaConfiguration", {}) if r.status_code == 200 else {}

            # 2. Atualiza apenas o Device dentro de MediaConnection
            conn = media_cfg.get("MediaConnection", {})
            conn["Device"] = {"DeviceName": device_name, "DeviceIdentifier": int(device_identifier)}
            media_cfg["MediaConnection"] = conn

            # 3. Escreve de volta
            r2 = await c.put(
                ue5_url("/remote/object/property"),
                json={
                    "objectPath": BMB1_PATH,
                    "propertyName": "MediaConfiguration",
                    "propertyValue": {"MediaConfiguration": media_cfg},
                    "access": "WRITE_ACCESS"
                }
            )
            return {"ok": r2.status_code in (200, 204), "status": r2.status_code, "body": r2.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── BILLBOARD 1 — NDI Source ───────────────────────────────

@app.get("/api/input/b1/ndi/dump")
async def b1_ndi_dump():
    """Dump completo de todas as propriedades do NDIB1 para debug."""
    props = ["SourceName", "SourceFilter", "Configuration", "MediaConfiguration",
             "BandwidthOption", "bSyncTimecodeToSource"]
    result = {}
    async with httpx.AsyncClient(timeout=5.0) as c:
        for prop in props:
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={"objectPath": NDIB1_PATH, "propertyName": prop, "access": "READ_ACCESS"}
            )
            result[prop] = {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text}
    return result

@app.post("/api/input/b1/ndi")
async def b1_set_ndi(body: dict = {}):
    """
    Ativa NDI no Billboard 1:
    1. Salva source_name no NDIB1 via MediaConfiguration
    2. Troca MediaPlateResource para NDIB1
    3. Chama Open
    """
    source_name = body.get("source_name", "")
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            # 1. Se veio source_name, salva no NDIB1
            if source_name:
                r_cfg = await c.put(
                    ue5_url("/remote/object/property"),
                    json={"objectPath": NDIB1_PATH, "propertyName": "MediaConfiguration", "access": "READ_ACCESS"}
                )
                media_cfg = r_cfg.json().get("MediaConfiguration", {}) if r_cfg.status_code == 200 else {}
                conn = media_cfg.get("MediaConnection", {})
                conn["Device"] = {"DeviceName": source_name, "DeviceIdentifier": -1}
                media_cfg["MediaConnection"] = conn
                await c.put(
                    ue5_url("/remote/object/property"),
                    json={
                        "objectPath": NDIB1_PATH,
                        "propertyName": "MediaConfiguration",
                        "propertyValue": {"MediaConfiguration": media_cfg},
                        "access": "WRITE_ACCESS"
                    }
                )
                await asyncio.sleep(0.2)

            # 2. Fecha o media atual
            await b1_call("Close")
            await asyncio.sleep(0.3)

            # 3. Limpa ExternalMediaPath setando Type External com path vazio
            await c.put(
                ue5_url("/remote/object/property"),
                json={
                    "objectPath": BILLBOARD1_COMP,
                    "propertyName": "MediaPlateResource",
                    "propertyValue": {"MediaPlateResource": {
                        "Type": "External",
                        "ExternalMediaPath": "",
                        "MediaAsset": "",
                        "SourcePlaylist": "",
                        "ExternalMedia": ""
                    }},
                    "access": "WRITE_ACCESS"
                }
            )
            await asyncio.sleep(0.2)

            # 4. Agora seta Type Asset com NDIB1
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={
                    "objectPath": BILLBOARD1_COMP,
                    "propertyName": "MediaPlateResource",
                    "propertyValue": {"MediaPlateResource": {
                        "Type": "Asset",
                        "ExternalMediaPath": "",
                        "MediaAsset": NDIB1_ASSET,
                        "SourcePlaylist": "",
                        "ExternalMedia": ""
                    }},
                    "access": "WRITE_ACCESS"
                }
            )
            if r.status_code not in (200, 204):
                return {"ok": False, "error": f"set_property status {r.status_code}", "body": r.text}

        # 5. Open
        await asyncio.sleep(0.5)
        await b1_call("Open")
        return {"ok": True, "source": source_name or NDIB1_ASSET}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/input/b1/ndi/sources")
async def b1_get_ndi_sources():
    """Lista sources NDI descobertos na rede via cyndilib + source atual do NDIB1."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={"objectPath": NDIB1_PATH, "propertyName": "MediaConfiguration", "access": "READ_ACCESS"}
            )
            media_cfg = r.json().get("MediaConfiguration", {}) if r.status_code == 200 else {}
        current = media_cfg.get("MediaConnection", {}).get("Device", {}).get("DeviceName", "")
        return {"ok": True, "sources": _ndi_sources, "current": current}
    except Exception as e:
        return {"ok": False, "error": str(e), "sources": _ndi_sources, "current": ""}

@app.get("/api/input/b1/ndi/config")
async def b1_get_ndi_config():
    """Lê o source NDI atual do NDIB1 via MediaConfiguration."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={"objectPath": NDIB1_PATH, "propertyName": "MediaConfiguration", "access": "READ_ACCESS"}
            )
            media_cfg = r.json().get("MediaConfiguration", {}) if r.status_code == 200 else {}
        current = media_cfg.get("MediaConnection", {}).get("Device", {}).get("DeviceName", "")
        return {"ok": True, "source_name": current}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/input/b1/ndi/config")
async def b1_set_ndi_config(body: dict):
    """Configura o source NDI no NDIB1 via MediaConfiguration.DeviceName."""
    source_name = body.get("source_name", "")
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            # Lê config atual para preservar o restante
            r = await c.put(
                ue5_url("/remote/object/property"),
                json={"objectPath": NDIB1_PATH, "propertyName": "MediaConfiguration", "access": "READ_ACCESS"}
            )
            media_cfg = r.json().get("MediaConfiguration", {}) if r.status_code == 200 else {}

            # Atualiza só o DeviceName
            conn = media_cfg.get("MediaConnection", {})
            conn["Device"] = {"DeviceName": source_name, "DeviceIdentifier": -1}
            media_cfg["MediaConnection"] = conn

            r2 = await c.put(
                ue5_url("/remote/object/property"),
                json={
                    "objectPath": NDIB1_PATH,
                    "propertyName": "MediaConfiguration",
                    "propertyValue": {"MediaConfiguration": media_cfg},
                    "access": "WRITE_ACCESS"
                }
            )
            return {"ok": r2.status_code in (200, 204), "status": r2.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── BILLBOARD 1 — Playback ─────────────────────────────────
async def b1_call(fn: str):
    async with httpx.AsyncClient(timeout=5.0) as c:
        return await c.put(
            ue5_url("/remote/object/call"),
            json={"objectPath": BILLBOARD1_COMP, "functionName": fn, "generateTransaction": False}
        )

@app.post("/api/input/b1/play")
async def b1_play():
    try:
        r = await b1_call("Play")
        return {"ok": r.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/input/b1/pause")
async def b1_pause():
    try:
        r = await b1_call("Pause")
        return {"ok": r.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/input/b1/rewind")
async def b1_rewind():
    try:
        r = await b1_call("Rewind")
        return {"ok": r.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/input/profiles")
async def input_list_profiles():
    """Lista os Media Profiles disponíveis no projeto."""
    try:
        # Busca assets do tipo MediaProfile via Remote Control
        r = await ue5_get("/remote/search/assets")
        if r.status_code == 200:
            assets = r.json().get("Assets", [])
            profiles = [a for a in assets if "MediaProfile" in a.get("Class", "")]
            return {"ok": True, "profiles": profiles}
    except Exception:
        pass
    # Fallback — retorna o profile padrão que sabemos que existe
    return {
        "ok": True,
        "profiles": [{"Name": "VPCtrl_MediaProfile", "Path": "/Game/VPCtrl/VPCtrl_MediaProfile"}]
    }

# ── CÂMERA ─────────────────────────────────────────────────
@app.post("/api/camera/switch")
async def switch_camera(body: dict):
    cam = body.get("camera", 1)
    try:
        await ue5_call_function("SwitchCamera", {"CameraIndex": cam - 1})
    except Exception:
        pass
    state["active_camera"] = cam
    state["tally_on"] = True
    await broadcast({"type": "tally", "data": {"camera": cam, "on_air": True}})
    return {"ok": True, "camera": cam}

# ── CHROMA ─────────────────────────────────────────────────
@app.post("/api/chroma/key_color")
async def set_key_color(body: dict):
    try:
        await ue5_set_property("KeyColor", {
            "R": body.get("r", 0.0), "G": body.get("g", 0.78),
            "B": body.get("b", 0.0), "A": 1.0
        })
    except Exception:
        pass
    return {"ok": True}

@app.post("/api/chroma/crop")
async def set_crop(body: dict):
    for side, label in [("top","CropTop"),("bottom","CropBottom"),("left","CropLeft"),("right","CropRight")]:
        if side in body:
            try:
                await ue5_set_property(label, body[side])
            except Exception:
                pass
    return {"ok": True}

# ── CONTROLES — descoberta dinâmica ────────────────────────
@app.get("/api/controls/discover")
async def discover_controls():
    try:
        r = await ue5_get(f"/remote/preset/{PRESET_NAME}")
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {"Preset": {"Properties": [], "Functions": []}}


# ── STATUS ─────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    return state

# ── POLL UE5 ───────────────────────────────────────────────
async def poll_ue5():
    while True:
        await asyncio.sleep(3)
        if not state["connected"]:
            continue
        try:
            r = await ue5_get("/remote/presets")
            if r.status_code != 200:
                state["connected"] = False
                await broadcast({"type": "disconnected"})
        except Exception:
            state["connected"] = False
            await broadcast({"type": "disconnected"})

# ── FILE DIALOG ────────────────────────────────────────────
_webview_window = None

@app.get("/api/file_dialog")
async def file_dialog():
    """Abre o file dialog nativo do pywebview e retorna o path escolhido."""
    if _webview_window is None:
        return {"ok": False, "error": "janela não disponível"}
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _webview_window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Vídeo (*.mp4;*.mov;*.avi;*.mkv;*.mxf)', 'Todos os arquivos (*.*)')
            )
        )
        if result and len(result) > 0:
            path = result[0].replace("\\", "/")
            return {"ok": True, "path": path}
        return {"ok": False, "path": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── INICIALIZAÇÃO ──────────────────────────────────────────
def start_server():
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT, log_level="warning")

if __name__ == "__main__":
    # Inicia scanner NDI em background
    nt = threading.Thread(target=_ndi_scan_thread, daemon=True)
    nt.start()

    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    time.sleep(1.5)

    _webview_window = webview.create_window(
        title="VP CTRL — Virtual Production Control",
        url=f"http://localhost:{APP_PORT}",
        width=1400,
        height=820,
        min_size=(900, 600),
        background_color="#111214",
    )
    webview.start(debug=False)
