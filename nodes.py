"""Node classes for Broadlink PG3 plugin."""

from __future__ import annotations

import time
from typing import Dict, List

import udi_interface

from broadlink_client import BroadlinkHubClient
from config_parser import PluginConfig, build_config

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom
VERSION = "0.1.1"


class BaseNode(udi_interface.Node):
    """Common helpers shared by all nodes."""

    def _set(self, driver: str, value, uom: int | None = None, force: bool = False) -> None:
        if uom is None:
            self.setDriver(driver, value, True, force)
        else:
            self.setDriver(driver, value, True, force, uom=uom)


class BroadlinkCodeNode(BaseNode):
    """Subnode representing one IR or RF code."""

    id = "blircode"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV30", "value": 0, "uom": 25},
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def __init__(self, polyglot, primary, address: str, name: str, mode: str, code_name: str, controller):
        super().__init__(polyglot, primary, address, name)
        self.mode = mode
        self.code_name = code_name
        self.controller = controller
        if self.mode == "rf":
            self.id = "blrfcode"

    def set_code_name(self, code_name: str) -> None:
        self.code_name = code_name

    def start(self):
        self._set("GV30", 1)
        self._set("TIME", int(time.time()), 151)

    def stop(self):
        self._set("GV30", 0)

    def query(self, command=None):
        self._set("TIME", int(time.time()), 151)

    def send_code(self, command=None):
        try:
            self.controller.send_configured_code(self.mode, self.code_name)
            self._set("ST", 1)
            self._set("GV30", 1)
        except Exception as err:
            LOGGER.error("Failed sending %s code '%s': %s", self.mode, self.code_name, err)
            self._set("ST", 2)
            self._set("GV30", 0)
        self._set("TIME", int(time.time()), 151)

    commands = {
        "TXCODE": send_code,
        "QUERY": query,
    }


class BroadlinkRemoteNode(BaseNode):
    """Parent node for IR or RF code subnodes."""

    id = "blirremote"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV0", "value": 0, "uom": 56},
        {"driver": "GV30", "value": 0, "uom": 25},
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def __init__(self, polyglot, primary, address: str, name: str, mode: str, controller):
        super().__init__(polyglot, primary, address, name)
        self.mode = mode
        self.controller = controller
        if self.mode == "rf":
            self.id = "blrfremote"

    def start(self):
        self.update_status()

    def stop(self):
        self._set("GV30", 0)

    def update_status(self, command=None):
        code_count = len(self.controller.get_mode_codes(self.mode))
        connected = 1 if self.controller.is_connected() else 0
        self._set("ST", 1 if connected else 0)
        self._set("GV0", code_count)
        self._set("GV30", connected)
        self._set("TIME", int(time.time()), 151)

    def learn_code(self, command=None):
        try:
            name, _ = self.controller.learn_code(self.mode)
            LOGGER.info("Learned %s code: %s", self.mode.upper(), name)
            self._set("ST", 1)
            self._set("GV30", 1)
        except Exception as err:
            LOGGER.error("Failed to learn %s code: %s", self.mode, err)
            self._set("ST", 2)
            self._set("GV30", 0)
        self.update_status()

    commands = {
        "UPDATE": update_status,
        "QUERY": update_status,
        "LEARNCODE": learn_code,
    }


