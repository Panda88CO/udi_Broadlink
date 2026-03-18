#!/usr/bin/env python3
"""
Broadlink Node Server for UDI Polyglot v3 (PG3)
Integrates Broadlink RM4 Pro devices for IR/RF learning and transmission.

Architecture:
  - Controller Node (setup): Hub representation
  - Service Nodes (ir, rf): Parent nodes for IR and RF control
  - Dynamic Sub-nodes: Learned codes under respective parents
"""

import udi_interface
import logging
import time
import json
import base64
from nodes import BroadlinkSetup, BroadlinkIR, BroadlinkRF, BroadlinkCode

# =====================================================================
# Logger Configuration
# =====================================================================
LOGGER = udi_interface.LOGGER
LOGGER.setLevel(logging.DEBUG)

# =====================================================================
# Node Server Class
# =====================================================================
class BroadlinkNodeServer(udi_interface.Node):
    """
    Main Node Server controller. Initializes all nodes and manages lifecycle.
    """
    
    def __init__(self, polyglot):
        """
        Initialize the node server.
        
        Args:
            polyglot: UDI interface polyglot object
        """
        super().__init__(polyglot, 'udi_broadlink', 'udi_broadlink', True, 'udi_broadlink')
        
        self.polyglot = polyglot
        self.ready = False
        self.hub_device = None
        self.ir_parent = None
        self.rf_parent = None
        self.code_nodes = {}  # {node_address: node_object}
        
        # Handler bindings
        self.polyglot.onConfig(self.handle_config)
        self.polyglot.onStop(self.handle_stop)
        self.polyglot.onStart(self.handle_start)
        self.polyglot.onDelete(self.handle_delete)
        self.polyglot.onPoll(self.poll)
        
        # Event handlers
        self.polyglot.onEvent('ADDNODEDONE', self.on_add_node_done)
        self.polyglot.onEvent('ST', self.on_status_update)
        
        LOGGER.info('BroadlinkNodeServer initialized.')
    
    def handle_config(self, config):
        """
        Handle configuration changes from PG3.
        
        Args:
            config: Configuration dictionary
        """
        LOGGER.info('Configuration received.')
        
        # Extract custom parameters
        self.custom_params = config.get('customParams', {})
        LOGGER.debug(f'Custom params: {list(self.custom_params.keys())}')
    
    def handle_start(self):
        """
        Called when the node server starts. Initialize discovery and nodes.
        """
        LOGGER.info('Node server starting...')
        
        # Set ready flag to False until nodes are fully initialized
        self.ready = False
        
        # Discover and authenticate to Broadlink hub
        if not self._discover_and_auth():
            LOGGER.error('Failed to discover/authenticate hub. Posting notice and continuing.')
            self.polyglot.Notices['hub_not_found'] = (
                'Broadlink hub not found. Check HUB_IP in configuration.'
            )
        
        # Create parent nodes if they don't exist
        self._ensure_parent_nodes()
        
        # Build code subnodes from configured parameters
        self._build_code_nodes()
        
        LOGGER.info('Node server startup sequence complete.')
    
    def handle_stop(self):
        """
        Called when the node server stops. Clean up resources.
        """
        LOGGER.info('Node server stopping.')
        self.ready = False
        self.hub_device = None
    
    def handle_delete(self):
        """
        Called when a node is deleted.
        """
        LOGGER.info('Delete event received.')
    
    def on_add_node_done(self, event, *args, **kwargs):
        """
        Handle ADDNODEDONE event. Called when all nodes have been added/synced.
        This is the correct point to set ready=True and update drivers.
        """
        LOGGER.info('ADDNODEDONE event received. Nodes fully registered.')
        self.ready = True
        
        # Now safe to update drivers
        self.setDriver('ST', 1, force=True)
        LOGGER.info('Node server ready flag set to True.')
    
    def on_status_update(self, event, *args, **kwargs):
        """
        Handle status update event.
        """
        LOGGER.debug(f'Status update event: {event}')
    
    def _discover_and_auth(self):
        """
        Discover Broadlink hub and authenticate.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            hub_ip = self.custom_params.get('HUB_IP', '').strip()
            if not hub_ip:
                LOGGER.error('HUB_IP not configured.')
                return False
            
            # Import broadlink here to allow graceful failures
            import broadlink
            
            LOGGER.info(f'Attempting to discover hub at {hub_ip}...')
            
            # Direct discovery by IP
            try:
                self.hub_device = broadlink.rm4pro((hub_ip, 80), None, None, allow_errors=False)
                self.hub_device.timeout = 5  # Explicit 5-second timeout
            except Exception as e:
                LOGGER.error(f'Failed to connect to hub at {hub_ip}: {e}')
                return False
            
            # Attempt authentication
            try:
                if not self.hub_device.auth():
                    LOGGER.error('Authentication failed for hub.')
                    return False
            except Exception as e:
                LOGGER.error(f'Auth error: {e}')
                return False
            
            LOGGER.info('Hub authenticated successfully.')
            return True
            
        except Exception as e:
            LOGGER.error(f'Exception during discovery: {e}', exc_info=True)
            return False
    
    def _ensure_parent_nodes(self):
        """
        Create IR and RF parent nodes if they don't exist.
        """
        try:
            # Check if IR parent exists
            ir_address = 'ir'
            if ir_address not in self.polyglot.nodes:
                LOGGER.info('Creating IR parent node...')
                self.ir_parent = BroadlinkIR(self.polyglot, 'udi_broadlink', ir_address)
                self.polyglot.addNode(self.ir_parent)
            else:
                self.ir_parent = self.polyglot.nodes[ir_address]
            
            # Check if RF parent exists
            rf_address = 'rf'
            if rf_address not in self.polyglot.nodes:
                LOGGER.info('Creating RF parent node...')
                self.rf_parent = BroadlinkRF(self.polyglot, 'udi_broadlink', rf_address)
                self.polyglot.addNode(self.rf_parent)
            else:
                self.rf_parent = self.polyglot.nodes[rf_address]
            
            LOGGER.info('Parent nodes verified/created.')
        
        except Exception as e:
            LOGGER.error(f'Exception while creating parent nodes: {e}', exc_info=True)
    
    def _build_code_nodes(self):
        """
        Build dynamic subnodes from IR_CODES and RF_CODES parameters.
        Loads from both params and persistent customData.
        """
        try:
            # Parse IR codes
            ir_codes = self._parse_code_param('IR_CODES')
            for code_name, code_value in ir_codes.items():
                self._create_or_update_code_node('ir', code_name, code_value)
            
            # Parse RF codes
            rf_codes = self._parse_code_param('RF_CODES')
            for code_name, code_value in rf_codes.items():
                self._create_or_update_code_node('rf', code_name, code_value)
            
            LOGGER.info(f'Built {len(self.code_nodes)} code subnodes.')
        
        except Exception as e:
            LOGGER.error(f'Exception while building code nodes: {e}', exc_info=True)
    
    def _parse_code_param(self, param_name):
        """
        Parse IR_CODES or RF_CODES from custom parameters.
        Supports both JSON and key=value formats.
        
        Returns:
            dict: {code_name: code_value}
        """
        param_value = self.custom_params.get(param_name, '').strip()
        if not param_value:
            return {}
        
        # Try JSON first
        if param_value.startswith('{'):
            try:
                return json.loads(param_value)
            except json.JSONDecodeError:
                LOGGER.warning(f'Failed to parse {param_name} as JSON.')
                return {}
        
        # Try key=value format
        codes = {}
        for line in param_value.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                codes[key.strip()] = val.strip()
        
        return codes
    
    def _create_or_update_code_node(self, parent_type, code_name, code_value):
        """
        Create or update a code subnode under IR or RF parent.
        
        Args:
            parent_type: 'ir' or 'rf'
            code_name: Display name for the code
            code_value: The learned code (hex or b64)
        """
        try:
            # Generate address (sanitize code name)
            addr_base = code_name.lower().replace(' ', '_').replace('-', '_')
            addr = f'{parent_type}_{addr_base}'
            
            if addr in self.polyglot.nodes:
                # Update existing node
                node = self.polyglot.nodes[addr]
                node.name = code_name
                LOGGER.debug(f'Updated code node: {addr}')
            else:
                # Create new node
                parent = self.ir_parent if parent_type == 'ir' else self.rf_parent
                node = BroadlinkCode(
                    self.polyglot,
                    'udi_broadlink',
                    addr,
                    parent.address,
                    code_name,
                    code_value,
                    parent_type
                )
                self.polyglot.addNode(node)
                self.code_nodes[addr] = node
                LOGGER.info(f'Created code node: {addr} ({code_name})')
        
        except Exception as e:
            LOGGER.error(f'Exception creating/updating code node {code_name}: {e}', exc_info=True)
    
    def poll(self, polltype):
        """
        Handle short and long polls.
        
        Args:
            polltype: 'short' or 'long'
        """
        if polltype == 'short':
            self._short_poll()
        elif polltype == 'long':
            self._long_poll()
    
    def _short_poll(self):
        """
        Short poll: Heartbeat and basic status.
        """
        try:
            if not self.ready:
                return
            
            # Toggle heartbeat driver
            current_st = self.getDriver('ST')
            new_st = 0 if current_st == 1 else 1
            self.setDriver('ST', new_st)
            
        except Exception as e:
            LOGGER.error(f'Exception in short poll: {e}', exc_info=True)
    
    def _long_poll(self):
        """
        Long poll: Refresh hub connectivity, sync node renames, verify learned codes.
        """
        try:
            if not self.ready:
                return
            
            # Re-check hub connectivity
            if self.hub_device:
                try:
                    if self.hub_device.auth():
                        LOGGER.debug('Hub auth check passed.')
                    else:
                        LOGGER.warning('Hub auth check failed.')
                except Exception as e:
                    LOGGER.warning(f'Hub connectivity check failed: {e}')
            
            # Sync node renames: check if any code nodes were renamed in UI
            self._sync_node_renames()
            
        except Exception as e:
            LOGGER.error(f'Exception in long poll: {e}', exc_info=True)
    
    def _sync_node_renames(self):
        """
        Check if code subnodes were renamed in the admin UI.
        Update customData if names changed.
        This is called during longPoll to catch user-initiated renames.
        """
        try:
            # Load current customData
            custom_data = self.polyglot.customData or {}
            updated = False
            
            # Check IR and RF code nodes
            for code_addr, code_node in self.code_nodes.items():
                old_name = custom_data.get(f'{code_addr}_name', code_node.name)
                # The node's name property reflects the current ISY/IoX name
                if code_node.name != old_name:
                    LOGGER.info(f'Detected rename: {code_addr} from "{old_name}" to "{code_node.name}"')
                    custom_data[f'{code_addr}_name'] = code_node.name
                    updated = True
            
            if updated:
                self.polyglot.customData = custom_data
                self.polyglot.saveCustomData(custom_data)
                LOGGER.info('Synced node renames to customData.')
        
        except Exception as e:
            LOGGER.error(f'Exception syncing node renames: {e}', exc_info=True)
    
    def get_hub_device(self):
        """
        Get the authenticated hub device for use by child nodes.
        
        Returns:
            broadlink device or None
        """
        return self.hub_device
    
    def add_learned_code(self, parent_type, code_name, code_value):
        """
        Add a newly learned code to the node tree and persist it.
        
        Args:
            parent_type: 'ir' or 'rf'
            code_name: Display name
            code_value: Learned code (hex or b64)
        """
        try:
            # Store in customData for persistence
            custom_data = self.polyglot.customData or {}
            key = f'learned_{parent_type}_{int(time.time())}'
            custom_data[key] = json.dumps({
                'name': code_name,
                'code': code_value,
                'type': parent_type,
                'timestamp': time.time()
            })
            self.polyglot.customData = custom_data
            self.polyglot.saveCustomData(custom_data)
            
            # Create the corresponding subnode
            self._create_or_update_code_node(parent_type, code_name, code_value)
            
            LOGGER.info(f'Added learned {parent_type.upper()} code: {code_name}')
        
        except Exception as e:
            LOGGER.error(f'Exception adding learned code: {e}', exc_info=True)


# =====================================================================
# Entry Point
# =====================================================================
if __name__ == '__main__':
    try:
        polyglot = udi_interface.Interface([BroadlinkSetup, BroadlinkIR, BroadlinkRF, BroadlinkCode])
        polyglot.start()
        
        # Get the node server instance
        ns = polyglot.nodes['udi_broadlink']
        
        # Keep the process alive
        while True:
            time.sleep(1)
    
    except Exception as e:
        LOGGER.error(f'Fatal error in main: {e}', exc_info=True)
        exit(1)
