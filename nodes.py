"""Node classes for Broadlink PG3 plugin."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, List

import udi_interface

from broadlink_client import BroadlinkHubClient
from config_parser import PluginConfig, build_config

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom
VERSION = "0.1.5"

LEARN_STATE_IDLE = 0
LEARN_STATE_WAIT_BUTTON = 1
LEARN_STATE_RF_SWEEP = 2
LEARN_STATE_RF_FREQ_FOUND = 3
LEARN_STATE_WAIT_PACKET = 4
LEARN_STATE_SUCCESS = 5
LEARN_STATE_FAILED = 6


def _code_preview(code_value: str, max_chars: int = 80) -> str:
    """Return a short, log-safe preview of an encoded code string."""
    if not code_value:
        return ""
    if len(code_value) <= max_chars:
        return code_value
    return f"{code_value[:max_chars]}..."


def _canonical_address(address: str) -> str:
    """Normalize addresses so plugin logic can compare PG3 and local forms."""
    text = str(address or "").strip().lower()
    if not text:
        return ""
    match = re.match(r"^n\d+_(.+)$", text)
    if match:
        return match.group(1)
    return text


def _address_matches_mode(address: str, mode: str) -> bool:
    canon = _canonical_address(address)
    prefixes = ("blir", "bir") if mode == "ir" else ("blrf", "brf")
    return canon.startswith(prefixes)


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

    def __init__(self, polyglot, primary, address: str, name: str, mode: str, code_value: str, controller):
        super().__init__(polyglot, primary, address, name)
        self.mode = mode
        self.code_value = code_value
        self.controller = controller
        if self.mode == "rf":
            self.id = "blrfcode"

    def set_code_value(self, code_value: str) -> None:
        self.code_value = code_value

    def start(self):
        self._set("GV30", 1)
        self._set("TIME", int(time.time()), 151)

    def stop(self):
        self._set("GV30", 0)

    def query(self, command=None):
        self._set("TIME", int(time.time()), 151)

    def send_code(self, command=None):
        try:
            LOGGER.info(
                "TXCODE requested node=%s mode=%s code_len=%d code_preview=%s",
                self.address,
                self.mode,
                len(self.code_value or ""),
                _code_preview(self.code_value),
            )
            self.controller.send_code_packet(self.mode, self.code_value)
            self._set("ST", 1)
            self._set("GV30", 1)
            LOGGER.info("TXCODE completed node=%s mode=%s", self.address, self.mode)
        except Exception as err:
            LOGGER.error("Failed sending %s code on node '%s': %s", self.mode, self.address, err)
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
        {"driver": "GV2", "value": 0, "uom": 25},
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
        self._set("GV2", LEARN_STATE_IDLE)
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
        def progress(event: str) -> None:
            self._set_learning_state(event)

        try:
            name, _ = self.controller.learn_code(self.mode, status_callback=progress)
            LOGGER.info("Learned %s code: %s", self.mode.upper(), name)
            self._set("ST", 1)
            self._set("GV30", 1)
            self._set("GV2", LEARN_STATE_SUCCESS)
            self.controller.poly.Notices[f"learn_{self.mode}_state"] = (
                f"{self.mode.upper()} learned. New code node '{name}' is ready to send."
            )
        except Exception as err:
            LOGGER.error("Failed to learn %s code: %s", self.mode, err)
            self._set("ST", 2)
            self._set("GV30", 0)
            self._set("GV2", LEARN_STATE_FAILED)
            self.controller.poly.Notices[f"learn_{self.mode}_state"] = f"{self.mode.upper()} learn failed: {err}"
        self.update_status()

    def _set_learning_state(self, event: str) -> None:
        notices = self.controller.poly.Notices

        if event in {"enter_learning", "awaiting_button"}:
            self._set("GV2", LEARN_STATE_WAIT_BUTTON)
            notices[f"learn_{self.mode}_state"] = (
                f"{self.mode.upper()} learning active. Point remote and press the target button."
            )
            return

        if event == "sweep_started":
            self._set("GV2", LEARN_STATE_RF_SWEEP)
            notices[f"learn_{self.mode}_state"] = (
                "RF sweep started. Long press the target button until frequency is found."
            )
            return

        if event == "awaiting_first_press":
            self._set("GV2", LEARN_STATE_RF_SWEEP)
            notices[f"learn_{self.mode}_state"] = (
                "RF frequency detect step. Long press the target remote button."
            )
            return

        if event == "frequency_found":
            self._set("GV2", LEARN_STATE_RF_FREQ_FOUND)
            notices[f"learn_{self.mode}_state"] = "RF frequency found. Preparing packet learning step."
            return

        if event == "awaiting_second_press":
            self._set("GV2", LEARN_STATE_WAIT_PACKET)
            notices[f"learn_{self.mode}_state"] = "RF packet step. Short press the same button now."
            return

        if event == "packet_received":
            self._set("GV2", LEARN_STATE_SUCCESS)
            notices[f"learn_{self.mode}_state"] = "Packet captured. Creating code node."
            return

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
        self.code_records: Dict[str, Dict[str, Dict[str, str]]] = {"ir": {}, "rf": {}}
        self.code_records_key = "code_records"

        self.client: BroadlinkHubClient | None = None
        self.ir_parent: BroadlinkRemoteNode | None = None
        self.rf_parent: BroadlinkRemoteNode | None = None
        self.ir_nodes: Dict[str, BroadlinkCodeNode] = {}
        self.rf_nodes: Dict[str, BroadlinkCodeNode] = {}
        self.pending_renames: Dict[str, str] = {}
        self.custom_data_loaded = False

        self._load_code_records()

        self.poly.subscribe(self.poly.START, self.start, self.address)
        self.poly.subscribe(self.poly.STOP, self.stop)
        self.poly.subscribe(self.poly.ADDNODEDONE, self._handle_add_node_done)
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
        try:
            self._prune_deleted_code_records()
            self.update_codes(notify=False)
        except Exception as err:
            LOGGER.error("Failed to persist codes during stop: %s", err)
        self._set("ST", 0)
        self._set("GV1", 0)

    def handle_log_level(self, level):
        if isinstance(level, dict) and "level" in level:
            LOGGER.info("New log level: %s", level["level"])

    def _handle_add_node_done(self, node):
        address = _canonical_address(getattr(node, "address", "") or (node.get("address", "") if isinstance(node, dict) else ""))
        if not address:
            return

        desired_name = self.pending_renames.pop(address, "")
        if not desired_name:
            return

        target = self.poly.getNodes().get(address)
        if target is None:
            for raw_addr, existing_node in self.poly.getNodes().items():
                if _canonical_address(raw_addr) == address:
                    target = existing_node
                    break

        if target is None:
            LOGGER.debug("ADDNODEDONE for %s but node object was not found for deferred rename", address)
            return

        current_name = str(getattr(target, "name", "")).strip()
        if current_name == desired_name:
            LOGGER.debug("ADDNODEDONE rename skipped for %s because name already matches", address)
            return

        LOGGER.info("ADDNODEDONE applying deferred rename address=%s old=%s new=%s", address, current_name, desired_name)
        target.rename(desired_name)

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

        # Load code records from customdata
        self._load_code_records_from_custom_data()
        self.custom_data_loaded = True

        # If nodes are already initialized, refresh the dynamic node set.
        if self.ir_parent or self.rf_parent:
            self._reconcile_nodes()
            self._refresh_parents()

    def poll(self, poll_type):
        self._set("TIME", int(time.time()), 151)
        self._capture_node_renames()

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
        codes: Dict[str, str] = {}
        for addr, rec in self.code_records.get(mode, {}).items():
            code_value = str(rec.get("code", "")).strip()
            if not code_value:
                continue
            codes[addr] = code_value
        return codes

    def learn_code(self, mode: str, status_callback=None):
        if self.client is None:
            raise RuntimeError("Broadlink client is not initialized")

        if mode == "ir":
            packet = self.client.learn_ir(status_callback=status_callback)
        elif mode == "rf":
            packet = self.client.learn_rf(status_callback=status_callback)
        else:
            raise ValueError(f"Unsupported learn mode: {mode}")

        if not packet:
            raise RuntimeError("Learning returned an empty packet")

        code_value = packet.hex()
        code_name = self._next_learned_code_name(mode)
        address = self._next_code_address(mode)

        # Validate the packet by sending it once before we publish a new node.
        self.client.send_code(code_value)

        self.code_records[mode][address] = {
            "name": code_name,
            "code": code_value,
            "source": "learned",
            "source_key": code_name,
        }

        self._persist_code_records()
        self._reconcile_nodes()
        self._refresh_parents()
        self._set("ST", 1)
        self._set("GV1", 1)
        self.poly.Notices[f"learn_{mode}"] = f"Learned {mode.upper()} code '{code_name}'"
        return code_name, code_value

    def send_code_packet(self, mode: str, code_value: str) -> None:
        if not code_value:
            raise ValueError(f"No {mode.upper()} code payload is configured for this node")
        if self.client is None:
            raise RuntimeError("Broadlink client is not initialized")

        LOGGER.debug(
            "send_code_packet mode=%s code_len=%d code_preview=%s",
            mode,
            len(code_value),
            _code_preview(code_value),
        )
        self.client.send_code(code_value)
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

        self.update_codes(notify=False)

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
        self._log_node_routing_state("before_reconcile")
        self._capture_node_renames()
        self._sync_config_records()
        self._adopt_existing_node_names()
        self._ensure_parent_nodes()
        if not self.ir_parent or not self.rf_parent:
            LOGGER.debug(
                "Reconcile aborted: ir_parent=%s rf_parent=%s",
                bool(self.ir_parent),
                bool(self.rf_parent),
            )
            return
        self._reconcile_mode_nodes("ir", self.ir_nodes, self.ir_parent.address)
        self._reconcile_mode_nodes("rf", self.rf_nodes, self.rf_parent.address)
        self._remove_stale_nodes()
        self._persist_code_records()
        self._log_node_routing_state("after_reconcile")

    def _log_node_routing_state(self, stage: str):
        nodes = self.poly.getNodes()
        runtime_rf = sorted([_canonical_address(addr) for addr in nodes.keys() if _address_matches_mode(addr, "rf")])
        runtime_ir = sorted([_canonical_address(addr) for addr in nodes.keys() if _address_matches_mode(addr, "ir")])
        LOGGER.debug(
            "Routing state %s: records_rf=%s records_ir=%s map_rf=%s map_ir=%s runtime_rf=%s runtime_ir=%s",
            stage,
            sorted(self.code_records.get("rf", {}).keys()),
            sorted(self.code_records.get("ir", {}).keys()),
            sorted(self.rf_nodes.keys()),
            sorted(self.ir_nodes.keys()),
            runtime_rf,
            runtime_ir,
        )

    def _adopt_existing_node_names(self):
        """Use names already stored in PG3/runtime so startup does not overwrite user renames."""
        adopted = []
        existing_nodes = self.poly.getNodes()
        runtime_name_by_addr = {}

        for raw_addr, node in existing_nodes.items():
            canon_addr = _canonical_address(raw_addr)
            if not canon_addr or canon_addr in {"setup", "blirhub", "blrfhub"}:
                continue
            runtime_name = str(getattr(node, "name", "")).strip()
            if runtime_name:
                runtime_name_by_addr[canon_addr] = runtime_name

        get_node_name = getattr(self.poly, "getNodeNameFromDb", None)

        for mode in ("ir", "rf"):
            for addr, record in self.code_records.get(mode, {}).items():
                existing_name = runtime_name_by_addr.get(addr, "")
                if not existing_name and callable(get_node_name):
                    try:
                        existing_name = str(get_node_name(addr) or "").strip()
                    except Exception:
                        existing_name = ""

                if not existing_name:
                    continue

                if record.get("name") == existing_name:
                    continue

                record["name"] = existing_name
                adopted.append((addr, existing_name))

        if adopted:
            LOGGER.info("Adopted existing node names from PG3/runtime: %s", adopted)
            self._persist_code_records()

    def _queue_node_rename(self, address: str, desired_name: str):
        canon_addr = _canonical_address(address)
        desired = str(desired_name or "").strip()
        if not canon_addr or not desired:
            return
        self.pending_renames[canon_addr] = desired
        LOGGER.debug("Queued deferred rename address=%s desired_name=%s", canon_addr, desired)

    def _seed_records_from_pg3_nodes(self):
        """Adopt existing PG3 nodes so commands can route before codes are configured."""
        getter = getattr(self.poly, "getNodesFromDb", None)
        if not callable(getter):
            LOGGER.debug("PG3 DB snapshot unavailable: getNodesFromDb() not supported by this interface version")
            return

        try:
            pg3_nodes = getter()
        except Exception as err:
            LOGGER.debug("Unable to read PG3 node database snapshot: %s", err)
            return

        if not isinstance(pg3_nodes, list):
            LOGGER.debug("PG3 DB snapshot returned unexpected type: %s", type(pg3_nodes).__name__)
            return

        seeded = 0
        db_rf = []
        db_ir = []
        for node in pg3_nodes:
            if not isinstance(node, dict):
                continue

            addr = _canonical_address(node.get("address", ""))
            if not addr or addr in {"setup", "blirhub", "blrfhub"}:
                continue

            mode = None
            if _address_matches_mode(addr, "ir"):
                mode = "ir"
                db_ir.append(addr)
            elif _address_matches_mode(addr, "rf"):
                mode = "rf"
                db_rf.append(addr)
            if mode is None:
                continue

            records = self.code_records.get(mode, {})
            if addr in records:
                continue

            fallback_name = f"{mode.upper()} {addr}"
            display_name = self.poly.getValidName(str(node.get("name", "")).strip() or fallback_name)
            records[addr] = {
                "name": display_name,
                "code": "",
                "source": "pg3",
                "source_key": addr,
            }
            seeded += 1

        if seeded:
            LOGGER.info("Seeded %d code node record(s) from PG3 DB snapshot", seeded)
        LOGGER.debug(
            "PG3 DB snapshot nodes: rf=%s ir=%s seeded=%d",
            sorted(set(db_rf)),
            sorted(set(db_ir)),
            seeded,
        )

    def _ensure_parent_nodes(self):
        existing_nodes = self.poly.getNodes()

        existing_ir = existing_nodes.get("blirhub")
        if existing_ir is None:
            for raw_addr, node in existing_nodes.items():
                if _canonical_address(raw_addr) == "blirhub":
                    existing_ir = node
                    break
        if existing_ir and getattr(existing_ir, "primary", None) != "blirhub":
            self._delete_mode_nodes("ir")
            self.poly.delNode("blirhub")
            self.ir_parent = None

        existing_rf = existing_nodes.get("blrfhub")
        if existing_rf is None:
            for raw_addr, node in existing_nodes.items():
                if _canonical_address(raw_addr) == "blrfhub":
                    existing_rf = node
                    break
        if existing_rf and getattr(existing_rf, "primary", None) != "blrfhub":
            self._delete_mode_nodes("rf")
            self.poly.delNode("blrfhub")
            self.rf_parent = None

        if not self.ir_parent:
            self.ir_parent = BroadlinkRemoteNode(self.poly, "blirhub", "blirhub", "Broadlink IR", "ir", self)
            self.poly.addNode(self.ir_parent, rename=False)
            self._queue_node_rename(self.ir_parent.address, self.ir_parent.name)

        if not self.rf_parent:
            self.rf_parent = BroadlinkRemoteNode(self.poly, "blrfhub", "blrfhub", "Broadlink RF", "rf", self)
            self.poly.addNode(self.rf_parent, rename=False)
            self._queue_node_rename(self.rf_parent.address, self.rf_parent.name)

    def _delete_mode_nodes(self, mode: str):
        node_map = self.ir_nodes if mode == "ir" else self.rf_nodes
        for addr in list(node_map.keys()):
            self.poly.delNode(addr)
            del node_map[addr]

        parent_addr = "blirhub" if mode == "ir" else "blrfhub"
        for node_addr in list(self.poly.getNodes().keys()):
            canon_addr = _canonical_address(node_addr)
            if canon_addr == parent_addr:
                continue
            if _address_matches_mode(canon_addr, mode):
                self.poly.delNode(node_addr)

    def _reconcile_mode_nodes(self, mode: str, node_map: Dict[str, BroadlinkCodeNode], primary: str):
        records = {
            _canonical_address(addr): value for addr, value in self.code_records.get(mode, {}).items() if _canonical_address(addr)
        }
        self.code_records[mode] = records
        expected_addresses = sorted(records.keys())
        existing_nodes = self.poly.getNodes()
        canonical_to_raw = {_canonical_address(raw_addr): raw_addr for raw_addr in existing_nodes.keys()}
        LOGGER.debug(
            "Reconcile %s nodes: expected_addresses=%s current_registered=%s",
            mode,
            expected_addresses,
            sorted(
                [
                    _canonical_address(addr)
                    for addr in existing_nodes.keys()
                    if _address_matches_mode(addr, "ir") or _address_matches_mode(addr, "rf")
                ]
            ),
        )

        for addr in expected_addresses:
            record = records[addr]
            display_name = self.poly.getValidName(record.get("name", f"{mode.upper()} Code"))
            code_value = record.get("code", "")

            if addr in node_map:
                node = node_map[addr]
                node.set_code_value(code_value)
                if node.name != display_name:
                    self._queue_node_rename(addr, display_name)
                    if getattr(node, "added", False):
                        LOGGER.info("Applying immediate rename for ready node address=%s old=%s new=%s", addr, node.name, display_name)
                        node.rename(display_name)
                continue

            stale_raw_addr = canonical_to_raw.get(addr)
            if stale_raw_addr:
                self.poly.delNode(stale_raw_addr)

            node = BroadlinkCodeNode(self.poly, primary, addr, display_name, mode, code_value, self)
            self.poly.addNode(node, rename=False)
            node_map[addr] = node
            self._queue_node_rename(addr, display_name)
            LOGGER.info("Registered %s code node address=%s name=%s", mode.upper(), addr, display_name)

        for addr in list(node_map.keys()):
            if addr not in expected_addresses:
                self.poly.delNode(addr)
                del node_map[addr]

    def _remove_stale_nodes(self):
        expected = {
            _canonical_address(self.address),
            "blirhub",
            "blrfhub",
            *self.ir_nodes.keys(),
            *self.rf_nodes.keys(),
        }
        for node_addr in list(self.poly.getNodes().keys()):
            canon_addr = _canonical_address(node_addr)
            if canon_addr in expected:
                continue
            if _address_matches_mode(canon_addr, "ir") or _address_matches_mode(canon_addr, "rf"):
                self.poly.delNode(node_addr)

    def _prune_deleted_code_records(self):
        """Drop persisted learned nodes that were deleted from the live runtime."""
        runtime_nodes = self.poly.getNodes()
        runtime_addresses = {_canonical_address(addr) for addr in runtime_nodes.keys()}
        removed: list[str] = []

        for mode in ("ir", "rf"):
            records = self.code_records.get(mode, {})
            for addr in list(records.keys()):
                record = records[addr]
                if record.get("source") == "config":
                    continue
                if addr in runtime_addresses:
                    continue
                removed.append(addr)
                del records[addr]

        if removed:
            LOGGER.info("Pruned deleted code records before stop: %s", sorted(removed))
            self._persist_code_records()
        else:
            LOGGER.debug("Stop prune: no deleted dynamic code records found")

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
        existing = {record.get("name", "") for record in self.code_records.get(mode, {}).values()}
        index = 1
        while True:
            name = f"{prefix} {index:02d}"
            if name not in existing:
                return name
            index += 1

    def _next_code_address(self, mode: str) -> str:
        used = set(self.code_records.get(mode, {}).keys())
        prefix = "blir" if mode == "ir" else "blrf"
        index = 1
        while True:
            addr = f"{prefix}{index:02d}"
            if addr not in used and addr not in {"blirhub", "blrfhub"}:
                return addr
            index += 1

    def _find_existing_code_node_address(self, mode: str, code_name: str) -> str | None:
        used = set(self.code_records.get(mode, {}).keys())
        existing_nodes = self.poly.getNodes()

        for raw_addr, node in existing_nodes.items():
            addr = _canonical_address(raw_addr)
            if addr in used or not _address_matches_mode(addr, mode) or addr in {"blirhub", "blrfhub"}:
                continue
            if str(getattr(node, "name", "")).strip() == str(code_name).strip():
                return addr

        for raw_addr in sorted(existing_nodes.keys()):
            addr = _canonical_address(raw_addr)
            if addr in used or not _address_matches_mode(addr, mode) or addr in {"blirhub", "blrfhub"}:
                continue
            return addr

        return None

    def _sync_config_records(self):
        self._sync_config_records_for_mode("ir", self.config.ir_codes)
        self._sync_config_records_for_mode("rf", self.config.rf_codes)

    def _sync_config_records_for_mode(self, mode: str, config_codes: Dict[str, str]):
        records = self.code_records[mode]
        desired_keys = {name for name, value in config_codes.items() if str(value).strip()}
        default_name_by_key = {name: self.poly.getValidName(f"{mode.upper()} {name}") for name in config_codes.keys()}

        for addr in list(records.keys()):
            record = records[addr]
            if record.get("source") == "config" and record.get("source_key") not in desired_keys:
                del records[addr]

        for code_name, code_value in config_codes.items():
            normalized_code = str(code_value).strip()
            if not normalized_code:
                continue

            existing_addr = None
            for addr, record in records.items():
                if record.get("source") == "config" and record.get("source_key") == code_name:
                    existing_addr = addr
                    break

            if existing_addr:
                records[existing_addr]["code"] = normalized_code
                continue

            # If the config key changed but payload stayed the same, treat it as a rename.
            rename_addr = None
            for addr, record in records.items():
                if record.get("source") != "config":
                    continue
                if record.get("source_key") in desired_keys:
                    continue
                if str(record.get("code", "")).strip() != normalized_code:
                    continue
                rename_addr = addr
                break

            if rename_addr:
                record = records[rename_addr]
                old_key = str(record.get("source_key", "")).strip()
                old_default_name = self.poly.getValidName(f"{mode.upper()} {old_key}") if old_key else ""
                record["source_key"] = code_name
                record["code"] = normalized_code
                if record.get("name") == old_default_name or not str(record.get("name", "")).strip():
                    record["name"] = default_name_by_key[code_name]
                continue

            addr = self._next_code_address(mode)
            records[addr] = {
                "name": default_name_by_key[code_name],
                "code": normalized_code,
                "source": "config",
                "source_key": code_name,
            }

    def update_codes(self, command=None, notify: bool = True):
        self._capture_node_renames()
        self._sync_config_records()

        # Remove invalid/empty records to keep the persisted JSON clean.
        for mode in ("ir", "rf"):
            for addr in list(self.code_records.get(mode, {}).keys()):
                record = self.code_records[mode][addr]
                if not str(record.get("code", "")).strip():
                    del self.code_records[mode][addr]
                    continue
                if not str(record.get("name", "")).strip():
                    fallback = "IR Code" if mode == "ir" else "RF Code"
                    self.code_records[mode][addr]["name"] = self.poly.getValidName(fallback)

        self._persist_code_records()
        self._reconcile_nodes()
        self._refresh_parents()
        if notify:
            self.poly.Notices["codes"] = "Code records updated and saved"
            LOGGER.info("Code records reconciled and persisted")

    def _capture_node_renames(self):
        changed = False
        for mode, node_map in (("ir", self.ir_nodes), ("rf", self.rf_nodes)):
            records = self.code_records.get(mode, {})
            for addr, node in node_map.items():
                if addr not in records:
                    continue
                current_name = str(node.name).strip()
                if current_name and records[addr].get("name") != current_name:
                    records[addr]["name"] = current_name
                    changed = True

        if changed:
            self._persist_code_records()

    def _load_code_records(self):
        """Load code records from customdata. Called at start() if needed."""
        self._load_code_records_from_custom_data()

    def _load_code_records_from_custom_data(self):
        """Load code records from customdata storage."""
        payload = self.data_store.get(self.code_records_key, {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception as err:
                LOGGER.error("Failed parsing customdata code_records payload: %s", err)
                payload = {}

        self.code_records = self._parse_code_records_payload(payload)

    def _parse_code_records_payload(self, payload):
        """Parse code records from a dict payload."""
        parsed = {"ir": {}, "rf": {}}
        if not isinstance(payload, dict):
            return parsed

        for mode in ("ir", "rf"):
            records = payload.get(mode, []) if isinstance(payload.get(mode), list) else {}
            if isinstance(records, list):
                # Old list format: convert to dict
                for item in records:
                    if not isinstance(item, dict):
                        continue
                    addr = _canonical_address(str(item.get("address", "")).strip().lower())
                    name = str(item.get("name", "")).strip()
                    code = str(item.get("code", "")).strip()
                    if not addr or not name or not code:
                        continue
                    parsed[mode][addr] = {
                        "name": name,
                        "code": code,
                        "source": str(item.get("source", "learned")).strip() or "learned",
                        "source_key": str(item.get("source_key", name)).strip() or name,
                    }
            elif isinstance(records, dict):
                # Dict format
                for addr, record in records.items():
                    if not isinstance(record, dict):
                        continue
                    addr = _canonical_address(str(addr).strip().lower())
                    name = str(record.get("name", "")).strip()
                    code = str(record.get("code", "")).strip()
                    if not addr or not name or not code:
                        continue
                    parsed[mode][addr] = {
                        "name": name,
                        "code": code,
                        "source": str(record.get("source", "learned")).strip() or "learned",
                        "source_key": str(record.get("source_key", name)).strip() or name,
                    }

        return parsed

    def _persist_code_records(self):
        """Persist code records to customdata storage."""
        if not self.custom_data_loaded:
            LOGGER.debug("Skipping code record persistence until customdata has been loaded")
            return

        payload = {"ir": {}, "rf": {}}
        for mode in ("ir", "rf"):
            for addr in sorted(self.code_records.get(mode, {}).keys()):
                record = self.code_records[mode][addr]
                payload[mode][addr] = {
                    "name": record.get("name", ""),
                    "code": record.get("code", ""),
                    "source": record.get("source", "learned"),
                    "source_key": record.get("source_key", record.get("name", "")),
                }

        self.data_store[self.code_records_key] = payload

    def _import_legacy_learned_codes(self):
        """Import learned codes from legacy customdata field if code_records is empty."""
        if self.code_records["ir"] or self.code_records["rf"]:
            return

        if self.learned_ir_codes:
            for name, code in self.learned_ir_codes.items():
                addr = self._find_existing_code_node_address("ir", name) or self._next_code_address("ir")
                self.code_records["ir"][addr] = {
                    "name": name,
                    "code": code,
                    "source": "learned",
                    "source_key": name,
                }

        if self.learned_rf_codes:
            for name, code in self.learned_rf_codes.items():
                addr = self._find_existing_code_node_address("rf", name) or self._next_code_address("rf")
                self.code_records["rf"][addr] = {
                    "name": name,
                    "code": code,
                    "source": "learned",
                    "source_key": name,
                }

        if self.learned_ir_codes or self.learned_rf_codes:
            LOGGER.info("Migrated legacy learned codes from customdata into code_records")
            self._persist_code_records()

    def force_update(self, command=None):
        self.apply_config()

    commands = {
        "UPDATE": force_update,
        "UPDATECODES": update_codes,
        "APSETUP": ap_setup,
    }
