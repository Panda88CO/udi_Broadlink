# Developer Quick Reference — Broadlink Node Server

## File Organization

```
udi_Broadlink/
│
├─ MAIN IMPLEMENTATION
│  ├─ udi_broadlink.py       ← Entry point (start here)
│  ├─ nodes.py               ← Node class defs
│  ├─ broadlink_client.py    ← API wrapper
│  └─ config_parser.py       ← Config utilities
│
├─ DOCUMENTATION
│  ├─ QUICKSTART.md          ← User guide (learn first)
│  ├─ ARCHITECTURE.md        ← Technical deep-dive
│  ├─ IMPLEMENTATION_GUIDE.md← API reference
│  ├─ IMPLEMENTATION_COMPLETE.md ← Summary
│  ├─ POLYGLOT_CONFIG.md     ← Param reference
│  └─ README.md              ← General info
│
├─ CONFIGURATION
│  ├─ requirements.txt       ← pip packages
│  ├─ server.json           ← PG3 manifest
│  └─ install.sh            ← Install script
│
└─ VCS
   └─ .git/                 ← Version control
```

---

## Class Hierarchy

```
udi_interface.Node (base class)
│
├─ BroadlinkSetup (controller)
│  └─ Represents: Broadlink RM4 Pro hub
│  └─ Drivers: ST (online/offline)
│  └─ Commands: APSETUP, RESTART
│
├─ BroadlinkIR (parent node)
│  └─ Represents: IR learning/control
│  └─ Drivers: ST, GV0 (progress 0-100%)
│  └─ Commands: LEARNCODE, DON, DOF
│  └─ Children: IR code subnodes
│
├─ BroadlinkRF (parent node)
│  └─ Represents: RF learning/control (2-step)
│  └─ Drivers: ST, GV0 (progress 0-100%)
│  └─ Commands: LEARNCODE, DON, DOF
│  └─ Children: RF code subnodes
│
└─ BroadlinkCode (subnode)
   └─ Represents: Individual learned/configured code
   └─ Drivers: ST (momentary on send)
   └─ Commands: TXCODE (transmit)
   └─ Fields: code_value, code_type (ir/rf)
```

---

## Startup Sequence (Timing)

```
T=0s          udi_broadlink.py starts
              │
              ├─ polyglot.Interface([BroadlinkSetup, ...])
              │  └─ Registers node classes
              │
              └─ polyglot.start()
                 │
                 ├─ T=0-1s: handle_config() fires
                 │          └─ Loads custom parameters
                 │
                 ├─ T=1-2s: handle_start() fires
                 │          ├─ _discover_and_auth()
                 │          │  └─ Hub found & authenticated
                 │          │     OR notice posted (doesn't crash)
                 │          ├─ _ensure_parent_nodes()
                 │          │  └─ Creates ir, rf nodes if missing
                 │          └─ _build_code_nodes()
                 │             └─ Creates subnodes from params
                 │
                 │          >>> ready = False (still!)
                 │
                 └─ T=2-3s: PG3 syncs nodes
                            │
                            └─ Posts ADDNODEDONE event
                               │
                               └─ on_add_node_done() fires
                                  │
                                  └─ ready = True ✓
                                     └─ setDriver('ST', 1)

>> Node server fully initialized by T=3s <<
```

---

## Learning Sequence (IR vs RF)

### IR Learning (Single Step)

```
User clicks: Broadlink IR → LEARNCODE

│
├─ learning = True
├─ GV0 = 0%
│
├─ hub.enter_learning()          ← Send device to learning mode
│  └─ GV0 = 10%
│
├─ Check for data (30s timeout)  ← Poll for IR packet
│  ├─ GV0 = 50%
│  └─ (sleep 0.5s, retry)
│
├─ data received!
│  ├─ GV0 = 100%
│  ├─ Encode as hex
│  ├─ code_name = "Learned IR 9876"
│  └─ add_learned_code('ir', code_name, hex_code)
│     └─ Creates BroadlinkCode subnode
│        └─ Persists to customData
│
├─ Sleep 2s
├─ GV0 = 0% (reset)
└─ learning = False

>>> Learned code now available in ISY <<<
```

### RF Learning (2-Step)

```
User clicks: Broadlink RF → LEARNCODE

│
├─ learning = True
├─ GV0 = 0%
│
├─ STEP 1: Frequency Sweep
│  ├─ hub.sweep_frequency()      ← Scan for RF signal
│  ├─ GV0 = 10%
│  └─ Frequency found
│
├─ CRITICAL: Sleep 2 seconds     ← Required by Broadlink! 
│  └─ GV0 = 25%
│
├─ STEP 2: Learn Code
│  ├─ hub.check_frequency()      ← Verify frequency
│  ├─ GV0 = 40%
│  │
│  ├─ Check for data (20s timeout) ← Poll for RF packet
│  │  ├─ GV0 = 50% → 85%
│  │  └─ (sleep 0.5s, retry)
│  │
│  └─ data received!
│
├─ GV0 = 100%
├─ Encode as hex
├─ code_name = "Learned RF 5432"
└─ add_learned_code('rf', code_name, hex_code)
   └─ Creates BroadlinkCode subnode
      └─ Persists to customData

├─ Sleep 2s
├─ GV0 = 0% (reset)
└─ learning = False

>>> Learned code now available in ISY <<<
```

