# Cura printers, materials, and profiles

Call `cura_configuration` to discover the active printer and the choices Cura exposes for it. Available presets depend on the printer, print cores, and materials. Use the returned IDs even if the UI uses translated labels.

1. Select a configured printer, print core, material, built-in quality preset, or custom profile with `set_configuration`. Send the same arguments first to `confirm_cura_operation`, then to `cura_operation` with the returned token. Material and core selection use a zero-based extruder index. Cura may ask whether to keep current overrides.
2. Use `cura_settings` to read effective values and `set_settings` to make adjustments. Example keys include `layer_height`, `wall_line_count`, `top_layers`, and `bottom_layers`.
3. To save a new reusable profile, use `set_configuration` with `configuration_kind: "create_profile"` and supply the new name in `target_id`. Cura copies the active profile settings and current overrides. To save into the active custom profile, use `"update_profile"` with that profile's exact ID. Built-in presets serve as starting points for new custom profiles.
4. Use `save_project` separately to save the scene and its configuration in a Cura project.

These operations affect the desktop slicer. Selecting a material or print core in Cura changes the slicer's configuration for that slot.

## Keep or discard profile overrides

When a change triggers Cura's **Discard or Keep changes** dialog, Cura 5.14
uses the application preference `cura/choice_on_profile_override`.
Set the policy in the dialog's drop-down and answer the current prompt
using the enabled button. The policy applies to subsequent changes in
that Cura installation.

| Cura option | Stored value | What happens |
| --- | --- | --- |
| **Always ask me this** | `always_ask` | A person must choose **Keep changes** or **Discard changes** when the dialog appears. |
| **Keep and never ask again** | `always_keep` | Cura carries over the current overrides automatically. |
| **Discard and never ask again** | `always_discard` | Cura discards current overrides automatically and uses the destination profile's defaults for those settings. |

For unattended profile changes, configure one of the automatic policies
in Cura before running the MCP workflow. Use **Keep** when the job relies
on tuned overrides and **Discard** when the destination profile should
supply those values. Restore **Always ask** in Cura's preferences when
interactive review is needed again.

The bridge follows Cura's existing preference. It currently exposes no
per-operation override policy or dialog response tool. With **Always ask**
enabled, stop before slicing if the dialog is pending. After Cura resolves
the change, use `cura_configuration` to check the selected core, material
or profile and `cura_settings` to verify the effective values the job
depends on. The native project-open confirmation has its own policy.

[Cura 5.14 application source](https://github.com/Ultimaker/Cura/blob/5.14.0/cura/CuraApplication.py) · [Cura 5.14 profile changes dialog](https://github.com/Ultimaker/Cura/blob/5.14.0/resources/qml/Dialogs/DiscardOrKeepProfileChangesDialog.qml)

Use `import_profile` with an absolute `.curaprofile` path inside the staging directory. The confirmation binds the file contents. Use `export_profile` with an existing custom profile ID and a new staged `.curaprofile` path. File export preserves the native global and per-extruder profile containers.
