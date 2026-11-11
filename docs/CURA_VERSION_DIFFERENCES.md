# Cura 5.13.0 and 5.14.0 deployment differences

Runtime 0.1.11 adds local progress and webcam snapshot tools independent of
Cura's plugin APIs. They need only the local printer origin; no Cura plugin
update or desktop restart. Reconnect the MCP runtime to load the new tools.

Release 0.1.10 adds existing cloud profile discovery/selection via the native
machine and output-device managers. No local HTTP origin is required. Live
selection targets Windows Cura 5.14.0; 5.13/macOS behavior remains unverified.
Reconnect the MCP runtime after updating to discover the three connection tools.

Release 0.1.9 adds a native UM3NetworkPrinting cloud adapter. Its source-level
integration targets Cura 5.14.0, including internal cached account/upload
attributes. Offline cloud guards are tested; live 5.13 and macOS cloud writes
remain unverified. Update both plugin and MCP runtime, then restart Cura and
reconnect the MCP client to discover the four new tools. See
[cloud workflow](CLOUD_PRINTING.md) for exact boundaries.

| Item | Cura 5.13.0 | Cura 5.14.0 |
| --- | --- | --- |
| UltiMaker SDK | 8.12.x | 8.13.x |
| Windows profile root | `%APPDATA%\cura\5.13` | `%APPDATA%\cura\5.14` |
| macOS profile root | `~/Library/Application Support/cura/5.13` | `~/Library/Application Support/cura/5.14` |
| Installer and MCP runtime | Set `CURA_MCP_CURA_VERSION=5.13` or supply explicit paths | Default target |
| Native Pause at Height layer field | Integer layer setting with Redo Layer | Text field for the last completed Preview layer, with no Redo Layer setting |
| Earlier live coverage | Configuration and extension discovery, preset listing and confirmation preview | Scene controls, estimates, layer inspection, profile export, package inventory, and new comparison smoke testing |

Install the plugin under `plugins/CuraMcpBridge` inside the selected profile
root. The plugin uses Uranium's configuration storage path and writes
`cura-mcp-bridge.json` in the profile of the running Cura instance. The MCP
server reads that version's file. An explicit
`CURA_MCP_BRIDGE_CONNECTION_PATH` takes precedence over
`CURA_MCP_CURA_VERSION`. Change the explicit path when upgrading an existing
Codex configuration. Both versions use loopback port 49621. Run one
bridge-enabled Cura instance at a time.

For Windows PowerShell, set `$env:CURA_MCP_CURA_VERSION = '5.13'` before
running the installer for 5.13. For macOS, export the same environment
variable before running the installer or launcher. Restart Cura after
installing the plugin and restart the MCP connection after updating its
tool catalog.

The same source tree targets both versions. The latest changes were
developed against 5.14.0. They use native Cura package queues and extension
menus. In 5.14.0 the package manager exposes pending-restart state as a
property. Comparison waits for the CuraEngine settings-change timer before
forcing a slice. Earlier 5.13 smoke results cover the earlier bridge
revision. Treat new commands on 5.13 as unverified until rerun there.

The bridge accepts the same zero-based `pause_layer` boundary in both versions.
In 5.14, `pause_layer: 23` sets the native field to text `"23"`. The pause follows
Preview layer 23 and precedes G-code layer 23. Export checks the position of the
single Griffin `M0` and verifies that the rest of the command sequence matches
the native slice.

The existing Tabbed Settings add-on reported that its installed build is
untested on Cura 5.14 and disabled itself. Native Cura settings and the
MCP comparison remained available. The separate 3D Model Assistant support
notice during model testing did not block either slice. Support
settings were left as configured for that comparison.

[UltiMaker Cura SDK version history](https://github.com/Ultimaker/Cura/wiki/SDK-Versions)
