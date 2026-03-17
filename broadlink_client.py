"""Broadlink hub wrapper used by PG3 nodes.

This wrapper keeps Broadlink specifics in one place so new Broadlink device
classes can be added later without changing node classes.
"""

from __future__ import annotations

import base64
from threading import Lock
import time
from typing import Callable

import broadlink
import udi_interface


LOGGER = udi_interface.LOGGER


def _str_preview(value: str, max_chars: int = 80) -> str:
    if not value:
        return ""
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}..."


def _bytes_hex_preview(value: bytes, max_bytes: int = 16) -> str:
    if not value:
        return ""
    snippet = value[:max_bytes]
    return snippet.hex()


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
            LOGGER.debug("Broadlink connect: hello() start hub_ip=%s", self.hub_ip)
            start = time.time()
            device = broadlink.hello(self.hub_ip)
            LOGGER.debug("Broadlink connect: hello() returned device={}".format(device))
            if device is None:
                LOGGER.debug("Broadlink connect: hello() returned no device hub_ip=%s", self.hub_ip)
                raise RuntimeError(f"No Broadlink device found at {self.hub_ip}")
            LOGGER.debug("Broadlink connect: hello() completed in %.3fs", time.time() - start)

            # Some hubs are temporarily busy; a short retry often succeeds.
            last_err = None
            for attempt in range(1, 3):
                try:
                    LOGGER.debug("Broadlink connect: auth() start hub_ip=%s attempt=%d", self.hub_ip, attempt)
                    auth_start = time.time()
                    device.auth()
                    LOGGER.debug(
                        "Broadlink connect: auth() completed in %.3fs attempt=%d",
                        time.time() - auth_start,
                        attempt,
                    )
                    break
                except Exception as err:
                    last_err = err
                    LOGGER.debug("Broadlink connect: auth() failed attempt=%d err=%s", attempt, err)
                    if attempt < 2:
                        # Re-run hello before retrying auth to refresh the session bootstrap.
                        time.sleep(0.3)
                        LOGGER.debug("Broadlink connect: retry hello() before auth attempt=%d", attempt + 1)
                        device = broadlink.hello(self.hub_ip)
                        if device is None:
                            raise RuntimeError(f"No Broadlink device found at {self.hub_ip}")
                    else:
                        self._device = None
                        raise RuntimeError(
                            "Broadlink auth failed after retry. AP setup is only needed when the device is in AP "
                            "mode or not joined to Wi-Fi. If the hub is already on your LAN, verify HUB_IP and "
                            f"network reachability. Underlying error: {last_err}"
                        ) from err

            self._device = device
            LOGGER.debug("Broadlink connect: connected=True total_time=%.3fs", time.time() - start)
            return True

    def refresh(self) -> bool:
        """Best-effort connectivity refresh."""
        with self._lock:
            if self._device is None:
                LOGGER.debug("Broadlink refresh: skipped because device is not connected")
                return False
            try:
                LOGGER.debug("Broadlink refresh: ping() start")
                self._device.ping()
                LOGGER.debug("Broadlink refresh: ping() ok")
                return True
            except Exception as err:
                LOGGER.debug("Broadlink refresh: ping() failed, retrying auth() err=%s", err)
                try:
                    self._device.auth()
                    LOGGER.debug("Broadlink refresh: auth() re-established session")
                    return True
                except Exception as auth_err:
                    LOGGER.debug("Broadlink refresh: auth() failed, dropping device err=%s", auth_err)
                    self._device = None
                    return False

    def send_code(self, encoded_code: str) -> bool:
        """Transmit an IR or RF packet to the Broadlink hub."""
        LOGGER.debug(
            "Broadlink send_code: encoded_len=%d encoded_preview=%s",
            len(encoded_code or ""),
            _str_preview(encoded_code),
        )
        packet = decode_code_string(encoded_code)
        LOGGER.debug(
            "Broadlink send_code: decoded packet_len=%d packet_hex_preview=%s",
            len(packet),
            _bytes_hex_preview(packet),
        )

        with self._lock:
            if self._device is None:
                LOGGER.debug("Broadlink send_code: not connected, calling connect()")
                self.connect()
            LOGGER.debug("Broadlink send_code: send_data() start packet_len=%d", len(packet))
            start = time.time()
            self._device.send_data(packet)
            LOGGER.debug("Broadlink send_code: send_data() completed in %.3fs", time.time() - start)
            return True

    def learn_ir(
        self,
        timeout_sec: int = 30,
        poll_interval: float = 1.0,
        status_callback: Callable[[str], None] | None = None,
    ) -> bytes:
        """Learn a single IR packet and return raw Broadlink bytes."""
        with self._lock:
            if self._device is None:
                LOGGER.debug("Broadlink learn_ir: not connected, calling connect()")
                self.connect()

            LOGGER.debug(
                "Broadlink learn_ir: enter_learning() timeout_sec=%s poll_interval=%s",
                timeout_sec,
                poll_interval,
            )
            self._device.enter_learning()
            if status_callback:
                status_callback("enter_learning")
                status_callback("awaiting_button")
            packet = self._wait_for_learned_packet(
                timeout_sec=timeout_sec,
                poll_interval=poll_interval,
                status_callback=status_callback,
            )
            LOGGER.debug("Broadlink learn_ir: packet received packet_len=%d", len(packet))
            return packet

    def learn_rf(
        self,
        timeout_sec: int = 45,
        poll_interval: float = 1.0,
        status_callback: Callable[[str], None] | None = None,
    ) -> bytes:
        """Learn a single RF packet and return raw Broadlink bytes.

        For devices that support RF sweep APIs we use sweep->check_frequency->find_rf_packet.
        If not supported, we fall back to the generic learning method.
        """
        with self._lock:
            if self._device is None:
                LOGGER.debug("Broadlink learn_rf: not connected, calling connect()")
                self.connect()

            if hasattr(self._device, "sweep_frequency") and hasattr(self._device, "check_frequency"):
                LOGGER.debug(
                    "Broadlink learn_rf: using sweep mode timeout_sec=%s poll_interval=%s",
                    timeout_sec,
                    poll_interval,
                )
                if status_callback:
                    status_callback("sweep_started")
                    status_callback("awaiting_first_press")
                self._device.sweep_frequency()
                start = time.time()
                found = False
                frequency = None

                while (time.time() - start) < timeout_sec:
                    time.sleep(poll_interval)
                    try:
                        found, frequency = self._device.check_frequency()
                    except Exception as err:
                        LOGGER.debug("Broadlink learn_rf: check_frequency() retry err=%s", err)
                        continue
                    if found:
                        LOGGER.debug("Broadlink learn_rf: frequency found=%s", frequency)
                        if status_callback:
                            status_callback("frequency_found")
                        break

                if not found:
                    try:
                        self._device.cancel_sweep_frequency()
                    except Exception as err:
                        LOGGER.debug("Broadlink learn_rf: cancel_sweep_frequency() err=%s", err)
                        pass
                    raise TimeoutError("RF frequency sweep timed out")

                LOGGER.debug("Broadlink learn_rf: find_rf_packet() start frequency=%s", frequency)
                try:
                    self._device.find_rf_packet(frequency)
                except TypeError:
                    # python-broadlink documents find_rf_packet() without args.
                    self._device.find_rf_packet()

                if status_callback:
                    status_callback("awaiting_second_press")
                packet = self._wait_for_learned_packet(
                    timeout_sec=timeout_sec,
                    poll_interval=poll_interval,
                    status_callback=status_callback,
                )
                LOGGER.debug("Broadlink learn_rf: packet received packet_len=%d", len(packet))
                return packet

            # Some remote models learn RF through the same generic IR flow.
            LOGGER.debug("Broadlink learn_rf: falling back to enter_learning()")
            self._device.enter_learning()
            if status_callback:
                status_callback("enter_learning")
                status_callback("awaiting_button")
            packet = self._wait_for_learned_packet(
                timeout_sec=timeout_sec,
                poll_interval=poll_interval,
                status_callback=status_callback,
            )
            LOGGER.debug("Broadlink learn_rf: fallback packet received packet_len=%d", len(packet))
            return packet

    def _wait_for_learned_packet(
        self,
        timeout_sec: int = 30,
        poll_interval: float = 1.0,
        status_callback: Callable[[str], None] | None = None,
    ) -> bytes:
        """Poll the hub until a learned packet is available."""
        LOGGER.debug(
            "Broadlink wait_for_packet: start timeout_sec=%s poll_interval=%s",
            timeout_sec,
            poll_interval,
        )
        start = time.time()
        while (time.time() - start) < timeout_sec:
            time.sleep(poll_interval)
            try:
                packet = self._device.check_data()
            except Exception as err:
                LOGGER.debug("Broadlink wait_for_packet: check_data() retry err=%s", err)
                continue
            if packet:
                LOGGER.debug("Broadlink wait_for_packet: packet available packet_len=%d", len(packet))
                if status_callback:
                    status_callback("packet_received")
                return packet

        LOGGER.debug("Broadlink wait_for_packet: timeout after %.3fs", time.time() - start)
        raise TimeoutError("No learned packet received before timeout")

    def provision_ap(self, ssid: str, password: str, security_mode: int = 4, setup_ip: str = "255.255.255.255") -> bool:
        """Provision a Broadlink device in AP mode using broadlink.setup."""
        if not ssid:
            raise ValueError("WIFI_SSID is required for AP setup")
        if security_mode < 0 or security_mode > 4:
            raise ValueError("WIFI_SECURITY_MODE must be between 0 and 4")

        LOGGER.debug(
            "Broadlink provision_ap: setup() start ssid=%s security_mode=%s setup_ip=%s",
            ssid,
            security_mode,
            setup_ip,
        )
        start = time.time()
        broadlink.setup(ssid=ssid, password=password, security_mode=security_mode, ip_address=setup_ip)
        LOGGER.debug("Broadlink provision_ap: setup() completed in %.3fs", time.time() - start)
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
        decoded = base64.b64decode(text[4:].strip())
        LOGGER.debug("Broadlink decode_code_string: base64 decoded packet_len=%d", len(decoded))
        return decoded

    hex_text = "".join(text.split())
    decoded = bytes.fromhex(hex_text)
    LOGGER.debug("Broadlink decode_code_string: hex decoded packet_len=%d", len(decoded))
    return decoded
