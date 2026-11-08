# Cura scene operations

The bridge calls the same Cura desktop actions used by the Edit and extruder
menus. These operations run on Cura's main thread and do not contact the printer.
Both the Cura plug-in and the MCP server must be updated, then Cura and the MCP
connection must be restarted.

Start with `cura_inspect`. Its `scene_nodes` list includes IDs for model
parts and groups, their parent IDs, build plate and current extruder assignment.
Match extruder IDs against `extruders`; the operation argument `extruder`
is zero based (0 is UI extruder 1).

| Action | Arguments | Behavior |
| --- | --- | --- |
| `clear_scene` | None | Runs Cura's Clear Build Plate action. Removes selectable scene models; save work first. |
| `center_objects` | `object_ids` | Centers each selected object or its containing group. Select the whole group to keep parts aligned. |
| `merge_objects` | Two or more top-level `object_ids` on the same plate | Runs Cura's Merge Models. Check the result in Cura; it is not a mesh Boolean or a correction for incompatible source origins. |
| `assign_extruder` | `object_ids`, `extruder` | Assigns selected individual model parts to an enabled slot. |
| `set_extruder_enabled` | `extruder`, `enabled` | Toggles the slot through Cura's machine manager. Does not select or change a material profile. |

Use `confirm_cura_operation` and then `cura_operation` with the same arguments
and the returned token. If the scene changes in between, inspect it again and
prepare a new confirmation. Inspect the scene after merging to get the new
group ID. Model IDs are scoped to the current Cura session.
# Additional scene controls

The bridge supports selection, group and ungroup, deletion, duplication, arrangement, and Lay Flat through Cura's native actions. Duplication, arrangement, and Lay Flat report scheduling. Reinspect the scene to check the result.

Use `move_objects`, `rotate_objects`, `scale_objects`, or `mirror_objects` with a three-component `vector`. Coordinates follow Cura's internal axes with Y up. Move is a relative offset in millimetres, rotation is an Euler delta in degrees, scale uses positive multipliers, and mirror uses −1 on the reflected axes and 1 elsewhere. Transform a registered group as one top-level object to keep its parts aligned.

Object inspection returns position, bounds, and per-model overrides. Use `set_model_settings`, `reset_model_settings`, or `set_mesh_type` on an individual mesh. `cura_snapshot` returns a native isometric PNG and `cura_estimates` reports time and material for the active sliced plate.

Use `export_mesh` with object IDs and an absolute path to a new STL under the staging directory. Export preserves the objects' Cura placement in the STL geometry.

`scale_to_fit` uniformly shrinks and centers one top-level object or group, using the active build dimensions and Cura's edge allowance. Its Cura boundary result can still flag machine-specific exclusion zones.

`cura_layers` reads paginated numbered layer comments, feature markers and tool-change commands from the finished slice. `reset_settings` removes named global or extruder user overrides and returns the inherited values.

`compare_slices` runs two to five named variants against the active plate.
Each variant has a `name` and a `values` map with numeric overrides for layer
height, infill density, walls, top/bottom layers, or print speed. Confirm the
whole comparison, then poll `cura_comparison_status` with the returned ID.
Results include estimated duration and material per extruder.
`cura_comparison_cancel` stops the comparison and restores its temporary
overrides. Slice again with the desired settings before exporting.

### Sample comparison

Open [comparison-sample.stl](../examples/comparison-sample.stl) as a model on
an empty build plate. It is an original 24 × 24 × 12 mm solid. Pass the
following arguments to `confirm_cura_operation`, then pass the same arguments
and the returned token to `cura_operation`.

```json
{
  "action": "compare_slices",
  "variants": [
    {"name": "0.15 mm", "values": {"layer_height": 0.15}},
    {"name": "0.25 mm", "values": {"layer_height": 0.25}}
  ]
}
```

Poll `cura_comparison_status` using the returned `comparison_id`.
Estimates depend on the active printer, materials, and other slice settings.

In a Windows Cura 5.14.0 smoke test with the S5 profile, the included STL
returned the following slicer estimates.

| Layer height | Estimated duration | Estimated material |
| --- | --- | --- |
| 0.15 mm | 28 min 48 s | 4.00 g |
| 0.25 mm | 17 min 48 s | 4.07 g |
