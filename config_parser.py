"""
Configuration Parser for Broadlink Node Server

Handles parsing and validation of custom parameters from PG3.
Supports both JSON and key=value formats for code parameters.
"""

import logging
import json

LOGGER = logging.getLogger(__name__)


class ConfigParser:
    """
    Parse and validate PG3 custom parameters.
    """
    
    @staticmethod
    def parse_custom_params(config_dict):
        """
        Extract and validate custom parameters from config.
        
        Args:
            config_dict: Dictionary from PG3 config
            
        Returns:
            dict: Parsed parameters with defaults
        """
        params = config_dict.get('customParams', {})
        
        return {
            'user_id': params.get('USER_ID', '').strip(),
            'user_password': params.get('USER_PASSWORD', '').strip(),
            'hub_ip': params.get('HUB_IP', '').strip(),
            'wifi_ssid': params.get('WIFI_SSID', '').strip(),
            'wifi_password': params.get('WIFI_PASSWORD', '').strip(),
            'wifi_security': int(params.get('WIFI_SECURITY_MODE', '4')),
            'setup_ip': params.get('SETUP_IP', '255.255.255.255').strip(),
            'ir_codes': params.get('IR_CODES', ''),
            'rf_codes': params.get('RF_CODES', ''),
        }
    
    @staticmethod
    def validate_hub_config(params):
        """
        Validate that required hub parameters are present.
        
        Args:
            params: Parsed params from parse_custom_params
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not params['hub_ip']:
            return False, 'HUB_IP is required.'
        
        # Validate IP format (basic)
        ip_parts = params['hub_ip'].split('.')
        if len(ip_parts) != 4:
            return False, f'Invalid HUB_IP format: {params["hub_ip"]}'
        
        try:
            for part in ip_parts:
                num = int(part)
                if num < 0 or num > 255:
                    raise ValueError()
        except (ValueError, AttributeError):
            return False, f'Invalid HUB_IP format: {params["hub_ip"]}'
        
        return True, None
    
    @staticmethod
    def validate_ap_config(params):
        """
        Validate AP provisioning parameters.
        
        Args:
            params: Parsed params
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not params['wifi_ssid'] or not params['wifi_password']:
            return False, 'WIFI_SSID and WIFI_PASSWORD required for AP provisioning.'
        
        if params['wifi_security'] < 0 or params['wifi_security'] > 4:
            return False, f'Invalid WIFI_SECURITY_MODE: {params["wifi_security"]}'
        
        return True, None
    
    @staticmethod
    def parse_code_dict(code_str):
        """
        Parse IR_CODES or RF_CODES parameter.
        Supports both JSON and key=value formats.
        
        Args:
            code_str: Raw code parameter string
            
        Returns:
            dict: {code_name: code_value}
        """
        if not code_str or not code_str.strip():
            return {}
        
        code_str = code_str.strip()
        
        # Try JSON first
        if code_str.startswith('{'):
            try:
                return json.loads(code_str)
            except json.JSONDecodeError as e:
                LOGGER.warning(f'Failed to parse as JSON: {e}')
                return {}
        
        # Try key=value format
        codes = {}
        for line in code_str.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if '=' not in line:
                LOGGER.warning(f'Skipping malformed line: {line}')
                continue
            
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip()
            
            if key and val:
                codes[key] = val
        
        return codes
    
    @staticmethod
    def validate_code_value(code_value):
        """
        Validate that a code value is valid hex or base64.
        
        Args:
            code_value: Code to validate
            
        Returns:
            tuple: (is_valid, normalized_value, error_message)
        """
        if not code_value or not code_value.strip():
            return False, None, 'Code value is empty.'
        
        code_value = code_value.strip()
        
        # Check for base64 prefix
        if code_value.startswith('b64:'):
            try:
                import base64
                base64.b64decode(code_value[4:])
                return True, code_value, None
            except Exception as e:
                return False, None, f'Invalid base64 encoding: {e}'
        
        # Try hex
        try:
            bytes.fromhex(code_value)
            return True, code_value, None
        except ValueError as e:
            return False, None, f'Invalid hex encoding: {e}'
    
    @staticmethod
    def sanitize_node_address(name):
        """
        Sanitize a code name into a valid node address.
        
        Args:
            name: Code name
            
        Returns:
            str: Sanitized address
        """
        # Convert to lowercase, replace spaces/hyphens with underscores
        addr = name.lower().replace(' ', '_').replace('-', '_')
        # Remove any non-alphanumeric except underscore
        addr = ''.join(c for c in addr if c.isalnum() or c == '_')
        # Ensure not too long
        addr = addr[:20]
        return addr if addr else 'code'


