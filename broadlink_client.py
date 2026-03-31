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
import logging

import broadlink





class BroadlinkHubClient:
    def __init__(self, hub_ips: Optional[list[str]] = None, user_id: Optional[str] = None, user_password: Optional[str] = None):
        self.hub_ips = hub_ips or []
        self.user_id = user_id
        self.user_password = user_password
        self.devices = []  # List of all discovered/connected devices
        self.connected = False
        self.logger = logging.getLogger("BroadlinkHubClient")
        if not self.logger.hasHandlers():
            logging.basicConfig(level=logging.DEBUG)

    def _discover_devices(self, timeout: int = 5):
        found_devices = []
        found_ips = set()
        # First, try to connect directly to each specified IP
        logging.debug(f"Starting device discovery with specified hub IPs: {self.hub_ips}")
        if self.hub_ips:
            for ip in self.hub_ips:
                self.logger.debug(f"Attempting direct connection to Broadlink device at {ip}")
                try:
                    devs = broadlink.hello(ip)
                    if devs:
                        dev = devs[0]
                        self.logger.info(f"Discovered device at {ip} using hello(): {dev}")
                        found_devices.append(dev)
                        found_ips.add(ip)
                        continue
                except Exception as e:
                    self.logger.debug(f"hello() failed for {ip}: {e}")
                try:
                    dev = broadlink.gendevice(0x2737, (ip, 80))
                    dev.auth()
                    self.logger.info(f"Connected to device at {ip} using gendevice: {dev}")
                    found_devices.append(dev)
                    found_ips.add(ip)
                except Exception as e:
                    self.logger.debug(f"gendevice failed for {ip}: {e}")
        # Fallback to discovery for any additional devices
        self.logger.debug("Falling back to broadlink.discover()")
        devices = broadlink.discover(timeout=timeout)
        if not devices:
            self.logger.warning("No Broadlink devices discovered on network")
        else:
            for dev in devices:
                try:
                    host = dev.host[0]
                except Exception:
                    continue
                if host not in found_ips:
                    self.logger.info(f"Found additional device from discovery at {host}: {dev}")
                    found_devices.append(dev)
                    found_ips.add(host)
        if not found_devices:
            self.logger.warning("No Broadlink devices found via direct IP or discovery.")
        return found_devices

    def connect(self):
        self.logger.debug("Connecting to Broadlink devices...")
        devices = self._discover_devices()
        if not devices:
            self.logger.error("No Broadlink devices discovered on network")
            raise RuntimeError("No Broadlink devices discovered on network")
        # Try to authenticate all devices (if possible)
        for dev in devices:
            try:
                dev.auth()
                self.logger.info(f"Authenticated with device: {dev}")
            except Exception as e:
                self.logger.warning(f"Device auth failed or not required: {e}")
        self.devices = devices
        self.connected = True
        self.logger.info(f"Connected to {len(devices)} Broadlink device(s)")

    def refresh(self) -> bool:
        if not self.devices:
            return False
        refreshed = False
        for dev in self.devices:
            try:
                dev.auth()
                refreshed = True
            except Exception:
                continue
        return refreshed

    def learn_ir(self, timeout: int = 30) -> dict:
        if not self.devices:
            raise RuntimeError("No devices connected")
        results = {}
        for dev in self.devices:
            try:
                dev.enter_learning()
            except Exception:
                pass
        start = time.time()
        while time.time() - start < timeout:
            for dev in self.devices:
                try:
                    data = dev.check_data()
                    if data:
                        if isinstance(data, bytes):
                            results[dev.host[0]] = data
                        else:
                            try:
                                results[dev.host[0]] = binascii.unhexlify(data)
                            except Exception:
                                results[dev.host[0]] = bytes(data)
                except Exception:
                    continue
            if results:
                return results
            time.sleep(0.5)
        raise TimeoutError("IR learn timed out for all devices")

    def learn_rf(self, timeout: int = 30) -> dict:
        # Many Broadlink RM series use the same learning API for RF
        return self.learn_ir(timeout=timeout)

    def send_code(self, packet_hex_or_bytes):
        if not self.devices:
            raise RuntimeError("No devices connected")
        if isinstance(packet_hex_or_bytes, str):
            try:
                packet = binascii.unhexlify(packet_hex_or_bytes)
            except Exception:
                packet = packet_hex_or_bytes.encode()
        else:
            packet = packet_hex_or_bytes

        results = {}
        for dev in self.devices:
            sent = False
            if hasattr(dev, "send_data"):
                try:
                    dev.send_data(packet)
                    sent = True
                except Exception as err:
                    self.logger.warning(f"send_data failed for {dev.host[0]}: {err}")
            if not sent and hasattr(dev, "send_packet"):
                try:
                    dev.send_packet(packet)
                    sent = True
                except Exception as err:
                    self.logger.warning(f"send_packet failed for {dev.host[0]}: {err}")
            results[dev.host[0]] = sent
        return results

    def provision_ap(self, ssid, password, security_mode=None, setup_ip=None):
        # python-broadlink doesn't provide a generic AP provisioning helper across all devices.
        # Leave as not implemented for safety; device-specific provisioning can be added later.
        raise NotImplementedError("AP provisioning is device and platform specific")
