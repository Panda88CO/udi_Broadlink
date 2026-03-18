# Quick Start Guide — Broadlink Node Server

## Installation

### Prerequisites

- Python 3.6+
- pip (Python package manager)
- Broadlink RM4 Pro device on your network

### Local Setup

```bash
# Clone repository
cd udi_Broadlink

# Install dependencies
pip install -r requirements.txt

# Get your hub IP
ping broadlink.local  # or check your router

# Configure (choose one):
# Option A: Environment variables
export HUB_IP=192.168.1.120

# Option B: Edit udi_broadlink.py (for testing)
# Line 95: hub_ip = '192.168.1.120'

# Run
python udi_broadlink.py
```

**Expected Output:**
```
INFO:udi_interface.Logger:BroadlinkNodeServer initialized.
INFO:udi_interface.Logger:Node server starting...
INFO:udi_interface.Logger:Attempting to discover Broadlink hub at 192.168.1.120...
INFO:udi_interface.Logger:Hub authenticated successfully.
INFO:udi_interface.Logger:Parent nodes verified/created.
INFO:udi_interface.Logger:ADDNODEDONE event received. Nodes fully registered.
INFO:udi_interface.Logger:Node server ready flag set to True.
```

---

## PG3 Installation

### 1. Create Node Server

In **Polyglot v3 Dashboard**:
- Click **nodeServers** → **Add a Node Server**
- Choose **Python Node Servers** category
- Find **Broadlink Remote** (or paste GitHub URL)
- Click **Install**

### 2. Configure Parameters

After install, click **Configuration**:

| Parameter | Required? | Example |
|-----------|-----------|---------|
| USER_ID | Yes | `admin` |
| USER_PASSWORD | Yes | `password123` |
| HUB_IP | **Required** | `192.168.1.120` |
| WIFI_SSID | No (AP only) | `MySSID` |
| WIFI_PASSWORD | No (AP only) | `WiFiPwd` |
| WIFI_SECURITY_MODE | No (AP only) | `4` (WPA) |
| SETUP_IP | No (AP only) | `255.255.255.255` |
| IR_CODES | No | See below |
| RF_CODES | No | See below |

### 3. Add Pre-Configured Codes (Optional)

**IR_CODES** and **RF_CODES** support two formats:

**JSON Format** (recommended):
```json
{
  "TV Power": "2600d200949512949512...",
  "Volume Up": "2600d200949512...",
  "Volume Down": "2600d200949512..."
}
```

**Key=Value Format**:
```
TV Power=2600d200949512...
Volume Up=2600d200949512...
Volume Down=2600d200949512...
```

**Base64 Format** (with prefix):
```json
{
  "Receiver Power": "b64:AAECAw==",
  "Receiver Volume Up": "b64:AAECAw=="
}
```

### 4. Start & Verify

Click **Install** and **Start**.

**In ISY/IoX Admin Console:**
- Navigate to **Setup** → **Nodes**
- You should see:
  - Broadlink Setup (controller)
  - Broadlink IR (parent)
  - Broadlink RF (parent)
  - Any pre-configured codes under respective parents

---

## Learn Your First Code

### IR Code Learning

1. Go to **ISY/IoX Admin Console** → **Broadlink IR** node
2. Click **Learn IR Code** command
3. Within 30 seconds, point your IR remote at the device and press a button
4. Monitor the **Learning Progress** (GV0 driver) on the IR parent node
5. A new subnode appears: "Learned IR 1234"
6. **Rename** the node (click node name) to something meaningful (e.g., "TV Power")
   - Name persists across restarts automatically ✓

### RF Code Learning (2-Step)

1. Go to **Broadlink RF** node
2. Click **Learn RF Code** command
3. **RF Learning is a 2-step process:**
   - **Step 1: Frequency Sweep** (10% → 25%) — Just wait
   - **Pause: 2 seconds** (required by Broadlink)
   - **Step 2: Learn Code** (40% → 100%) — Trigger RF remote/device
4. New subnode appears under **Broadlink RF**
5. Rename for clarity

---

## Send a Code

### Option 1: From Admin Console

1. Find the code subnode (e.g., "TV Power")
2. Click **Send Code** command
3. Hub transmits the IR/RF packet immediately

### Option 2: From Automation

**ISY Programs:**
```
IF
   (some condition)

THEN
   'Broadlink IR' / 'TV Power' Send Code

ELSE
   (nothing)
```

Or use **ISY Automation Rules** (newer ISY25 syntax):

```
Trigger: When 'Living Room' / 'Wireless Switch' is switched Off
Action: Send 'Broadlink IR' / 'TV Power' Send Code
```

---

## Directory Structure

After installation, your node server folder contains:

```
udi_Broadlink/
├── udi_broadlink.py          # Main entry point (executable)
├── nodes.py                   # Node classes: Setup, IR, RF, Code
├── config_parser.py           # Config validation & parsing
├── broadlink_client.py        # Broadlink API wrapper
├── requirements.txt           # Dependencies (udi_interface, broadlink)
├── server.json               # PG3 manifest (name, executable, etc)
├── POLYGLOT_CONFIG.md        # Config guide
├── README.md                 # General documentation
├── IMPLEMENTATION_GUIDE.md   # Detailed API reference
├── ARCHITECTURE.md           # Technical deep-dive
├── LICENSE.md                # MIT license
└── .git/                     # Git version control
```

---

## Node Server Status

### Viewing Status

**Online Status:**
- **Broadlink Setup** node → **ST** driver
  - 0 = Hub offline / discovering
  - 1 = Hub online and authenticated