class CodeStore:
    """
    Persistent storage for learned codes in customData.
    """
    
    LEARNED_CODE_PREFIX = 'learned_'
    CODE_NAME_SUFFIX = '_name'
    CODE_VALUE_SUFFIX = '_value'
    CODE_TYPE_SUFFIX = '_type'
    CODE_TIMESTAMP_SUFFIX = '_ts'
    
    @staticmethod
    def store_learned_code(custom_data, code_type, code_name, code_value):
        """
        Store a newly learned code in customData.
        
        Args:
            custom_data: Polyglot customData dict
            code_type: 'ir' or 'rf'
            code_name: Display name
            code_value: Code value (hex or b64)
            
        Returns:
            dict: Updated customData
        """
        if custom_data is None:
            custom_data = {}
        
        # Generate unique key
        timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
        key_base = f'{CodeStore.LEARNED_CODE_PREFIX}{code_type}_{timestamp}'
        
        # Store code details
        custom_data[f'{key_base}{CodeStore.CODE_NAME_SUFFIX}'] = code_name
        custom_data[f'{key_base}{CodeStore.CODE_VALUE_SUFFIX}'] = code_value
        custom_data[f'{key_base}{CodeStore.CODE_TYPE_SUFFIX}'] = code_type
        custom_data[f'{key_base}{CodeStore.CODE_TIMESTAMP_SUFFIX}'] = timestamp
        
        LOGGER.info(f'Stored learned {code_type} code: {code_name}')
        return custom_data
    
    @staticmethod
    def get_learned_codes(custom_data, code_type=None):
        """
        Retrieve learned codes from customData.
        
        Args:
            custom_data: Polyglot customData dict
            code_type: Filter by 'ir' or 'rf' (None for all)
            
        Returns:
            list: [{'name': ..., 'value': ..., 'type': ...}, ...]
        """
        if not custom_data:
            return []
        
        codes = []
        key_bases = set()
        
        # Find all code entries
        for key in custom_data.keys():
            if CodeStore.LEARNED_CODE_PREFIX in key:
                # Extract base key
                for suffix in [CodeStore.CODE_NAME_SUFFIX, CodeStore.CODE_VALUE_SUFFIX,
                              CodeStore.CODE_TYPE_SUFFIX, CodeStore.CODE_TIMESTAMP_SUFFIX]:
                    if key.endswith(suffix):
                        base = key[:-len(suffix)]
                        key_bases.add(base)
                        break
        
        # Build code objects
        for base in key_bases:
            code_type_str = custom_data.get(f'{base}{CodeStore.CODE_TYPE_SUFFIX}')
            
            if code_type and code_type_str != code_type:
                continue
            
            code_obj = {
                'name': custom_data.get(f'{base}{CodeStore.CODE_NAME_SUFFIX}'),
                'value': custom_data.get(f'{base}{CodeStore.CODE_VALUE_SUFFIX}'),
                'type': code_type_str,
                'timestamp': custom_data.get(f'{base}{CodeStore.CODE_TIMESTAMP_SUFFIX}'),
            }
            
            if code_obj['name'] and code_obj['value']:
                codes.append(code_obj)
        
        return codes
    
    @staticmethod
    def delete_learned_code(custom_data, code_name):
        """
        Delete a learned code from customData.
        
        Args:
            custom_data: Polyglot customData dict
            code_name: Code name to delete
            
        Returns:
            dict: Updated customData
        """
        if not custom_data:
            return custom_data
        
        keys_to_delete = []
        for key in custom_data.keys():
            if key.endswith(CodeStore.CODE_NAME_SUFFIX):
                if custom_data[key] == code_name:
                    base = key[:-len(CodeStore.CODE_NAME_SUFFIX)]
                    # Mark all related keys for deletion
                    for suffix in [CodeStore.CODE_NAME_SUFFIX, CodeStore.CODE_VALUE_SUFFIX,
                                  CodeStore.CODE_TYPE_SUFFIX, CodeStore.CODE_TIMESTAMP_SUFFIX]:
                        keys_to_delete.append(f'{base}{suffix}')
        
        for key in keys_to_delete:
            custom_data.pop(key, None)
        
        LOGGER.info(f'Deleted learned code: {code_name}')
        return custom_data


import time
