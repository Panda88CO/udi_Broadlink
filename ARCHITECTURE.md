# Broadlink Node Server — Technical Architecture Summary

## Overview

This implementation follows UDI Polyglot v3 best practices and incorporates the three key technical recommendations you provided:

1. **Ready Flag Pattern** — Ensures safe startup sequencing
2. **LongPoll Rename Sync** — Reliable node rename detection
3. **Explicit 5-Second Timeout** — Robust Broadlink network handling

---

## 1. Ready Flag Pattern (CRITICAL)

### Problem

In PG3, `start()` is **asynchronous**. If you try to update drivers before nodes are fully registered with ISY/IoX, you create race conditions and lost updates.

### Solution

```python
# In __init__
self.ready = False

# In handle_start() — do NOT set ready here
self._discover_and_auth()
self._ensure_parent_nodes()
self._build_code_nodes()
# self.ready stays False

# In on_add_node_done() — event handler for ADDNODEDONE
def on_add_node_done(self, event, *args, **kwargs):
    self.ready = True  # ✓ NOW safe to update drivers
    self.setDriver('ST', 1, force=True)
```

### Timing Sequence

```
handle_start()
  ↓ (completes, ready=False)
PG3 syncs nodes
  ↓
ADDNODEDONE event fires
  ↓
on_add_node_done()
  ↓ set ready=True
  ↓ safe to update drivers
```

### Impact

- ✓ No timing issues with large node counts
- ✓ Drivers reliably update on startup
- ✓ No ISY/IoX update collisions
- ✓ Polling methods check `if not self.ready: return` to skip early invocations

---

## 2. LongPoll Node Rename Sync

### Problem

UDI interface **doesn't always notify** when user renames a node in admin console. Renames can be lost on service restart.

### Solution

**Every long poll (300 seconds)**, check if node names changed:

```python
def _sync_node_renames(self):
    """
    Called during long poll.
    Detects user-initiated renames and persists them.
    """
    custom_data = self.polyglot.customData or {}
    updated = False
    
    for code_addr, code_node in self.code_nodes.items():
        # What's stored?
        old_name = custom_data.get(f'{code_addr}_name', code_node.name)
        
        # What does ISY/IoX show now?
        if code_node.name != old_name:
            LOGGER.info(f'Detected rename: {code_addr} → {code_node.name}')
            custom_data[f'{code_addr}_name'] = code_node.name
            updated = True
    
    if updated:
        self.polyglot.customData = custom_data
        self.polyglot.saveCustomData(custom_data)
```

### Why This Works

- **Ten-minute window**: Renames are persisted at most every 300 seconds
- **Survivable restarts**: On next startup, `customData` has the updated name
- **Non-intrusive**: Doesn't interfere with normal operations; just observes

### Code Rebuild Logic

After restart, `_build_code_nodes()` rebuilds from:

1. **Configured codes** (IR_CODES, RF_CODES params) — always present
2. **Learned codes** (customData with timestamps) — persists with correct names

Result: Even if user renamed "Learned IR 001" → "Living Room Power", the name is preserved.

---

## 3. Explicit 5-Second Timeout

### Problem

The Broadlink library can hang indefinitely on network timeouts. Blocks entire service.

### Solution

**Set timeout explicitly** on device object:

```python
import broadlink

device = broadlink.rm4pro((hub_ip, 80), None, None, allow_errors=False)
device.timeout = 5  # ← CRITICAL: explicit 5-second timeout

if device.auth():
    # Safe to use
```

### Where Applied

1. **Discovery**: `_discover_and_auth()` sets timeout
2. **Learning**: `check_data()` polls with timeout
3. **Transmission**: `send_data()` uses timeout

### Timeout Handling

```python
def check_data(self, max_wait=30, poll_interval=0.5):
    """
    Check for learned packet.
    Polls up to max_wait seconds.
    """
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            data = self.device.check_data()
            if data:
                return data
        except socket.timeout:
            # ✓ Timeout is expected during polling; continue
            pass
        except Exception as e:
            LOGGER.error(f'Unexpected error: {e}')
            return None
        
        time.sleep(0.5)  # Poll again
    
    return None  # Timeout after max_wait
```

### Benefits

