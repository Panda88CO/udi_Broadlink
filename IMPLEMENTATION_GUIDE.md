# Broadlink Node Server Implementation Guide

## Overview

This Node Server integrates **Broadlink RM4 Pro** devices with **UDI Polyglot v3 (PG3/PG3x)** using the `udi_interface` library. It provides IR/RF learning, code transmission, and persistent storage of learned codes.

**Architecture:**
- **Controller Node** (`setup`): Hub representation + AP provisioning
- **Service Nodes** (`ir`, `rf`): Parent nodes for IR and RF control
- **Dynamic Sub-nodes**: Individual learned/configured codes (e.g., `ir_tv_power`)

---

## File Structure

```
udi_broadlink/
├── udi_broadlink.py          # Main entry point, node server controller
├── nodes.py                   # Node class definitions
├── config_parser.py           # Configuration parsing utilities
├── broadlink_client.py        # Broadlink API wrapper with error handling
├── requirements.txt           # Python dependencies
├── server.json               # PG3 configuration manifest
├── POLYGLOT_CONFIG.md        # Configuration guide (user-facing)
└── README.md                 # General README
```

---

## Module Documentation

### 1. **udi_broadlink.py** — Main Entry Point

**Class: `BroadlinkNodeServer(udi_interface.Node)`**

The primary node server controller. Manages lifecycle, discovery, node creation, and persistent storage.

#### Key Methods:

- **`__init__(polyglot)`**
  - Initializes controller with `ready=False`
  - Binds event handlers (`onConfig`, `onStart`, `onStop`, `onDelete`, `onPoll`)
  - Registers `ADDNODEDONE` listener for startup synchronization

- **`handle_start()`**
  - Called at startup; triggers discovery/auth
  - Creates parent nodes (`ir`, `rf`)
  - Builds code subnodes from parameters
  - **Does NOT set `ready=True`** — waits for `ADDNODEDONE`

- **`on_add_node_done(event, *args, **kwargs)`**
  - Event handler for `ADDNODEDONE`
  - **Sets `ready=True`** — critical for safe driver updates
  - Updates controller `ST` driver

