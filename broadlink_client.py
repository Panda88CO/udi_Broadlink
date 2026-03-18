"""
Broadlink Client Wrapper

Provides a high-level interface to the python-broadlink library with:
- Automatic timeout management
- Robust error handling
- Comprehensive logging of all Broadlink traffic
"""

import logging
import time
import socket

LOGGER = logging.getLogger(__name__)


class BroadlinkClient:
    """
    Wrapper around python-broadlink API.
    Handles device discovery, authentication, and control operations.
    """
    
    DEFAULT_TIMEOUT = 5  # seconds
    DEFAULT_PORT = 80
    
    def __init__(self, hub_ip, timeout=None):
        """
        Initialize Broadlink client.
        
        Args:
            hub_ip: IP address of Broadlink hub
            timeout: Network timeout in seconds (default: 5)
        """
        self.hub_ip = hub_ip
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.device = None
        self.authenticated = False
        
        LOGGER.info(f'BroadlinkClient initialized for {hub_ip} (timeout={self.timeout}s)')
    
    def discover(self):
        """
        Discover and connect to the Broadlink hub.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import broadlink
            
            LOGGER.info(f'Attempting to discover Broadlink hub at {self.hub_ip}...')
            
            # Direct connection by IP
            try:
                self.device = broadlink.rm4pro(
                    (self.hub_ip, self.DEFAULT_PORT),
                    None,  # mac
                    None,  # devtype
                    allow_errors=False
                )
                self.device.timeout = self.timeout
                LOGGER.debug(f'Device object created: {self.device}')
            except Exception as e:
                LOGGER.error(f'Failed to create device object for {self.hub_ip}: {e}')
                return False
            
            # Authenticate
            if not self.authenticate():
                LOGGER.error('Authentication failed.')
                return False
            
            LOGGER.info('Broadlink hub discovered and authenticated successfully.')
            return True
        
        except Exception as e:
            LOGGER.error(f'Exception during discovery: {e}', exc_info=True)
            return False
    
    def authenticate(self):
        """
        Authenticate with the Broadlink hub.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.device:
                LOGGER.error('No device object available for authentication.')
                return False
            
            LOGGER.debug('Sending auth() to hub...')
            result = self.device.auth()
            
            if result:
                self.authenticated = True
                LOGGER.info('Hub authentication successful.')
                return True
            else:
                LOGGER.warning('Hub authentication returned False.')
                return False
        
        except socket.timeout:
            LOGGER.error('Authentication timeout.')
            return False
        except Exception as e:
            LOGGER.error(f'Exception during authentication: {e}', exc_info=True)
            return False
    
    def check_authentication(self):
        """
        Verify current authentication status.
        
        Returns:
            bool: True if authenticated, False otherwise
        """
        try:
            if not self.device:
                return False
            
            # Perform a lightweight auth check
            result = self.device.auth()
            self.authenticated = bool(result)
            
            if self.authenticated:
                LOGGER.debug('Authentication check passed.')
            else:
                LOGGER.warning('Authentication check failed.')
            
            return self.authenticated
        
        except Exception as e:
            LOGGER.error(f'Exception during auth check: {e}')
            self.authenticated = False
            return False
    
    def enter_learning_mode_ir(self):
        """
        Enter IR learning mode.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._verify_device():
                return False
            
            LOGGER.info('Entering IR learning mode...')
            result = self.device.enter_learning()
            
            LOGGER.info(f'enter_learning() result: {result}')
            return True
        
        except socket.timeout:
            LOGGER.error('IR learning mode timeout.')
            return False
        except Exception as e:
            LOGGER.error(f'Exception entering IR learning mode: {e}', exc_info=True)
            return False
    
    def sweep_frequency_rf(self):
        """
        Sweep RF frequency (RF learning step 1).
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._verify_device():
                return False
            
            LOGGER.info('Starting RF frequency sweep...')
            result = self.device.sweep_frequency()
            
            LOGGER.info(f'sweep_frequency() result: {result}')
            return True
        
        except socket.timeout:
            LOGGER.error('RF sweep timeout.')
            return False
        except Exception as e:
            LOGGER.error(f'Exception during RF sweep: {e}', exc_info=True)
            return False
    
    def check_frequency_rf(self):
        """
        Check RF frequency findings (RF learning step 2 part 1).
        
        Returns:
            bool: True if frequency found, False otherwise
        """
        try:
            if not self._verify_device():
                return False
            
            LOGGER.debug('Checking RF frequency...')
            result = self.device.check_frequency()
            
            if result:
                LOGGER.info(f'RF frequency check passed: {result}')
                return True
            else:
                LOGGER.warning('RF frequency check returned False.')
                return False
        
        except socket.timeout:
            LOGGER.error('RF frequency check timeout.')
            return False
        except Exception as e:
            LOGGER.error(f'Exception checking RF frequency: {e}', exc_info=True)
            return False
    
    def check_data(self, max_wait=30, poll_interval=0.5):
        """
        Check for learned data (IR or RF packet).
        Polls until data received or timeout.
        
        Args:
            max_wait: Maximum time to wait in seconds
            poll_interval: Poll interval in seconds
            
        Returns:
            bytes: Learned code data, or None if timeout/error
        """
        try:
            if not self._verify_device():
                return None
            
            LOGGER.debug(f'Checking for data (max_wait={max_wait}s, poll_interval={poll_interval}s)...')
            
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                try:
                    data = self.device.check_data()
                    
                    if data:
                        LOGGER.info(f'Data received: {len(data)} bytes')
                        LOGGER.debug(f'Data (hex): {data.hex()[:100]}...')
                        return data
                
                except socket.timeout:
                    # Timeout on this individual check is normal; continue polling
                    pass
                except Exception as e:
                    LOGGER.debug(f'check_data exception (may be normal during polling): {e}')
                
                time.sleep(poll_interval)
            
            LOGGER.warning(f'No data received within {max_wait} seconds.')
            return None
        
        except Exception as e:
            LOGGER.error(f'Exception in check_data: {e}', exc_info=True)
            return None
    
    def send_data(self, data):
        """
        Send learned code data via hub.
        
        Args:
            data: bytes object containing the code
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._verify_device():
                return False
            
            LOGGER.info(f'Sending data: {len(data)} bytes')
            LOGGER.debug(f'Data (hex): {data.hex()[:100]}...')
            
            result = self.device.send_data(data)
            
            LOGGER.info(f'send_data() result: {result}')
            return True
        
        except socket.timeout:
            LOGGER.error('Send data timeout.')
            return False
        except Exception as e:
            LOGGER.error(f'Exception sending data: {e}', exc_info=True)
            return False
    
    def get_temperature(self):
        """
        Query hub temperature (if supported).
        
        Returns:
            float: Temperature in Celsius, or None
        """
        try:
            if not self._verify_device():
                return None
            
            if not hasattr(self.device, 'get_temperature'):
                LOGGER.debug('Device does not support get_temperature()')
                return None
            
            temp = self.device.get_temperature()
            LOGGER.debug(f'Hub temperature: {temp}°C')
            return temp
        
        except Exception as e:
            LOGGER.debug(f'Exception getting temperature: {e}')
            return None
    
    def _verify_device(self):
        """
        Verify device object exists and is authenticated.
        
        Returns:
            bool: True if ready, False otherwise
        """
        if not self.device:
            LOGGER.error('Device not initialized.')
            return False
        
        if not self.authenticated:
            LOGGER.warning('Device not authenticated. Attempting re-auth...')
            if not self.authenticate():
                LOGGER.error('Re-authentication failed.')
                return False
        
        return True
    
    def close(self):
        """
        Close connection and cleanup.
        """
        try:
            self.device = None
            self.authenticated = False
            LOGGER.info('Broadlink client closed.')
        except Exception as e:
            LOGGER.error(f'Exception closing client: {e}')


class BroadlinkSetupHelper:
    """
    Helper for AP mode provisioning.
    """
    
    @staticmethod
    def provision_device(ssid, password, security_mode=4, host='255.255.255.255'):
        """
        Provision a Broadlink device in AP mode.
        
        Args:
            ssid: Target Wi-Fi SSID
            password: Target Wi-Fi password
            security_mode: 0=open, 4=WPA (default)
            host: Broadcast address for provisional packet
            
        Returns:
            dict: Result dictionary, or None if error
        """
        try:
            import broadlink
            
            LOGGER.info(f'Provisioning device: SSID={ssid}, security={security_mode}')
            
            result = broadlink.setup(
                ssid=ssid,
                password=password,
                security_mode=security_mode,
                host=host
            )
            
            LOGGER.info(f'Provisioning result: {result}')
            return result
        
        except socket.timeout:
            LOGGER.error('Provisioning timeout.')
            return None
        except Exception as e:
            LOGGER.error(f'Exception during provisioning: {e}', exc_info=True)
            return None
