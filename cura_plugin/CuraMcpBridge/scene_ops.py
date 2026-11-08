"""Guarded calls to Cura's native scene operations (Cura main thread only)."""
import hashlib
import json
import math
import os
import tempfile


TRANSFORMS = {"move_objects", "rotate_objects", "scale_objects", "mirror_objects"}
ACTIONS = {"clear_scene", "center_objects", "merge_objects", "assign_extruder",
           "set_extruder_enabled", "select_objects", "group_objects", "ungroup_objects",
           "delete_objects", "duplicate_objects", "arrange_objects",
           "set_model_settings", "reset_model_settings", "set_mesh_type", "lay_flat", "export_mesh",
           "scale_to_fit", *TRANSFORMS}
MESH_TYPES = {"normal": "", "infill_mesh": "infill_mesh", "cutting_mesh": "cutting_mesh",
              "support_mesh": "support_mesh", "anti_overhang_mesh": "anti_overhang_mesh"}


def inspect_layers(chunks, payload):
    first, limit = payload.get("first_layer", -1000), payload.get("limit", 50)
    if type(first) is not int or first < -1000 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Provide a starting layer and a limit of 1 to 200")
    result = []
    count = 0
    layer = None
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith(";LAYER:"):
                try:
                    number = int(line[7:])
                except ValueError:
                    continue
                count += 1
                layer = None
                if number >= first and len(result) < limit:
                    layer = {"layer": number, "features": [], "tool_changes": []}
                    result.append(layer)
            elif layer is not None and line.startswith(";TYPE:"):
                feature = line[6:].strip()
                if feature not in layer["features"]:
                    layer["features"].append(feature)
            elif layer is not None and line.startswith("T"):
                tool = line.partition(";")[0].split()[0][1:]
                if tool.isdecimal():
                    layer["tool_changes"].append(int(tool))
    return {"total_layer_markers": count, "layers": result}


def xyz(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]


def model_overrides(node):
    stack = node.callDecoration("getStack")
    if stack is None:
        return {}
    settings = stack.getTop()
    return {key: settings.getProperty(key, "value") for key in sorted(settings.getAllKeys())}


def export_mesh(app, nodes, filename):
    from UM.Mesh.MeshWriter import MeshWriter

    if not isinstance(filename, str) or not os.path.isabs(filename) or not filename.lower().endswith(".stl"):
        raise ValueError("Provide an absolute .stl path")
    if os.path.lexists(filename):
        raise ValueError("Mesh export requires a new file")
    if any(node.getParent() in nodes for node in nodes):
        raise ValueError("Select a group or its children for export")
    writer = app.getMeshFileHandler().getWriter("STLWriter")
    if writer is None:
        raise ValueError("Cura STL writer is unavailable")
    with tempfile.TemporaryDirectory(dir=os.path.dirname(filename)) as temporary:
        staged = os.path.join(temporary, "mesh.stl")
        with open(staged, "wb") as output:
            if not writer.write(output, nodes, MeshWriter.OutputMode.BinaryMode):
                raise ValueError("Cura could not write the selected meshes")
        os.link(staged, filename)
    return {"file_path": filename, "bytes": os.path.getsize(filename)}


def change_model_settings(action, node, stack, payload):
    from cura.Settings.SettingOverrideDecorator import SettingOverrideDecorator
    from UM.Settings.SettingInstance import SettingInstance

    values = payload.get("values")
    keys = payload.get("keys") if action == "reset_model_settings" else list(values or {})
    if not isinstance(keys, list) or not 1 <= len(keys) <= 100 or any(not isinstance(key, str) for key in keys):
        raise ValueError("Provide 1 to 100 setting keys")
    if action == "set_model_settings":
        if not isinstance(values, dict) or any(type(value) not in (str, int, float, bool) or
                (type(value) is str and value.startswith("=")) for value in values.values()):
            raise ValueError("Provide literal Cura setting values")
        for key in keys:
            if key not in stack.getAllKeys() or not stack.getProperty(key, "settable_per_mesh"):
                raise ValueError("Setting is unavailable per model: " + key)
    local = node.callDecoration("getStack")
    if action == "reset_model_settings":
        if local is not None:
            for key in keys:
                if local.getTop().getInstance(key) is not None:
                    local.getTop().removeInstance(key)
    else:
        if local is None:
            node.addDecorator(SettingOverrideDecorator())
            local = node.callDecoration("getStack")
        settings = local.getTop()
        for key, value in values.items():
            instance = settings.getInstance(key)
            if instance is None:
                instance = SettingInstance(local.getSettingDefinition(key), settings)
                instance.setProperty("value", value)
                settings.addInstance(instance)
            else:
                settings.setProperty(key, "value", value)
    return model_overrides(node)