**Learning Progress:**
- **Broadlink IR** node → **GV0** driver (0-100%)
- **Broadlink RF** node → **GV0** driver (0-100%)

**Code Status:**
- Each code subnode → **ST** driver (momentary toggle when sent)

### Viewing Logs

**In PG3:**
- Dashboard → Node Server → **Logs**
- Search for `Broadlink` or error terms

**Local Testing:**
```bash
python udi_broadlink.py 2>&1 | grep -i error
```

---

## Troubleshooting

### Hub Not Found

**Symptom:** PG3 shows notice "Broadlink hub not found."

**Solutions:**
1. Verify IP: `ping 192.168.1.120`
2. Check firewall: Hub listens on port 80
3. Restart hub (power cycle)
4. Update **HUB_IP** in PG3 Configuration
5. Click **Restart Node Server**

### Learning Timeout

**Symptom:** GV0 reaches 100% but no subnode appears.

**Solutions:**
1. Aim remote/RF device directly at the hub
2. Try again in 5 seconds (device may need cooldown)
3. Check hub temp hasn't exceeded limit
4. Some remotes use different protocols; may not be learnable

### Code Won't Transmit

**Symptom:** Click "Send Code" but device doesn't respond.

**Solutions:**
1. Verify code was learned (check logs)
2. Re-learn the code
3. Test with known-working code (pre-configured)
4. Check hub has line-of-sight to IR receiver

### Service Crashes

**Symptomatic:** Node server stops running.

**Solutions:**
- Should not happen with this implementation (robust error handling)
- Check logs for exceptions
- Restart node server from PG3
- Report issue with log snippet

---

## Common Tasks

### Rename a Learned Code

1. In **ISY/IoX Admin Console**, find the code node (e.g., "Learned IR 1234")
2. Right-click node → **Rename**
3. Type new name (e.g., "Living Room TV Power")
4. Apply
5. Name persists across service restarts ✓ (synced via longPoll)

### Delete a Learned Code

1. Right-click code node in ISY/IoX
2. **Delete** (or **Remove**)
3. Confirm

**Note:** Manually deletion does not remove from customData yet. To fully remove, you'd need to edit `polyglot.customData` directly (advanced). For now, renamed codes simply remain in storage.

### Provision Device in AP Mode

If your Broadlink device is in **AP (Access Point) mode**:

1. Configure:
   - **WIFI_SSID**: Your target network SSID
   - **WIFI_PASSWORD**: Your network password
   - **WIFI_SECURITY_MODE**: 4 (WPA, most common)

2. In **ISY/IoX**, select **Broadlink Setup** node
3. Click **Provision AP Setup** command
4. Device will connect to your network within 30 seconds
5. Update **HUB_IP** with device's new IP address
6. Restart node server

### Backup Learned Codes

Learned codes are stored in `polyglot.customData` (persistent JSON file).

**To backup:**
1. In PG3, click **Node Server** → **Custom Data**
2. Copy the JSON content
3. Save to file or paste elsewhere

---

## Performance Tips

### For Large Code Libraries

If you have 50+ learned codes:

1. **Use shortPoll frequency**: Already optimized (60s)
2. **Avoid real-time learning**: Use offline tools for bulk code capture
3. **Organize by parent**: IR and RF parents keep tree manageable

### Network Optimization

- **Hub closer to network**: Reduces latency
- **2.4 GHz Wi-Fi preferred**: RM4 devices typically older chips
- **Avoid power line interference**: Don't plug hub next to other electronics

---

## Advanced: Local Testing with Mock Hub

To test without a real hub, modify `broadlink_client.py`:

```python
class MockBroadlinkDevice:
    def __init__(self):
        self.timeout = 5
    
    def auth(self):
        return True
    
    def enter_learning(self):
        return True
    
    def check_data(self):
        # Return mock IR packet
        return bytes.fromhex('2600d20094951294...')
```

Then in `udi_broadlink.py`:
```python
# Testing only
# hub = MockBroadlinkDevice()
```

---

## Next Steps

1. **Learn a few codes** (IR and RF)
2. **Rename them** meaningfully
3. **Create ISY programs** that use Send Code commands
4. **Automate**: Trigger on time, switch, or scene
5. **Scale**: Add more devices or integrate with voice assistants

---

## Support & Resources

- **UDI Polyglot Forum**: https://forum.universaldevices.com/
- **GitHub Issues**: https://github.com/chris/udi_Broadlink/issues
- **Broadlink Docs**: https://github.com/mjg59/python-broadlink
- **ISY Developer Docs**: https://docs.universaldevices.com/

---

## FAQ

**Q: Can I control multiple Broadlink hubs?**  
A: Not yet; this version supports one hub. Future versions will support hub selection.

**Q: Can I record macro sequences (multiple codes in sequence)?**  
A: Not currently; future enhancement. For now, create multiple subnodes and trigger in sequence.

**Q: Does it work with Broadlink SmartPlug, Temperature Sensor, etc.?**  
A: Not yet; this version targets RM (remote) devices only. Extensible architecture for future device types.

**Q: What's the learning code timeout?**  
A: 30 seconds for IR, 20 seconds for RF. Increase in `nodes.py` `_learn_code_thread()` if needed.

**Q: Can names be persisted without manual rename?**  
A: Yes; use `IR_CODES` or `RF_CODES` parameters with your preferred names, and codes are created with those names automatically.

---

**Version:** 0.1.0  
**Last Updated:** 2026-03-17
