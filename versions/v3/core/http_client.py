"""
VP CTRL v2 — HTTP REST client para UE5 Remote Control API (porta 30010).
BP path e preset são fixos — invisíveis ao usuário.
"""
import logging
import threading
import requests

from config.settings import DEFAULT_HOST, HTTP_PORT, BP_ACTOR_PATH, PRESET_NAME, CAMERA_ACTORS, MEDIA_OUTPUT_ASSET, SUPPORTED_UE_VERSION

logger = logging.getLogger(__name__)


def _base_url(host: str) -> str:
    return f"http://{host}:{HTTP_PORT}"


# ------------------------------------------------------------------
# Verificação de versão do UE5
# ------------------------------------------------------------------

def check_ue5_version(host: str, uproject_path: str = "") -> tuple[bool, str]:
    """
    Verifica a versão do UE5. Estratégia em cascata:
    1. Lê o EngineAssociation do arquivo .uproject (mais confiável)
    2. Tenta GET /remote/info (endpoint legado — nem sempre retorna versão)
    Retorna (ok: bool, version_string: str).
    """
    # 1. Tenta via .uproject — mais confiável
    if uproject_path:
        version_str = _version_from_uproject(uproject_path)
        if version_str:
            ok = _is_version_supported(version_str)
            logger.info("UE5 version (uproject): %s → %s", version_str, "OK" if ok else "INCOMPATÍVEL")
            return ok, version_str

    # 2. Fallback: GET /remote/info
    url = f"{_base_url(host)}/remote/info"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            logger.warning("check_ue5_version: /remote/info retornou %d", r.status_code)
            return False, ""
        data = r.json()
        logger.debug("check_ue5_version /remote/info response: %s", data)
        # Tenta campos conhecidos
        raw = (
            data.get("engineVersion")
            or data.get("EngineVersion")
            or data.get("version")
            or data.get("Version")
            or ""
        )
        # Se a resposta for lista (HttpRoutes), não tem versão aqui
        if isinstance(data, list) or not raw:
            logger.warning("check_ue5_version: /remote/info não retornou versão (resposta: %s)", str(data)[:120])
            return False, ""
        version_str = _parse_ue_version(raw)
        ok = _is_version_supported(version_str)
        logger.info("UE5 version (/remote/info): %s → %s", raw, "OK" if ok else "INCOMPATÍVEL")
        return ok, version_str
    except Exception as e:
        logger.warning("check_ue5_version falhou: %s", e)
        return False, ""


def _version_from_uproject(uproject_path: str) -> str:
    """
    Lê a versão do engine a partir do arquivo .uproject.
    O campo EngineAssociation pode ser '5.7', '5.7.4' ou um GUID (custom build).
    Retorna string no formato 'M.m' ou 'M.m.p', ou '' se não encontrar.
    """
    import json as _json
    from pathlib import Path as _Path
    try:
        p = _Path(uproject_path)
        logger.debug("_version_from_uproject: path=%s is_file=%s is_dir=%s", p, p.is_file(), p.is_dir())
        if not p.is_file():
            # Recebeu pasta — procura o .uproject dentro
            files = list(p.glob("*.uproject"))
            logger.debug("_version_from_uproject: uproject files encontrados: %s", files)
            if not files:
                return ""
            p = files[0]
        data = _json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("EngineAssociation", "")
        logger.debug("_version_from_uproject: EngineAssociation=%r", raw)
        # Se for GUID (custom build), não conseguimos extrair versão semântica
        if raw and "{" not in raw:
            # Extrai só os dígitos M.m ou M.m.p
            import re as _re
            m = _re.match(r"(\d+\.\d+(?:\.\d+)?)", raw)
            if m:
                return m.group(1)
    except Exception as e:
        logger.warning("_version_from_uproject falhou: %s", e)
    return ""


def _parse_ue_version(raw: str) -> str:
    """
    Extrai 'M.m.p' de strings como '5.7.4-37670630+++UE5+Release-5.7'
    Retorna string vazia se não conseguir parsear.
    """
    import re
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return ""


