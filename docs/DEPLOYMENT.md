# Deployment

Use a trusted local workstation and network. The Node service speaks MCP over
stdin/stdout; it does not expose a public HTTP MCP listener. The plugin binds
only loopback, uses a generated token and processes Cura operations on its main
thread. Do not expose its port directly to the Internet.

## Install the Cura plugin

Save your work and quit every Cura instance. Copy `cura_plugin/CuraMcpBridge` as
one folder under Cura 5.14's `plugins` directory. Back up an existing plugin
first. Cura's **Help > Show Configuration Folder** is the preferred way to find
the correct version's folder. Relaunch Cura once after installation.

The platform defaults are constructed from the user's home directory at runtime:

| Platform | Plugin directory, relative to home | Private connection file, relative to home |
|---|---|---|
| Windows | AppData/Roaming/cura/5.14/plugins | AppData/Roaming/cura/5.14/cura-mcp-bridge.json |
| macOS | Library/Application Support/cura/5.14/plugins | Library/Application Support/cura/5.14/cura-mcp-bridge.json |

The plugin creates the connection file. It contains a token; never commit,
upload, paste or include it in an issue. This repository does not include one.
Default bridge port: **49621**, bound to **127.0.0.1**. It is a configuration
constant, not an identifier for a particular printer. Conflicting Cura listeners
are rejected; close duplicate application instances before restarting.

## Configure Node MCP

Use absolute paths appropriate to your own checkout. Example client JSON, with
placeholders that **must be replaced locally**, including the blank printer origin:

```json
{
  "mcpServers": {
    "cura-local": {
      "command": "node",
      "args": ["/path/to/checkout/src/server.mjs"],
      "env": {
        "CURA_PRINTER_BASE_URL": "",
        "CURA_MCP_PRINT_FILE_ROOT": "/path/to/print_files",
        "CURA_MCP_PYTHON": "/path/to/python3"
      }
    }
  }
}
```

On Windows use locally appropriate absolute paths and JSON escaping or forward
slashes. Configure your client's working directory as the checkout if it supports
that option. Do not assume every client expands `~` or environment substitutions.

| Variable | Purpose |
|---|---|
| CURA_PRINTER_BASE_URL | Required HTTP(S) printer origin; credentials, path, query and fragment are refused |
| CURA_MCP_PRINT_FILE_ROOT | Existing staging folder for model loads, G-code export and uploads |
| CURA_MCP_BRIDGE_CONNECTION_PATH | Override the platform-specific Cura connection-file path |
| CURA_MCP_PYTHON | Python 3 executable used by the private printer transport |
| CURA_MCP_NODE | Optional executable override used by the macOS launcher |

Create the staging directory first. A neutral, shared user Documents/Application
Support directory is suitable. On packaged Windows applications, the apparent
LocalAppData path may be redirected into an app-specific cache that Cura cannot
see. `cura_path_info` checks visibility from Cura itself. Project Save As accepts
an explicitly confirmed absolute destination outside staging; print transfers
remain confined to staging after realpath/symlink resolution.

On macOS, `scripts/run_macos.sh` resolves Intel/Apple Silicon Node locations and
Python 3, sets platform connection/staging defaults, and requires an explicit
printer origin. Invoke it with `/bin/bash`. Existing MCP tunnels can launch this
command, but tunnel binaries/accounts/keys and cloud deployment are not supplied.
Stop an old runtime before reconnecting; refresh the client's tool list after
updating Node source. A plugin update additionally requires a Cura restart.

## Pairing and first checks

Begin with `cura_status`, `cura_inspect`, `cura_settings` and `printer_api_catalog`.
Some reads work without pairing; other routes require printer authorization.
Pair using the cataloged `/auth/request` write only after explicit authorization
and accept it on the printer display. The transport stores the returned key in
the OS credential store and suppresses it in the tool response. Verification
and pairing status remain separate from network reachability.

macOS uses Keychain; Windows uses Credential Manager. Linux has no secure pairing
storage backend in this release; it can run mock tests and unpaired reads, but
credential-dependent workflows require additional implementation.

Optional Developer-mode SSH access is a separate channel for printer-side Linux
inspection, D-Bus diagnostics and touchscreen capture. See [SSH capabilities](SSH_ACCESS.md).
Normal Cura automation/HTTP access does not require an SSH shell.

Do not test motion, heaters, network/firmware or job-changing writes on an active
printer. A printer may schedule an uploaded job automatically according to its
queue policy. Test Save As using a disposable Cura project and a new filename.
If the native import-conflict dialog appears, resolve it in Cura before assuming
the requested project is loaded. Inspect state and poll asynchronous saves.

## Platform walkthroughs and helpers

See the [configuration comparison](PLATFORM_CONFIGURATIONS.md),
[macOS walkthrough](MACOS.md) and [Windows walkthrough](WINDOWS.md).
`python scripts/install_plugin.py` shows a no-write plan; `--apply` installs only
the plugin after checking Cura is closed, preserving credentials and profiles.
`python scripts/check_deployment.py` reports local diagnostic booleans; it never
contacts the printer. `--check-listener` adds one command-free loopback TCP check.
Platform-specific client templates keep the printer origin blank.