---

## LongPoll Rename Sync (300 seconds)

```
Every 300 seconds:

_long_poll()
│
├─ Check hub connectivity
│
└─ _sync_node_renames()
   │
   ├─ Load customData
   │
   ├─ For each code_node:
   │  │
   │  ├─ old_name = customData['ir_tv_power_name']
   │  │              (e.g., "Living Room TV")
   │  │
   │  ├─ current_name = code_node.name
   │  │                 (from ISY/IoX, user may have renamed)
   │  │
   │  └─ if old_name != current_name:
   │     │
   │     ├─ DETECTED RENAME!
   │     ├─ Update customData
   │     └─ polyglot.saveCustomData(custom_data)
   │        └─ Persists to disk
   │
   └─ Done; next sync in 300s

On next restart:
├─ _build_code_nodes()
├─ Reads customData
└─ Recreates nodes with SAVED NAMES ✓
   └─ Rename survives restart!
```

---

## Error Handling Matrix

| Scenario | Handling | Result |
|----------|----------|--------|
| Hub not found | Try connect, post notice | Service online, msg in PG3 |
| Auth timeout | Log error, set authenticated=False | Notice posted |
| Learning timeout (30s) | Return None, reset GV0 | User can retry |
| Code transmit fails | Log error, continue | Try again next time |
| Network glitch | Socket timeout caught, retry | Silent recovery |
| Config invalid | Log warning, continue | Guide user to fix |
| Node lookup fails | Catch exception, log | Service continues |

---

## Code Persistence Format

### In customData (JSON)

```json
{
  "learned_ir_1710700000000_name": "Living Room TV Power",
  "learned_ir_1710700000000_value": "2600d20094951294...",
  "learned_ir_1710700000000_type": "ir",
  "learned_ir_1710700000000_ts": 1710700000000,
  
  "learned_rf_1710700001000_name": "Garage Opener",
  "learned_rf_1710700001000_value": "b64:AAECAw==",
  "learned_rf_1710700001000_type": "rf",
  "learned_rf_1710700001000_ts": 1710700001000,
  
  "ir_tv_power_name": "TV Power",
  "rf_garage_name": "Garage Door"
}
```

### Loading on Startup

```
_build_code_nodes()
│
├─ Parse IR_CODES param → create subnodes
├─ Parse RF_CODES param → create subnodes
│
└─ Iterate customData keys:
   └─ if key.startswith('learned_'):
      ├─ Extract: type, code_name, code_value
      └─ Create subnode with stored name ✓
```

---

## Driver Quick Reference

| Node | Driver | UOM | Min | Max | Purpose |
|------|--------|-----|-----|-----|---------|
| Setup | ST | 2 | 0 | 1 | Online (0=off, 1=on) |
| IR | ST | 2 | 0 | 1 | Status |
| IR | GV0 | 25 | 0 | 100 | Learning progress |
| RF | ST | 2 | 0 | 1 | Status |
| RF | GV0 | 25 | 0 | 100 | Learning progress |
| Code | ST | 2 | 0 | 1 | Momentary (on send) |

**UOM 2** = Boolean (standard on/off)  
**UOM 25** = Percentage (0 to 100)

---

## Command Quick Reference

| Node | Command | Parameter | Effect |
|------|---------|-----------|--------|
| Setup | APSETUP | — | Provision device in AP mode |
| Setup | RESTART | — | Restart hub (if supported) |
| IR | LEARNCODE | — | Enter IR learning mode |
| IR | DON | — | Turn on (test) |
| IR | DOF | — | Turn off (test) |
| RF | LEARNCODE | — | Enter RF learning (2-step) |
| RF | DON | — | Turn on (test) |
| RF | DOF | — | Turn off (test) |
| Code | TXCODE | — | Transmit the code |

---

## Timeout Behavior

```
Network Call (e.g., hub.auth())
│
├─ device.timeout = 5 seconds (explicit!)
│
└─ Try:
   ├─ device.auth()
   │  ├─ Success within 5s → continue
   │  └─ Timeout after 5s → except socket.timeout
   │
   └─ Except:
      ├─ socket.timeout → graceful fallback
      │  └─ Log warning, continue
      │
      └─ Other Exception → log error, continue
         └─ Service never hangs
```

---

## Testing Commands

### Syntax Check
```bash
python -m py_compile udi_broadlink.py nodes.py \
  config_parser.py broadlink_client.py
```

