Act as a Python Expert specializing in Universal Devices (UDI) Node Servers. 
Goal: Create a Node Server template using the udi_interface udi_interface library to integrate home automation devices.  This must serve as the bases for differnt node servers for different home automation system - one node server per vendor 


Architecture:
1. The node server must be able to take some parameters input through customParams.  It can must save stored data in customData and not files
2. The node should create nodes and up to one layer of subnodes during start up.  Care must be taken to ensure nodes are created before starting to address them.
3. ISY is the main controller controlling the node - the node can provide updated data bad to the ISY and can send change commands, but most actions originate from ISY.  Update can happen through polls (long and or short) or when data is pushed from the homeautomation API 



Functional Requirements:
-Python code
-Careful sequencing is required when initalizing the system.  It is a multi threaded environment 
- Use the 'ADDNODEDONE' event or a 'ready' flag to ensure nodes are fully registered before attempting to update drivers or add sub-nodes.
-Parameters to support the home automation API must be passed through customPsrams.
-Data stored must be stored in customData
-If nodes are renames in the ISY, the code must detect this and store it so it is remember next time system starts



Technical Constraints:

- Use udi_interface API. https://github.com/UniversalDevicesInc/udi_python_interface
- refer to documentation on using udi_interface https://github.com/UniversalDevicesInc/udi_python_interface/blob/master/API.md
- Implement robust logging use differnt level for relevance for all traffic 
- Wrap Home Automaation calls calls in try-except blocks to prevent service crashes.
- Use 'shortPoll' for a simple heartbeat functionality.
-if possible use the new JSON approach to profiles, but if not the traditional profile directory structure must be maintained 

Please provide the 'controller.py' and 'nodes' class definitions.

Key Technical Advice for your Implementation
The "Ready" Flag: In PG3, the start() method is asynchronous. I recommend setting self.ready = False in __init__ and switching it to True only after the STOPSYNC or ADDNODEDONE event for your primary nodes.

Node Renaming: The UDI interface doesn't always "push" a name change event. Your idea of checking in longPoll is the most reliable way to sync the internal database with what the user typed in the Admin Console.

Follow some of the start flow approaces amd node creation (with sub nodes) used in e.g. https://github.com/Panda88CO/udi-yolink