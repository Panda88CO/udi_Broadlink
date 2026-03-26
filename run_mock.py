"""Run a DeviceManager using the mock Broadlink client and a fake udi_interface.

This script injects a minimal `udi_interface` shim into `sys.modules` so the
existing node classes and DeviceManager can be imported without the real
Polyglot environment. It then exercises learn/send flows using the mock client.
"""
import sys
import types
import time

# Minimal udi_interface shim
udi = types.SimpleNamespace()

class SimpleLogger:
    def info(self, *a, **k):
        print("INFO:", *a)
    def debug(self, *a, **k):
        print("DEBUG:", *a)
    def error(self, *a, **k):
        print("ERROR:", *a)

class Custom(dict):
    def __init__(self, poly, name):
        super().__init__()
    def load(self, data):
        self.clear()
        if data:
            self.update(data)

class Node:
    def __init__(self, poly, primary, address, name):
        self.poly = poly
        self.primary = primary
        self.address = address
        self.name = name
        self.drivers = {}
    def setDriver(self, driver, value, report=True, force=False, uom=None):
        self.drivers[driver] = value
    def rename(self, new_name):
        print(f"Renamed node {self.address} -> {new_name}")
        self.name = new_name
    def reportCmd(self, cmd, val):
        print(f"reportCmd: {cmd} {val}")

udi.LOGGER = SimpleLogger()
udi.Custom = Custom
udi.Node = Node
udi_interface = types.ModuleType("udi_interface")
udi_interface.LOGGER = SimpleLogger()
udi_interface.Custom = Custom
udi_interface.Node = Node
udi_interface.Interface = None
udi_interface.START = "start"
udi_interface.STOP = "stop"
udi_interface.POLL = "poll"
udi_interface.CUSTOMPARAMS = "customparams"
udi_interface.CUSTOMDATA = "customdata"
udi_interface.LOGLEVEL = "loglevel"
udi_interface.DISCOVER = "discover"

sys.modules["udi_interface"] = udi_interface

from device_manager import DeviceManager
import broadlink_client_mock as mock


class FakePoly:
    def __init__(self):
        self._nodes = {}
        self.Notices = {}
    def subscribe(self, ev, fn, *args, **kwargs):
        pass
    def updateProfile(self):
        pass
    def ready(self):
        pass
    def addNode(self, node, rename=False, conn_status=None):
        print(f"Adding node: {node.address} name={node.name}")
        self._nodes[node.address] = node
    def delNode(self, addr):
        print(f"Deleting node: {addr}")
        self._nodes.pop(addr, None)
    def getValidAddress(self, base):
        return base
    def getValidName(self, name):
        return name
    def getNodes(self):
        return dict(self._nodes)


def main():
    poly = FakePoly()
    dm = DeviceManager(poly)

    # Use mock client
    dm.client = mock.BroadlinkHubClient()
    dm.client.connect()

    print("Client connected?", dm.is_connected())

    print("Reconciling nodes (initial)")
    dm._reconcile_nodes()

    print("Learning an IR code using mock")
    name, val = dm.learn_code("ir")
    print("Learned:", name, val[:16])

    print("Reconciling nodes (after learn)")
    dm._reconcile_nodes()

    # Send the learned code
    print("Sending learned code")
    dm.send_configured_code("ir", name)

    print("Final nodes:")
    for addr, node in poly.getNodes().items():
        print(" -", addr, node.name)


if __name__ == "__main__":
    main()