def _is_version_supported(version_str: str) -> bool:
    """
    Retorna True se version_str corresponde a SUPPORTED_UE_VERSION.
    Aceita match parcial M.m quando o .uproject não inclui o patch:
      ex: "5.7" é aceito se SUPPORTED_UE_VERSION é (5, 7, x).
    """
    if not version_str:
        return False
    try:
        parts = tuple(int(x) for x in version_str.split("."))
        supported = SUPPORTED_UE_VERSION
        # Match exato (M.m.p)
        if len(parts) == 3:
            return parts == supported
        # Match parcial M.m — aceita se major e minor batem
        if len(parts) == 2:
            return parts == supported[:2]
        return False
    except Exception:
        return False


PYTHON_OBJECT = "/Script/PythonScriptPlugin.Default__PythonScriptLibrary"

# ------------------------------------------------------------------
# Verificação de plugins
# ------------------------------------------------------------------

# Plugins que o VP CTRL exige, com nome amigável para exibição
REQUIRED_PLUGINS = [
    "OSC",
    "EnhancedInput",
    "PythonScriptPlugin",
    "RemoteControl",
]

_PLUGIN_CHECK_SCRIPT = (
    "import unreal, json, os; "
    "enabled = set(unreal.PluginBlueprintLibrary.get_enabled_plugin_names()); "
    "result = dict(OSC='OSC' in enabled, EnhancedInput='EnhancedInput' in enabled, PythonScriptPlugin='PythonScriptPlugin' in enabled, RemoteControl='RemoteControl' in enabled); "
    "path = os.path.join(os.environ.get('TEMP', 'C:/Temp'), 'vpctrl_plugins.json'); "
    "open(path, 'w').write(json.dumps(result))"
)


def check_plugins(host: str) -> dict[str, bool]:
    """
    Executa Python no UE5 para verificar quais plugins estão ativos.
    Escreve resultado em %TEMP%/vpctrl_plugins.json e lê de volta.
    Retorna dict {plugin_name: bool}. Em caso de falha retorna dict vazio.
    """
    import os, json as _json, time as _time
    temp_file = os.path.join(os.environ.get("TEMP", "C:/Temp"), "vpctrl_plugins.json")

    # Remove arquivo anterior para evitar leitura de resultado stale
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    except Exception:
        pass

    # Dispara o script Python no UE5
    url = f"{_base_url(host)}/remote/object/call"
    body = {
        "objectPath": PYTHON_OBJECT,
        "functionName": "ExecutePythonScript",
        "parameters": {"PythonScript": _PLUGIN_CHECK_SCRIPT},
        "generateTransaction": False,
    }
    try:
        r = requests.put(url, json=body, timeout=8)
        if not r.json().get("ReturnValue", False):
            logger.warning("check_plugins: ExecutePythonScript retornou false")
            return {}
    except requests.exceptions.ConnectionError as e:
        logger.warning("check_plugins: host inacessível (%s): %s", host, e)
        return {"_host_unreachable": True}
    except requests.exceptions.Timeout:
        logger.warning("check_plugins: timeout conectando a %s", host)
        return {"_host_unreachable": True}
    except Exception as e:
        logger.warning("check_plugins: falhou ao executar script: %s", e)
        return {}

    # Aguarda o arquivo aparecer (UE5 executa Python de forma assíncrona)
    for i in range(50):
        if os.path.exists(temp_file):
            break
        _time.sleep(0.2)
    else:
        logger.warning("check_plugins: timeout aguardando arquivo %s", temp_file)
        return {}

    try:
        result = _json.loads(open(temp_file, encoding="utf-8").read())
        logger.info("check_plugins resultado: %s", result)
        return result
    except Exception as e:
        logger.warning("check_plugins: erro ao ler resultado: %s", e)
        return {}


# ------------------------------------------------------------------
# Leitura de propriedades
# ------------------------------------------------------------------

def get_property_http(host: str, property_name: str, object_path: str = None) -> dict | None:
    """Lê uma propriedade via HTTP REST. Retorna o dict de resposta ou None."""
    url = f"{_base_url(host)}/remote/object/property"
    body = {
        "objectPath": object_path or BP_ACTOR_PATH,
        "propertyName": property_name,
        "access": "READ_ACCESS",
    }
    try:
        r = requests.put(url, json=body, timeout=5)
        if r.status_code == 200:
            return r.json()
        logger.warning("HTTP GET %s → %d", property_name, r.status_code)
    except Exception as e:
        logger.warning("HTTP GET falhou: %s", e)
    return None


