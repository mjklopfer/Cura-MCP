"""Typed controls for Cura's native machine and profile managers."""
import hashlib
import json
import os
import tempfile
import shutil

KINDS = {"printer", "material", "core", "quality", "intent", "custom_profile",
         "create_profile", "update_profile", "import_profile", "export_profile"}


def package_state(manager):
    state = {
        "installed": [{"id": key, "version": str(version)}
                      for key, version in sorted(manager.getAllInstalledPackageIdsAndVersions())],
        "queued_install": sorted(manager.getPackagesToInstall()),
        "queued_remove": sorted(manager.getToRemovePackageIDs()),
        "pending_restart": bool(manager.hasPackagesToRemoveOrInstall),
    }
    state["revision"] = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return state


def manage_package(manager, payload):
    from .project_io import file_hash
    from UM.Version import Version

    state = package_state(manager)
    if state["revision"] != payload.get("expected_package_state"):
        raise ValueError("Cura package state changed after confirmation")
    operation, target = payload.get("package_action"), payload.get("target_id")
    if (operation not in {"install", "update", "remove"} or not isinstance(target, str)
            or not target or len(target) > 200 or target.casefold() == "curamcpbridge"):
        raise ValueError("Invalid Cura package operation")
    if target in state["queued_install"] or target in state["queued_remove"]:
        raise ValueError("This package already has a queued operation")
    installed = {item["id"]: item["version"] for item in state["installed"]}
    if operation == "remove":
        if target not in installed or not manager.isUserInstalledPackage(target):
            raise ValueError("Choose a user-installed package")
        manager.removePackage(target)
        if target not in manager.getToRemovePackageIDs():
            raise ValueError("Cura did not queue the removal")
    else:
        filename = payload.get("file_path")
        if (not isinstance(filename, str) or not os.path.isabs(filename)
                or not filename.lower().endswith(".curapackage") or not os.path.isfile(filename)
                or os.path.getsize(filename) > 100_000_000):
            raise ValueError("Provide an absolute .curapackage file up to 100 MB")
        if (operation == "update") != (target in installed):
            raise ValueError("Install requires a new ID and update requires an installed ID")
        with tempfile.TemporaryDirectory() as directory:
            staged = os.path.join(directory, "package.curapackage")
            shutil.copyfile(filename, staged)
            if file_hash(staged) != payload.get("package_sha256"):
                raise ValueError("Cura package contents changed after confirmation")
            info = manager.getPackageInfo(staged)
            if info.get("package_id") != target or not info.get("package_version"):
                raise ValueError("Package ID or version did not match the request")
            if operation == "update" and Version(info["package_version"]) <= Version(installed[target]):
                raise ValueError("The update must have a newer version")
            if manager.getPackageLicense(staged):
                raise ValueError("Use Cura's native Marketplace to review this package license")
            if manager.installPackage(staged) != target or target not in manager.getPackagesToInstall():
                raise ValueError("Cura did not queue the package")
    return {"package_id": target, "operation": operation, "queued": True, "restart_required": True}


def profile_file(app, kind, custom, target, payload):
    filename = payload.get("file_path")
    if not isinstance(filename, str) or not os.path.isabs(filename) or not filename.endswith(".curaprofile"):
        raise ValueError("Provide an absolute .curaprofile path")
    registry = app.getContainerRegistry()
    if kind == "import_profile":
        from .project_io import file_hash
        if not os.path.isfile(filename) or os.path.getsize(filename) > 10_000_000:
            raise ValueError("Profile must be a readable file up to 10 MB")
        if file_hash(filename) != payload.get("profile_sha256"):
            raise ValueError("Profile file changed after confirmation")
        result = registry.importProfile(filename)
        if result.get("status") == "error":
            raise ValueError(result.get("message", "Cura profile import failed"))
        return result
    if target not in custom or os.path.lexists(filename):
        raise ValueError("Choose an existing custom profile and a new output filename")
    from UM.PluginRegistry import PluginRegistry
    plugins = PluginRegistry.getInstance()
    if "CuraProfileWriter" not in plugins.getActivePlugins():
        raise ValueError("The Cura profile writer is unavailable")
    writer = plugins.getPluginObject("CuraProfileWriter")
    group = custom[target]
    containers = [registry.findContainers(id=entry["id"])[0] for entry in
                  [group.metadata_for_global, *group.metadata_per_extruder.values()]]
    with tempfile.TemporaryDirectory(dir=os.path.dirname(filename)) as temporary:
        staged = os.path.join(temporary, "profile.curaprofile")
        if not writer.write(staged, containers):
            raise ValueError("Cura profile export failed")
        os.link(staged, filename)
    return {"status": "success", "file_path": filename, "bytes": os.path.getsize(filename)}


def current(stack):
    return {
        "printer": {"id": stack.getId(), "name": stack.getName()},
        "quality": {"id": stack.quality.getMetaDataEntry("quality_type"), "name": stack.quality.getName()},
        "custom_profile": {"id": stack.qualityChanges.getId(), "name": stack.qualityChanges.getName()},
        "extruders": [{"position": i, "core": e.variant.getName(),
                       "material_id": e.material.getMetaDataEntry("base_file") or e.material.getId(),
                       "material": e.material.getName(),
                       "intent": e.intent.getMetaDataEntry("intent_category", "default")}
                      for i, e in enumerate(stack.extruderList)]
    }