### Import Check
```bash
python -c "from nodes import *; print('OK')"
```

### Local Run
```bash
python udi_broadlink.py
# Should show:
# - Node server initialized
# - Discovery attempted
# - Nodes created
# - ADDNODEDONE event
# - Ready = True
```

### Debug Logging
```python
# In udi_broadlink.py (line 15)
LOGGER.setLevel(logging.DEBUG)

# Now run and search logs for detail
```

---

## Common Code Patterns

### Creating a New Node
```python
node = BroadlinkCode(
    polyglot,           # Interface object
    'udi_broadlink',    # Primary (controller)
    'ir_tv_power',      # Address
    'ir',               # Parent address
    'TV Power',         # Display name
    '2600d200...',      # Code value
    'ir'                # Type (ir/rf)
)
polyglot.addNode(node)
```

### Updating Driver
```python
self.setDriver('GV0', 50)  # 50% progress
self.setDriver('ST', 1)    # On

self.setDriver('GV0', 0, force=True)  # Force update
```

### Try-Except Pattern
```python
try:
    result = hub.auth()
    if not result:
        LOGGER.error('Auth failed')
        return False
except socket.timeout:
    LOGGER.error('Auth timeout')
    return False
except Exception as e:
    LOGGER.error(f'Auth exception: {e}', exc_info=True)
    return False

return True
```

### Background Thread Pattern
```python
def public_command(self, command=None):
    thread = Thread(target=self._background_work, daemon=True)
    thread.start()

def _background_work(self):
    try:
        # Long-running work
        self.setDriver('GV0', 50)
        # More work
        self.setDriver('GV0', 100)
    except Exception as e:
        LOGGER.error(f'Exception: {e}', exc_info=True)
```

---

## Debugging Checklist

- [ ] Check logs for "Hub authenticated" (discovery worked)
- [ ] Check logs for "ADDNODEDONE" (nodes registered)
- [ ] Verify `ready = True` set before driver updates
- [ ] Confirm parent nodes exist (IR, RF)
- [ ] Verify code subnodes created from parameters
- [ ] Check customData saved (learned codes persisted)
- [ ] Monitor GV0 during learning (should progress)
- [ ] Verify code transmission logged (no exception)
- [ ] Check ISY nodes reflect updates (not stale)

---

## Extension Checklist

To add a new feature:

1. **Define in node class**
   ```python
   commands = {
       'MYNEWCMD': my_new_command,
   }
   ```

2. **Implement method**
   ```python
   def my_new_command(self, command=None):
       LOGGER.info('Command executed')
       # Implementation
   ```

3. **Add stub**
   ```python
   def my_new_command(self, command=None):
       if hasattr(self, 'my_new_command'):
           self.my_new_command(command)
   ```

4. **Add driver (if needed)**
   ```python
   drivers = [
       {'driver': 'GV5', 'value': 0, 'uom': 56},  # New!
   ]
   ```

5. **Test locally**
   ```bash
   python udi_broadlink.py
   # Verify new command appears
   ```

---

## Quick Troubleshooting

| Problem | Check | Fix |
|---------|-------|-----|
| Hub not found | HUB_IP in logs | Verify IP, restart |
| No subnodes | `_build_code_nodes()` called? | Check params, run again |
| Learning hangs | Timeout hit? | Increase `max_wait` in `check_data()` |
| Name lost on restart | customData saved? | Check longPoll ran |
| Command not working | Command registered? | Add to `commands` dict |
| Transmission fails | Code format valid? | Re-learn code |

---

## Lines of Code Overview

| Module | Lines | Focus |
|--------|-------|-------|
| udi_broadlink.py | ~500 | Lifecycle, discovery, coordination |
| nodes.py | ~450 | Node defs, learning logic, threading |
| broadlink_client.py | ~350 | API wrapper, timeout management |
| config_parser.py | ~300 | Config utilities, validation |
| **Total** | **~1600** | Production-grade implementation |

---

## Reference Links

- **UDI Interface:** https://github.com/UniversalDevicesInc/udi_interface
- **python-broadlink:** https://github.com/mjg59/python-broadlink
- **PG3 Docs:** https://docs.universaldevices.com/polyglot-v3/
- **UDI Forum:** https://forum.universaldevices.com/

---

## Key Takeaways

✓ **Ready flag** — Wait for ADDNODEDONE before updating drivers  
✓ **LongPoll sync** — Check for renames every 300s  
✓ **Explicit timeout** — Set device.timeout = 5 always  
✓ **Error handling** — Try-except every Broadlink call  
✓ **Persistence** — Use customData for learned codes  
✓ **Threading** — Background threads for learning  
✓ **Logging** — DEBUG, INFO, ERROR at all key points  

---

**Version:** 0.1.0  
**Date:** 2026-03-17  
**Status:** Production-Ready
