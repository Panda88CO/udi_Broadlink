Act as a Python Expert specializing in Universal Devices (UDI) Node Servers. 
Goal: Create a Node Server using the udi_interface (PG3) library to integrate Broadlink devices (RM4 Pro) for IR/RF learning and transmission.

Architecture:
1. Controller Node (Hub): Represents the RM4 Pro.
2. Service Nodes: Two child nodes—one for "RF Control" and one for "IR Control".
3. Dynamic Sub-nodes: When a code is learned, create a new node under the respective Service Node (e.g., RF_code1).

Functional Requirements:
- Discovery: Use 'broadlink.discover()' to find the hub. Handle "Hub Not Found" with a Node Server Notice (do not crash).
- Learning Logic: 
    - IR: Use 'enter_learning()' and 'check_data()'.
    - RF: Implement the 2-step process (sweep frequency first, then learn). 
    - State Management: Update a driver with UOM 25 (0-100%) to show learning progress. Include a 2-second sleep between frequency sweep and packet capture.
- Persistence: Store learned codes (Base64/Hex) and their custom names in 'polyglot.customData'. 
- Sync/Renaming: In the 'longPoll' (every 10 mins), check if a user renamed a node in the UI. Update 'customData' so names persist across restarts.
- Startup Flow: Use the 'ADDNODEDONE' event or a 'ready' flag to ensure nodes are fully registered before attempting to update drivers or add sub-nodes.

Technical Constraints:
- Use 'python-broadlink' API.
- Implement robust logging for all Broadlink traffic (sent/received).
- Wrap Broadlink network calls in try-except blocks to prevent service crashes.
- Use 'shortPoll' for a simple heartbeat driver.

Please provide the 'controller.py' and 'nodes' class definitions.
Key Technical Advice for your Implementation
The "Ready" Flag: In PG3, the start() method is asynchronous. I recommend setting self.ready = False in __init__ and switching it to True only after the STOPSYNC or ADDNODEDONE event for your primary nodes.

Node Renaming: The UDI interface doesn't always "push" a name change event. Your idea of checking in longPoll is the most reliable way to sync the internal database with what the user typed in the Admin Console.

Broadlink Timeout: The broadlink library can be finicky with network timeouts. Ensure you set a explicit timeout value (e.g., 5 seconds) when initializing the device object.