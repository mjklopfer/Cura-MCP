# Windows PC and macOS configurations

These are reproducible configurations, not exported workstation settings. All
printer origins are blank in the example files and must be supplied by the user.
No original accounts, hostnames, user paths or device identifiers are included.

| Item | Windows PC | macOS |
|---|---|---|
| Cura target | 5.14.0 | 5.14.0 |
| Printer interface baseline | S5 R1, firmware 9.0.3.0 | Same local HTTP interface; no hardcoded printer origin |
| Node | Node 22 used for offline checks; minimum accepted by code is 20 | Same requirement; use a maintained release, with Node 22 as the tested baseline |
| External Python | Python 3.10+ for printer transport/tools; CI uses 3.12 | Python 3.10+; separate from Cura's bundled Python |
| Plugin runtime | Cura's own Python/Qt/Uranium | Cura's own Python/Qt/Uranium |
| MCP transport | Local stdio Node process | Local stdio via Node or the provided Bash launcher |
| Cura listener | 127.0.0.1, port 49621 | Same, on the Mac itself |
| Config discovery | APPDATA/cura/5.14 | Home-relative Library/Application Support/cura/5.14 |
| Plugin directory | Config directory/plugins/CuraMcpBridge | Same relative plugin layout |
| Connection file | Config directory/cura-mcp-bridge.json | Same filename; generated independently on each machine |
| Pairing storage | Windows Credential Manager | macOS Keychain |
| Staging | Explicit shared user Documents folder recommended | Explicit user Application Support/Documents folder; launcher has a default |
| Launch environment | Use absolute Node/Python paths in MCP client | Finder/services may lack shell PATH; launcher handles common runtime locations |
| Example | [Windows client template](../examples/mcp-client-windows.json) | [Mac client template](../examples/mcp-client-macos.json) |
| Walkthrough | [Windows](WINDOWS.md) | [macOS](MACOS.md) |

The earlier Windows Cura workflow established live settings, staging/load,
slicing/export and native Save/Save As behavior on Cura 5.13.0. Hosted CI tests
the bridge against mocks on Windows, macOS and Linux. A complete live Mac Cura
deployment of the current public build has not been established. Exact desktop
OS releases, Mac CPU and installation-specific runtime paths are not claimed as
a tested compatibility matrix. See [tested versions](TESTED.md).

Each workstation runs its own Cura plugin, connection token and MCP process.
Do not copy tokens or credential-store contents between systems. If both clients
target one printer, coordinate write operations: the queue/hardware is shared,
even when the Cura applications and MCP processes are independent.

A Windows project path does not become a valid Mac path. Transfer the actual
project/model to the receiving workstation's staging directory, use its local
absolute path and resolve any native material/machine import conflicts. Inspect
core/material/extruder assignments before slicing; portability of a 3MF file does
not establish identical profiles or safe print parameters on another setup.
