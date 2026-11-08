# Cura navigation and extensions

`cura_extensions` lists Cura's active plug-ins and native stage and toolbar
IDs, plus the loaded Post Processing scripts and active script indexes.
`cura_navigate` accepts `prepare`, `preview`, `monitor`, `post_processing`,
`marketplace`, `move`, `scale`, `rotate`, and `mirror`. These invoke Cura's own controller
or dialog; selecting a transform tool does not transform the model.
For workspace commands (clear, center, merge, assignment, slice, save),
use the corresponding bridge operation.

Marketplace navigation opens Cura's native dialog. Search, package actions,
and UltiMaker account sign-in are not currently exposed. Cura's account
login opens a separate browser flow, so opening the Marketplace is not a
sign-in or an authentication check.

To configure a Griffin pause, inspect the active scripts. Remove any
unwanted script using `remove_post_processing_script` with its current
`script_index`, then use `add_griffin_pause` with `pause_layer` set to the
zero-based G-code layer to pause **before**. Each edit uses
`confirm_cura_operation` followed by `cura_operation`. Inspect again after
each removal because indexes can change. Configuration is stored through
Cura's native Post Processing plug-in and can affect later jobs for the same
printer profile; remove the pause after use.

Slice again after edits. MCP G-code export applies one native Griffin pause
to a copy of the slice, verifies that the only added command is one M0 at
the requested layer boundary, and rejects raft layers, unsupported scripts,
or already post-processed G-code. A pause does not validate physical filament
unload/load/resume behavior.

`cura_extensions` lists menus registered by active Cura extensions. Use
`activate_extension_menu` with the exact `target_id` and `menu_item` from
that list. A confirmation binds the native action. The response reports
dispatch. Any dialog or subsequent operation belongs to the extension.

`manage_package` queues native package changes for the next Cura restart.
Use an exact package ID and `package_action` of `install`, `update`, or
`remove`. Install and update require a staged local `.curapackage`. The
confirmation binds the archive hash and current package inventory. Packages
with a license prompt go through Cura's Marketplace interface. Remote catalog
transactions and account subscriptions are separate from local queueing.

Update both the Cura plug-in and MCP server, then restart Cura and reconnect
the MCP session to load the new tools.