# ------------------------------------------------------------------
# Escrita de propriedades
# ------------------------------------------------------------------

def set_property_http(host: str, property_name: str, value, object_path: str = None) -> bool:
    """Escreve uma propriedade via HTTP REST."""
    url = f"{_base_url(host)}/remote/object/property"
    body = {
        "objectPath": object_path or BP_ACTOR_PATH,
        "propertyName": property_name,
        "propertyValue": {property_name: value},
        "access": "WRITE_ACCESS",
    }
    try:
        r = requests.put(url, json=body, timeout=3)
        logger.debug("HTTP SET %s=%s → %d", property_name, value, r.status_code)
        return r.status_code == 200
    except Exception as e:
        logger.warning("HTTP SET falhou: %s", e)
        return False


def set_property_http_async(host: str, property_name: str, value, object_path: str = None):
    """Dispara set_property_http em background thread."""
    t = threading.Thread(
        target=set_property_http,
        args=(host, property_name, value, object_path),
        daemon=True,
    )
    t.start()


# ------------------------------------------------------------------
# Chamada de funções Blueprint
# ------------------------------------------------------------------

def call_function_http(host: str, function_name: str, parameters: dict = None, object_path: str = None) -> bool:
    """Chama uma função Blueprint via HTTP REST."""
    url = f"{_base_url(host)}/remote/object/call"
    body = {
        "objectPath": object_path or BP_ACTOR_PATH,
        "functionName": function_name,
        "parameters": parameters or {},
        "generateTransaction": False,
    }
    try:
        r = requests.put(url, json=body, timeout=3)
        logger.debug("HTTP CALL %s → %d", function_name, r.status_code)
        return r.status_code == 200
    except Exception as e:
        logger.warning("HTTP CALL falhou: %s", e)
        return False


def call_function_http_async(host: str, function_name: str, parameters: dict = None, object_path: str = None):
    """Dispara call_function_http em background thread."""
    t = threading.Thread(
        target=call_function_http,
        args=(host, function_name, parameters, object_path),
        daemon=True,
    )
    t.start()


# ------------------------------------------------------------------
# Python executor (PIE control)
# ------------------------------------------------------------------

def _execute_python(host: str, script: str):
    call_function_http(host, "ExecutePythonScript", {"PythonScript": script}, PYTHON_OBJECT)


def ue5_begin_play(host: str):
    script = "import unreal; unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()"
    threading.Thread(target=_execute_python, args=(host, script), daemon=True).start()


def ue5_end_play(host: str):
    script = "import unreal; unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()"
    threading.Thread(target=_execute_python, args=(host, script), daemon=True).start()


def ue5_pilot_actor(host: str):
    """Lock the editor viewport to BP_VPB1."""
    script = (
        "import unreal; "
        "actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors(); "
        f"actor = next((a for a in actors if '{BP_ACTOR_PATH.split('.')[-1]}' in a.get_path_name()), None); "
        "unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).pilot_level_actor(actor) if actor else None"
    )
    threading.Thread(target=_execute_python, args=(host, script), daemon=True).start()


def ue5_eject_pilot(host: str):
    """Release the editor viewport pilot."""
    script = "import unreal; unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).eject_pilot_level_actor()"
    threading.Thread(target=_execute_python, args=(host, script), daemon=True).start()


def ue5_switch_camera(host: str, camera: int):
    """Troca câmera ativa no Media Capture BlackMagic (1, 2 ou 3)."""
    actor_name = CAMERA_ACTORS.get(camera)
    if not actor_name:
        logger.warning("ue5_switch_camera: câmera %d inválida", camera)
        return
    script = (
        "import unreal; "
        "panel = unreal.MediaFrameworkCapturePanelLibrary.get_media_capture_panel(); "
        f"output = unreal.load_asset('{MEDIA_OUTPUT_ASSET}'); "
        "actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors(); "
        f"cam = next((x for x in actors if '{actor_name}' in str(x.get_path_name())), None); "
        "panel.stop_capture(); "
        "panel.empty_viewport_capture(); "
        "panel.add_viewport_capture(output, cam, unreal.MediaCaptureOptions()); "
        "panel.start_capture()"
    )
    threading.Thread(target=_execute_python, args=(host, script), daemon=True).start()
    logger.info("Camera switch → %d (%s)", camera, actor_name)


