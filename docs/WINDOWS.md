# Windows PC deployment

Target: Cura 5.14.0 and a local stdio MCP process. Node 22 is the tested offline
baseline (code minimum 20); use external Python 3.10+. Cura supplies its own
plugin runtime. This is a user-local install; administrator access is not needed
for the normal configuration folder.

## Install and configure

1. Put the checkout in a stable folder. In PowerShell, verify `node --version`
   and `python --version`. Configure actual executable paths if either command
   resolves to a missing interpreter or application-store alias.
2. Save/quit Cura and stop the previous MCP runtime. Run
   `python scripts/install_plugin.py` to inspect the plan, then
   `python scripts/install_plugin.py --apply` to install. The helper preserves
   the existing connection file, profiles and credentials and backs up the plugin.
3. Relaunch Cura once. By default its config is under `APPDATA/cura/5.14`.
   Verify with **Help > Show Configuration Folder**; `--config-dir` supports an
   explicitly selected configuration directory.
4. Copy the [Windows MCP template](../examples/mcp-client-windows.json) into the
   MCP client's local settings. Replace the Node, Python, checkout and staging
   placeholders. Fill the blank printer origin yourself. Use forward slashes or
   correctly escaped backslashes in JSON; preserve paths with spaces as one value.
5. Create the staging folder and launch the Node stdio server through the client.
   Refresh the client's tool list after replacing Node code. Restart Cura for
   plugin updates; do not launch multiple Cura/runtime copies.

The plugin binds loopback port 49621 and generates its own private connection
file. Printer Digest pairing is stored in Windows Credential Manager. Do not
copy either into a release or export credentials to the Mac.

## Shared-path caveat

Packaged Windows applications can see a redirected LocalAppData cache instead of
the path another desktop process sees. Use an explicitly configured shared user
Documents staging folder for bridge-created model/project/G-code transfers.
Do not assume that a file visible to the MCP host is visible to Cura. Use
`cura_path_info` to check from Cura's process. Do not paste real path diagnostics
into a public issue without redacting your account/folder names.

Project Save As can use an explicitly confirmed absolute folder outside staging;
print exports/uploads and file loads retain staging confinement. A `.3mf` is a
Cura project, not a printer-ready USB job. Export sliced `.gcode`, `.gcode.gz` or
`.ufp` as supported by the printer. Never just rename a model to a printable type.

## Check without changing the printer

Run `python scripts/check_deployment.py` with the same overrides as your client;
optionally add `--check-listener` for a loopback TCP reachability check. It prints
no connection token, origin or personal path and never contacts the printer.
Then use `cura_status`, `cura_inspect`, `cura_settings` and `printer_api_catalog`.
Token/file presence and a listening port do not prove a working MCP runtime or
correct live machine/material configuration. Native 3MF conflicts may still need
the Cura UI. Verify the [known gaps](KNOWN_ISSUES.md) before automating.
