# Tested versions and evidence boundaries

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
