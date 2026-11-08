"""Bounded, main-thread CuraEngine comparison of temporary settings."""
from time import monotonic
from uuid import uuid4

from . import configuration_ops, scene_ops


LIMITS = {"layer_height": (0.04, 1), "infill_sparse_density": (0, 100),
          "wall_line_count": (0, 20), "top_layers": (0, 50), "bottom_layers": (0, 50),
          "speed_print": (5, 300)}
INTEGER_SETTINGS = {"wall_line_count", "top_layers", "bottom_layers"}


def validate(variants):
    if not isinstance(variants, list) or not 2 <= len(variants) <= 5:
        raise ValueError("Provide 2 to 5 slice variants")
    names = set()
    for variant in variants:
        if not isinstance(variant, dict) or set(variant) != {"name", "values"}:
            raise ValueError("Each variant needs a name and settings")
        name, values = variant["name"], variant["values"]
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or name in names:
            raise ValueError("Use unique variant names of 1 to 80 characters")
        names.add(name)
        if not isinstance(values, dict) or not values:
            raise ValueError("Provide supported numeric settings for each variant")
        for key, value in values.items():
            if (key not in LIMITS or type(value) not in (int, float) or
                    not LIMITS[key][0] <= value <= LIMITS[key][1] or
                    (key in INTEGER_SETTINGS and type(value) is not int)):
                raise ValueError("Invalid comparison setting: " + key)


class Comparison:
    def __init__(self, app, stack, variants, expected_scene, expected_configuration, parent):
        from PyQt6.QtCore import QCoreApplication, QTimer
        from UM.Backend.Backend import BackendState

        validate(variants)
        self.app = app
        self.stack = stack
        self.overrides = stack.userChanges
        self.scene = app.getController().getScene()
        self.plate = app.getMultiBuildPlateModel().activeBuildPlate
        self.backend = app.getBackend()
        self.states = BackendState
        self.variants = variants
        self.results = []
        self.original = {}
        self.applied = {}
        self.id = uuid4().hex
        self.status = "running"
        self.error = None
        self.conflicts = []
        self.scene_revision, rows = self.scene_state()
        self.configuration = configuration_ops.revision(stack)
        if expected_scene != self.scene_revision or expected_configuration != self.configuration:
            raise ValueError("Scene or configuration changed after confirmation")
        if not any(row["build_plate"] == self.plate and not row["group"] for row in rows):
            raise ValueError("Load a model on the active build plate")
        if self.backend._slicing or getattr(app, "_currently_loading_files", None):
            raise ValueError("Wait for Cura's current operation to finish")
        if any(key not in stack.getAllKeys() for variant in variants for key in variant["values"]):
            raise ValueError("A comparison setting is unavailable on this machine")
        self.timer = QTimer(parent)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.tick)
        self.deadline = None
        self.ready_at = None
        self.quit_signal = QCoreApplication.instance().aboutToQuit
        self.quit_signal.connect(self.cancel)
        self.timer.start()

    def scene_state(self):
        from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
        root = self.scene.getRoot()
        _, rows, revision = scene_ops.scene_snapshot(root, list(DepthFirstIterator(root)), self.stack)
        return revision, rows

    def start_next(self):
        variant = self.variants[len(self.results)]
        overrides = self.overrides
        for key, value in variant["values"].items():
            instance = overrides.getInstance(key)
            if instance is not None:
                self.original[key] = instance.value
            self.applied[key] = value
            overrides.setProperty(key, "value", value)
            if overrides.getInstance(key) is None or overrides.getProperty(key, "value") != value:
                raise ValueError("Cura did not accept comparison setting: " + key)
        self.configuration = configuration_ops.revision(self.stack)
        self.deadline = monotonic() + 120
        self.ready_at = monotonic() + 1.5

    def restore(self):
        overrides = self.overrides
        for key, value in self.applied.items():
            if overrides.getInstance(key) is None or overrides.getProperty(key, "value") != value:
                self.conflicts.append(key)
                continue
            if key in self.original:
                overrides.setProperty(key, "value", self.original[key])
            else:
                overrides.removeInstance(key)
        self.original.clear()
        self.applied.clear()

    def tick(self):
        try:
            if self.deadline is None:
                if (self.app.getGlobalContainerStack() is not self.stack or
                        self.app.getMultiBuildPlateModel().activeBuildPlate != self.plate or
                        self.scene_state()[0] != self.scene_revision or
                        configuration_ops.revision(self.stack) != self.configuration or self.backend._slicing):
                    self.finish("failed", "Cura changed before the comparison started")
                else:
                    self.start_next()
                return
            if (self.app.getGlobalContainerStack() is not self.stack or
                    self.app.getMultiBuildPlateModel().activeBuildPlate != self.plate or
                    self.scene_state()[0] != self.scene_revision or
                    configuration_ops.revision(self.stack) != self.configuration):
                self.finish("failed", "Cura scene or settings changed during comparison")
            elif monotonic() > self.deadline:
                self.finish("failed", "CuraEngine exceeded the per-variant timeout")
            elif self.ready_at is not None:
                if monotonic() >= self.ready_at and not self.backend._change_timer.isActive():
                    self.ready_at = None
                    if not self.backend._slicing:
                        self.backend.forceSlice()
            elif self.backend._backend_state == self.states.Done and not self.backend._slicing:
                if not getattr(self.scene, "gcode_dict", {}).get(self.plate):
                    self.finish("failed", "CuraEngine produced no slice for the active plate")
                    return
                info = self.app.getPrintInformation()
                self.results.append({**self.variants[len(self.results)],
                                     "duration_seconds": int(info.currentPrintTime),
                                     "material_lengths": list(info.materialLengths),
                                     "material_weights": list(info.materialWeights)})
                self.restore()
                if len(self.results) == len(self.variants):
                    self.finish("done")
                else:
                    self.start_next()
        except Exception as error:
            self.finish("failed", str(error))

    def cancel(self):
        if self.status == "running":
            self.finish("cancelled")

    def finish(self, status, error=None):
        if self.status != "running":
            return
        self.status, self.error = status, error
        self.timer.stop()
        self.quit_signal.disconnect(self.cancel)
        try:
            if self.deadline is not None:
                self.backend.stopSlicing()
        finally:
            self.restore()
            if self.deadline is not None:
                self.backend.markSliceAll()

    def report(self):
        return {"comparison_id": self.id, "status": self.status, "results": self.results,
                "variant_count": len(self.variants), "failure_reason": self.error,
                "settings_changed_externally": self.conflicts}
