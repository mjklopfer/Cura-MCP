# Native Cura cloud printing

## Connect a preinstalled cloud printer

No local printer IP is required. The printer must already be added to Cura
and linked through its existing UltiMaker account session.

1. `cura_cloud_connections` lists installed cloud printer profiles with
   `machine_id`, current selection and available native cloud outputs.
2. `confirm_cura_cloud_connection` binds the exact installed `machine_id`
   and current selection to a five-minute one-use token.
3. `cura_cloud_connect` selects that profile, refreshes native connections
   and chooses the matching cloud output. It never creates a printer,
   signs in, uploads a file or starts a print.
4. Inspect `cura_cloud_connections` again. `selected` means the output is
   chosen; `connected`, `logged_in` and `active` establish readiness.
   `connecting` means discovery is pending. `pending_profile_selection`
   means a native switch/dialog has not completed.

Unknown/local-only profile IDs and stale confirmations are rejected. Changing
connections during uploads is blocked. Existing printer jobs continue.
Selecting another profile can change Cura materials/cores/settings and
invalidate a slice, so inspect configuration and slice after switching.
If account login expires, complete it manually in Cura.

Cura MCP uses the installed UM3NetworkPrinting `CloudOutputDevice`, including
its account session, native UFP export, upload and printer-queue request.
No cloud password, OAuth token or upload URL is returned to the MCP client.
Login remains in Cura's own interface; the bridge never automates login.

1. `cura_cloud_devices` lists explicit cloud device IDs/names and cached
   connection, login, printer and upload state. It makes no forced network
   request and does not select a default destination.
2. Slice through Cura and confirm `cura_estimates.available`.
3. `confirm_cura_cloud_print` takes the exact `device_id`. Its one-use,
   five-minute token binds the machine, active plate, scene, toolpath hash,
   postprocessing revision and destination name/ID.
4. `cura_cloud_print` uses that token and ID to invoke native `requestWrite`.
   The result is an asynchronous operation, not proof of delivery or start.
5. Poll `cura_cloud_print_status` with `operation_id`. Native `writeFinished`
   becomes `submitted_or_awaiting_approval`: Cura uses this same signal for
   successful submission and pending approval. Check destination job state
   separately to prove actual printing. `writeError` becomes `error`.

Submission may queue or start automatically under printer/cloud policy. It
does not cancel an existing print. Workspace changes are blocked during a
bridge-managed upload. Native uploads already running are also rejected.
Duplicate slice/destination submissions are blocked in the current Cura
session, including ambiguous failures. A native already-uploaded job is
rejected rather than silently invoking Cura's reprint behavior. No automatic
retry occurs. If a response times out, inspect `recent_operations` from cloud
discovery and the destination queue before retrying. History/duplicate guards
are session-local and are not durable across Cura restarts.

## Updating the local printer address

Local HTTP controls and cloud printing are independent routes. Create
`cura-mcp-printer.json` beside the selected `cura-mcp-bridge.json`:

```json
{"printer_origin":"http://printer-hostname.local"}
```

The user-local file is re-read for every operation, so DHCP changes do not
require a server restart. Set `CURA_MCP_PRINTER_CONFIG_PATH` to choose another
file. This file takes precedence over `CURA_PRINTER_BASE_URL`; an invalid
file fails closed instead of silently using an old environment address.
Without a file, the explicit environment origin is used. No host is bundled.

## Deployment and compatibility

Install the updated Cura plugin and restart Cura once; separately restart or
reconnect the MCP runtime so its `tools/list` includes the seven cloud tools.
Updating only the connector or only the plugin is insufficient. An existing
printer job continues independently during Cura restart.

Cura 5.14.0 native cloud source was inspected locally. The adapter uses
`CloudOutputDevice.requestWrite` plus native started/finished/error signals.
Cached login/upload state accesses `_account`, `_progress` and
`_uploaded_print_job`, which are internal attributes and require version
checks. Cura 5.13 and macOS live cloud submission are unverified; do not infer
parity from shared source or offline tests. Current tests cover state binding,
guards, one-use tokens, completion/error callbacks and duplicate prevention.
End-to-end cloud writes must be verified with an authorized new job; a running
job must not be duplicated just to smoke-test the endpoint.