- **`_discover_and_auth()`**
  - Connects to hub at `HUB_IP`
  - Sets explicit 5-second timeout
  - Posts notice if hub not found (doesn't crash)

- **`_build_code_nodes()`**
  - Parses `IR_CODES` and `RF_CODES` parameters
  - Creates subnodes for each configured/learned code

- **`_parse_code_param(param_name)`**
  - Supports both JSON and key=value formats
  - Example: `{"TV Power": "2600d200...", "Vol Up": "b64:AAE..."}`

- **`_long_poll()` → `_sync_node_renames()`**
  - Checks for user-initiated node renames in ISY/Admin Console
  - Updates `customData` so names persist across restarts
  - Called every 300 seconds (configured in `server.json`)

- **`add_learned_code(parent_type, code_name, code_value)`**
  - Persists newly learned code to `customData`
  - Creates subnode automatically

#### Drivers:

| Driver | UOM | Purpose |
|--------|-----|---------|
| `ST` | 2 (bool) | Online status (0=offline, 1=online) |

---

### 2. **nodes.py** — Node Classes

#### **Class: `BroadlinkSetup`**

Controller node representing the Broadlink hub itself.

**Drivers:**
- `ST`: Online status
- `HEARTBEAT`: Status toggle (toggled every short poll)

**Commands:**
- `APSETUP`: Provision device in AP mode (calls `broadlink.setup()`)
- `RESTART`: Placeholder for future hub restart support

---

#### **Class: `BroadlinkIR`**

IR parent node with learning capability.

**Drivers:**
- `ST`: Status
- `GV0`: Learning progress (UOM 25 → 0-100%)

**Commands:**
- `LEARNCODE`: Initiate IR learning
  - Runs in background thread (non-blocking)
  - Updates `GV0` progress: 10% → 50% → 100%
  - Listens for IR packet (up to 30 seconds)
  - Creates subnode automatically upon success

**Learning Flow:**
```
1. Call enter_learning()
2. Wait for IR packet (check_data() in loop)
3. Encode as hex
4. Create subnode + store in customData
```

---

#### **Class: `BroadlinkRF`**

RF parent node with 2-step learning.

**Drivers:**
- `ST`: Status
- `GV0`: Learning progress (0-100%)

**Commands:**
- `LEARNCODE`: Initiate RF learning (2-step process)

**Learning Flow (2-Step):**
```
Step 1: Sweep Frequency
  - Call sweep_frequency()
  - Progress: 10%

Delay: 2-second sleep (as per requirements)
  - Progress: 25%

Step 2: Learn Code
  - Call check_frequency()
  - Wait for packet (check_data() in loop)
  - Progress: 50% → 85%
  - Encode as hex, create subnode + store
```

**Why 2-step?** RF requires frequency identification before packet capture.

---

#### **Class: `BroadlinkCode`**

Subnode representing a single code (learned or configured).

**Drivers:**
- `ST`: Status (momentary on/off for visual feedback)

**Commands:**
- `TXCODE`: Transmit the code
  - Decodes hex or base64
  - Calls `hub.send_data(bytes)`
  - Toggles `ST` for visual feedback

---

### 3. **config_parser.py** — Configuration Utilities

**Class: `ConfigParser`**

Static utilities for parsing PG3 custom parameters.

#### Key Methods:

- **`parse_custom_params(config_dict)`**
  - Extracts all custom parameters with defaults
  - Returns dict with keys: `hub_ip`, `wifi_ssid`, etc.

- **`parse_code_dict(code_str)`**
  - Parses `IR_CODES` / `RF_CODES` parameter
  - Handles both JSON and key=value formats
  - Returns: `{code_name: code_value}`

- **`validate_code_value(code_value)`**
  - Validates hex or base64 encoding
  - Returns: `(is_valid, normalized_value, error_msg)`

- **`sanitize_node_address(name)`**
  - Converts code name to valid address
  - Example: "Living Room TV" → "living_room_tv"

---

**Class: `CodeStore`**

Persistent storage for learned codes.

#### Key Methods:

- **`store_learned_code(custom_data, code_type, code_name, code_value)`**
  - Stores code in `customData` with timestamp
  - Returns updated `customData`

- **`get_learned_codes(custom_data, code_type=None)`**
  - Retrieves all or filtered learned codes
  - Returns list of code objects

---

### 4. **broadlink_client.py** — Broadlink API Wrapper

**Class: `BroadlinkClient`**

High-level wrapper around `python-broadlink` with robust error handling.

#### Key Methods:

- **`discover()`** → `authenticate()`
  - Connects to hub at given IP
  - Sets timeout = 5 seconds (explicit)
  - Returns: `bool`

- **`enter_learning_mode_ir()`**
  - Enters IR learning mode
  - Returns: `bool`

- **`sweep_frequency_rf()`** / **`check_frequency_rf()`**
  - RF frequency sweep (step 1 & 2)
  - Returns: `bool`

- **`check_data(max_wait=30, poll_interval=0.5)`**
  - Polls for learned packet
  - Handles socket timeouts gracefully
  - Returns: `bytes` or `None`

- **`send_data(data)`**
  - Transmits code bytes
  - Returns: `bool`

- **`check_authentication()`**
  - Re-checks auth status
  - Useful for long-poll connectivity verification

#### Design Notes:

- **All network calls wrapped in try-except**
- **Socket timeouts handled gracefully** (continue polling)
- **Comprehensive logging** of all Broadlink traffic
- **Explicit 5-second timeout** on device object

---

## Startup Flow (Ready Flag Pattern)

```
Main Entry Point (udi_broadlink.py)
│
├─ polyglot.Interface([...])
│  └─ Registers node classes with UDI
│
├─ polyglot.start()
│  ├─ Triggers handle_config()  [Custom params loaded]
│  └─ Triggers handle_start()
│     ├─ Discovers/auths hub    [self.hub_device = device]
│     ├─ Creates parent nodes   [ir, rf]
│     ├─ Builds code subnodes   [ir_tv_power, rf_garage, ...]
│     └─ self.ready = False     [✓ Nodes registered but drivers NOT updated yet]
│
├─ PG3 Syncs Nodes
│  └─ Posts ADDNODEDONE event
│
└─ on_add_node_done() [Event Handler]
   ├─ self.ready = True         [✓ Safe to update drivers now]
   └─ setDriver('ST', 1)        [Updates controller status]
```

**Why this matters:**
- UDI interface is asynchronous; nodes must be fully registered before driver updates
- Setting `ready=True` only after `ADDNODEDONE` prevents ISY/IoX update collisions
- Polling methods check `if not self.ready: return` to skip early calls

---

## Persistent Storage (customData)

Learned codes are stored in `polyglot.customData` (a JSON-backed dictionary).

### Storage Format:

```json
{
  "learned_ir_1710700000000_name": "Living Room TV Power",
  "learned_ir_1710700000000_value": "2600d200949512...",
  "learned_ir_1710700000000_type": "ir",
  "learned_ir_1710700000000_ts": 1710700000000,

  "learned_rf_1710700001000_name": "Garage Opener",
  "learned_rf_1710700001000_value": "b64:AAECAw...",
  "learned_rf_1710700001000_type": "rf",
  "learned_rf_1710700001000_ts": 1710700001000
}
```

### On Restart:

1. Custom parameters parsed (includes configured `IR_CODES` / `RF_CODES`)
2. Code subnodes rebuilt from both:
   - **Configured codes** (from `IR_CODES`, `RF_CODES` params)
   - **Learned codes** (from `customData`)
3. Names in `customData` are preserved via `_sync_node_renames()` in long poll

---

## Node Renaming (longPoll Sync)

**Problem:** UDI interface doesn't always "push" rename events.

**Solution:** Check in `longPoll` every 10 minutes:

```python
def _sync_node_renames(self):
    for code_addr, code_node in self.code_nodes.items():
        old_name = custom_data.get(f'{code_addr}_name')
        if code_node.name != old_name:  # Detected rename
            custom_data[f'{code_addr}_name'] = code_node.name
            self.polyglot.saveCustomData(custom_data)
```

---

## Error Handling Strategy

### Hub Not Found

```python
if not self._discover_and_auth():
    LOGGER.error('Hub not found.')
    self.polyglot.Notices['hub_not_found'] = (
        'Broadlink hub not found. Check HUB_IP.'
    )
    # ✓ Does not crash; continues
```

**Result:** Node server starts with notice in PG3 Admin Console. User can fix config and restart.

### Broadlink Timeouts

All network calls are wrapped:

```python
try:
    data = hub.check_data()
except socket.timeout:
    LOGGER.debug('Timeout (normal during polling)')
    # Continue polling
except Exception as e:
    LOGGER.error(f'Unexpected error: {e}', exc_info=True)
```

**Result:** Graceful recovery; no service crash.

---

## Usage Examples

### 1. Configure via PG3

**Custom Parameters:**

```json
{
  "USER_ID": "admin",
  "USER_PASSWORD": "password",
  "HUB_IP": "192.168.1.120",
  "IR_CODES": {
    "TV Power": "2600d200949512...",
    "Vol Up": "2600d200949512..."
  },
  "RF_CODES": {
    "Garage Door": "b64:AAECAw..."
  }
}
```

### 2. Learn New IR Code

- Go to **PG3 Admin Console** → Select "Broadlink IR" node
- Click **Learn IR Code** command
- Point IR remote at hub within 30 seconds
- New subnode appears: "Learned IR 1234"
- Name it via admin console (persists across restarts)

### 3. Send Code

- Select code subnode (e.g., "TV Power")
- Click **Send Code** command
- Hub transmits IR/RF packet

---

## Extension Points

### Add New Code Type

1. Define in `nodes.py`:
   ```python
   class BroadlinkRF2(BroadlinkRF):
       """Extended RF learning"""
       def _learn_code_thread(self):
           # Custom logic
   ```

2. Register in `udi_broadlink.py`:
   ```python
   polyglot.Interface([BroadlinkSetup, BroadlinkIR, BroadlinkRF, BroadlinkRF2])
   ```

3. Add nodedef in profile (not included in this implementation)

### Add New Hub Type

1. Extend `BroadlinkClient`:
   ```python
   class BroadlinkRM4Client(BroadlinkClient):
       def __init__(self, hub_ip):
           super().__init__(hub_ip)
           self.device_type = 'rm4pro'
   ```

2. Override methods for device-specific behavior

---

## Testing

### Local Test

```bash
pip install -r requirements.txt
python udi_broadlink.py
```

Output:
```
INFO: BroadlinkNodeServer initialized.
INFO: Node server starting...
INFO: Attempting to discover Broadlink hub at 192.168.1.120...
INFO: Hub authenticated successfully.
INFO: Parent nodes verified/created.
INFO: Built 2 code subnodes.
INFO: Node server startup sequence complete.
INFO: ADDNODEDONE event received. Nodes fully registered.
INFO: Node server ready flag set to True.
```

### Logging Levels

- **DEBUG**: Detailed Broadlink traffic, polling details
- **INFO**: Node creation, learning started/completed, code transmission
- **ERROR**: Hub not found, auth failed, learning timeout

Enable debug logging:
```python
LOGGER.setLevel(logging.DEBUG)
```

---

## Troubleshooting

### Hub Not Discovered

1. Check `HUB_IP` in PG3 config
2. Verify hub is on network: `ping 192.168.1.120`
3. Check firewall (port 80 needed)
4. Look for notice in PG3 Admin Console

### Learning Timeout

1. Point remote/RF device directly at hub
2. Try again; may take 2-3 attempts
3. Check hub doesn't already have a learning session active

### Code Won't Transmit

1. Verify code was learned successfully
2. Try re-learning in a few seconds
3. Check hub temperature (GV0 driver on parent)

---

## Future Enhancements

1. **Multi-Hub Support**: Add hub selection parameter
2. **Scene Recording**: Record IR sequences (multiple codes sent in sequence)
3. **Timer Support**: Schedule code transmission
4. **Temperature Monitoring**: Dashboard widgets for hub temp
5. **Learned Code Index**: UI listing of all learned codes
6. **Macro Support**: IF-THEN rules combining multiple codes

---

## References

- **UDI Interface**: https://github.com/UniversalDevicesInc/udi_interface
- **python-broadlink**: https://github.com/mjg59/python-broadlink
- **Polyglot v3 Docs**: https://docs.universaldevices.com/polyglot-v3/
- **ISY Nodedef Format**: https://docs.universaldevices.com/isy/nodedef-xml-schema

---

## License

MIT (Same as repository)

**Author:** Chris (UDI Broadlink Node Server)  
**Version:** 0.1.0  
**Date:** 2026-03-17