def revision(stack):
    overrides = [{k: s.userChanges.getProperty(k, "value") for k in sorted(s.userChanges.getAllKeys())}
                 for s in [stack, *stack.extruderList]]
    data = json.dumps([current(stack), overrides], sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def native(app, stack):
    from cura.Machines.ContainerTree import ContainerTree
    tree = ContainerTree.getInstance()
    printers = {s.getId(): s for s in app.getContainerRegistry().findContainerStacks(type="machine")}
    machine = tree.machines.get(stack.definition.getId())
    variants = machine.variants if machine else {}
    quality = tree.getCurrentQualityGroups()
    custom = {g.metadata_for_global["id"]: g for g in tree.getCurrentQualityChangesGroups()
              if g.metadata_for_global and "id" in g.metadata_for_global}
    return printers, variants, quality, custom


def inspect(app, stack):
    printers, variants, quality, custom = native(app, stack)
    manager = app.getMachineManager()
    state = current(stack)
    materials = []
    for i, ext in enumerate(stack.extruderList):
        variant = variants.get(ext.variant.getName())
        entries = variant.materials if variant else {}
        materials.append({"extruder": i, "choices": [
            {"id": key, "name": node.container.getName()}
            for key, node in sorted(entries.items()) if node.container is not None]})
    active_quality = state["quality"]["id"]
    active_group = quality.get(active_quality)
    intents = {"default"}
    if active_group:
        intents.update(i.intent_category for node in active_group.nodes_for_extruders.values()
                       for i in node.intents.values())
    return {"revision": revision(stack), "current": state,
            "printers": [{"id": key, "name": s.getName()} for key, s in printers.items()],
            "cores": sorted(variants),
            "materials": materials,
            "quality_profiles": [{"id": key, "name": group.getName()} for key, group in quality.items()],
            "custom_profiles": [{"id": key, "name": group.name} for key, group in custom.items()],
            "intents": sorted(intents),
            "has_unsaved_profile_overrides": bool(manager.hasUserSettings)}


def execute(app, stack, payload):
    if payload.get("expected_configuration") != revision(stack):
        raise ValueError("Cura configuration changed after confirmation; inspect again")
    kind, target = payload.get("configuration_kind"), payload.get("target_id")
    if kind not in KINDS or (kind != "import_profile" and
            (not isinstance(target, str) or not target.strip() or len(target) > 256)):
        raise ValueError("Invalid Cura configuration target")
    manager = app.getMachineManager()
    printers, variants, quality, custom = native(app, stack)
    if kind in {"import_profile", "export_profile"}:
        return profile_file(app, kind, custom, target, payload)
    index = payload.get("extruder")
    if kind in {"material", "core"}:
        if type(index) is not int or not 0 <= index < len(stack.extruderList):
            raise ValueError("Invalid extruder index")
    elif index is not None:
        raise ValueError("Extruder is only used for material and core selection")
    if kind == "printer":
        if target not in printers:
            raise ValueError("Unknown configured Cura printer")
        if target != stack.getId():
            manager.setActiveMachine(target)
        stack = app.getGlobalContainerStack()
        valid = stack is not None and stack.getId() == target
    elif kind == "material":
        before = current(stack)["extruders"][index]["material_id"]
        if before != target and not manager.setMaterialById(str(index), target):
            raise ValueError("Material is unavailable for this printer and core")
        valid = current(stack)["extruders"][index]["material_id"] == target
    elif kind == "core":
        if target not in variants:
            raise ValueError("Core is unavailable for this printer")
        if stack.extruderList[index].variant.getName() != target:
            manager.setVariantByName(str(index), target)
        valid = stack.extruderList[index].variant.getName() == target
    elif kind == "quality":
        if target not in quality:
            raise ValueError("Quality is unavailable for this configuration")
        manager.setQualityGroup(quality[target])
        valid = stack.quality.getMetaDataEntry("quality_type") == target
    elif kind == "intent":
        if target not in inspect(app, stack)["intents"]:
            raise ValueError("Intent is unavailable for the active quality")
        manager.setIntentByCategory(target)
        valid = manager.activeIntentCategory == target
    elif kind == "custom_profile":
        if target not in custom:
            raise ValueError("Custom profile is unavailable for this configuration")
        manager.setQualityChangesGroup(custom[target])
        valid = stack.qualityChanges.getId() == target
    elif kind == "create_profile":
        if any(c.name.casefold() == target.casefold() for c in custom.values()):
            raise ValueError("A profile with that name already exists")
        if not manager.hasUserSettings:
            raise ValueError("Change a setting before saving an adjusted profile")
        previous = stack.qualityChanges.getId()
        app.getQualityManagementModel().createQualityChanges(target, True)
        valid = stack.qualityChanges.getId() != previous
    else:
        if target not in custom or stack.qualityChanges.getId() != target:
            raise ValueError("Only the explicitly identified active custom profile can be updated")
        if not manager.hasUserSettings:
            raise ValueError("No pending settings to save to this profile")
        from cura.Settings.ContainerManager import ContainerManager
        updated = ContainerManager.getInstance().updateQualityChanges()
        valid = updated and stack.qualityChanges.getId() == target and not manager.hasUserSettings
    if not valid:
        raise ValueError("Cura did not verify the requested selection; inspect the active configuration")
    return {"applied": kind, "target_id": target, "current": current(stack)}
