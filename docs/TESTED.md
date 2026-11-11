# Tested versions and evidence boundaries

Runtime 0.1.12 multi-camera preparation: fresh stdio discovery advertised
37 tools. Native index 0 returned a JPEG; index 1 returned HTTP 404. Inventory
reported available/not_exposed, and a two-index capture returned the working
image with a separate missing-feed result. No USB camera was added and no
printer service was changed. Two-camera acquisition remains hardware-unverified.
Offline tests cover two available indices, partial/all-missing results,
distinct-index validation, and explicitly allowed versus rejected service ports.

Runtime 0.1.11 monitoring: a fresh stdio MCP process advertised 35 tools.
The local progress tool returned current printing state, elapsed time and a
remaining estimate. The webcam tool followed the printer's native snapshot
redirect and returned a JPEG as an inline MCP image block. No print-control
write was made. Offline tests cover time-source fallback, missing estimates,
read-only HTTP methods, snapshot redirect restrictions, MIME/signature checks
and size limits. The captured image and job details remain private runtime
evidence and are not included here. Cura plugin 0.1.10 is unchanged; this
runtime-only addition does not require Cura restart.

Release 0.1.10 on Windows Cura 5.14.0: live discovery found a previously
configured cloud printer profile. Confirmation and native connection selection
returned `selected` with connected/logged-in/active state while the local-IP
environment variable was unset. No upload or print was invoked. A fresh stdio
runtime advertised 33 tools, including seven cloud tools. Switching to a
different physical printer, expired-login recovery and macOS/5.13 selection
remain unverified. Offline tests cover stale/unknown profile IDs, cross-action
token reuse and refusing selection during uploads.

Release 0.1.9 cloud checks on Windows Cura 5.14.0: updated plugin loaded;
fresh stdio runtime advertised 30 tools, including all four cloud tools.
Native cloud discovery returned a connected, logged-in destination with
cached printing state. Local printer job status was readable through the
updated origin-file configuration. No new cloud write was sent in this
endpoint smoke test, avoiding duplication of an active job. Confirmation,
callback/error and duplicate guards are covered offline, not an end-to-end
new-tool submission result. Existing MCP client sessions must reconnect to
reload the runtime and discover the new tools.

| Component | Baseline | What is established |
|---|---|---|
| Cura | 5.14.0 | Windows desktop smoke tests covered scene edits, slice comparison and cancellation, settings restoration, preview, layers, STL and profile export, extension discovery and package inventory |
| Cura | 5.13.0 | Earlier Windows baseline covered settings, staged load, slice/export and native Save/Save As |
| Printer | UltiMaker S5 R1, firmware 9.0.3.0 | Read-only API/source inspection and printing/recovery research; not every cataloged write tested |
| Node | 20+ required; offline checks on Node 22 | Dependency-free stdio server and mock transport tests |
| Python | 3.10+ recommended | File/archive/transport fixtures and privacy checks; Cura uses bundled Python |
| macOS | Hosted macOS offline CI; deployment guide/helpers provided | Platform launch paths and Keychain code provided; updated live Cura/tunnel installation not verified |
| Linux | Offline server checks | Hosted offline CI; not a supported credential-pairing desktop deployment |
| STM32 controller draft | Portable C++11/native, role-local sensor tests, both role-sketch stub paths and build guards | No real STM32 core compile, timing/memory, electrical or accessory interoperability result |

No raw logs, screenshots, printer UUIDs, firmware dumps, backup metadata, project
files, workstation paths or personal test evidence are included. The repository
includes an original sample STL. Public test
results contain aggregate outcomes only. Test addresses are loopback; fixture
secrets are deterministic dummy strings and are not working credentials.

The offline suites cover exact-request confirmation, one-use/expiry checks,
busy-printer restrictions, staging symlink boundaries, native save planning and
atomic archive validation. They never require the actual printer. Hardware/native
tests model protocol, calibration and control logic; they do not prove physical IO.

For the reproducible setup, see [platform configurations](PLATFORM_CONFIGURATIONS.md),
[macOS](MACOS.md) and [Windows](WINDOWS.md). Hosted runner tests do not establish
a live Cura GUI install or actual Keychain pairing on either Mac architecture.