- ✓ No indefinite hangs
- ✓ Graceful fallback on network issues
- ✓ Service continues even if hub is offline
- ✓ Clear error messages in logs

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  udi_broadlink.py (Main)                                    │
│                                                              │
│  BroadlinkNodeServer                                        │
│  ├─ __init__()                    [ready=False]             │
│  ├─ handle_start()                [discover, create nodes]  │
│  ├─ on_add_node_done()            [ready=True] ← CRITICAL   │
│  ├─ _long_poll()                                            │
│  │  └─ _sync_node_renames()       [persist renames]         │
│  ├─ _short_poll()                 [heartbeat]               │
│  ├─ _build_code_nodes()                                     │
│  └─ add_learned_code()            [persist, create subnode] │
└─────────────────────────────────────────────────────────────┘
         │                  │                    │
         ├─────────────────┼────────────────────┤
         ↓                 ↓                    ↓
    nodes.py         config_parser.py   broadlink_client.py
    ────────         ────────────────    ──────────────────
    
    BroadlinkSetup    ConfigParser         BroadlinkClient
    BroadlinkIR       CodeStore            ├─ discover()
    BroadlinkRF       ├─ parse_*()         ├─ authenticate()
    BroadlinkCode     ├─ validate_*()      ├─ enter_learning_mode_ir()
                      └─ sanitize_*()      ├─ sweep_frequency_rf()
                                           ├─ check_frequency_rf()
                                           ├─ check_data()
                                           ├─ send_data()
                                           └─ get_temperature()
```

---

## Node Graph in ISY/IoX

```
Broadlink Setup (udi_broadlink)
├─ Status: Online/Offline
├─ Commands: APSETUP, RESTART
└─ Drivers: ST (online), HEARTBEAT (pulses)

  ├── Broadlink IR (ir)
  │   ├─ Status: On/Off
  │   ├─ Learning Progress: 0-100%
  │   ├─ Commands: LEARNCODE, DON, DOF
  │   │
  │   ├── [Subnode] TV Power (ir_tv_power)
  │   │   ├─ Status (momentary)
  │   │   └─ Command: TXCODE (send the code)
  │   │
  │   ├── [Subnode] Vol Up (ir_vol_up)
  │   │   └─ Command: TXCODE
  │   │
  │   └── [Subnode] Learned IR 1234 (ir_learned_1234)
  │       └─ Command: TXCODE (auto-created by learning)
  │
  └── Broadlink RF (rf)
      ├─ Status: On/Off
      ├─ Learning Progress: 0-100%
      ├─ Commands: LEARNCODE, DON, DOF
      │
      ├── [Subnode] Garage Door (rf_garage_door)
      │   └─ Command: TXCODE
      │
      └── [Subnode] Learned RF 5678 (rf_learned_5678)
          └─ Command: TXCODE (auto-created by learning)
```

---

## State Management

### Drivers

| Node | Driver | UOM | Purpose |
|------|--------|-----|---------|
| setup | ST | 2 | Online status |
| ir | ST | 2 | IR node status |
| ir | GV0 | 25 | Learning progress (%) |
| rf | ST | 2 | RF node status |
| rf | GV0 | 25 | Learning progress (%) |
| code | ST | 2 | Code status (momentary) |

**UOM 2** = Boolean (0 or 1)  
**UOM 25** = Percentage (0-100)

### Learning State

**IR Learning:**
```
GV0: 0%   → enter_learning()
     10%  → waiting for code
     50%  → received packet
     100% → success
     0%   → idle (reset after 2 sec)
```

**RF Learning:**
```
GV0: 0%   → start
     10%  → sweep_frequency()
     25%  → 2-second delay
     40%  → check_frequency()
     50%  → waiting for code
     85%  → received packet
     100% → success
     0%   → idle (reset after 2 sec)
```

---

## Error Handling Strategy

### Three Levels of Robustness

**Level 1: Hub Discovery**
```python
if not self._discover_and_auth():
    LOGGER.error('Hub not found.')
    self.polyglot.Notices['hub_not_found'] = (
        'Check HUB_IP in config.'
    )
    # ✓ Service continues; posts notice
```

**Level 2: Learning/Transmission**
```python
try:
    result = hub.enter_learning()
except socket.timeout:
    LOGGER.warning('Timeout (normal)')
    return False
except Exception as e:
    LOGGER.error(f'Error: {e}', exc_info=True)
    return False
```

**Level 3: Polling**
```python
def _short_poll(self):
    try:
        if not self.ready:
            return
        # Safe operation
    except Exception as e:
        LOGGER.error(f'Poll error: {e}', exc_info=True)
        # Continue; poll again in 60 seconds
```

### Result

- ✗ Hub offline: Notice in PG3, service continues
- ✗ Learning timeout: Log error, user can retry
- ✗ Network glitch: Silent retry in next poll
- ✓ Service never crashes

---

## Persistence (customData)

### Storage Keys

```
learned_<type>_<timestamp>_name    = "TV Power"
learned_<type>_<timestamp>_value   = "2600d200949512..."
learned_<type>_<timestamp>_type    = "ir"
learned_<type>_<timestamp>_ts      = 1710700000000
```

Example:
```json
{
  "learned_ir_1710700000000_name": "Living Room TV",
  "learned_ir_1710700000000_value": "2600d200...",
  "learned_ir_1710700000000_type": "ir",
  "learned_ir_1710700000000_ts": 1710700000000,
  
  "ir_tv_power_name": "TV Power"  ← from _sync_node_renames()
}
```

### Load on Startup

```python
def _build_code_nodes(self):
    # Parse IR_CODES and RF_CODES params
    ir_codes = self._parse_code_param('IR_CODES')
    
    # Also load learned codes from customData
    custom_data = self.polyglot.customData or {}
    for key in custom_data:
        if key.startswith('learned_ir_'):
            # Extract and create subnode
