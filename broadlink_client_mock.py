import time
import random

class BroadlinkHubClient:
    def __init__(self, hub_ip=None, user_id=None, user_password=None):
        self.hub_ip = hub_ip
        self.user_id = user_id
        self.user_password = user_password
        self.connected = False

    def connect(self):
        # Simulate connect delay
        time.sleep(0.1)
        self.connected = True

    def refresh(self):
        # Randomly simulate online/ offline
        return True if self.connected else False

    def learn_ir(self, timeout=30):
        # Return a pseudo-random packet bytes
        time.sleep(0.1)
        return bytes([random.randint(0, 255) for _ in range(16)])

    def learn_rf(self, timeout=30):
        time.sleep(0.1)
        return bytes([random.randint(0, 255) for _ in range(12)])

    def send_code(self, packet_hex: str):
        # Accept either hex string or bytes
        time.sleep(0.05)
        return True

    def provision_ap(self, ssid, password, security_mode=None, setup_ip=None):
        time.sleep(0.1)
        return True
