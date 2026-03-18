"""
Node Classes for Broadlink Node Server

Implements:
  - BroadlinkSetup: Controller node (hub representation)
  - BroadlinkIR: IR parent node with learning capability
  - BroadlinkRF: RF parent node with learning capability
  - BroadlinkCode: Subnode for individual learned codes
"""

import udi_interface
import logging
import time
import base64
import json
from threading import Thread

LOGGER = udi_interface.LOGGER

# =====================================================================
# BroadlinkSetup: Controller Node
# =====================================================================
class BroadlinkSetup(udi_interface.Node):
    """
    Primary controller node representing the Broadlink RM4 Pro hub.
    Handles AP provisioning and basic status.
    """
    
    id = 'udi_broadlink'
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 2},  # Status (0=offline, 1=online)
        {'driver': 'HEARTBEAT', 'value': 0, 'uom': 2},  # Heartbeat
    ]
    commands = {
        'APSETUP': set_ap_mode,
        'RESTART': restart,
    }
    
    def __init__(self, polyglot, primary, address, name=None, private=False):
        """
        Initialize the setup controller node.
        
        Args:
            polyglot: UDI interface
            primary: Primary node address
            address: This node's address
            name: Node name
            private: Private node flag
        """
        super().__init__(polyglot, primary, address, name or 'Broadlink Setup', True)
        self.polyglot = polyglot
    
    def set_ap_mode(self, command=None):
        """
        Provision a device in AP mode using broadlink.setup().
        Called by APSETUP command from PG3.
        """
        LOGGER.info('AP provisioning requested.')
        
        try:
            # Get custom parameters
            custom = self.polyglot.customData or {}
            params = getattr(self.polyglot, 'customParams', {})
            
            ssid = params.get('WIFI_SSID', '').strip()
            password = params.get('WIFI_PASSWORD', '').strip()
            security = int(params.get('WIFI_SECURITY_MODE', '4'))
            setup_ip = params.get('SETUP_IP', '255.255.255.255').strip()
            
            if not ssid or not password:
                LOGGER.error('WIFI_SSID or WIFI_PASSWORD not configured.')
                return
            
            import broadlink
            
            LOGGER.info(f'Calling broadlink.setup(ssid={ssid}, security={security}, host={setup_ip})...')
            
            # Call broadlink.setup() - this provisions a device in AP mode
            result = broadlink.setup(
                ssid=ssid,
                password=password,
                security_mode=security,
                host=setup_ip
            )
            
            LOGGER.info(f'AP provisioning result: {result}')
        
        except Exception as e:
            LOGGER.error(f'AP provisioning failed: {e}', exc_info=True)
    
    def restart(self, command=None):
        """
        Restart the hub device.
        """
        LOGGER.info('Restart command received.')
        try:
            # Get the hub device from the node server
            import udibroadlink as ns_module
            ns = getattr(ns_module, 'ns', None)
            if ns and hasattr(ns, 'get_hub_device'):
                hub = ns.get_hub_device()
                if hub:
                    # Attempt to restart the hub
                    try:
                        # Most broadlink devices don't support restart directly
                        # This is a placeholder for future expansion
                        LOGGER.info('Hub restart requested (may not be supported).')
                    except Exception as e:
                        LOGGER.error(f'Hub restart failed: {e}')
        except Exception as e:
            LOGGER.error(f'Exception in restart: {e}', exc_info=True)


