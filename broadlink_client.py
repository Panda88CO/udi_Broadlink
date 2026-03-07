"""Broadlink hub wrapper used by PG3 nodes.

This wrapper keeps Broadlink specifics in one place so new Broadlink device
classes can be added later without changing node classes.
"""

from __future__ import annotations

import base64
from threading import Lock
import time

import broadlink


class BroadlinkHubClient:
    """Thin wrapper around python-broadlink remote functionality."""

    def __init__(self, hub_ip: str, user_id: str = "", user_password: str = "") -> None:
        self.hub_ip = hub_ip
        self.user_id = user_id
        self.user_password = user_password
        self._device = None
        self._lock = Lock()

    @property
    def connected(self) -> bool:
        return self._device is not None

    def connect(self) -> bool:
        """Discover and authenticate the Broadlink device at the configured IP."""
        with self._lock:
            if not self.hub_ip:
                raise ValueError("HUB_IP is required")

            # hello() fetches devtype/mac, then auth() prepares encrypted session.
            device = broadlink.hello(self.hub_ip)
            if device is None:
                raise RuntimeError(f"No Broadlink device found at {self.hub_ip}")
            device.auth()
            self._device = device
            return True

    def refresh(self) -> bool:
        """Best-effort connectivity refresh."""
        with self._lock:
            if self._device is None:
                return False
            try:
                self._device.ping()
                return True
            except Exception:
                try:
                    self._device.auth()
                    return True
                except Exception:
                    self._device = None
                    return False

    def send_code(self, encoded_code: str) -> bool:
        """Transmit an IR or RF packet to the Broadlink hub."""
        packet = decode_code_string(encoded_code)

        with self._lock:
            if self._device is None:
                self.connect()
            self._device.send_data(packet)
            return True

    def learn_ir(self, timeout_sec: int = 30, poll_interval: float = 1.0) -> bytes:
        """Learn a single IR packet and return raw Broadlink bytes."""
        with self._lock:
            if self._device is None:
                self.connect()

            self._device.enter_learning()
            return self._wait_for_learned_packet(timeout_sec=timeout_sec, poll_interval=poll_interval)

    def learn_rf(self, timeout_sec: int = 45, poll_interval: float = 1.0) -> bytes:
        """Learn a single RF packet and return raw Broadlink bytes.

        For devices that support RF sweep APIs we use sweep->check_frequency->find_rf_packet.
        If not supported, we fall back to the generic learning method.
        """
        with self._lock:
            if self._device is None:
                self.connect()

            if hasattr(self._device, "sweep_frequency") and hasattr(self._device, "check_frequency"):
                self._device.sweep_frequency()
                start = time.time()
                found = False
                frequency = None

                while (time.time() - start) < timeout_sec:
                    time.sleep(poll_interval)
                    try:
                        found, frequency = self._device.check_frequency()
                    except Exception:
                        continue
                    if found:
                        break

                if not found:
                    try:
                        self._device.cancel_sweep_frequency()
                    except Exception:
                        pass
                    raise TimeoutError("RF frequency sweep timed out")

                self._device.find_rf_packet(frequency)
                return self._wait_for_learned_packet(timeout_sec=timeout_sec, poll_interval=poll_interval)

            # Some remote models learn RF through the same generic IR flow.
            self._device.enter_learning()
            return self._wait_for_learned_packet(timeout_sec=timeout_sec, poll_interval=poll_interval)

    def _wait_for_learned_packet(self, timeout_sec: int = 30, poll_interval: float = 1.0) -> bytes:
        """Poll the hub until a learned packet is available."""
        start = time.time()
        while (time.time() - start) < timeout_sec:
            time.sleep(poll_interval)
            try:
                packet = self._device.check_data()
            except Exception:
                continue
            if packet:
                return packet

        raise TimeoutError("No learned packet received before timeout")


def decode_code_string(raw: str) -> bytes:
    """Decode user code strings into Broadlink packet bytes.

    Supported input:
    - Hex string (with or without spaces)
    - base64 with `b64:` prefix
    """
    text = str(raw).strip()
    if not text:
        raise ValueError("Code string is empty")

    if text.lower().startswith("b64:"):
        return base64.b64decode(text[4:].strip())

    hex_text = "".join(text.split())
    return bytes.fromhex(hex_text)
