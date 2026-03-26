# profile_json.py
# udi_interface DynamicProfile JSON equivalent for Broadlink IR/RF nodes.
# Mirrors profile/nodedef/nodedefs.xml, profile/editor/editors.xml, and profile/nls/en_us.txt
PROFILE = {
  "version": "1.0",
  "nodedefs": [
    {
      "def_id": "blirremote",
      "nls": "nlsblirremote",
      "sts": [
        {"id": "ST",  "editor": "txstatus"},
        {"id": "GV0", "editor": "count"},
        {"id": "GV30","editor": "yesno"},
        {"id": "TIME","editor": "unixtime"}
      ],
      "cmds": {"accepts": ["UPDATE", "QUERY", "LEARNCODE"]}
    },
    {
      "def_id": "blrfremote",
      "nls": "nlsblrfremote",
      "sts": [
        {"id": "ST",  "editor": "txstatus"},
        {"id": "GV0", "editor": "count"},
        {"id": "GV30","editor": "yesno"},
        {"id": "TIME","editor": "unixtime"}
      ],
      "cmds": {"accepts": ["UPDATE", "QUERY", "LEARNCODE"]}
    },
    {
      "def_id": "blircode",
      "nls": "nlsblircode",
      "sts": [
        {"id": "ST",  "editor": "txstatus"},
        {"id": "GV30","editor": "yesno"},
        {"id": "TIME","editor": "unixtime"}
      ],
      "cmds": {"accepts": ["TXCODE", "QUERY"]}
    },
    {
      "def_id": "blrfcode",
      "nls": "nlsblrfcode",
      "sts": [
        {"id": "ST",  "editor": "txstatus"},
        {"id": "GV30","editor": "yesno"},
        {"id": "TIME","editor": "unixtime"}
      ],
      "cmds": {"accepts": ["TXCODE", "QUERY"]}
    },
    {
      "def_id": "setup",
      "nls": "nlssetup",
      "sts": [
        {"id": "ST",  "editor": "connect"},
        {"id": "GV1", "editor": "yesno"},
        {"id": "TIME","editor": "unixtime"}
      ],
      "cmds": {"sends": ["DON", "DOF"], "accepts": ["UPDATE", "APSETUP"]}
    }
  ],
  "editors": [
    {"id": "connect",  "range": {"uom": 25, "subset": [0,1,2], "nls": "connect"}},
    {"id": "yesno",    "range": {"uom": 25, "subset": [0,1], "nls": "yesno"}},
    {"id": "txstatus", "range": {"uom": 25, "subset": [0,1,2,99], "nls": "txstatus"}},
    {"id": "count",    "range": {"uom": 56, "min": 0, "max": 255, "step": 1}},
    {"id": "unixtime", "range": {"uom": 151, "min": 0, "max": 2147483647, "step": 1}}
  ],
  "nls": {
    "en_us": {
      "ND-setup-NAME": "Broadlink Setup",
      "ND-blirremote-NAME": "Broadlink IR Remote",
      "ND-blrfremote-NAME": "Broadlink RF Remote",
      "ND-blircode-NAME": "IR Code",
      "ND-blrfcode-NAME": "RF Code",

      "ST-nlssetup-ST-NAME": "Node Server Status",
      "ST-nlssetup-GV1-NAME": "Broadlink Connected",
      "ST-nlssetup-TIME-NAME": "Last Poll Time",
      "CMD-nlssetup-DON-NAME": "Heartbeat On",
      "CMD-nlssetup-DOF-NAME": "Heartbeat Off",
      "CMD-nlssetup-UPDATE-NAME": "Reload Configuration",
      "CMD-nlssetup-APSETUP-NAME": "Provision AP Setup",

      "ST-nlsblirremote-ST-NAME": "IR Last Command Status",
      "ST-nlsblirremote-GV0-NAME": "IR Configured Codes",
      "ST-nlsblirremote-GV30-NAME": "IR Hub Online",
      "ST-nlsblirremote-TIME-NAME": "IR Last Update",
      "CMD-nlsblirremote-UPDATE-NAME": "Update Status",
      "CMD-nlsblirremote-QUERY-NAME": "Query",
      "CMD-nlsblirremote-LEARNCODE-NAME": "Learn IR Code",

      "ST-nlsblrfremote-ST-NAME": "RF Last Command Status",
      "ST-nlsblrfremote-GV0-NAME": "RF Configured Codes",
      "ST-nlsblrfremote-GV30-NAME": "RF Hub Online",
      "ST-nlsblrfremote-TIME-NAME": "RF Last Update",
      "CMD-nlsblrfremote-UPDATE-NAME": "Update Status",
      "CMD-nlsblrfremote-QUERY-NAME": "Query",
      "CMD-nlsblrfremote-LEARNCODE-NAME": "Learn RF Code",

      "ST-nlsblircode-ST-NAME": "IR Send Status",
      "ST-nlsblircode-GV30-NAME": "IR Code Node Online",
      "ST-nlsblircode-TIME-NAME": "IR Last Transmit Attempt",
      "CMD-nlsblircode-TXCODE-NAME": "Send IR Code",

      "ST-nlsblrfcode-ST-NAME": "RF Send Status",
      "ST-nlsblrfcode-GV30-NAME": "RF Code Node Online",
      "ST-nlsblrfcode-TIME-NAME": "RF Last Transmit Attempt",
      "CMD-nlsblrfcode-TXCODE-NAME": "Send RF Code",

      "connect-0": "Disconnected",
      "connect-1": "Connected",
      "connect-2": "Failed",
      "yesno-0": "No",
      "yesno-1": "Yes",
      "txstatus-0": "Idle",
      "txstatus-1": "Success",
      "txstatus-2": "Failed",
      "txstatus-99": "Unknown"
    }
  }
}