# ------------------------------------------------------------------
# Sync — lê array Paths do UE5
# ------------------------------------------------------------------

def fetch_paths(host: str) -> list[dict] | None:
    """Lê o array Paths do Blueprint. Retorna lista de dicts ou None."""
    result = get_property_http(host, "Paths")
    if result:
        return result.get("Paths")
    return None


# Cache local do array Paths — evita leitura a cada escrita
_paths_cache: list[dict] | None = None
_paths_keys: dict = {}  # chaves UUID descobertas uma vez


def _discover_keys(paths: list[dict]):
    global _paths_keys
    if not paths:
        return
    _paths_keys = {}
    for k in paths[0]:
        kl = k.lower()
        if "duration" in kl:
            _paths_keys["duration"] = k
        elif "focallengtha" in kl:
            _paths_keys["focal_a"] = k
        elif "focallengthb" in kl:
            _paths_keys["focal_b"] = k
        elif "focusdistancea" in kl or "focaldistancea" in kl:
            _paths_keys["focus_a"] = k
        elif "focusdistanceb" in kl or "focaldistanceb" in kl:
            _paths_keys["focus_b"] = k
        elif "pointa" in kl:
            _paths_keys["point_a"] = k
        elif "pointb" in kl:
            _paths_keys["point_b"] = k


def set_path_transform(host: str, path_index: int, point: str,
                       loc: dict = None, rot_quat: dict = None):
    """
    Escreve Translation e/ou Rotation de um ponto (point='a' ou 'b') no cache.
    loc = {"X": float, "Y": float, "Z": float}
    rot_quat = {"X": float, "Y": float, "Z": float, "W": float}
    """
    global _paths_cache
    if _paths_cache is None or path_index >= len(_paths_cache):
        return
    key = _paths_keys.get(f"point_{point}")
    if not key:
        logger.warning("set_path_transform: chave point_%s não encontrada", point)
        return
    entry = _paths_cache[path_index][key]
    if loc:
        entry["Translation"] = loc
    if rot_quat:
        entry["Rotation"] = rot_quat
    _write_paths_async(host)


def set_path_transform_async(host: str, path_index: int, point: str,
                              loc: dict = None, rot_quat: dict = None):
    threading.Thread(
        target=set_path_transform,
        args=(host, path_index, point, loc, rot_quat),
        daemon=True,
    ).start()


def warm_cache(host: str):
    """Carrega o array Paths do UE5 para cache local. Chamar após conectar."""
    global _paths_cache
    paths = fetch_paths(host)
    if paths:
        _paths_cache = paths
        _discover_keys(paths)
        logger.debug("Cache Paths aquecido: %d paths, keys=%s", len(paths), list(_paths_keys.keys()))


def _write_paths_async(host: str):
    """Escreve o cache atual de volta para o UE5 em background."""
    if _paths_cache is None:
        return
    snapshot = list(_paths_cache)  # cópia para thread safety básica
    threading.Thread(
        target=set_property_http, args=(host, "Paths", snapshot), daemon=True
    ).start()


def set_path_field(host: str, path_index: int, field: str, value: float):
    """
    Atualiza um campo do array Paths no cache local e envia para o UE5.
    field: 'duration', 'focal_a', 'focal_b', 'focus_a', 'focus_b'
    """
    global _paths_cache
    if _paths_cache is None or path_index >= len(_paths_cache):
        logger.warning("set_path_field: cache vazio, ignorando %s=%s", field, value)
        return
    key = _paths_keys.get(field)
    if not key:
        logger.warning("set_path_field: chave '%s' não encontrada", field)
        return
    _paths_cache[path_index][key] = value
    _write_paths_async(host)


def set_path_field_async(host: str, path_index: int, field: str, value: float):
    threading.Thread(
        target=set_path_field, args=(host, path_index, field, value), daemon=True
    ).start()


