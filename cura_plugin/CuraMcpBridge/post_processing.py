"""Discover Cura extensions and control the native Griffin layer pause."""
import hashlib
import json
import re

KEY = "PauseAtHeight"
ACTIONS = {"add_griffin_pause", "remove_post_processing_script"}
SAFE = {"pause_at": "layer_no", "pause_method": "griffin", "redo_layer": False,
        "display_text": "", "custom_gcode_before_pause": "",
        "custom_gcode_after_pause": "", "beep_at_pause": False}


def revision(plugin, stack):
    # The native serialized configuration binds options and ordering, including
    # settings of scripts we do not expose for editing.
    keys = list(plugin.scriptList)
    pause_values = [{key: s.getSettingValueByKey(key) for key in (*SAFE, "pause_layer")}
                    for key_name, s in zip(keys, plugin._script_list) if key_name == KEY]
    data = [stack.getId(), keys, pause_values,
            stack.getMetaDataEntry("post_processing_scripts", "")]
    return hashlib.sha256(json.dumps(data, default=str).encode()).hexdigest()


def inspect(plugin, stack):
    active = []
    keys = list(plugin.scriptList)
    for index, script in enumerate(plugin._script_list):
        key = keys[index]
        item = {"index": index, "key": key, "label": plugin.getScriptLabelByKey(key)}
        if key == KEY:
            item["settings"] = {k: script.getSettingValueByKey(k)
                                for k in ("pause_at", "pause_method", "pause_layer", "redo_layer")}
        active.append(item)
    return {"extension": "PostProcessingPlugin", "revision": revision(plugin, stack),
            "available": [{"key": k, "label": plugin.getScriptLabelByKey(k),
                           "mcp_configurable": k == KEY} for k in plugin.loadedScriptList],
            "active": active}


def execute(plugin, stack, action, payload):
    if payload.get("expected_post_processing") != revision(plugin, stack):
        raise ValueError("Cura post-processing scripts changed after confirmation")
    if action == "remove_post_processing_script":
        index = payload.get("script_index")
        if type(index) is not int or not 0 <= index < len(plugin.scriptList):
            raise ValueError("Invalid post-processing script index")
        plugin.removeScriptByIndex(index)
    elif action == "add_griffin_pause":
        layer = payload.get("pause_layer")
        if type(layer) is not int or not 1 <= layer <= 100000:
            raise ValueError("Provide a zero-based layer from 1 to 100000")
        if stack.getProperty("machine_gcode_flavor", "value") != "Griffin":
            raise ValueError("Griffin pause requires a Griffin machine profile")
        if plugin.scriptList:
            raise ValueError("Remove existing scripts before adding a managed Griffin pause")
        plugin.loadAllScripts()
        if KEY not in plugin.loadedScriptList:
            raise ValueError("Native Pause at Height script is unavailable")
        plugin.addScriptToList(KEY)
        try:
            script = plugin._script_list[-1]
            values = {**SAFE, "pause_layer": layer}
            if not values.keys() <= script.getSettingData()["settings"].keys():
                raise ValueError("Unsupported native Pause at Height script version")
            for key, value in values.items():
                script._instance.setProperty(key, "value", value)
            if any(script.getSettingValueByKey(key) != value for key, value in values.items()):
                raise ValueError("Cura did not apply all pause settings")
        except Exception:
            plugin.removeScriptByIndex(len(plugin.scriptList) - 1)
            plugin.writeScriptsToStack()
            raise
    plugin.writeScriptsToStack()
    return inspect(plugin, stack)


def _commands(text):
    return [c for line in text.splitlines() if (c := line.split(";", 1)[0].strip())]


def export_lines(plugin, stack, chunks):
    if not plugin.scriptList:
        return chunks, None
    if list(plugin.scriptList) != [KEY]:
        raise ValueError("MCP export supports one native Griffin pause; remove other scripts or export using Cura's UI")
    script = plugin._script_list[0]
    if stack.getProperty("machine_gcode_flavor", "value") != "Griffin" or any(
            script.getSettingValueByKey(key) != val for key, val in SAFE.items()):
        raise ValueError("MCP export supports only the Griffin layer pause with no extra commands")
    layer = script.getSettingValueByKey("pause_layer")
    if type(layer) is not int or layer < 1:
        raise ValueError("Invalid Griffin pause layer")
    before = "".join(chunks)
    markers = list(re.finditer(r"(?m)^;LAYER:(-?\d+)\r?$", before))
    target = [m for m in markers if int(m.group(1)) == layer]
    if len(target) != 1 or any(int(m.group(1)) < 0 for m in markers):
        raise ValueError("Managed pause requires one matching layer and no raft")
    commands = _commands(before)
    if ";POSTPROCESSED" in before or any(re.match(r"^M0(?:\s|$)", c) for c in commands):
        raise ValueError("Slice again before exporting; G-code already contains post-processing or a pause")
    # Cura's native script prepends M0 to the matching layer chunk.
    after = "".join(script.execute(list(chunks)))
    processed = _commands(after)
    at = len(_commands(before[:target[0].start()]))
    if processed != commands[:at] + ["M0"] + commands[at:]:
        raise ValueError("Native script did not insert exactly one pause at the requested boundary")
    return [after], layer
