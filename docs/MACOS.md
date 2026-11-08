# macOS deployment and adjunct tools

Target: Cura 5.14.0, external Node 22 as the tested offline baseline (code minimum
20), and external Python 3.10+. Cura supplies the plugin's Python/Qt libraries;
do not install a separate PyQt package into Cura for this bridge.

Both Intel and Apple Silicon runtime search paths are supported by the launcher.
That is deployment logic, not a claim of live hardware testing on both Mac types.
Use a maintained runtime suitable for your OS. See the official [Node downloads](https://nodejs.org/en/download),
[Python macOS guide](https://docs.python.org/3/using/mac.html) and, if used,
[Homebrew installation guide](https://docs.brew.sh/Installation). Package-manager
support for older OS/Intel combinations is separate from this project's code.

## 1. Prepare a stable checkout

Extract a verified source release or clone the repository into a stable local
folder. Avoid leaving the active runtime in a temporary download-extraction
directory. Open Terminal there and check:

```sh
node --version
python3 --version
```

Node and Python for the external MCP process are separate from Cura's embedded
runtime. No npm package install is required. Set absolute executable paths when
your MCP client or launch service does not inherit Terminal's PATH.

## 2. Install only the original bridge plugin

Save the Cura project, quit all Cura copies and stop the previous MCP/tunnel
runtime through its normal controls. From the checkout:

```sh
python3 scripts/install_plugin.py
python3 scripts/install_plugin.py --apply
```

The first command shows the plan without writing. The second refuses when a known
Cura process is running, stages four original plugin files, backs up an existing
plugin outside the plugins directory and installs the new plugin. It does not
copy a connection file, touch Keychain, install Node/Python, change profiles or
start a print. Relaunch Cura once after installation.

The default config directory is derived from home as
`Library/Application Support/cura/5.14`. Use Cura's **Help > Show Configuration
Folder** and `--config-dir /path/to/configuration` if the actual directory differs.
The installer does not install or alter an MCP client/tunnel service.

## 3. Configure the MCP client

Copy [mcp-client-macos.json](../examples/mcp-client-macos.json) into your client's
local configuration. Replace the checkout, Python and staging placeholders with
your own absolute paths. Fill the deliberately blank `CURA_PRINTER_BASE_URL` with
your printer's HTTP(S) origin. Do not include a username/password in that URL.
The launcher will refuse an empty printer origin rather than select a default.

The command is `/bin/bash`, with your absolute `scripts/run_macos.sh` as its
argument. The launcher locates Node using an explicit `CURA_MCP_NODE` first, then
common `/opt/homebrew/bin`, `/usr/local/bin` and system/PATH locations. A custom
installation or version manager may require an explicit executable override.
It similarly supports `CURA_MCP_PYTHON`; check its version rather than assuming
the system Python meets the requirement. Paths containing spaces must remain one
JSON argument. Client JSON does not necessarily expand `~` or shell variables.

Without a staging override, the launcher creates a home-relative
`Library/Application Support/CuraMcpBridge/print_files` directory. Without a
connection override it reads Cura's home-relative configuration file. Neither
default supplies a printer address or imports another machine's token.

For an existing tunnel, keep its registration and account setup, but retarget
its MCP launch command to the absolute Bash launcher in the new checkout. Stop
the old managed runtime first and refresh the client's tool list after restarting.
No tunnel binary, key, tunnel ID, registration or auto-start agent is shipped.
Client-specific tunnel installation remains the client's responsibility.

## 4. Diagnose without exposing values

After Cura opens:

```sh
python3 scripts/check_deployment.py
python3 scripts/check_deployment.py --check-listener
```

The helper reports booleans for runtime compatibility, connection metadata,
token presence and loopback configuration without printing the token, file path
or printer origin. The optional check opens/closes one loopback TCP connection
without sending a command. It never contacts the printer or reads Keychain.
Run it with the same environment variables as the MCP client for comparable
results. A Terminal environment may differ from a client launched by Finder.

Token/file presence, TCP reachability, a healthy Cura bridge and a working Node
MCP runtime are separate checks. In the MCP client use `cura_status` and
`printer_api_catalog` first; discovery should show 18 tools. Later inspect Cura
and test Save As with a disposable project/new filename. Accept native import
conflict dialogs in Cura when necessary. Do not test printer writes on an active
job. Pairing uses the Mac's own Keychain and printer-display approval.

## Troubleshooting

| Symptom | Next check |
|---|---|
| Node/Python found in Terminal but not client | Use absolute executable overrides; verify the client/service environment |
| Empty origin error | Fill the blank origin locally; this is intentional |
| Missing connection file | Verify plugin config folder, restart Cura once, inspect plugin load errors |
| Port unavailable/duplicate listeners | Close duplicate Cura copies and old runtimes; start one of each |
| File exists but load fails | Use `cura_path_info`; check local staging permissions and native project-import dialog |
| Keychain prompt/access failure | Use the same logged-in user/session; do not work around it by publishing a key |
| Old tool list | Reconnect the MCP client; Node changes require a fresh process |

Automatic login/startup services are not installed. Configure them only after a
manual deployment works, using the same user account, environment and absolute
paths. See [known issues](KNOWN_ISSUES.md) for unimplemented Cura wrappers.

The stdio server must be attached to an MCP client. Do not install Node alone
as an independent launchd daemon and expect remote tool access. A login agent
would need to run a supported MCP client/tunnel wrapper that owns the stdio pipes;
that client-specific integration is outside this repository.