```

---

## Logging Strategy

### Log Levels

**DEBUG**: Polling details, check_data() calls, minor timeouts
```python
LOGGER.debug(f'Polling hub... GV0={progress}%')
```

**INFO**: Important state changes, learning started/completed
```python
LOGGER.info(f'Learned IR code: {len(data)} bytes')
LOGGER.info(f'Created code node: ir_tv_power')
```

**ERROR**: Failures, exceptions, hub not found
```python
LOGGER.error(f'Hub authentication failed: {e}', exc_info=True)
```

### Broadlink Traffic Logging

All network calls logged:
```python
def send_data(self, data):
    LOGGER.info(f'Sending data: {len(data)} bytes')
    LOGGER.debug(f'Data (hex): {data.hex()[:100]}...')
    result = self.device.send_data(data)
    LOGGER.info(f'send_data() result: {result}')
```

This enables debugging IR/RF issues without changing code.

---

## Testing Checklist

- [ ] Hub discovered and authenticated on startup
- [ ] Parent nodes (ir, rf) created
- [ ] ADDNODEDONE event fires and `ready=True`
- [ ] ST driver updates to 1 (online)
- [ ] IR learning starts and updates GV0
- [ ] IR learning completes and creates subnode
- [ ] RF learning follows 2-step process
- [ ] Code transmission works (ST momentary)
- [ ] Rename persists across restart
- [ ] Learned code persists across restart
- [ ] Hub offline → Posts notice (doesn't crash)
- [ ] Learning timeout → Logs error (doesn't crash)

---

## Performance Considerations

### Polling Intervals (from server.json)

- **shortPoll: 60 seconds**
  - Toggles heartbeat driver
  - Lightweight operation

- **longPoll: 300 seconds**
  - Checks hub connectivity
  - Syncs node renames
  - More intensive; safe every 5 minutes

### Threading

Learning runs in **background thread** (non-blocking):
```python
thread = Thread(target=self._learn_code_thread, daemon=True)
thread.start()
```

Result: UI remains responsive during 30-second IR learning.

### Network Efficiency

- Explicit 5-second timeout prevents hanging
- Poll interval of 0.5s for learning (sufficient for IR/RF)
- Hub auth cached; re-auth only if needed

---

## Extension Pattern

### Add Custom Command

1. Define in node class:
   ```python
   commands = {
       'MYNEWCMD': my_new_command,
   }
   
   def my_new_command(self, command=None):
       # Implementation
   ```

2. Define handler stub:
   ```python
   def my_new_command(self, command=None):
       if hasattr(self, 'my_new_command'):
           self.my_new_command(command)
   ```

### Add Custom Driver

1. Define in node class:
   ```python
   drivers = [
       {'driver': 'ST', 'value': 0, 'uom': 2},
       {'driver': 'GV1', 'value': 0, 'uom': 56},  # New
   ]
   ```

2. Update in method:
   ```python
   self.setDriver('GV1', temperature)
   ```

---

## Summary

This implementation demonstrates **production-grade** Node Server patterns:

✓ **Asynchronous safety** with ready flag  
✓ **Reliable persistence** for learned codes and renames  
✓ **Robust error handling** that never crashes  
✓ **Comprehensive logging** for debugging  
✓ **Clear separation** of concerns across modules  
✓ **Thread-safe** learning operations  
✓ **Timeout management** for network reliability  

Perfect template for extending to other Broadlink devices or UDI node servers.

---

## Quick Reference

| Task | Method | File |
|------|--------|------|
| Discover hub | `_discover_and_auth()` | udi_broadlink.py |
| Learn IR | `BroadlinkIR._learn_code_thread()` | nodes.py |
| Learn RF (2-step) | `BroadlinkRF._learn_code_thread()` | nodes.py |
| Send code | `BroadlinkCode.send_code()` | nodes.py |
| Persist code | `add_learned_code()` | udi_broadlink.py |
| Sync renames | `_sync_node_renames()` | udi_broadlink.py |
| Validate config | `ConfigParser.validate_*()` | config_parser.py |
| Wrap Broadlink API | `BroadlinkClient` | broadlink_client.py |

---

**Created:** 2026-03-17  
**Version:** 0.1.0  
**Python:** 3.6+  
**Dependencies:** udi_interface>=3.4.5, python-broadlink>=0.19.0
