"""
VP CTRL v2 — Performance panel.
CPU%, RAM e GPU% do processo UE5 + FPS via UE5 HTTP.
"""
import logging
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel

logger = logging.getLogger(__name__)

try:
    import psutil
    _HAS_PSUTIL = True
    _CPU_COUNT = psutil.cpu_count(logical=True) or 1
except ImportError:
    _HAS_PSUTIL = False
    _CPU_COUNT = 1
    logger.warning("psutil not installed — run: pip install psutil")

try:
    import pynvml
    pynvml.nvmlInit()
    _HAS_NVML = True
except Exception:
    _HAS_NVML = False

UE5_NAMES = {"UnrealEditor", "UE5Editor", "UE4Editor", "UnrealEditor-Win64-Shipping"}


def _get_ue5_proc():
    if not _HAS_PSUTIL:
        return None
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if any(n in proc.info["name"] for n in UE5_NAMES):
                return proc
        except Exception:
            pass
    return None


def _get_gpu_pct(pid: int) -> float:
    """GPU% do processo UE5 via pynvml (NVIDIA)."""
    if not _HAS_NVML:
        return -1
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            procs = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
            procs += pynvml.nvmlDeviceGetGraphicsRunningProcesses(handle)
            for p in procs:
                if p.pid == pid:
                    # utilization geral da GPU (não por processo — limitação NVML)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    return float(util.gpu)
    except Exception:
        pass
    return -1


class _PerfWorker(QObject):
    stats_ready = pyqtSignal(float, float, float, float)  # cpu%, ram_mb, gpu%, fps

    def __init__(self, host: str):
        super().__init__()
        self._host = host
        self._running = False
        self._proc = None
        self._last_time = 0.0

    def _get_ue5_fps(self) -> float:
        """Estima FPS do processo UE5 via CPU time delta — sem HTTP."""
        if not _HAS_PSUTIL or self._proc is None:
            return -1
        try:
            now = time.monotonic()
            dt = now - self._last_time
            if dt < 0.1:
                return -1
            self._last_time = now
            # Lê frames via número de threads ativas como proxy, ou retorna -1
            # UE5 não expõe FPS via psutil diretamente
            return -1
        except Exception:
            return -1

    def run(self):
        self._running = True
        self._last_time = time.monotonic()
        while self._running:
            cpu = ram = gpu = -1
            try:
                if self._proc is None or not self._proc.is_running():
                    self._proc = _get_ue5_proc()
                if self._proc:
                    cpu = self._proc.cpu_percent(interval=1.5) / _CPU_COUNT
                    ram = self._proc.memory_info().rss / (1024 * 1024)
                    gpu = _get_gpu_pct(self._proc.pid)
            except Exception:
                self._proc = None

            self.stats_ready.emit(cpu, ram, -1, -1)

    def stop(self):
        self._running = False


class PerfPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._thread = None
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 2, 8, 2)
        root.setSpacing(16)

        self._lbl_cpu = self._metric("CPU: —")
        self._lbl_ram = self._metric("RAM: —")
        self._lbl_gpu = self._metric("GPU: —")

        root.addWidget(self._lbl_cpu)
        root.addWidget(self._sep())
        root.addWidget(self._lbl_ram)
        root.addWidget(self._sep())
        root.addWidget(self._lbl_gpu)
        root.addStretch()

    def _metric(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("class", "perf-metric")
        return lbl

    def _sep(self) -> QLabel:
        lbl = QLabel("|")
        lbl.setStyleSheet("color: #30363d;")
        return lbl

    def start(self, host: str = "127.0.0.1"):
        self.stop()
        if not _HAS_PSUTIL:
            return
        self._worker = _PerfWorker(host)
        self._worker.stats_ready.connect(self._update)
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._worker:
            self._worker.stop()
            self._worker = None
        for lbl, txt in [
            (self._lbl_cpu, "CPU: —"),
            (self._lbl_ram, "RAM: —"),
            (self._lbl_gpu, "GPU: —"),
        ]:
            lbl.setText(txt)

    def _update(self, cpu: float, ram_mb: float, gpu: float, _fps: float):
        self._lbl_cpu.setText(f"CPU: {cpu:.0f}%" if cpu >= 0 else "CPU: —")
        self._lbl_ram.setText(f"RAM: {ram_mb / 1024:.1f} GB" if ram_mb >= 0 else "RAM: —")
        self._lbl_gpu.setText(f"GPU: {gpu:.0f}%" if gpu >= 0 else "GPU: —")
