"""
VP CTRL v3 — OSC client.
Toda comunicação de controle de câmera vai por OSC.
Porta fixa: 8001 (configurada no BP_VPB1).
"""
import logging
import threading
from pythonosc.udp_client import SimpleUDPClient

from config.settings import OSC_PORT

logger = logging.getLogger(__name__)


def _send(host: str, address: str, args: list = None):
    try:
        client = SimpleUDPClient(host, OSC_PORT)
        client.send_message(address, args or [])
        logger.debug("OSC → %s:%d %s", host, OSC_PORT, address)
    except Exception as e:
        logger.warning("OSC falhou: %s", e)


def osc_send_async(host: str, address: str, args: list = None):
    threading.Thread(target=_send, args=(host, address, args), daemon=True).start()


def osc_trigger_path(host: str, index: int):
    """Dispara animação do path via OSC. index é 0-based."""
    osc_send_async(host, f"/path{index + 1}")


def osc_set_active_path(host: str, index: int):
    """Define o path ativo no BP. index é 0-based."""
    osc_send_async(host, "/active_path", [index])


def osc_goto_a(host: str):
    """Move câmera para o ponto A do path ativo."""
    osc_send_async(host, "/goto/a")


def osc_goto_b(host: str):
    """Move câmera para o ponto B do path ativo."""
    osc_send_async(host, "/goto/b")


def osc_record_a(host: str):
    """Grava posição atual da câmera como ponto A do path ativo."""
    osc_send_async(host, "/record/a")


def osc_record_b(host: str):
    """Grava posição atual da câmera como ponto B do path ativo."""
    osc_send_async(host, "/record/b")


def osc_focal_a(host: str, value: float):
    osc_send_async(host, "/focal/a", [value])

def osc_focal_b(host: str, value: float):
    osc_send_async(host, "/focal/b", [value])

def osc_focus_a(host: str, value: float):
    osc_send_async(host, "/focus/a", [value])

def osc_focus_b(host: str, value: float):
    osc_send_async(host, "/focus/b", [value])

def osc_duration(host: str, value: float):
    osc_send_async(host, "/duration", [value])
