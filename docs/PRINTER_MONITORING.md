# Print progress and webcam stills

These read-only MCP runtime tools use the configured local printer origin.
They work while printing and do not need Cura to be running. They do not
pause, resume, restart or otherwise change a printer job.

## Current print status

Call `printer_print_status` with `{}`. The tool reads
`/api/v1/printer/status` and `/api/v1/print_job` and returns:

- Printer/job state, job name and progress percentage.
- Elapsed and remaining seconds plus `HH:MM:SS` display values.
- UTC check timestamp and the source of the remaining-time estimate.

Remaining time uses positive `time_total` minus `time_elapsed`, falling back
to `time_estimated` when needed. Unknown values remain null; negative results
clamp to zero. Post-print/cleanup has zero remaining printing time, which
does not mean cooling or operator cleanup has finished. A missing job while
the printer reports printing yields an unknown remaining time. Treat these
as printer estimates; pauses, cooling and operator actions may add wall time.
Device serials, material identifiers and account fields are not returned.

## Webcam image in the conversation

Call `printer_camera_snapshot` with `{}` or `{"camera_index":0}`. The tool
requests `/api/v1/camera/{index}/snapshot` and returns an MCP `image` block
alongside timestamp, MIME type and byte count. Clients can display the image
directly; it is distinct from `cura_snapshot`, which renders Cura's model.

S5 firmware may redirect this endpoint to its camera service on port 8080
with `/?action=snapshot`. The tool permits at most two redirects, restricted
to the configured printer hostname, the same scheme, and the configured
port or camera port 8080. Only snapshot paths are allowed. No credentials
are added to redirect requests. Foreign-host, stream and credential-bearing
redirects are rejected. JPEG/PNG MIME type and magic bytes are checked;
responses are capped at 5 MiB and an eight-second timeout. No continuous
stream is opened. Images are not automatically saved on disk.

The image is private runtime data delivered only to the requesting MCP
client; do not add captures, job-status responses or connection files to a
source repository. A still image does not establish ongoing extrusion or
the mechanical seating of a Bowden tube outside its field of view.

## Deployment and limits

Available in MCP runtime 0.1.11. These tools require no Cura plugin update
and no Cura restart. Reconnect/restart the MCP runtime to refresh its tool
manifest. Configure a local origin as described in
[cloud/local connection documentation](CLOUD_PRINTING.md). Cloud-only access
does not currently provide a webcam still or a remaining-time calculation
through these tools. Digest-authenticated camera servers are not supported
by this unauthenticated snapshot adapter; existing protected local API
operations retain their separate credential handling.

Offline tests cover time fallback/missing values, image response blocks,
read-only requests, redirect restrictions, invalid images and byte limits.
