# Changelog

## 0.1.11

- Add read-only local print progress with elapsed/remaining-time estimates.
- Return bounded webcam stills as inline MCP images with restricted snapshot
  redirects; keep runtime images and job data outside the repository.
- Runtime-only update; no Cura plugin restart required.

## 0.1.10

- Discover preinstalled cloud printer profiles independently of local HTTP
  configuration and select them through native Cura connection management.
- Add guarded connection selection without login automation or print submission.

## 0.1.9

- Add native Cura cloud destination discovery, guarded current-slice submission
  and asynchronous completion/error status with session duplicate protection.
- Re-read an optional user-local printer origin file on each HTTP operation.
- Document connector/plugin restart requirements and cloud verification limits.

## Controller draft 0.2.0

- Separate STM32 Air Manager and Material Station bench targets; suggested Nucleo boards and 3.3 V signal plan.
- Native startup identity, firmware-check/reset requirements and accessory health map.
- Generic UMB/D-Bus extension map, independent probe buses and disabled build guards.
- Physical pin assignments, real STM32 builds, startup and hardware compatibility remain unvalidated.

## 0.1.8

- Target Cura 5.14.0 and document the version-specific setup for 5.13 and 5.14.
- Add native scene editing, per-model overrides, profile management, and STL export.
- Add layer inspection, snapshots, estimates, and cancellable slice comparisons.
- Discover and dispatch native extension menu actions and queue local package changes.
- Include an original STL sample and a repeatable comparison workflow.
- Configure and validate Griffin pauses using Cura 5.14's text layer field.

## 0.1.7

- Reference Cura and printer firmware versions in the setup documentation.
- Developer SSH capabilities, touchscreen capture and experimental UI-input guidance.
- Air Manager register formats, observed ranges, units and status values.

## 0.1.6

- Windows and macOS configuration examples and deployment guides.
- Plugin installer with backup support and local deployment diagnostics.
- macOS launcher integration tests.

## 0.1.5

- Local Cura automation and S5 printer access through 18 MCP tools.
- Model/project loading, settings, slicing, G-code export and native Save/Save As.
- S5 R1 interface documentation and experimental Arduino examples.

See [tested versions](docs/TESTED.md) and [known limitations](docs/KNOWN_ISSUES.md).
Arduino examples are untested on physical hardware.
