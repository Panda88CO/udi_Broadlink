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
    def __init__(self, hub_ips: Optional[list[str]] = None, user_id: Optional[str] = None, user_password: Optional[str] = None):
        self.hub_ips = hub_ips or []
        self.user_id = user_id
        self.user_password = user_password
        self.device = None
        self.connected = False

    def _discover_device(self, timeout: int = 5):
        devices = broadlink.discover(timeout=timeout)
        if not devices:
            return None
        if self.hub_ips:
            for dev in devices:
                try:
                    host = dev.host[0]
                except Exception:
                    continue
                if host in self.hub_ips:
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
