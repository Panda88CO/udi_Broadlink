# Broadlink Node Server Configuration

## Required Parameters

- `USER_ID`: User identifier for your Broadlink setup (stored for compatibility/future cloud extensions)
- `USER_PASSWORD`: User password (stored for compatibility/future cloud extensions)
- `HUB_IP`: IP address of your Broadlink RM hub (for example `192.168.1.120`)

## AP Provisioning Parameters (broadlink.setup)

Use these only when provisioning a device in AP mode:

- `WIFI_SSID`: target Wi-Fi SSID
- `WIFI_PASSWORD`: target Wi-Fi password
- `WIFI_SECURITY_MODE`: `0..4` (`4` = WPA1/2 default)
- `SETUP_IP`: destination IP for setup packet (default `255.255.255.255`)

After setting these, run the setup-node command `Provision AP Setup`.

## Code Configuration

Two parameters define the transmit codes and automatically create subnodes:

- `IR_CODES`
- `RF_CODES`

Both support either JSON or `key=value` lines.

### JSON example
```json
{
  "TV Power": "2600d200949512...",
  "Receiver Vol Up": "b64:AAECAwQFBgc..."
}
```

### key/value example
```text
TV Power=2600d200949512...
Receiver Vol Up=b64:AAECAwQFBgc...
```

Encoding options:
- Hex (default)
- Base64 with `b64:` prefix

## Operational Notes

- Changing `IR_CODES` or `RF_CODES` updates the code subnodes.
- Each code subnode has a `TXCODE` command to send its packet.
- IR and RF parent nodes support `LEARNCODE` to learn packets directly from the hub and create subnodes automatically.
- Setup node supports `APSETUP` ("Provision AP Setup") which calls `broadlink.setup(...)`.
- `shortPoll` provides heartbeat updates.
- `longPoll` refreshes Broadlink connectivity state.
