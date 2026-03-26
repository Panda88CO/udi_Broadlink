from __future__ import annotations

"""Wrapper around python-broadlink to provide a minimal, stable API for DeviceManager.

This module exposes `BroadlinkHubClient` with the methods used by the node server:
 - connect()
 - refresh()
 - learn_ir(timeout)
 - learn_rf(timeout)
 - send_code(packet_hex_or_bytes)
 - provision_ap(...)

The implementation attempts to discover a matching device by IP when `hub_ip` is provided
and falls back to the first discoverable device. It uses `dev.auth()` where available.
"""

import time
import binascii
from typing import Optional

import broadlink


class BroadlinkHubClient:
    def __init__(self, hub_ip: Optional[str] = None, user_id: Optional[str] = None, user_password: Optional[str] = None):
        self.hub_ip = hub_ip
        self.user_id = user_id
        self.user_password = user_password
        self.device = None
        self.connected = False

    def _discover_device(self, timeout: int = 5):
        devices = broadlink.discover(timeout=timeout)
        if not devices:
            return None
        if self.hub_ip:
            for dev in devices:
                try:
                    host = dev.host[0]
                except Exception:
                    continue
                if host == self.hub_ip:
                    return dev
        return devices[0]

    def connect(self):
        dev = self._discover_device()
        if dev is None:
            raise RuntimeError("No Broadlink devices discovered on network")
        try:
            dev.auth()
        except Exception:
            # Some devices/auth flows may fail but still be usable; continue
            pass
        self.device = dev
        self.connected = True

    def refresh(self) -> bool:
        if not self.device:
            return False
        try:
            # Some devices respond to auth as a lightweight check
            self.device.auth()
            return True
        except Exception:
            return False

    def learn_ir(self, timeout: int = 30) -> bytes:
        if not self.device:
            raise RuntimeError("Device not connected")
        # Enter learning mode and poll for data
        try:
            self.device.enter_learning()
        except Exception:
            # Some devices use different API; try fallback
            pass

        start = time.time()
        while time.time() - start < timeout:
            try:
                data = self.device.check_data()
                if data:
                    if isinstance(data, bytes):
                        return data
                    try:
                        return binascii.unhexlify(data)
                    except Exception:
                        return bytes(data)
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError("IR learn timed out")

    def learn_rf(self, timeout: int = 30) -> bytes:
        # Many Broadlink RM series use the same learning API for RF
        return self.learn_ir(timeout=timeout)

    def send_code(self, packet_hex_or_bytes):
        if not self.device:
            raise RuntimeError("Device not connected")
        if isinstance(packet_hex_or_bytes, str):
            try:
                packet = binascii.unhexlify(packet_hex_or_bytes)
            except Exception:
                # maybe it's a raw hex without separators
                packet = packet_hex_or_bytes.encode()
        else:
            packet = packet_hex_or_bytes

        # Use device.send_data where available
        if hasattr(self.device, "send_data"):
            try:
                self.device.send_data(packet)
                return True
            except Exception as err:
                raise RuntimeError(f"send_data failed: {err}")

        # Fallback to send_packet if available
        if hasattr(self.device, "send_packet"):
            try:
                self.device.send_packet(packet)
                return True
            except Exception as err:
                raise RuntimeError(f"send_packet failed: {err}")

        raise NotImplementedError("Device does not support sending data via known APIs")

    def provision_ap(self, ssid, password, security_mode=None, setup_ip=None):
        # python-broadlink doesn't provide a generic AP provisioning helper across all devices.
        # Leave as not implemented for safety; device-specific provisioning can be added later.
        raise NotImplementedError("AP provisioning is device and platform specific")
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

    def provision_ap(self, ssid: str, password: str, security_mode: int = 4, setup_ip: str = "255.255.255.255") -> bool:
        """Provision a Broadlink device in AP mode using broadlink.setup."""
        if not ssid:
            raise ValueError("WIFI_SSID is required for AP setup")
        if security_mode < 0 or security_mode > 4:
            raise ValueError("WIFI_SECURITY_MODE must be between 0 and 4")

        broadlink.setup(ssid=ssid, password=password, security_mode=security_mode, ip_address=setup_ip)
        return True


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
