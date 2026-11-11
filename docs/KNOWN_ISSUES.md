# Known shortcomings and TODO

## Cura bridge

- [ ] Investigate connector-level HTTP 429 handling: identify throttling layers,
  quota/concurrency conditions and Retry-After guidance using redacted diagnostics.
  Assess bounded read backoff without replaying state-changing requests whose
  execution outcome is uncertain. Distinguish connector availability from local
  Cura/printer availability.

- Cura 5.14.0 has live Windows smoke coverage. New operations on 5.13.0 and
  macOS need equivalent desktop tests.
- Native 3MF machine/material/settings conflict resolution can require Cura's UI.
- Current-project path tracking is reliable for bridge loads/saves; a native UI
  project open may clear the known path. Use explicit Save As rather than guessing.
- Scene IDs apply to the live scene. Undo/redo and full multiple-plate workflows
  need native wrappers.
- Printer, material and core switching and profile create/update/import need
  additional live tests.
- Detailed slice progress, cancellation, validation errors and stale-result identity
  are not exposed as complete workflows. Successful slicing is not a physical test.
- Local package queueing and native extension menu dispatch need live transaction
  tests. Remote Marketplace transactions and extension-specific dialog controls
  remain open.
- Save jobs should be observed until completion; workspace edits during saving are
  unsupported. Request retry after a timeout requires inspecting current state.

## Printer API

- Catalog inclusion does not prove firmware support, permission or safe execution.
  Firmware-specific behavior and many hazardous writes have not been exercised.
- The URL must be configured locally. No network discovery or automatic host is
  shipped. Printer HTTP may be cleartext; use a trusted LAN and secure local files.
- Secure Digest credential storage exists on Windows/macOS, not Linux.
- No automatic stale pairing cleanup or comprehensive reconnect UI is supplied.
- Camera streams and active diagnostic sampling are intentionally restricted.
- Cloud/team/registration routes found in shared web code are not exposed as local
  APIs: a local HTML fallback was not evidence of a functioning cloud endpoint.
- The three schemas are interface inventories, not complete request-body validators.
  Catalog parameters are checked for presence; callers must still follow their types.
- The stdio protocol is dependency-free and intentionally limited. Test compatibility
  with your MCP client; a public hosted MCP service or tunnel is not included.
- Developer-mode UI capture is a separate SSH/D-Bus procedure, not an MCP tool.
  Coordinate-based button input is untested and is not covered by MCP write guards;
  see [touchscreen access](DEVELOPER_TOUCHSCREEN.md).

## Hardware/controller research

- [ ] Compare installed A20 boot/DTB code with the reviewed sun7i sources and
  trace any R1 UMB enable circuitry. The i.MX8 drive-enable patch is a related
  platform clue, not a transferable pin map. Validate data-only microSD boot and
  mounting separately; job-spool expansion is not automatic.

- Exact external UMB pinout, voltage/signaling standard, electrical isolation,
  chaining and stock bootstrap remain unresolved. 115200 8E1 proves framing only.
- Accessory register permissions, delimiter behavior and dynamic indices need actual
  accessory captures. Linux consumer code is not complete accessory MCU firmware.
- The optional two-STM32 controller draft is disabled by default and has not passed real STM32 builds,
  SRAM/timer analysis, fan/motor test, stock enumeration or S5-connected test.
- Confirm fan model, power and control/tach levels before wiring; an assumed 24 V
  industrial fan does not establish the printer accessory connector's electricals.
- Add actual PWM/tach drivers, calibrated airflow conversion, motor/solenoid drivers,
  feeder/rewinder state machines, sensor fault handling and measured thermal tuning.
- Speaker routing remains unresolved without continuity or exact-board evidence.
- No bare-metal restoration or maintenance-SD boot was validated by this project.

Use existing Cura operations, scene/container APIs and documented printer routes
when extending the project. Keep UI operations on Cura's main thread, preserve
confirmation/staging guards, and add meaningful offline tests before hardware tests.
# Cloud tool activation and verification

The native cloud adapter requires both the 0.1.9 Cura plugin and MCP runtime.
After upgrading, restart Cura and reconnect the MCP client. Existing sessions
cache the earlier tool list and JavaScript modules; editing configuration or
files alone does not replace that running process. Native cloud discovery is
verified on Windows Cura 5.14.0. New-tool cloud submission remains unverified
with an actual new job; offline lifecycle tests are not physical validation.
See [cloud workflow](CLOUD_PRINTING.md).
