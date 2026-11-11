"""Loopback-only MCP status and guarded workspace-command endpoint for Cura."""
import json
import os
import secrets
import socket
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .project_io import path_info, plan_save, atomic_project_write
from . import scene_ops, post_processing, configuration_ops, comparison, cloud_ops

from PyQt6.QtCore import QObject, QTimer, QUrl

from UM.Extension import Extension
from UM.Logger import Logger
from UM.Resources import Resources


class ExclusiveLoopbackServer(ThreadingHTTPServer):
    """Prevent competing Windows Cura instances from sharing one bridge port."""
    allow_reuse_address = False

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CuraMcpBridge(QObject, Extension):
    """Run a loopback bridge without touching Cura state until a command is accepted."""

    PORT = 49621
    CONNECTION_FILE = "cura-mcp-bridge.json"

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        Extension.__init__(self)
        self._lock = threading.Lock()
        self._pending_commands = []
        self._started = False
        self._current_project = None
        self._pending_project = None
        self._tracking_connected = False
        self._save_jobs = {}
        self._comparison = None
        self._cloud = cloud_ops.CloudOperations()
        self._snapshot = {"schema_version": 1, "ready": False, "detail": "Cura bridge is starting."}
        self._connection_path = os.path.join(self._preferences_directory(), self.CONNECTION_FILE)
        self._token = self._load_or_create_token()
        self._timer = QTimer(self)
        self._timer.setInterval(750)
        # Do not inspect the active machine, extruders, or scene at startup.
        # Cura lazily constructs those objects; doing so can surface a damaged
        # user profile and make an otherwise recoverable session unusable.
        self._timer.timeout.connect(self._execute_pending_commands)
        # Startup deliberately avoids CuraApplication, Preferences, machine stacks,
        # material containers, and scene state. This plugin must not influence Cura's
        # profile recovery or material filtering.
        QTimer.singleShot(0, self._start)

    @staticmethod
    def _preferences_directory():
        return Resources.getConfigStoragePath()

    def _load_or_create_token(self):
        try:
            with open(self._connection_path, "r", encoding="utf-8") as source:
                existing = json.load(source).get("token")
            if isinstance(existing, str) and existing:
                return existing
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return secrets.token_urlsafe(32)

    def _start(self):
        if self._started:
            return
        self._started = True
        with self._lock:
            self._snapshot = {
                "schema_version": 1,
                "ready": True,
                "bridge_version": "0.1.10",
                "process_id": os.getpid(),
                "printer": None,
                "active_profile": None,
                "extruders": [],
                "build_plate_object_count": 0,
                "detail": "Bridge is running without inspecting Cura configuration, profiles, materials, or scene state.",
            }
        self._timer.start()
        self._start_http_server()

    def _start_http_server(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/v1/status":
                    self.send_error(404)
                    return
                if not secrets.compare_digest(self.headers.get("X-Cura-Bridge-Token", ""), bridge._token):
                    self.send_error(401)
                    return
                with bridge._lock:
                    body = json.dumps(bridge._snapshot).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                command_name = self.path.removeprefix('/v1/commands/')
                if command_name not in {'load_file', 'inspect', 'get_settings', 'set_settings', 'reset_settings', 'slice', 'export_gcode',
                                        'path_info', 'plan_project_save', 'save_project', 'project_save_status',
                                        'inspect_extensions', 'navigate', 'inspect_configuration',
                                        'set_configuration', 'inspect_estimates', 'inspect_layers', 'snapshot',
                                        'compare_slices', 'comparison_status', 'cancel_comparison',
                                        'manage_package', 'activate_extension_menu'} | scene_ops.ACTIONS | post_processing.ACTIONS | cloud_ops.ACTIONS:
                    self.send_error(404)
                    return
                if not secrets.compare_digest(self.headers.get("X-Cura-Bridge-Token", ""), bridge._token):
                    self.send_error(401)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 1 or length > 16 * 1024:
                        raise ValueError("invalid request length")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    command = {'action': command_name, 'payload': payload, 'event': threading.Event(), 'cancelled': False}
                    with bridge._lock:
                        bridge._pending_commands.append(command)
                    if not command['event'].wait(6):
                        with bridge._lock:
                            command['cancelled'] = True
                        self.send_error(504, 'Cura main-thread command timed out; inspect state before retrying')
                        return
                    body = json.dumps(command['result'], default=str).encode('utf-8')
                    self.send_response(400 if 'error' in command['result'] else 200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                except (ValueError, json.JSONDecodeError) as error:
                    self.send_error(400, str(error))

            def log_message(self, *_args):
                return

        try:
            self._server = ExclusiveLoopbackServer(("127.0.0.1", self.PORT), Handler)
        except OSError as error:
            Logger.error("Cura MCP Bridge could not bind loopback port %s: %s", self.PORT, error)
            return
        thread = threading.Thread(target=self._server.serve_forever, name="CuraMcpBridge", daemon=True)
        thread.start()
        os.makedirs(os.path.dirname(self._connection_path), exist_ok=True)
        with open(self._connection_path, "w", encoding="utf-8") as output:
            json.dump({"host": "127.0.0.1", "port": self.PORT, "token": self._token}, output)
        try:
            os.chmod(self._connection_path, 0o600)
        except OSError:
            pass
        Logger.log("i", "Cura MCP Bridge status endpoint enabled on loopback.")

    def _execute_pending_commands(self):
        """Run queued loopback requests on Cura's main thread, never the HTTP thread."""
        with self._lock:
            commands = self._pending_commands
            self._pending_commands = []
        for command in commands:
            try:
                if command.get('cancelled'):
                    continue
                command['result'] = self._execute_workspace_command(command['action'], command['payload'])
            except Exception as error:
                Logger.logException("e", "Cura MCP Bridge command failed: %s", error)
                command['result'] = {'error': str(error)}
            finally:
                if 'event' in command:
                    command['event'].set()

    def _execute_workspace_command(self, action, payload):
        """Explicit on-demand Cura access, exclusively on the main thread."""
        from cura.CuraApplication import CuraApplication
        app = CuraApplication.getInstance()
        if not self._tracking_connected:
            app.workspaceLoaded.connect(self._on_workspace_loaded)
            self._tracking_connected = True
        if action == 'path_info':
            return path_info(payload.get('file_path'))
        if action in {'inspect_cloud','cloud_print_status','inspect_cloud_connections','plan_cloud_connection'}:
            return self._cloud.execute(app, action, payload)
        if action == 'project_save_status':
            job = self._save_jobs.get(payload.get('operation_id'))
            if job is None:
                raise ValueError('Unknown project save operation')
            return {key: value for key, value in job.items() if key not in ('job', 'callback')}
        mutations = {'load_file', 'set_settings', 'reset_settings', 'slice', 'save_project',
                     'set_configuration', 'compare_slices', 'manage_package',
                     'activate_extension_menu', 'submit_cloud_print', 'connect_cloud'} | scene_ops.ACTIONS | post_processing.ACTIONS
        if action in mutations and any(j['status'] == 'running' for j in self._save_jobs.values()):
            raise ValueError('A project save is running; poll its status before changing the workspace')
        if action in {'comparison_status', 'cancel_comparison'}:
            comparison_id = payload.get('comparison_id')
            if self._comparison is None or (
                    (comparison_id is not None or action == 'cancel_comparison') and
                    self._comparison.id != comparison_id):
                raise ValueError('Unknown slice comparison')
            if action == 'cancel_comparison':
                self._comparison.cancel()
            return self._comparison.report()
        if self._comparison and self._comparison.status == 'running' and action in (
                mutations | {'export_gcode', 'inspect_estimates', 'inspect_layers'}):
            raise ValueError('A slice comparison is running; poll or cancel it first')
        if action in mutations and any(j['status'] in ('starting','uploading') for j in self._cloud.jobs.values()):
            raise ValueError('A cloud submission is running; poll its status before changing the workspace')
        if action=='connect_cloud':
            return self._cloud.execute(app, action, payload)
        if action in {'plan_cloud_print','submit_cloud_print'}:
            import hashlib
            state = self._execute_workspace_command('inspect', {})
            plate = app.getMultiBuildPlateModel().activeBuildPlate
            chunks = getattr(app.getController().getScene(), 'gcode_dict', {}).get(plate, [])
            digest = hashlib.sha256()
            for chunk in chunks:
                digest.update(chunk.encode('utf-8'))
            context = {'machine_id':state['machine']['id'], 'build_plate':plate,
                       'scene_revision':state['scene_revision'],
                       'post_processing_revision':state['post_processing_revision'],
                       'toolpath_sha256':digest.hexdigest(),
                       'slice_ready':state['backend_state']=='Done' and bool(chunks)}
            return self._cloud.execute(app, action, payload, context)
        if action == 'load_file':
            filename = payload.get('file_path')
            info = path_info(filename)
            if not info.get('is_file') or not info.get('readable'):
                raise ValueError('Cura cannot read requested file: ' + json.dumps(info))
            if os.path.splitext(filename)[1].lower() not in {'.stl', '.3mf', '.obj', '.amf', '.x3d', '.gcode', '.ufp'}:
                raise ValueError('Unsupported Cura file extension')
            mode = payload.get('project_mode', 'open_as_project')
            if mode not in ('open_as_project', 'open_as_model'):
                raise ValueError('Invalid project_mode')
            if filename.lower().endswith('.3mf') and mode == 'open_as_project':
                self._pending_project = os.path.realpath(filename)
            app.readLocalFile(QUrl.fromLocalFile(filename), project_mode=mode)
            return {'accepted': True, 'file_path': filename, 'project_mode': mode,
                    'detail': 'File read requested; inspect scene after loading completes.'}
        if action == 'plan_project_save':
            location = self._project_location(app)
            return plan_save(payload, location['file_path'], location['folder'])
        if action == 'save_project':
            return self._start_project_save(app, payload)
        stack = app.getGlobalContainerStack()
        if stack is None:
            raise ValueError('No active Cura machine')
        if action == 'compare_slices':
            self._comparison = comparison.Comparison(app, stack, payload.get('variants'),
                payload.get('expected_scene'), payload.get('expected_configuration'), self)
            return self._comparison.report()
        if action == 'manage_package':
            return configuration_ops.manage_package(app.getPackageManager(), payload)
        if action == 'activate_extension_menu':
            plugin_id, item = payload.get('target_id'), payload.get('menu_item')
            choices = [extension for extension in app.getExtensions()
                       if extension.getPluginId() == plugin_id and item in extension.getMenuItemList()]
            if len(choices) != 1 or choices[0] is self:
                raise ValueError('Choose one exact active extension menu action')
            QTimer.singleShot(0, lambda: choices[0].activateMenuItem(item))
            return {'plugin_id': plugin_id, 'menu_item': item, 'scheduled': True}
        if action == 'inspect_configuration':
            return configuration_ops.inspect(app, stack)
        if action == 'set_configuration':
            return configuration_ops.execute(app, stack, payload)
        if action in {'inspect_estimates', 'inspect_layers'}:
            from UM.Backend.Backend import BackendState
            scene = app.getController().getScene()
            plate = app.getMultiBuildPlateModel().activeBuildPlate
            if app.getBackend()._backend_state != BackendState.Done or not getattr(scene, 'gcode_dict', {}).get(plate):
                return {'available': False, 'build_plate': plate}
            if action == 'inspect_layers':
                chunks = scene.gcode_dict[plate]
                return {'available': True, 'build_plate': plate, **scene_ops.inspect_layers(chunks, payload)}
            info = app.getPrintInformation()
            return {'available': True, 'build_plate': plate,
                    'duration_seconds': int(info.currentPrintTime),
                    'material_lengths': list(info.materialLengths),
                    'material_weights': list(info.materialWeights),
                    'material_names': list(info.materialNames)}
        if action == 'snapshot':
            import base64
            from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
            from cura.Snapshot import Snapshot
            image = Snapshot.isometricSnapshot(400, 400)
            if image is None or image.isNull():
                raise ValueError('No renderable build plate snapshot is available')
            data = QByteArray()
            buffer = QBuffer(data)
            if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, 'PNG'):
                raise ValueError('Cura could not encode the build plate snapshot')
            return {'image_png': base64.b64encode(bytes(data)).decode('ascii')}
        if action in {'inspect_extensions', 'navigate', 'inspect', 'export_gcode'} | post_processing.ACTIONS:
            from UM.PluginRegistry import PluginRegistry
            registry = PluginRegistry.getInstance()
            active_plugins = registry.getActivePlugins()
            processor = (registry.getPluginObject('PostProcessingPlugin')
                         if 'PostProcessingPlugin' in active_plugins else None)
        if action == 'inspect_extensions':
            controller = app.getController()
            current = controller.getActiveStage()
            packages = app.getPackageManager()
            return {'active_plugins': sorted(active_plugins),
                    'extension_menus': [{'plugin_id': extension.getPluginId(),
                                         'name': extension.getMenuName(),
                                         'items': extension.getMenuItemList()}
                                        for extension in app.getExtensions()
                                        if extension is not self and extension.getMenuItemList()],
                    'marketplace': {**configuration_ops.package_state(packages),
                                    'signed_in': bool(app.getCuraAPI().account.isLoggedIn)},
                    'stages': sorted(controller.getAllStages()),
                    'active_stage': current.getId() if current else None,
                    'tools': sorted(controller.getAllTools()),
                    'navigation': ['prepare', 'preview', 'monitor', 'post_processing', 'marketplace', 'account_sign_in',
                                   'move', 'scale', 'rotate', 'mirror'],
                    'post_processing': post_processing.inspect(processor, stack) if processor else None}
        if action == 'navigate':
            controller = app.getController()
            view = payload.get('view')
            stages = {'prepare': 'PrepareStage', 'preview': 'PreviewStage', 'monitor': 'MonitorStage'}
            tools = {'move': 'TranslateTool', 'scale': 'ScaleTool',
                     'rotate': 'RotateTool', 'mirror': 'MirrorTool'}
            if view == 'post_processing' and processor:
                processor.showPopup()
            elif view == 'marketplace' and 'Marketplace' in active_plugins:
                registry.getPluginObject('Marketplace').show()
            elif view == 'account_sign_in':
                account = app.getCuraAPI().account
                if account.isLoggedIn:
                    return {'view': view, 'already_signed_in': True}
                QTimer.singleShot(0, account.login)
            elif view in stages and stages[view] in controller.getAllStages():
                controller.setActiveStage(stages[view])
                active = controller.getActiveStage()
                if not active or active.getId() != stages[view]:
                    raise ValueError('Cura did not switch to the requested stage')
            elif view in tools and tools[view] in controller.getAllTools():
                controller.setActiveTool(tools[view])
                active = controller.getActiveTool()
                if not active or active.getId() != tools[view]:
                    raise ValueError('Cura did not activate the requested toolbar tool')
            else:
                raise ValueError('Requested Cura view or toolbar tool is unavailable')
            return {'view': view, 'requested': True}
        if action in post_processing.ACTIONS:
            if not processor:
                raise ValueError('Cura Post Processing extension is unavailable')
            return post_processing.execute(processor, stack, action, payload)
        if action in scene_ops.ACTIONS:
            from cura.CuraActions import CuraActions
            from UM.Scene.Selection import Selection
            from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
            root = app.getController().getScene().getRoot()
            return scene_ops.execute(action, payload, app, stack, root,
                                     list(DepthFirstIterator(root)), Selection, CuraActions)
        if action == 'inspect':
            scene = app.getController().getScene()
            from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
            root = scene.getRoot()
            _, scene_nodes, scene_revision = scene_ops.scene_snapshot(
                root, list(DepthFirstIterator(root)), stack)
            objects = [{'name': node.getName()} for node in DepthFirstIterator(scene.getRoot())
                       if hasattr(node, 'callDecoration') and node.callDecoration('isSliceable') and node.getMeshData() is not None]
            return {'machine': {'id': stack.getId(), 'name': stack.getName()},
                    'quality': stack.quality.getName(),
                    'extruders': [{'position': extruder.position, 'material': extruder.material.getName(),
                                   'variant': extruder.variant.getName(), 'enabled': bool(extruder.isEnabled),
                                   'id': extruder.getId()} for extruder in stack.extruderList],
                    'scene_nodes': scene_nodes, 'scene_revision': scene_revision,
                    'post_processing_revision': post_processing.revision(processor, stack) if processor else None,
                    'objects': objects, 'backend_state': getattr(app.getBackend(), '_backend_state').name,
                    'gcode_build_plates': list(getattr(scene, 'gcode_dict', {}).keys()),
                    'project_location': self._project_location(app)}
        if action == 'reset_settings' and payload.get('expected_configuration') != configuration_ops.revision(stack):
            raise ValueError('Cura configuration changed after confirmation')
        index = payload.get('extruder')
        if index is not None:
            if not isinstance(index, int) or not 0 <= index < len(stack.extruderList):
                raise ValueError('Invalid extruder index')
            stack = stack.extruderList[index]
        if action == 'get_settings':
            keys = payload.get('keys')
            if not keys:
                return {'keys': sorted(stack.getAllKeys())}
            if len(keys) > 200:
                raise ValueError('Read at most 200 settings per call')
            return {'settings': {key: {'value': stack.getProperty(key, 'value'),
                'type': stack.getProperty(key, 'type'), 'enabled': stack.getProperty(key, 'enabled'),
                'user_override': stack.userChanges.getInstance(key) is not None}
                for key in keys if key in stack.getAllKeys()}}
        if action == 'reset_settings':
            keys = payload.get('keys')
            known = stack.getAllKeys()
            if (not isinstance(keys, list) or not 1 <= len(keys) <= 100 or
                    any(not isinstance(key, str) or key not in known for key in keys)):
                raise ValueError('Provide 1 to 100 known Cura settings')
            removed = []
            for key in dict.fromkeys(keys):
                if stack.userChanges.getInstance(key) is not None:
                    stack.userChanges.removeInstance(key)
                    removed.append(key)
            return {'reset': removed, 'values': {key: stack.getProperty(key, 'value') for key in keys}}
        if action == 'set_settings':
            values = payload.get('values')
            if not isinstance(values, dict) or not values or len(values) > 100:
                raise ValueError('Provide 1 to 100 setting values')
            for key in values:
                if key not in stack.getAllKeys():
                    raise ValueError('Unknown Cura setting: ' + key)
                if stack.getProperty(key, 'type') == 'category':
                    raise ValueError('Cannot write a setting category')
            previous = {key: stack.getProperty(key, 'value') for key in values}
            for key, value in values.items():
                stack.userChanges.setProperty(key, 'value', value)
            return {'updated': list(values), 'previous_values': previous,
                    'values': {key: stack.getProperty(key, 'value') for key in values}}
        if action == 'slice':
            app.getBackend().slice()
            return {'requested': True, 'detail': 'Slicing requested; inspect backend state before exporting.'}
        if action == 'export_gcode':
            filename = payload.get('file_path')
            if not isinstance(filename, str) or not os.path.isabs(filename) or not filename.lower().endswith('.gcode'):
                raise ValueError('Provide an absolute .gcode output path')
            plate = payload.get('build_plate', 0)
            lines = getattr(app.getController().getScene(), 'gcode_dict', {}).get(plate)
            if not lines:
                raise ValueError('No sliced G-code is available for this build plate')
            if 'done' not in getattr(app.getBackend(), '_backend_state').name.lower():
                # BackendState is an IntEnum in some Cura versions.
                from UM.Backend.Backend import BackendState
                if getattr(app.getBackend(), '_backend_state') != BackendState.Done:
                    raise ValueError('Slicing has not finished; refusing stale export')
            pause_layer = None
            if processor:
                if payload.get('expected_post_processing') != post_processing.revision(processor, stack):
                    raise ValueError('Cura post-processing scripts changed after confirmation')
                lines, pause_layer = post_processing.export_lines(processor, stack, lines)
            with open(filename, 'x', encoding='utf-8') as output:
                output.writelines(lines)
            return {'exported': True, 'file_path': filename, 'bytes': os.path.getsize(filename),
                    'griffin_pause_layer': pause_layer}
        raise ValueError('Unknown workspace command')

    def _project_location(self, app):
        folder = os.path.dirname(self._current_project) if self._current_project else app.getPreferences().getValue('local_file/dialog_save_path')
        return {'file_path': self._current_project, 'folder': folder or None,
                'source': 'bridge_open_or_save' if self._current_project else 'Cura_save_folder_only'}

    def _on_workspace_loaded(self, name=None):
        if not name:
            self._current_project = None
            return
        self._current_project = self._pending_project
        self._pending_project = None

    def _start_project_save(self, app, payload):
        from UM.Job import Job
        from UM.Workspace.WorkspaceWriter import WorkspaceWriter
        from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
        root = app.getController().getScene().getRoot()
        if not any(node.callDecoration('isSliceable') and node.getMeshData() is not None for node in DepthFirstIterator(root)):
            raise ValueError('No sliceable geometry to save')
        if payload.get('source_project') != self._current_project:
            raise ValueError('Current project changed after confirmation')
        writer = app.getWorkspaceFileHandler().getWriter('3MFWriter')
        if writer is None:
            raise ValueError('Native Cura 3MF writer is unavailable')
        options = {'mode': payload.get('mode'), 'create_folder': payload.get('create_folder', False)}
        if options['mode'] == 'save_as':
            options.update(folder=os.path.dirname(payload['file_path']), file_name=os.path.basename(payload['file_path']))
        plan = plan_save(options, self._current_project, self._project_location(app)['folder'])
        if plan != payload:
            raise ValueError('Save destination or existing file changed after confirmation')
        operation = str(uuid.uuid4())
        class ProjectSaveJob(Job):
            def run(job):
                try:
                    job.setResult(atomic_project_write(plan, lambda stream: writer.write(stream, [root], WorkspaceWriter.OutputMode.BinaryMode)))
                except Exception as error:
                    job.setError(error)
        job = ProjectSaveJob()
        callback = lambda finished: app.callLater(self._finish_project_save, operation, finished)
        self._save_jobs[operation] = {'operation_id': operation, 'status': 'running',
                                     'file_path': payload['file_path'], 'job': job, 'callback': callback}
        job.finished.connect(callback)
        job.start()
        return {'operation_id': operation, 'status': 'running', 'file_path': payload['file_path'], 'writer': type(writer).__name__,
                'detail': 'Poll project_save_status to confirm a validated completed save.'}

    def _finish_project_save(self, operation, job):
        result = self._save_jobs[operation]
        if job.hasError():
            result.update(status='failed', error=str(job.getError()))
        else:
            result.update(job.getResult(), status='completed')
            self._current_project = result['file_path']
            from cura.CuraApplication import CuraApplication
            app = CuraApplication.getInstance()
            app.getPreferences().setValue('local_file/dialog_save_path', os.path.dirname(self._current_project))
        result.pop('job', None)
        result.pop('callback', None)