class BroadlinkController(BaseNode):
    """Controller node and orchestration layer."""

    id = "setup"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV1", "value": 0, "uom": 25},
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def __init__(self, polyglot, primary, address, name):
        super().__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.config = PluginConfig()
        self.parameters = Custom(self.poly, "customparams")
        self.data_store = Custom(self.poly, "customdata")
        self.heartbeat_state = 0
        self.learned_ir_codes: Dict[str, str] = {}
        self.learned_rf_codes: Dict[str, str] = {}

        self.client: BroadlinkHubClient | None = None
        self.ir_parent: BroadlinkRemoteNode | None = None
        self.rf_parent: BroadlinkRemoteNode | None = None
        self.ir_nodes: Dict[str, BroadlinkCodeNode] = {}
        self.rf_nodes: Dict[str, BroadlinkCodeNode] = {}

        self.poly.subscribe(self.poly.START, self.start, self.address)
        self.poly.subscribe(self.poly.STOP, self.stop)
        self.poly.subscribe(self.poly.POLL, self.poll)
        self.poly.subscribe(self.poly.CUSTOMPARAMS, self.handle_params)
        self.poly.subscribe(self.poly.CUSTOMDATA, self.handle_custom_data)
        self.poly.subscribe(self.poly.LOGLEVEL, self.handle_log_level)
        self.poly.subscribe(self.poly.DISCOVER, self.discover)

        self.poly.updateProfile()
        self.poly.ready()
        self.poly.addNode(self, conn_status="ST", rename=True)

    def start(self):
        self._set("TIME", int(time.time()), 151)
        self.apply_config()

    def stop(self):
        self._set("ST", 0)
        self._set("GV1", 0)

    def handle_log_level(self, level):
        if isinstance(level, dict) and "level" in level:
            LOGGER.info("New log level: %s", level["level"])

    def handle_params(self, custom_params):
        self.parameters.load(custom_params)
        self.poly.Notices.clear()

        try:
            self.config = build_config(custom_params)
        except Exception as err:
            self.poly.Notices["config"] = f"Invalid configuration format: {err}"
            LOGGER.error("Failed to parse custom params: %s", err)
            return

        missing: List[str] = []
        if not self.config.user_id:
            missing.append("USER_ID")
        if not self.config.user_password:
            missing.append("USER_PASSWORD")
        if not self.config.hub_ip:
            missing.append("HUB_IP")

        if missing:
            self.poly.Notices["required"] = "Missing required parameters: " + ", ".join(missing)

        self.apply_config()

    def handle_custom_data(self, custom_data):
        self.data_store.load(custom_data or {})
        self.learned_ir_codes = self._safe_code_map(self.data_store.get("learned_ir_codes", {}))
        self.learned_rf_codes = self._safe_code_map(self.data_store.get("learned_rf_codes", {}))

        # If nodes are already initialized, refresh the dynamic node set.
        if self.ir_parent or self.rf_parent:
            self._reconcile_nodes()
            self._refresh_parents()

    def poll(self, poll_type):
        self._set("TIME", int(time.time()), 151)

        if poll_type == "shortPoll":
            self.heartbeat_state = 1 - self.heartbeat_state
            if self.heartbeat_state:
                self.reportCmd("DON", 2)
            else:
                self.reportCmd("DOF", 2)
            return

        if self.client:
            online = 1 if self.client.refresh() else 0
            self._set("GV1", online)
        self._refresh_parents()

    def discover(self, *_):
        self.apply_config()

    def is_connected(self) -> bool:
        return bool(self.client and self.client.connected)

    def get_mode_codes(self, mode: str) -> Dict[str, str]:
        if mode == "ir":
            merged = dict(self.learned_ir_codes)
            merged.update(self.config.ir_codes)
            return merged
        if mode == "rf":
            merged = dict(self.learned_rf_codes)
            merged.update(self.config.rf_codes)
            return merged
        return {}

    def learn_code(self, mode: str):
        if self.client is None:
            raise RuntimeError("Broadlink client is not initialized")

        if mode == "ir":
            packet = self.client.learn_ir()
        elif mode == "rf":
            packet = self.client.learn_rf()
        else:
            raise ValueError(f"Unsupported learn mode: {mode}")

        code_name = self._next_learned_code_name(mode)
        code_value = packet.hex()

        if mode == "ir":
            self.learned_ir_codes[code_name] = code_value
        else:
            self.learned_rf_codes[code_name] = code_value

        self._persist_learned_codes()
        self._reconcile_nodes()
        self._refresh_parents()
        self._set("ST", 1)
        self._set("GV1", 1)
        self.poly.Notices[f"learn_{mode}"] = f"Learned {mode.upper()} code '{code_name}'"
        return code_name, code_value

    def send_configured_code(self, mode: str, code_name: str) -> None:
        code_map = self.get_mode_codes(mode)
        if code_name not in code_map:
            raise KeyError(f"Code '{code_name}' is not configured")
        if self.client is None:
            raise RuntimeError("Broadlink client is not initialized")

        self.client.send_code(code_map[code_name])
        self._set("GV1", 1)
        self._set("ST", 1)

    def apply_config(self):
        required_ok = bool(self.config.user_id and self.config.user_password and self.config.hub_ip)
        if not required_ok:
            self._set("ST", 0)
            self._set("GV1", 0)
            self._refresh_parents()
            return

        self.client = BroadlinkHubClient(
            hub_ip=self.config.hub_ip,
            user_id=self.config.user_id,
            user_password=self.config.user_password,
        )

        try:
            self.client.connect()
            self._set("ST", 1)
            self._set("GV1", 1)
        except Exception as err:
            LOGGER.error("Broadlink connect/auth failed: %s", err)
            self._set("ST", 0)
            self._set("GV1", 0)
            self.poly.Notices["connect"] = f"Could not connect/auth with Broadlink hub: {err}"

        self._reconcile_nodes()
        self._refresh_parents()

    def ap_setup(self, command=None):
        """Provision Broadlink device while it is in AP mode."""
        try:
            temp_client = BroadlinkHubClient(hub_ip=self.config.hub_ip)
            temp_client.provision_ap(
                ssid=self.config.wifi_ssid,
                password=self.config.wifi_password,
                security_mode=self.config.wifi_security_mode,
                setup_ip=self.config.setup_ip,
            )
            self.poly.Notices["apsetup"] = "AP setup packet sent. Put device in AP mode and wait for it to join Wi-Fi."
            LOGGER.info("Sent broadlink.setup AP provisioning packet")
        except Exception as err:
            LOGGER.error("AP setup failed: %s", err)
            self.poly.Notices["apsetup"] = f"AP setup failed: {err}"

    def _refresh_parents(self):
        if self.ir_parent:
            self.ir_parent.update_status()
        if self.rf_parent:
            self.rf_parent.update_status()

    def _reconcile_nodes(self):
        self._ensure_parent_nodes()
        self._reconcile_mode_nodes("ir", self.ir_nodes, self.ir_parent.address)
        self._reconcile_mode_nodes("rf", self.rf_nodes, self.rf_parent.address)
        self._remove_stale_nodes()

    def _ensure_parent_nodes(self):
        if not self.ir_parent:
            self.ir_parent = BroadlinkRemoteNode(self.poly, self.address, "blirhub", "Broadlink IR", "ir", self)
            self.poly.addNode(self.ir_parent, rename=True)

        if not self.rf_parent:
            self.rf_parent = BroadlinkRemoteNode(self.poly, self.address, "blrfhub", "Broadlink RF", "rf", self)
            self.poly.addNode(self.rf_parent, rename=True)

    def _reconcile_mode_nodes(self, mode: str, node_map: Dict[str, BroadlinkCodeNode], primary: str):
        codes = sorted(self.get_mode_codes(mode).keys())
        expected_addresses = []

        for index, code_name in enumerate(codes, start=1):
            prefix = "blir" if mode == "ir" else "blrf"
            addr = self.poly.getValidAddress(f"{prefix}{index:02d}")
            expected_addresses.append(addr)
            display_name = self.poly.getValidName(f"{mode.upper()} {code_name}")

            if addr in node_map:
                node = node_map[addr]
                node.set_code_name(code_name)
                if node.name != display_name:
                    node.rename(display_name)
                continue

            node = BroadlinkCodeNode(self.poly, primary, addr, display_name, mode, code_name, self)
            self.poly.addNode(node, rename=True)
            node_map[addr] = node

        for addr in list(node_map.keys()):
            if addr not in expected_addresses:
                self.poly.delNode(addr)
                del node_map[addr]

    def _remove_stale_nodes(self):
        expected = {
            self.address,
            "blirhub",
            "blrfhub",
            *self.ir_nodes.keys(),
            *self.rf_nodes.keys(),
        }
        for node_addr in list(self.poly.getNodes().keys()):
            if node_addr in expected:
                continue
            if node_addr.startswith("blir") or node_addr.startswith("blrf"):
                self.poly.delNode(node_addr)

    def _safe_code_map(self, candidate) -> Dict[str, str]:
        if not isinstance(candidate, dict):
            return {}
        parsed: Dict[str, str] = {}
        for key, value in candidate.items():
            key_str = str(key).strip()
            value_str = str(value).strip()
            if not key_str or not value_str:
                continue
            parsed[key_str] = value_str
        return parsed

    def _persist_learned_codes(self):
        self.data_store["learned_ir_codes"] = dict(self.learned_ir_codes)
        self.data_store["learned_rf_codes"] = dict(self.learned_rf_codes)

    def _next_learned_code_name(self, mode: str) -> str:
        prefix = "Learned IR" if mode == "ir" else "Learned RF"
        existing = set(self.get_mode_codes(mode).keys())
        index = 1
        while True:
            name = f"{prefix} {index:02d}"
            if name not in existing:
                return name
            index += 1

    def force_update(self, command=None):
        self.apply_config()

    commands = {
        "UPDATE": force_update,
        "APSETUP": ap_setup,
    }
