"""Exercise bridge validation without importing Cura or Qt."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "post_processing", Path(__file__).resolve().parents[1] /
    "cura_plugin/CuraMcpBridge/post_processing.py")
pp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pp)


class Script:
    def __init__(self):
        self.values = {**pp.SAFE, "pause_layer": 1}
        self.result = None

    def getSettingValueByKey(self, key):
        return self.values[key]

    def execute(self, chunks):
        chunks[2] = "; Native pause\nM0 ; Do the actual pause\n" + chunks[2]
        return chunks if self.result is None else self.result


class Processor:
    scriptList = [pp.KEY]
    loadedScriptList = [pp.KEY, "FilamentChange"]

    def __init__(self):
        self._script_list = [Script()]

    def getScriptLabelByKey(self, key):
        return key


class Stack:
    def getId(self):
        return "test-machine"

    def getMetaDataEntry(self, key, default):
        return default

    def getProperty(self, key, prop):
        return "Griffin"


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.plugin = Processor()
        self.raw = [";HEADER\n", ";LAYER:0\nG1 X1 E1\n", ";LAYER:1\nG1 X2 E2\n"]

    def test_native_pause_exports_without_mutating_slice(self):
        output, layer = pp.export_lines(self.plugin, Stack(), self.raw)
        self.assertEqual(layer, 1)
        self.assertIn("M0 ; Do the actual pause\n;LAYER:1", output[0])
        self.assertNotIn("M0", "".join(self.raw))

    def test_discovery_reads_cura_list_properties(self):
        result = pp.inspect(self.plugin, Stack())
        self.assertEqual(result["active"][0]["settings"]["pause_layer"], 1)
        self.assertEqual([s["key"] for s in result["available"] if s["mcp_configurable"]],
                         [pp.KEY])

    def test_rejects_duplicate_or_unexpected_commands(self):
        self.plugin._script_list[0].result = ["G1 X1 E1\nM0\nG28\nG1 X2 E2\n"]
        with self.assertRaisesRegex(ValueError, "exactly one pause"):
            pp.export_lines(self.plugin, Stack(), self.raw)
        self.raw[0] += "M0\n"
        with self.assertRaisesRegex(ValueError, "already contains"):
            pp.export_lines(self.plugin, Stack(), self.raw)

    def test_rejects_raft_and_arbitrary_script_settings(self):
        with self.assertRaisesRegex(ValueError, "no raft"):
            pp.export_lines(self.plugin, Stack(), [";LAYER:-1\n", *self.raw])
        self.plugin._script_list[0].values["custom_gcode_after_pause"] = "G28"
        with self.assertRaisesRegex(ValueError, "no extra commands"):
            pp.export_lines(self.plugin, Stack(), self.raw)


if __name__ == "__main__":
    unittest.main()