# =====================================================================
# BroadlinkIR: IR Parent Node
# =====================================================================
class BroadlinkIR(udi_interface.Node):
    """
    IR control parent node. Allows learning and managing IR codes.
    """
    
    id = 'broadlink_ir'
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 2},  # Status
        {'driver': 'GV0', 'value': 0, 'uom': 25},  # Learning progress (0-100%)
    ]
    commands = {
        'LEARNCODE': learn_code,
    }
    
    def __init__(self, polyglot, primary, address, name=None, private=False):
        """
        Initialize the IR parent node.
        """
        super().__init__(polyglot, primary, address, name or 'Broadlink IR', False)
        self.polyglot = polyglot
        self.learning = False
    
    def learn_code(self, command=None):
        """
        Learn a new IR code from the hub.
        Runs in a background thread to avoid blocking.
        """
        LOGGER.info('IR learn code initiated.')
        
        if self.learning:
            LOGGER.warning('Already learning, ignoring.')
            return
        
        # Start learning in background thread
        thread = Thread(target=self._learn_code_thread, daemon=True)
        thread.start()
    
    def _learn_code_thread(self):
        """
        Background thread for IR learning.
        Updates GV0 (learning progress) driver.
        """
        try:
            self.learning = True
            self.setDriver('GV0', 0)  # Progress 0%
            
            # Get hub device from node server
            import udibroadlink
            ns = udibroadlink.BroadlinkNodeServer
            hub = None
            
            # Try to get from global (this is set during node server init)
            try:
                hub = ns.hub_device if hasattr(ns, 'hub_device') else None
            except:
                pass
            
            if not hub:
                LOGGER.error('Hub device not available for learning.')
                self.setDriver('GV0', 0)
                self.learning = False
                return
            
            LOGGER.info('Entering IR learning mode...')
            self.setDriver('GV0', 10)
            
            # Call enter_learning
            try:
                result = hub.enter_learning()
                LOGGER.debug(f'enter_learning result: {result}')
            except Exception as e:
                LOGGER.error(f'enter_learning failed: {e}')
                self.setDriver('GV0', 0)
                self.learning = False
                return
            
            # Wait for code (up to 30 seconds)
            self.setDriver('GV0', 50)
            start_time = time.time()
            timeout = 30
            learned_code = None
            
            while time.time() - start_time < timeout:
                try:
                    data = hub.check_data()
                    if data:
                        learned_code = data
                        LOGGER.info(f'IR code learned: {len(data)} bytes')
                        break
                except Exception as e:
                    LOGGER.debug(f'check_data error (may be normal): {e}')
                
                self.setDriver('GV0', 50 + int(30 * (time.time() - start_time) / timeout))
                time.sleep(0.5)
            
            if not learned_code:
                LOGGER.warning('No IR code received within timeout.')
                self.setDriver('GV0', 0)
                self.learning = False
                return
            
            # Encode as hex
            code_hex = learned_code.hex()
            LOGGER.debug(f'Learned IR code (hex): {code_hex[:80]}...')
            
            # Generate code name
            code_name = f'Learned IR {int(time.time()) % 1000}'
            
            # Add to node server and persist
            self.setDriver('GV0', 100)
            
            # Get reference to node server and add the learned code
            try:
                # Import the main module to access the node server instance
                from udibroadlink import BroadlinkNodeServer
                # This will be available after start
                polyglot = self.polyglot
                if hasattr(polyglot, 'nodes'):
                    for addr, node in polyglot.nodes.items():
                        if isinstance(node, BroadlinkNodeServer):
                            node.add_learned_code('ir', code_name, code_hex)
                            break
            except Exception as e:
                LOGGER.error(f'Failed to add learned code to node server: {e}', exc_info=True)
            
            time.sleep(2)
            self.setDriver('GV0', 0)
            self.learning = False
        
        except Exception as e:
            LOGGER.error(f'Exception in IR learning thread: {e}', exc_info=True)
            self.setDriver('GV0', 0)
            self.learning = False
    
    


# =====================================================================
# BroadlinkRF: RF Parent Node
# =====================================================================
class BroadlinkRF(udi_interface.Node):
    """
    RF control parent node. Allows learning and managing RF codes.
    Implements 2-step RF learning: sweep frequency, then learn.
    """
    
    id = 'broadlink_rf'
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 2},  # Status
        {'driver': 'GV0', 'value': 0, 'uom': 25},  # Learning progress (0-100%)
    ]
    commands = {
        'LEARNCODE': learn_code,
    }
    
    def __init__(self, polyglot, primary, address, name=None, private=False):
        """
        Initialize the RF parent node.
        """
        super().__init__(polyglot, primary, address, name or 'Broadlink RF', False)
        self.polyglot = polyglot
        self.learning = False
    
    def learn_code(self, command=None):
        """
        Learn a new RF code from the hub.
        Implements 2-step: sweep frequency, then learn.
        Runs in background thread.
        """
        LOGGER.info('RF learn code initiated.')
        
        if self.learning:
            LOGGER.warning('Already learning, ignoring.')
            return
        
        thread = Thread(target=self._learn_code_thread, daemon=True)
        thread.start()
    
    def _learn_code_thread(self):
        """
        Background thread for RF learning (2-step process).
        """
        try:
            self.learning = True
            self.setDriver('GV0', 0)
            
            # Get hub device
            import udibroadlink
            ns = udibroadlink.BroadlinkNodeServer
            hub = None
            
            try:
                hub = ns.hub_device if hasattr(ns, 'hub_device') else None
            except:
                pass
            
            if not hub:
                LOGGER.error('Hub device not available for RF learning.')
                self.setDriver('GV0', 0)
                self.learning = False
                return
            
            # Step 1: Sweep frequency
            LOGGER.info('RF Learning Step 1: Sweeping frequency...')
            self.setDriver('GV0', 10)
            
            try:
                result = hub.sweep_frequency()
                LOGGER.debug(f'sweep_frequency result: {result}')
            except Exception as e:
                LOGGER.error(f'sweep_frequency failed: {e}')
                self.setDriver('GV0', 0)
                self.learning = False
                return
            
            # Wait 2 seconds between frequency sweep and packet capture (as per requirements)
            LOGGER.info('Waiting 2 seconds between sweep and learn...')
            self.setDriver('GV0', 25)
            time.sleep(2)
            
            # Step 2: Learn the code
            LOGGER.info('RF Learning Step 2: Learning code...')
            self.setDriver('GV0', 40)
            
            try:
                result = hub.check_frequency()
                LOGGER.debug(f'check_frequency result: {result}')
            except Exception as e:
                LOGGER.error(f'check_frequency failed: {e}')
                self.setDriver('GV0', 0)
                self.learning = False
                return
            
            # Wait for RF code (up to 20 seconds)
            self.setDriver('GV0', 50)
            start_time = time.time()
            timeout = 20
            learned_code = None
            
            while time.time() - start_time < timeout:
                try:
                    data = hub.check_data()
                    if data:
                        learned_code = data
                        LOGGER.info(f'RF code learned: {len(data)} bytes')
                        break
                except Exception as e:
                    LOGGER.debug(f'check_data error (may be normal): {e}')
                
                self.setDriver('GV0', 50 + int(35 * (time.time() - start_time) / timeout))
                time.sleep(0.5)
            
            if not learned_code:
                LOGGER.warning('No RF code received within timeout.')
                self.setDriver('GV0', 0)
                self.learning = False
                return
            
            # Encode as hex
            code_hex = learned_code.hex()
            LOGGER.debug(f'Learned RF code (hex): {code_hex[:80]}...')
            
            # Generate code name
            code_name = f'Learned RF {int(time.time()) % 1000}'
            
            # Add to node server
            self.setDriver('GV0', 100)
            
            try:
                from udibroadlink import BroadlinkNodeServer
                polyglot = self.polyglot
                if hasattr(polyglot, 'nodes'):
                    for addr, node in polyglot.nodes.items():
                        if isinstance(node, BroadlinkNodeServer):
                            node.add_learned_code('rf', code_name, code_hex)
                            break
            except Exception as e:
                LOGGER.error(f'Failed to add learned RF code: {e}', exc_info=True)
            
            time.sleep(2)
            self.setDriver('GV0', 0)
            self.learning = False
        
        except Exception as e:
            LOGGER.error(f'Exception in RF learning thread: {e}', exc_info=True)
            self.setDriver('GV0', 0)
            self.learning = False
    
    


