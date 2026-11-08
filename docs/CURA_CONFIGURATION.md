# Cura printers, materials, and profiles

Call `cura_configuration` to discover the active printer and the choices Cura exposes for it. Available presets depend on the printer, print cores, and materials. Use the returned IDs even if the UI uses translated labels.

1. Select a configured printer, print core, material, built-in quality preset, or custom profile with `set_configuration`. Send the same arguments first to `confirm_cura_operation`, then to `cura_operation` with the returned token. Material and core selection use a zero-based extruder index. Cura may ask whether to keep current overrides.
2. Use `cura_settings` to read effective values and `set_settings` to make adjustments. Example keys include `layer_height`, `wall_line_count`, `top_layers`, and `bottom_layers`.
3. To save a new reusable profile, use `set_configuration` with `configuration_kind: "create_profile"` and supply the new name in `target_id`. Cura copies the active profile settings and current overrides. To save into the active custom profile, use `"update_profile"` with that profile's exact ID. Built-in presets serve as starting points for new custom profiles.
4. Use `save_project` separately to save the scene and its configuration in a Cura project.

These operations affect the desktop slicer. Selecting a material or print core in Cura changes the slicer's configuration for that slot.

Use `import_profile` with an absolute `.curaprofile` path inside the staging directory. The confirmation binds the file contents. Use `export_profile` with an existing custom profile ID and a new staged `.curaprofile` path. File export preserves the native global and per-extruder profile containers.
