# MCP tools

There are 26 tools. The [complete local HTTP inventory](ENDPOINTS.csv) lists every method/path. Read-only inspection of Cura
uses an authenticated loopback POST internally to schedule work on Cura's main
thread; it does not imply a printer write.

| Tool | Purpose |
|---|---|
| cura_status | Read loopback bridge status |
| printer_status | Read printer/cluster job status |
| preflight_print_action | Check requested upload/start readiness |
| create_print_confirmation | Bind upload/start to an exact request and state |
| upload_gcode | Transfer an authorized staged printable file |
| start_print | Explicitly start the authorized queued job |
| create_cura_confirmation | Bind a staged file load and project/model mode |
| load_cura_file | Load the authorized model/project into Cura |
| printer_api_catalog | List printer/cluster method/path inventories and schemas |
| printer_api_read | Read bounded supported GET endpoints |
| confirm_printer_api_write | Prepare a one-use printer write confirmation |
| printer_api_write | Execute the matching authorized printer write |
| cura_inspect | Inspect Cura's configured machine, settings/scene/backend context |
| cura_settings | Read effective global/extruder setting values |
| cura_configuration | Inspect printer, material, core, intent, and profile choices |
| cura_extensions | List extensions, native menus, packages and post-processing scripts |
| cura_navigate | Open a supported Cura stage, tool, or dialog |
| cura_snapshot | Capture a native PNG of the active plate |
| cura_estimates | Read duration and material estimates for the active sliced plate |
| cura_layers | Inspect layer markers, feature types and tool changes |
| cura_comparison_status | Poll a slice comparison |
| cura_comparison_cancel | Cancel a comparison and restore temporary settings |
| confirm_cura_operation | Bind a desktop action to an exact request and applicable state |
| cura_operation | Execute the authorized Cura operation |
| cura_project_save_status | Poll native project-save completion or failure |
| cura_path_info | Check a path from Cura's process without returning its contents |

The catalog exposes 94 printer templates/120 operations and 36 cluster templates/
41 operations. Each method is discovered through existing generic tools rather
than adding one MCP tool per printer control. Structural interface schemas are
preserved; vendor prose and examples are omitted from this public release.
Wi-Fi status GET is a separately attributed interface supplement, not a guessed
write API. Unbounded camera streams and active diagnostic sampling remain blocked
by the read transport even when their schema appears in the catalog.

Write confirmations expire after five minutes, are one-use and bind the exact
request. Printer state is rechecked before execution. Most configuration/motion
writes are blocked while busy; confirmed job pause/resume/abort and the narrow
allowlisted operations still require explicit operator intent. The code does not
create an independent human UI approval step: the MCP client/operator must honor
the tool descriptions. A confirmation token alone is not evidence of human consent.

## Save and Save As

Prepare `confirm_cura_operation` with one of these argument objects, review its
resolved target, then call `cura_operation` with identical arguments plus the
returned confirmation token:

```json
{"action":"save_project","mode":"save"}
```

```json
{"action":"save_project","mode":"save_as","file_name":"example.3mf"}
```

```json
{"action":"save_project","mode":"save_as","file_name":"example.3mf","folder":"/path/to/projects","create_folder":true}
```

Save uses the known current project location and refuses an intervening file
change. Save As refuses an existing destination. If the path is not known, use
an explicit Save As. The native `ThreeMFWorkspaceWriter` runs through `UM.Job`;
archive structure and integrity are checked before atomic replacement. Poll the
returned `operation_id` with `cura_project_save_status` until completed or failed.
Do not assume acceptance equals completion or edit the workspace during a save.
