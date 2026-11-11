# Print progress and webcam stills

## Preparing for a second camera

Runtime 0.1.12 adds:

- `printer_camera_inventory` with `{"camera_indices":[0,1]}` probes selected
  native snapshot endpoints. Results distinguish `available`, `not_exposed`
  (HTTP 404) and other `error` conditions. It does not enumerate USB devices.
- `printer_camera_snapshots` with the same arguments returns labeled inline
  images for available feeds. One missing camera does not discard the other
  image. Captures are sequential, not synchronized; two accessible indices
  are not proof of two independent physical cameras if firmware aliases them.

Both default to indices 0 and 1 and accept 1-4 distinct indices from 0-15.
Each still is bounded as below. Inventory temporarily requests/discards one
image per index; it does not start streams or store images. A request can
take up to approximately eight seconds per selected index if feeds time out.

The S5 native route is `GET /api/v1/camera/{index}/snapshot`; there is also
an indexed stream route, which these tools do not open. Observed firmware
exposed camera 0, while index 1 returned 404 before any second-camera install.
`GET /api/v1/camera` reported the primary feed, not a USB-device inventory.
Therefore the MCP is prepared to request camera 1, but stock firmware handling
of an added USB camera is not established. A 404 means the feed is not exposed,
not proof that Linux failed to detect the camera.

After installation, poll inventory and capture both feeds to check that their
views differ. If camera 1 remains unexposed, read-only developer SSH checks
such as `ls /sys/class/video4linux`, `ls /dev/v4l/by-id`, and (if installed)
`v4l2-ctl --list-devices` can distinguish Linux enumeration from API routing.
No firmware/service changes, USB probing or second-camera power/bandwidth
validation are performed by this release. A separate capture service would
need explicit setup if the stock service does not publish the new camera.

Camera redirects default to same-printer port 8080. If a separately configured
native camera service redirects to another port, explicitly allow it in the
private `cura-mcp-printer.json`, for example:

```json
{
  "printer_origin": "http://printer-hostname.local",
  "camera_service_ports": [8080, 8081]
}
```

This does not create a service on port 8081 or assign camera 1 to it. It only
permits a snapshot redirect already returned by the native API. Same-host,
same-scheme, snapshot-path, byte and time limits still apply. At most four
service ports may be configured. Runtime configuration stays untracked.

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
port or an explicitly allowed camera service port (default 8080). Only snapshot paths are allowed. No credentials
are added to redirect requests. Foreign-host, stream and credential-bearing
redirects are rejected. JPEG/PNG MIME type and magic bytes are checked;
responses are capped at 5 MiB and an eight-second timeout. No continuous
stream is opened. Images are not automatically saved on disk.

The image is private runtime data delivered only to the requesting MCP
client; do not add captures, job-status responses or connection files to a
source repository. A still image does not establish ongoing extrusion or
the mechanical seating of a Bowden tube outside its field of view.

## Deployment and limits

Basic monitoring is available in runtime 0.1.11; multi-camera tools in 0.1.12. These tools require no Cura plugin update
and no Cura restart. Reconnect/restart the MCP runtime to refresh its tool
manifest. Configure a local origin as described in
[cloud/local connection documentation](CLOUD_PRINTING.md). Cloud-only access
does not currently provide a webcam still or a remaining-time calculation
through these tools. Digest-authenticated camera servers are not supported
by this unauthenticated snapshot adapter; existing protected local API
operations retain their separate credential handling.

Offline tests cover time fallback/missing values, image response blocks,
read-only requests, redirect restrictions, invalid images and byte limits.