def transform(action, targets, payload):
    from UM.Math.Quaternion import Quaternion
    from UM.Math.Vector import Vector
    from UM.Operations.GroupedOperation import GroupedOperation
    from UM.Operations.MirrorOperation import MirrorOperation
    from UM.Operations.RotateOperation import RotateOperation
    from UM.Operations.ScaleOperation import ScaleOperation
    from UM.Operations.TranslateOperation import TranslateOperation

    values = payload.get("vector")
    if (not isinstance(values, list) or len(values) != 3 or
            any(type(value) not in (int, float) or not -10000 <= value <= 10000 for value in values)):
        raise ValueError("Provide three finite XYZ components within +/-10000")
    if action == "scale_objects" and any(value <= 0 for value in values):
        raise ValueError("Scale multipliers must be positive")
    if action == "mirror_objects" and (any(value not in (-1, 1) for value in values) or -1 not in values):
        raise ValueError("Use -1 for mirrored axes and 1 for other axes")
    operation = GroupedOperation()
    for node in targets:
        if action == "move_objects":
            edit = TranslateOperation(node, Vector(*values))
        elif action == "scale_objects":
            edit = ScaleOperation(node, Vector(*values))
        elif action == "mirror_objects":
            edit = MirrorOperation(node, Vector(*values), mirror_around_center=True)
        else:
            x, y, z = map(math.radians, values)
            rotation = (Quaternion.fromAngleAxis(z, Vector(0, 0, 1)) *
                        Quaternion.fromAngleAxis(y, Vector(0, 1, 0)) *
                        Quaternion.fromAngleAxis(x, Vector(1, 0, 0)))
            edit = RotateOperation(node, rotation)
        operation.addOperation(edit)
    operation.push()


def scene_snapshot(root, nodes, stack):
    visible = {}
    rows = []
    for node in nodes:
        if node is root or not node.isSelectable():
            continue
        group = bool(node.callDecoration("isGroup"))
        mesh = node.getMeshData()
        node_id = str(id(node))
        row = {
            "id": node_id, "name": node.getName(), "group": group,
            "parent_id": None if node.getParent() is root else str(id(node.getParent())),
            "build_plate": node.callDecoration("getBuildPlateNumber"),
            "extruder_id": node.callDecoration("getActiveExtruder"),
        }
        if group or (mesh is not None and node.callDecoration("isSliceable")):
            row["world_position"] = xyz(node.getWorldPosition())
            row["local_scale"] = xyz(node.getScale())
            row["setting_overrides"] = model_overrides(node)
            bounds = node.getBoundingBox()
            if bounds is not None:
                row["world_bounds"] = {"min": xyz(bounds.minimum), "max": xyz(bounds.maximum)}
            visible[node_id] = node
            rows.append(row)
    # Bind an approval to object identities, hierarchy, placement, and tool state.
    identity = [(str(id(n)), n.getName(), str(id(n.getParent())),
                 str(n.getWorldTransformation()), str(id(n.getMeshData())),
                 n.callDecoration("getBuildPlateNumber"),
                 n.callDecoration("getActiveExtruder"))
                for n in nodes if n is not root and n.isSelectable()]
    state = [stack.getId(), identity, [row["setting_overrides"] for row in rows],
             [(x.getId(), bool(x.isEnabled)) for x in stack.extruderList]]
    revision = hashlib.sha256(json.dumps(state, default=str).encode()).hexdigest()
    return visible, rows, revision


