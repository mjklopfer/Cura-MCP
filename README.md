# Cura MCP

A local MCP platform for the **UltiMaker S5** and **Cura**, with a loopback Cura
plugin, a dependency-free Node stdio MCP server, guarded printer operations, and
S5 R1 hardware/protocol research. Independent community project; not affiliated
with or supported by UltiMaker.

## Reference configuration

| Component | Version |
|---|---|
| Printer | UltiMaker S5 R1 |
| Printer firmware | **9.0.3.0** |
| UltiMaker Cura | **5.14.0** |

These are the versions used for the documented integration. Other versions
require validation; see [tested versions](docs/TESTED.md).

## What it provides

- Inspect Cura's machine, extruders, settings, scene and slicer state.
- Load models/projects, change settings, request slicing and export G-code.
- Place and transform models, set per-model overrides, select profiles, inspect
  layers, capture previews, and compare slicing variants using the
  [sample STL](examples/comparison-sample.stl).
- Discover native extension menus and queue local Cura package operations.
- Save a native full-workspace 3MF project: Save, Save As with a new filename,
  Save As in another folder, and asynchronous completion/status.
- Inspect a catalog of **130 local API paths / 161 HTTP operations**, including
  queue/status, temperatures, materials, diagnostics and system configuration.
- Read bounded printer endpoints and perform explicitly confirmed writes through
  the catalog. Upload and start are separate actions; uploading may still trigger
  the printer's own queue policy when idle.
- Review original S5 R1 PCB/serial/GPIO notes and a disabled-by-default two-STM32
  UMB accessory-controller draft with separate Air Manager and Material Station roles.
- Follow optional developer SSH procedures for Linux/service/device inspection,
  D-Bus diagnostics and actual printer-touchscreen capture.

Configure your printer address during deployment. See the
[deployment guide](docs/DEPLOYMENT.md) for setup and connection requirements.

```text
MCP client --stdio--> Node MCP server --loopback token--> Cura plugin --> Cura
                              |
                              +--configured LAN HTTP API--> S5
```

## Start here

1. Read the [Windows/Mac configuration comparison](docs/PLATFORM_CONFIGURATIONS.md),
   [macOS guide](docs/MACOS.md), [Windows guide](docs/WINDOWS.md) and [deployment](docs/DEPLOYMENT.md) and install the plugin while Cura is closed.
2. Set `CURA_PRINTER_BASE_URL`, the staging folder and connection-file path.
3. Start `node src/server.mjs` through your MCP client's stdio configuration.
4. Begin with `cura_status` and `printer_api_catalog`. Writes require exact-action
   authorization and a matching short-lived confirmation token.

See the [26-tool reference](docs/TOOLS.md), [tested versions](docs/TESTED.md),
[known shortcomings and TODOs](docs/KNOWN_ISSUES.md), and [security/privacy](SECURITY.md).
These upstream repositories are particularly relevant to extending the bridge
and investigating the printer hardware:

| Repository | Why it is useful |
|---|---|
| [Cura](https://github.com/Ultimaker/Cura/tree/5.13.0) / [Uranium](https://github.com/Ultimaker/Uranium/tree/5.13.0) | Native APIs for object movement/undo, profile selection, slicing and printer-upload workflows; foundations for additional bridge endpoints. |
| [CuraLiveScriptingPlugin](https://github.com/Ultimaker/CuraLiveScriptingPlugin) | Examples of accessing Cura settings and application internals. Older SDK/QML and background script execution require review before reuse. |
| [um-kernel](https://github.com/Ultimaker/um-kernel/tree/master/sun7i) | A20-era device trees, board identification, boot and recovery handling. A separate newer-board UMB drive-enable fix offers a tracing clue, not an R1 pinout. |
| [UltimakerMarlin](https://github.com/Ultimaker/UltimakerMarlin/tree/S-line) | Motion/heater interfaces and print-core EEPROM command handlers; upstream code must be checked against installed firmware. |
| [nfc_test](https://github.com/Ultimaker/nfc_test) / [m2m_certificates](https://github.com/Ultimaker/m2m_certificates) | Direct-reader NFC test configuration and NDEF certificate formats; neither establishes the complete Material Station UMB implementation. |
| [oib_testbench](https://github.com/Ultimaker/oib_testbench) / [Ultimaker3 hardware](https://github.com/Ultimaker/Ultimaker3) | Older interface-board GPIO/loopback and hardware references for tracing related circuitry; not a verified S5 R1 schematic. |
| [ulticontroller_interface_tester](https://github.com/Ultimaker/ulticontroller_interface_tester) / [framebuffer-vncserver](https://github.com/Ultimaker/framebuffer-vncserver) | Touchscreen diagnostics and remote display/input references; actual S5 UI routing and compatibility still need validation. |

See the [upstream research map](docs/UPSTREAM_RESEARCH.md) for inspected files,
version references and unresolved questions. These are research references;
their features are not all implemented or validated by this project.
Hardware notes start at [S5 R1 interfaces](hardware/S5_R1_INTERFACES.md);
the [UMB controller](hardware/umb-controller/README.md) is a separate offline draft.
See [miscellaneous notes](hardware/MISC_NOTES.md) for print-core identity versus
Cura settings, source-observed EEPROM commands and the older UM2 board reference.
For optional printer-side screen capture and experimental UI input, see
[developer-mode touchscreen access](docs/DEVELOPER_TOUCHSCREEN.md).
The [SSH access and capabilities guide](docs/SSH_ACCESS.md) explains the broader
Linux troubleshooting/maintenance access and its limits; SSH is not an additional
implemented MCP tool.

## Requirements and checks

- Cura **5.14.0** is the live test target for this release. For a 5.13 installation, set `CURA_MCP_CURA_VERSION=5.13` for the installer and MCP runtime. An explicit `CURA_MCP_BRIDGE_CONNECTION_PATH` overrides the runtime default.
- See [version differences](docs/CURA_VERSION_DIFFERENCES.md) for the 5.13 and 5.14 deployment requirements. The [scene operations](docs/CURA_SCENE_OPERATIONS.md), [configuration and profiles](docs/CURA_CONFIGURATION.md), and [navigation and extensions](docs/CURA_NAVIGATION_AND_EXTENSIONS.md) notes cover the desktop tools and their parameters.
- Node.js 20+ and Python 3.10+; Cura supplies its own Qt/Python plugin runtime.
- macOS Keychain or Windows Credential Manager for printer Digest pairing.
- A C++11 compiler is needed only for the optional offline controller tests.

From the repository root:

```sh
node --test
python -m unittest discover -s tests -p 'test_*.py'
python scripts/privacy_check.py
```

From `hardware/umb-controller`, run `python tools/run_tests.py` for native/stub
controller checks. These tests do not connect to a real printer. Never treat
offline tests, an accepted request or a sliced file as proof of a successful print.

## Release and attribution

Release **0.1.8** targets Cura 5.14.0 and includes an original STL sample for
testing slice comparisons.
The repository also includes the two-STM32 controller draft and hardware/NFC research.
See [changelog](CHANGELOG.md), [sanitization policy](docs/SANITIZATION.md),
[source references](hardware/SOURCES.md), [notices](NOTICE.md) and [MIT license](LICENSE).
Vendor firmware, recovery images, service source dumps, raw device captures,
third-party model files and proprietary schematics are not redistributed.
