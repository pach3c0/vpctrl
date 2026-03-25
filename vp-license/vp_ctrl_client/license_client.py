"""
license_client.py — VP CTRL license validation client.

Integration for versions/v3/core/license_client.py

Flow:
  1. App starts → load stored token from QSettings
  2. If valid token (offline RS256 check) and not expired → allow startup
  3. If no token or token expires in < 1 day → call /validate online
  4. If /validate fails (offline) → allow if token still valid (grace period)
  5. If no valid token at all → show activation dialog
  6. Background heartbeat every 60 minutes

Node-lock: fingerprint = SHA256(machine UUID + hostname + username)
Token stored in QSettings under "VPCtrl/license_token"
"""

import hashlib
import logging
import os
import platform
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import requests
from PyQt6.QtCore import QSettings, QThread, pyqtSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — update SERVER_URL and embed the real public key after keygen
# ---------------------------------------------------------------------------

SERVER_URL = "https://license.cliquezoom.com.br"

# Paste the contents of keys/public.pem here after generating RSA keys on VPS
# Replace the placeholder below with the actual PEM.
RSA_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
REPLACE_WITH_YOUR_PUBLIC_KEY_AFTER_KEYGEN
-----END PUBLIC KEY-----"""

SETTINGS_TOKEN_KEY = "VPCtrl/license_token"
SETTINGS_KEY_KEY   = "VPCtrl/license_key"
HEARTBEAT_INTERVAL = 3600  # seconds (1 hour)
OFFLINE_GRACE_DAYS = 3     # allow offline use for up to 3 days after token expiry

# ---------------------------------------------------------------------------
# Machine fingerprint
# ---------------------------------------------------------------------------

def get_machine_fingerprint() -> str:
    """
    Generate a stable machine fingerprint using platform-specific identifiers.
    Returns a 64-char hex SHA256 hash.
    """
    parts = []

    # Machine UUID (most stable identifier)
    try:
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.check_output(
                ["wmic", "csproduct", "get", "uuid"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip().split("\n")
            uuid = result[-1].strip()
            parts.append(uuid)
        elif platform.system() == "Linux":
            with open("/etc/machine-id") as f:
                parts.append(f.read().strip())
        elif platform.system() == "Darwin":
            import subprocess
            out = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode()
            for line in out.splitlines():
                if "Hardware UUID" in line:
                    parts.append(line.split(":")[-1].strip())
                    break
    except Exception:
        pass

    # Fallback components
    parts.append(socket.gethostname())
    parts.append(os.environ.get("USERNAME", os.environ.get("USER", "")))
    parts.append(platform.node())

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_machine_name() -> str:
    return platform.node() or socket.gethostname() or "Unknown"


def get_machine_hostname() -> str:
    try:
        return socket.getfqdn()
    except Exception:
        return socket.gethostname()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _decode_token_offline(token: str) -> Optional[dict]:
    """
    Validate and decode the license JWT using the embedded public key.
    Returns payload dict or None if invalid/expired.
    Allows expired tokens within OFFLINE_GRACE_DAYS for offline grace period.
    """
    try:
        payload = jwt.decode(
            token,
            RSA_PUBLIC_KEY_PEM,
            algorithms=["RS256"],
            options={"verify_exp": True},
        )
        return payload
    except jwt.ExpiredSignatureError:
        # Decode without expiry check for grace period logic
        try:
            payload = jwt.decode(
                token,
                RSA_PUBLIC_KEY_PEM,
                algorithms=["RS256"],
                options={"verify_exp": False},
            )
            exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
            grace_deadline = exp + timedelta(days=OFFLINE_GRACE_DAYS)
            if datetime.now(timezone.utc) <= grace_deadline:
                logger.warning("License token expired but within grace period (%d days)", OFFLINE_GRACE_DAYS)
                payload["_grace_period"] = True
                return payload
            return None
        except Exception:
            return None
    except jwt.InvalidTokenError as e:
        logger.warning("Token validation failed: %s", e)
        return None


def _token_needs_refresh(payload: dict) -> bool:
    """Returns True if token expires within 24 hours."""
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return datetime.now(timezone.utc) >= exp - timedelta(hours=24)


# ---------------------------------------------------------------------------
# License validation result
# ---------------------------------------------------------------------------

class LicenseStatus:
    VALID        = "valid"         # license active, token valid
    GRACE        = "grace"         # token expired but within grace period (offline)
    INVALID      = "invalid"       # no valid license
    SUSPENDED    = "suspended"     # license suspended by admin
    EXPIRED      = "expired"       # license past expiry date
    NOT_ACTIVATED = "not_activated"  # key exists but not activated on this machine


class LicenseResult:
    def __init__(self, status: str, message: str = "", customer_name: str = "", token: str = ""):
        self.status = status
        self.message = message
        self.customer_name = customer_name
        self.token = token

    @property
    def is_allowed(self) -> bool:
        return self.status in (LicenseStatus.VALID, LicenseStatus.GRACE)

    def __repr__(self):
        return f"LicenseResult(status={self.status}, customer={self.customer_name})"


# ---------------------------------------------------------------------------
# LicenseClient
# ---------------------------------------------------------------------------

class LicenseClient:
    """
    Main license client. Call check_license() on startup.
    Manages token storage, online validation, activation, and heartbeat.
    """

    def __init__(self):
        self._settings = QSettings()
        self._fingerprint = get_machine_fingerprint()
        self._heartbeat_thread: Optional[HeartbeatThread] = None
        logger.info("Machine fingerprint: %s…", self._fingerprint[:16])

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def check_license(self) -> LicenseResult:
        """
        Full license check. Call on app startup.
        Returns a LicenseResult indicating whether to allow the app to run.
        """
        stored_key = self._settings.value(SETTINGS_KEY_KEY, "")
        stored_token = self._settings.value(SETTINGS_TOKEN_KEY, "")

        # Step 1: Try offline validation of stored token
        if stored_token:
            payload = _decode_token_offline(stored_token)
            if payload:
                # Verify fingerprint matches this machine
                if payload.get("fingerprint") != self._fingerprint:
                    logger.warning("Token fingerprint mismatch — license was activated on different machine")
                    # Still try online validation
                else:
                    # Token is valid offline
                    grace = payload.get("_grace_period", False)
                    if not _token_needs_refresh(payload) and not grace:
                        # Fresh token, no need to go online
                        self._start_heartbeat(stored_key)
                        return LicenseResult(
                            status=LicenseStatus.VALID,
                            customer_name=payload.get("customer_name", ""),
                            token=stored_token,
                        )

        # Step 2: Try online validation/refresh
        if stored_key:
            result = self._validate_online(stored_key)
            if result.is_allowed:
                self._start_heartbeat(stored_key)
            return result

        # Step 3: If we have a grace-period token, allow offline
        if stored_token:
            payload = _decode_token_offline(stored_token)
            if payload and payload.get("_grace_period"):
                return LicenseResult(
                    status=LicenseStatus.GRACE,
                    message=f"Running offline (grace period). Connect to internet to refresh license.",
                    customer_name=payload.get("customer_name", ""),
                    token=stored_token,
                )

        return LicenseResult(
            status=LicenseStatus.INVALID,
            message="No valid license found. Please activate VP CTRL.",
        )

    def activate(self, license_key: str) -> LicenseResult:
        """
        Activate a license key on this machine.
        Stores the key and JWT token in QSettings on success.
        """
        license_key = license_key.strip().upper()
        try:
            resp = requests.post(
                f"{SERVER_URL}/api/v1/licenses/activate",
                json={
                    "license_key": license_key,
                    "machine_fingerprint": self._fingerprint,
                    "machine_name": get_machine_name(),
                    "machine_hostname": get_machine_hostname(),
                },
                timeout=15,
            )
            data = resp.json()
            if resp.ok:
                token = data["token"]
                self._save_token(license_key, token)
                self._start_heartbeat(license_key)
                return LicenseResult(
                    status=LicenseStatus.VALID,
                    customer_name=data.get("customer_name", ""),
                    token=token,
                )
            else:
                detail = data.get("detail", "Activation failed")
                status = self._map_http_error(resp.status_code, detail)
                return LicenseResult(status=status, message=detail)
        except requests.RequestException as e:
            return LicenseResult(
                status=LicenseStatus.INVALID,
                message=f"Cannot connect to license server: {e}",
            )

    def deactivate(self):
        """Call on clean app shutdown to soft-deactivate this machine."""
        key = self._settings.value(SETTINGS_KEY_KEY, "")
        if not key:
            return
        try:
            requests.post(
                f"{SERVER_URL}/api/v1/licenses/deactivate",
                json={"license_key": key, "machine_fingerprint": self._fingerprint},
                timeout=5,
            )
        except Exception:
            pass  # Best-effort on shutdown

    def stop_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.isRunning():
            self._heartbeat_thread.stop()

    def clear_stored_license(self):
        """Remove stored key and token (for re-activation)."""
        self._settings.remove(SETTINGS_KEY_KEY)
        self._settings.remove(SETTINGS_TOKEN_KEY)

    # ----------------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------------

    def _validate_online(self, license_key: str) -> LicenseResult:
        try:
            resp = requests.post(
                f"{SERVER_URL}/api/v1/licenses/validate",
                json={
                    "license_key": license_key,
                    "machine_fingerprint": self._fingerprint,
                },
                timeout=10,
            )
            data = resp.json()
            if resp.ok:
                token = data["token"]
                self._save_token(license_key, token)
                return LicenseResult(
                    status=LicenseStatus.VALID,
                    customer_name=data.get("customer_name", ""),
                    token=token,
                )
            else:
                detail = data.get("detail", "Validation failed")
                status = self._map_http_error(resp.status_code, detail)
                # If online says NOT_ACTIVATED, check grace period offline
                stored_token = self._settings.value(SETTINGS_TOKEN_KEY, "")
                if stored_token:
                    payload = _decode_token_offline(stored_token)
                    if payload and payload.get("_grace_period"):
                        return LicenseResult(
                            status=LicenseStatus.GRACE,
                            message="License server unreachable. Running on grace period.",
                            customer_name=payload.get("customer_name", ""),
                            token=stored_token,
                        )
                return LicenseResult(status=status, message=detail)
        except requests.RequestException:
            # Offline — check grace period
            stored_token = self._settings.value(SETTINGS_TOKEN_KEY, "")
            if stored_token:
                payload = _decode_token_offline(stored_token)
                if payload:
                    return LicenseResult(
                        status=LicenseStatus.GRACE if payload.get("_grace_period") else LicenseStatus.VALID,
                        message="License server unreachable — running offline." if payload.get("_grace_period") else "",
                        customer_name=payload.get("customer_name", ""),
                        token=stored_token,
                    )
            return LicenseResult(
                status=LicenseStatus.INVALID,
                message="Cannot reach license server and no valid offline token found.",
            )

    def _save_token(self, key: str, token: str):
        self._settings.setValue(SETTINGS_KEY_KEY, key)
        self._settings.setValue(SETTINGS_TOKEN_KEY, token)

    def _start_heartbeat(self, license_key: str):
        if self._heartbeat_thread and self._heartbeat_thread.isRunning():
            return
        self._heartbeat_thread = HeartbeatThread(
            server_url=SERVER_URL,
            license_key=license_key,
            fingerprint=self._fingerprint,
            interval=HEARTBEAT_INTERVAL,
        )
        self._heartbeat_thread.license_suspended.connect(self._on_license_suspended)
        self._heartbeat_thread.daemon = True
        self._heartbeat_thread.start()

    def _on_license_suspended(self, message: str):
        """Called from heartbeat thread when server returns 403 — license was suspended."""
        logger.warning("License suspended by server: %s", message)
        # Emit signal or show dialog — integrate with main_window.py as needed
        # Example: QMessageBox.warning(None, "License Suspended", message)

    @staticmethod
    def _map_http_error(status_code: int, detail: str) -> str:
        if status_code == 404:
            return LicenseStatus.INVALID
        if status_code == 403:
            if "expired" in detail.lower():
                return LicenseStatus.EXPIRED
            if "suspended" in detail.lower():
                return LicenseStatus.SUSPENDED
            return LicenseStatus.NOT_ACTIVATED
        if status_code == 409:
            return LicenseStatus.NOT_ACTIVATED
        return LicenseStatus.INVALID


# ---------------------------------------------------------------------------
# Heartbeat background thread
# ---------------------------------------------------------------------------

class HeartbeatThread(QThread):
    """
    Sends periodic heartbeat pings to the license server.
    Emits license_suspended signal if server returns 403 (license was revoked/suspended).
    """
    license_suspended = pyqtSignal(str)

    def __init__(self, server_url: str, license_key: str, fingerprint: str, interval: int):
        super().__init__()
        self._server_url = server_url
        self._license_key = license_key
        self._fingerprint = fingerprint
        self._interval = interval
        self._stop_event = threading.Event()

    def run(self):
        # Wait one full interval before first heartbeat (validate already sent one on startup)
        self._stop_event.wait(self._interval)
        while not self._stop_event.is_set():
            try:
                resp = requests.post(
                    f"{self._server_url}/api/v1/licenses/heartbeat",
                    json={
                        "license_key": self._license_key,
                        "machine_fingerprint": self._fingerprint,
                    },
                    timeout=10,
                )
                if resp.status_code == 204:
                    logger.debug("Heartbeat OK")
                elif resp.status_code == 403:
                    detail = resp.json().get("detail", "License suspended")
                    self.license_suspended.emit(detail)
                    break
                else:
                    logger.warning("Heartbeat returned %d", resp.status_code)
            except requests.RequestException:
                logger.debug("Heartbeat failed (offline)")

            self._stop_event.wait(self._interval)

    def stop(self):
        self._stop_event.set()
        self.wait(3000)


# ---------------------------------------------------------------------------
# Activation Dialog (PyQt6)
# ---------------------------------------------------------------------------

class ActivationDialog:
    """
    Simple activation dialog. Returns LicenseResult.
    Usage in main.py:
        dlg = ActivationDialog(parent)
        result = dlg.exec_dialog()
        if not result.is_allowed:
            sys.exit(1)
    """

    @staticmethod
    def exec_dialog(parent=None) -> LicenseResult:
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QLineEdit,
            QPushButton, QHBoxLayout, QMessageBox
        )
        from PyQt6.QtCore import Qt

        client = LicenseClient()
        dialog = QDialog(parent)
        dialog.setWindowTitle("VP CTRL — License Activation")
        dialog.setFixedSize(440, 240)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 28, 28, 28)

        title = QLabel("<b>Activate VP CTRL</b>")
        title.setStyleSheet("font-size: 16px;")
        layout.addWidget(title)

        subtitle = QLabel("Enter your license key to activate this installation.")
        subtitle.setStyleSheet("color: #7a8399; font-size: 13px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        key_input = QLineEdit()
        key_input.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        key_input.setMaxLength(19)
        key_input.setStyleSheet("font-family: Consolas; font-size: 15px; letter-spacing: 2px; padding: 8px;")
        layout.addWidget(key_input)

        status_label = QLabel("")
        status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        status_label.setWordWrap(True)
        layout.addWidget(status_label)

        btns = QHBoxLayout()
        cancel_btn = QPushButton("Exit")
        activate_btn = QPushButton("Activate")
        activate_btn.setDefault(True)
        btns.addWidget(cancel_btn)
        btns.addStretch()
        btns.addWidget(activate_btn)
        layout.addLayout(btns)

        result_holder = [LicenseResult(LicenseStatus.INVALID, "Cancelled")]

        def do_activate():
            key = key_input.text().strip().upper()
            if len(key) != 19:
                status_label.setText("Enter a valid key in XXXX-XXXX-XXXX-XXXX format.")
                return
            activate_btn.setEnabled(False)
            activate_btn.setText("Activating…")
            status_label.setText("")
            # Run in thread to avoid blocking UI
            import threading
            def _run():
                res = client.activate(key)
                result_holder[0] = res
                if res.is_allowed:
                    dialog.accept()
                else:
                    activate_btn.setEnabled(True)
                    activate_btn.setText("Activate")
                    status_label.setText(res.message or "Activation failed.")
            threading.Thread(target=_run, daemon=True).start()

        activate_btn.clicked.connect(do_activate)
        cancel_btn.clicked.connect(dialog.reject)

        dialog.exec()
        return result_holder[0]