# =====================================================================
# BroadlinkCode: Code Subnode
# =====================================================================
class BroadlinkCode(udi_interface.Node):
    """
    Subnode representing a single learned or configured code (IR or RF).
    Supports transmission with TXCODE command.
    """
    
    id = 'broadlink_code'
    drivers = [
        {'driver': 'ST', 'value': 0, 'uom': 2},  # Status
    ]
    commands = {
        'TXCODE': send_code,
    }
    
    def __init__(self, polyglot, primary, address, parent, name, code_value, code_type):
        """
        Initialize a code subnode.
        
        Args:
            polyglot: UDI interface
            primary: Primary node address
            address: This node's address
            parent: Parent node address
            name: Code display name
            code_value: The learned code (hex or b64)
            code_type: 'ir' or 'rf'
        """
        super().__init__(polyglot, primary, address, name or 'Code', False, parent)
        self.polyglot = polyglot
        self.code_value = code_value
        self.code_type = code_type
    
    def send_code(self, command=None):
        """
        Transmit the learned code via the hub.
        """
        LOGGER.info(f'Sending {self.code_type.upper()} code: {self.name}')
        
        try:
            # Parse code value (hex or b64)
            if self.code_value.startswith('b64:'):
                code_bytes = base64.b64decode(self.code_value[4:])
            else:
                code_bytes = bytes.fromhex(self.code_value)
            
            # Get hub device
            import udibroadlink
            ns = udibroadlink.BroadlinkNodeServer
            hub = None
            
            try:
                hub = ns.hub_device if hasattr(ns, 'hub_device') else None
            except:
                pass
            
            if not hub:
                LOGGER.error('Hub device not available for transmission.')
                return
            
            # Send code
            try:
                result = hub.send_data(code_bytes)
                LOGGER.info(f'Code transmitted successfully. Result: {result}')
                self.setDriver('ST', 1)
                time.sleep(0.5)
                self.setDriver('ST', 0)
            except Exception as e:
                LOGGER.error(f'Failed to send code: {e}', exc_info=True)
        
        except Exception as e:
            LOGGER.error(f'Exception in send_code: {e}', exc_info=True)


# =====================================================================
# Command Handler Stubs (Called by udi_interface)
# =====================================================================

def set_ap_mode(self, command=None):
    """Stub for AP mode command."""
    if hasattr(self, 'set_ap_mode'):
        self.set_ap_mode(command)

def restart(self, command=None):
    """Stub for restart command."""
    if hasattr(self, 'restart'):
        self.restart(command)

def learn_code(self, command=None):
    """Stub for learn code command."""
    if hasattr(self, 'learn_code'):
        self.learn_code(command)

def send_code(self, command=None):
    """Stub for send code command."""
    if hasattr(self, 'send_code'):
        self.send_code(command)


