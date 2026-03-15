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

Define each transmit code as its own custom parameter:

- `IR_<name>` for IR codes
- `RF_<name>` for RF codes

The `<name>` portion becomes the code node name.

### Example
```text
IR_TV_POWER=2600d200949512...
IR_RECEIVER_VOL_UP=b64:AAECAwQFBgc...
RF_FAN_ON=aa55...
RF_FAN_OFF=bb66...
```

Encoding options:
- Hex (default)
- Base64 with `b64:` prefix

## Operational Notes

- Changing any `IR_*` or `RF_*` parameter updates the code subnodes.
- Each code subnode has a `TXCODE` command to send its packet.
- IR and RF parent nodes support `LEARNCODE` to learn packets directly from the hub and create subnodes automatically.
- Setup node supports `APSETUP` ("Provision AP Setup") which calls `broadlink.setup(...)`.
- `shortPoll` provides heartbeat updates.
- `longPoll` refreshes Broadlink connectivity state.
