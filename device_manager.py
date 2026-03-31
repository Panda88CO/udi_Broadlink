"""DeviceManager: runtime orchestration of Broadlink IR/RF nodes using nodes.py classes."""
from __future__ import annotations

import time
from typing import Dict, Optional

import udi_interface

from config_parser import PluginConfig, build_config
from profile_json import PROFILE
from broadlink_client import BroadlinkHubClient
from nodes import BroadlinkRemoteNode, BroadlinkCodeNode, BroadlinkHubNode

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom



class DeviceManager:
    def __init__(self, polyglot):
        self.poly = polyglot
        self.parameters = Custom(self.poly, "customparams")
        self.data_store = Custom(self.poly, "customdata")
        self.config = PluginConfig()
        self.client: Optional[BroadlinkHubClient] = None

        self.learned_ir_codes: Dict[str, str] = {}
        self.learned_rf_codes: Dict[str, str] = {}

        self.hub_node: Optional[BroadlinkHubNode] = None
        self.ir_parent: Optional[BroadlinkRemoteNode] = None
        self.rf_parent: Optional[BroadlinkRemoteNode] = None
        self.ir_nodes: Dict[str, BroadlinkCodeNode] = {}
        self.rf_nodes: Dict[str, BroadlinkCodeNode] = {}

        self.poly.subscribe(self.poly.START, self.start)
        self.poly.subscribe(self.poly.STOP, self.stop)
        self.poly.subscribe(self.poly.POLL, self.poll)
        self.poly.subscribe(self.poly.CUSTOMPARAMS, self.handle_params)
        self.poly.subscribe(self.poly.CUSTOMDATA, self.handle_custom_data)
        self.poly.subscribe(self.poly.DISCOVER, self.discover)

        self._ensure_hub_node()
        self.poly.updateProfile()
        self.poly.ready()

    def _ensure_hub_node(self):
        if not self.hub_node:
            addr = self.poly.getValidAddress("blhub")
            name = "Broadlink Hub"
            self.hub_node = BroadlinkHubNode(self.poly, "", addr, name, self)
            self.poly.addNode(self.hub_node, rename=True)

    def start(self):
        self.apply_config()

    def stop(self):
        pass

    def poll(self, poll_type):
        if poll_type == "shortPoll":
            return
        if self.client:
            online = 1 if self.client.refresh() else 0
            LOGGER.debug("DeviceManager poll: client online=%s", online)
        # Always update hub node status
        if self.hub_node:
            self.hub_node.set_online(self.is_connected())
        self._reconcile_nodes()

    def discover(self, *_):
        self.apply_config()

    def handle_params(self, custom_params):
        self.parameters.load(custom_params)
        try:
            self.config = build_config(custom_params)
        except Exception as err:
            self.poly.Notices["config"] = f"Invalid configuration format: {err}"
            LOGGER.error("Failed to parse custom params: %s", err)
            return
        self.apply_config()

    def handle_custom_data(self, custom_data):
        self.data_store.load(custom_data or {})
        self.learned_ir_codes = dict(self.data_store.get("learned_ir_codes", {}))
        self.learned_rf_codes = dict(self.data_store.get("learned_rf_codes", {}))
        self._reconcile_nodes()

    def apply_config(self):
        required_ok = bool(self.config.user_id and self.config.user_password and self.config.hub_ips and len(self.config.hub_ips) > 0)
        if not required_ok:
            LOGGER.info("DeviceManager: missing required config, skipping client init")
            if self.hub_node:
                self.hub_node.set_online(False)
            return

        self.client = BroadlinkHubClient(
            hub_ips=self.config.hub_ips,
            user_id=self.config.user_id,
            user_password=self.config.user_password,
        )
        try:
            self.client.connect()
        except Exception as err:
            LOGGER.error("DeviceManager: client connect failed: %s", err)
            self.client = None

        if self.hub_node:
            self.hub_node.set_online(self.is_connected())
        self._reconcile_nodes()

    def is_connected(self) -> bool:
        return bool(self.client and getattr(self.client, "connected", False))

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

    def learn_code(self, mode: str, timeout: int = 30):
        if self.client is None:
            raise RuntimeError("Broadlink client is not initialized")
        if mode == "ir":
            packet = self.client.learn_ir(timeout=timeout)
        elif mode == "rf":
            packet = self.client.learn_rf(timeout=timeout)
        else:
            raise ValueError("Unsupported learn mode")

        code_name = self._next_learned_code_name(mode)
        code_value = packet.hex()
        if mode == "ir":
            self.learned_ir_codes[code_name] = code_value
        else:
            self.learned_rf_codes[code_name] = code_value

        self._persist_learned_codes()
        self._reconcile_nodes()
        return code_name, code_value

    def send_configured_code(self, mode: str, code_name: str):
        codes = self.get_mode_codes(mode)
        if code_name not in codes:
            raise KeyError("Code not found")
        if self.client is None:
            raise RuntimeError("Broadlink client is not initialized")
        self.client.send_code(codes[code_name])

    def _next_learned_code_name(self, mode: str) -> str:
        prefix = "Learned IR" if mode == "ir" else "Learned RF"
        existing = set(self.get_mode_codes(mode).keys())
        index = 1
        while True:
            name = f"{prefix} {index:02d}"
            if name not in existing:
                return name
            index += 1

    def _persist_learned_codes(self):
        self.data_store["learned_ir_codes"] = dict(self.learned_ir_codes)
        self.data_store["learned_rf_codes"] = dict(self.learned_rf_codes)

    def _ensure_parent_nodes(self):
        if not self.ir_parent:
            addr = self.poly.getValidAddress("blirhub")
            name = "Broadlink IR"
            self.ir_parent = BroadlinkRemoteNode(self.poly, "", addr, name, "ir", self)
            self.poly.addNode(self.ir_parent, rename=True)

        if not self.rf_parent:
            addr = self.poly.getValidAddress("blrfhub")
            name = "Broadlink RF"
            self.rf_parent = BroadlinkRemoteNode(self.poly, "", addr, name, "rf", self)
            self.poly.addNode(self.rf_parent, rename=True)

    def _reconcile_nodes(self):
        self._ensure_parent_nodes()
        self._reconcile_mode("ir", self.ir_nodes, self.ir_parent.address)
        self._reconcile_mode("rf", self.rf_nodes, self.rf_parent.address)

    def _reconcile_mode(self, mode: str, node_map: Dict[str, BroadlinkCodeNode], parent_addr: str):
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

            node = BroadlinkCodeNode(self.poly, parent_addr, addr, display_name, mode, code_name, self)
            self.poly.addNode(node, rename=True)
            node_map[addr] = node

        for addr in list(node_map.keys()):
            if addr not in expected_addresses:
                self.poly.delNode(addr)
                del node_map[addr]
