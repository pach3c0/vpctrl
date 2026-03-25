"""
Persistent WebSocket client for UE5 Remote Control API.
Runs in a QThread with its own asyncio event loop.
Host/port are passed at connect time — not hardcoded.
"""
import asyncio
import json
import logging
from typing import Optional

import websockets
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from config.settings import RECONNECT_INTERVAL

logger = logging.getLogger(__name__)


class WebSocketWorker(QObject):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    message_received = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._running = False
        self._send_queue: asyncio.Queue = None
        self._url: str = ""

    def enqueue(self, message: dict):
        if self._loop is None or not self._loop.is_running():
            logger.warning("Loop not running — message dropped: %s", message.get("MessageName"))
            return
        asyncio.run_coroutine_threadsafe(
            self._send_queue.put(message), self._loop
        )

    def stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def run(self, url: str):
        self._url = url
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_queue = asyncio.Queue()
        self._running = True
        try:
            self._loop.run_until_complete(self._connection_loop())
        finally:
            self._loop.close()

    async def _connection_loop(self):
        delay = RECONNECT_INTERVAL
        max_delay = RECONNECT_INTERVAL * 4

        while self._running:
            try:
                logger.info("Conectando a %s …", self._url)
                async with websockets.connect(
                    self._url,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=5,
                ) as ws:
                    self._ws = ws
                    delay = RECONNECT_INTERVAL
                    self.connected.emit()
                    logger.info("Conectado ao UE5 WebSocket")
                    await self._session(ws)
            except (OSError, websockets.exceptions.WebSocketException) as exc:
                logger.warning("WebSocket erro: %s — reconectando em %ds", exc, delay)
            except Exception as exc:
                logger.error("Erro inesperado: %s", exc)
            finally:
                self._ws = None
                self.disconnected.emit()

            if not self._running:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)

    async def _session(self, ws):
        await asyncio.gather(
            self._receiver(ws),
            self._sender(ws),
            return_exceptions=True,
        )

    async def _receiver(self, ws):
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("JSON inválido: %s", raw[:200])
                continue
            self.message_received.emit(data)

    async def _sender(self, ws):
        while True:
            message = await self._send_queue.get()
            try:
                await ws.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                await self._send_queue.put(message)
                break


class WebSocketThread(QThread):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    message_received = pyqtSignal(dict)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._worker = WebSocketWorker()
        self._worker.connected.connect(self.connected)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.message_received.connect(self.message_received)

    def run(self):
        self._worker.run(self._url)

    def send(self, message: dict):
        self._worker.enqueue(message)

    def stop(self):
        self._worker.stop()
        self.quit()
        self.wait(3000)
