"""Node classes for Broadlink PG3 plugin."""

from __future__ import annotations

import time
from typing import Dict

import udi_interface

LOGGER = udi_interface.LOGGER


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