def execute(action, payload, app, stack, root, nodes, selection, actions):
    by_id, _, revision = scene_snapshot(root, nodes, stack)
    if payload.get("expected_scene") != revision:
        raise ValueError("Cura scene changed after confirmation; inspect again")
    if getattr(app, "_currently_loading_files", None):
        raise ValueError("Cura is loading a model; wait for it to finish")
    if action == "clear_scene":
        app.deleteAll()
        return {"cleared": True}
    if action == "arrange_objects":
        app.arrangeAll()
        return {"action": action, "scheduled": True}
    if action in ("assign_extruder", "set_extruder_enabled"):
        index = payload.get("extruder")
        if type(index) is not int or not 0 <= index < len(stack.extruderList):
            raise ValueError("Invalid extruder index")
        extruder = stack.extruderList[index]
        if action == "set_extruder_enabled":
            enabled = payload.get("enabled")
            if type(enabled) is not bool:
                raise ValueError("Provide enabled as a boolean")
            app.getMachineManager().setExtruderEnabled(index, enabled)
            if bool(extruder.isEnabled) != enabled:
                raise ValueError("Cura did not apply the requested extruder state")
            return {"extruder": index, "enabled": enabled}
        if not extruder.isEnabled:
            raise ValueError("Enable the target extruder before assigning objects")
    ids = payload.get("object_ids")
    minimum = 2 if action in {"merge_objects", "group_objects"} else 1
    if (not isinstance(ids, list) or not minimum <= len(ids) <= 100
            or any(not isinstance(i, str) or i not in by_id for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Provide distinct current scene object IDs")
    targets = [by_id[i] for i in ids]
    if len({n.callDecoration("getBuildPlateNumber") for n in targets}) != 1:
        raise ValueError("Choose objects on the same build plate")
    if action == "export_mesh":
        return export_mesh(app, targets, payload.get("file_path"))
    if action in {"set_model_settings", "reset_model_settings"}:
        if len(targets) != 1 or targets[0].callDecoration("isGroup"):
            raise ValueError("Choose one individual mesh")
        overrides = change_model_settings(action, targets[0], stack, payload)
        app.getController().getScene().sceneChanged.emit(targets[0])
        return {"action": action, "object_ids": ids, "setting_overrides": overrides}
    top_level = {"merge_objects", "group_objects", "ungroup_objects", "duplicate_objects", "scale_to_fit", *TRANSFORMS}
    if action in top_level and any(n.getParent() is not root for n in targets):
        raise ValueError("This operation requires top-level objects")
    if action == "ungroup_objects" and any(not n.callDecoration("isGroup") for n in targets):
        raise ValueError("Choose groups to ungroup")
    if action == "duplicate_objects" and (type(payload.get("copies")) is not int or not 1 <= payload["copies"] <= 20):
        raise ValueError("Provide between 1 and 20 copies")
    if action in TRANSFORMS:
        transform(action, targets, payload)
        return {"action": action, "object_ids": ids}
    if action == "assign_extruder" and any(n.callDecoration("isGroup") for n in targets):
        raise ValueError("Assign individual mesh parts to an extruder")
    if action == "center_objects":
        top = {}
        for node in targets:
            while node.getParent() is not root and node.getParent().callDecoration("isGroup"):
                node = node.getParent()
            top[id(node)] = node
        targets = list(top.values())
    previous = list(selection.getAllSelectedObjects())
    selection.clear()
    try:
        for node in targets:
            selection.add(node)
        if action == "center_objects":
            actions().centerSelection()
        elif action == "scale_to_fit":
            if len(targets) != 1:
                raise ValueError("Choose one top-level object or registered group")
            bounds = targets[0].getBoundingBox()
            if bounds is None:
                raise ValueError("The object has no mesh bounds")
            volume = app.getBuildVolume()
            edge = max(0.0, float(volume.getEdgeDisallowedSize())) + 0.5
            available = [volume.getWidth() - 2 * edge, volume.getHeight() - 0.5,
                         volume.getDepth() - 2 * edge]
            dimensions = xyz(bounds.maximum - bounds.minimum)
            if min(available) <= 0 or max(dimensions) <= 0:
                raise ValueError("The active build volume or model dimensions are invalid")
            factor = min(1.0, *(limit / size for limit, size in zip(available, dimensions) if size > 0))
            if factor < 1.0:
                transform("scale_objects", targets, {"vector": [factor] * 3})
            actions().centerSelection()
            volume.updateNodeBoundaryCheck()
            return {"action": action, "object_ids": ids, "scale_factor": factor,
                    "cura_outside_build_area": bool(getattr(targets[0], "_outside_buildarea", False))}
        elif action == "merge_objects":
            app.mergeSelected()
        elif action == "group_objects":
            app.groupSelected()
        elif action == "ungroup_objects":
            app.ungroupSelected()
        elif action == "delete_objects":
            if not app.getController().getToolsEnabled():
                raise ValueError("Cura has disabled scene editing")
            actions().deleteSelection()
        elif action == "duplicate_objects":
            from cura.MultiplyObjectsJob import MultiplyObjectsJob
            offset = max(app.getBuildVolume().getEdgeDisallowedSize() + 2, 8)
            MultiplyObjectsJob(list(targets), payload["copies"], min_offset=offset).start()
            return {"action": action, "object_ids": ids, "scheduled": True}
        elif action == "lay_flat":
            tool = app.getController().getTool("RotateTool")
            if tool is None or any(n.getParent() is not root for n in targets):
                raise ValueError("Lay Flat requires the Rotate tool and top-level objects")
            tool.layFlat()
            return {"action": action, "object_ids": ids, "scheduled": True}
        elif action == "set_mesh_type":
            mesh_type = payload.get("mesh_type")
            tool = app.getController().getTool("PerObjectSettingsTool")
            if (tool is None or type(mesh_type) is not str or mesh_type not in MESH_TYPES or
                    len(targets) != 1 or targets[0].callDecoration("isGroup")):
                raise ValueError("Choose one mesh and a supported mesh type")
            tool.setMeshType(MESH_TYPES[mesh_type])
            if tool.getMeshType() != MESH_TYPES[mesh_type]:
                raise ValueError("Cura did not apply the mesh type")
            return {"action": action, "object_ids": ids, "mesh_type": mesh_type}
        elif action == "assign_extruder":
            actions().setExtruderForSelection(extruder.getId())
            if any(n.callDecoration("getActiveExtruder") != extruder.getId() for n in targets):
                raise ValueError("Cura did not apply the extruder assignment")
    finally:
        # Merge intentionally leaves Cura's resulting group selected.
        if action not in {"merge_objects", "group_objects", "ungroup_objects", "select_objects"}:
            selection.clear()
            for node in previous:
                if node.getParent() is not None:
                    selection.add(node)
    return {"action": action, "object_ids": ids}
