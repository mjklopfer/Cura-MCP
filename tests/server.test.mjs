import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import test from "node:test";

function requestProcess(child, request) {
  return new Promise((resolve, reject) => {
    let buffer = "";
    const onData = chunk => {
      buffer += chunk;
      const newline = buffer.indexOf("\n");
      if (newline >= 0) {
        child.stdout.off("data", onData);
        child.off("error", onError);
        resolve(JSON.parse(buffer.slice(0, newline)));
      }
    };
    const onError = error => {
      child.stdout.off("data", onData);
      reject(error);
    };
    child.stdout.on("data", onData);
    child.once("error", onError);
    child.stdin.write(`${JSON.stringify(request)}\n`);
  });
}

test("lists status tools and protects local printer writes with a one-use confirmation", async (t) => {
  const token = "test-token";
  let uploadedBody = "";
  const mock = createServer(async (request, response) => {
    response.setHeader("content-type", "application/json");
    if (request.url === "/v1/status") {
      assert.equal(request.headers["x-cura-bridge-token"], token);
      response.end(JSON.stringify({ schema_version: 1, ready: true, cura_version: "5.13.0", build_plate_object_count: 2 }));
      return;
    }
    if (request.url === "/v1/commands/load_file" && request.method === "POST") {
      assert.equal(request.headers["x-cura-bridge-token"], token);
      let body = "";
      for await (const chunk of request) body += chunk;
      assert.equal(JSON.parse(body).file_path, gcode);
      response.statusCode = 202;
      response.end(JSON.stringify({ accepted: true, action: "load_file" }));
      return;
    }
    if (request.url === "/cluster-api/v1/printers/") {
      response.end(JSON.stringify([{ uuid: "printer-1", unique_name: "test-printer", friendly_name: "Test S5", machine_variant: "Ultimaker S5", status: "idle", firmware_update_status: "up_to_date", configuration: [] }]));
      return;
    }
    if (request.url === "/cluster-api/v1/print_jobs/printing") { response.end(JSON.stringify([])); return; }
    if (request.url === "/cluster-api/v1/print_jobs/queued") { response.end(JSON.stringify([{ uuid: "job-1", name: "Queued test", status: "queued" }])); return; }
    if (request.url === "/cluster-api/v1/print_jobs/" && request.method === "POST") {
      for await (const chunk of request) uploadedBody += chunk;
      response.end(JSON.stringify({ uuid: "uploaded-job" }));
      return;
    }
    if (request.url === "/cluster-api/v1/print_jobs/job-1/action" && request.method === "PUT") {
      let body = "";
      for await (const chunk of request) body += chunk;
      assert.deepEqual(JSON.parse(body), { action: "print" });
      response.end(JSON.stringify({ uuid: "job-1", status: "printing" }));
      return;
    }
    response.statusCode = 404;
    response.end();
  });
  await new Promise(resolve => mock.listen(0, "127.0.0.1", resolve));
  t.after(() => mock.close());
  const folder = await mkdtemp(path.join(tmpdir(), "cura-mcp-"));
  const connection = path.join(folder, "connection.json");
  const staged = path.join(folder, "print_files");
  await writeFile(path.join(folder, "test.gcode"), "; not in staging\n");
  await writeFile(path.join(folder, "print_files.gcode"), "; not used\n");
  await (await import("node:fs/promises")).mkdir(staged);
  const gcode = path.join(staged, "test.gcode");
  await writeFile(gcode, "; generated test toolpath\n");
  await writeFile(connection, JSON.stringify({ host: "127.0.0.1", port: mock.address().port, token }));
  const child = spawn(process.execPath, ["src/server.mjs"], { cwd: path.resolve("."), env: { ...process.env, CURA_MCP_BRIDGE_CONNECTION_PATH: connection, CURA_PRINTER_BASE_URL: `http://127.0.0.1:${mock.address().port}`, CURA_MCP_PRINT_FILE_ROOT: staged } });
  t.after(() => child.kill());
  const initialize = await requestProcess(child, { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18" } });
  assert.equal(initialize.result.serverInfo.name, "cura-mcp-bridge");
  const listed = await requestProcess(child, { jsonrpc: "2.0", id: 2, method: "tools/list" });
  assert.deepEqual(listed.result.tools.map((tool) => tool.name), ["cura_status", "printer_status", "preflight_print_action", "create_print_confirmation", "upload_gcode", "start_print", "create_cura_confirmation", "load_cura_file", "printer_api_catalog", "printer_api_read", "confirm_printer_api_write", "printer_api_write", "cura_comparison_status", "cura_comparison_cancel", "cura_layers", "cura_estimates", "cura_snapshot", "cura_configuration", "cura_extensions", "cura_navigate", "cura_inspect", "cura_settings", "confirm_cura_operation", "cura_operation", "cura_project_save_status", "cura_path_info", "cura_cloud_connections", "confirm_cura_cloud_connection", "cura_cloud_connect", "cura_cloud_devices", "confirm_cura_cloud_print", "cura_cloud_print", "cura_cloud_print_status"]);
  const called = await requestProcess(child, { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "cura_status", arguments: {} } });
  assert.equal(called.result.structuredContent.build_plate_object_count, 2);
  const printer = await requestProcess(child, { jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "printer_status", arguments: {} } });
  assert.equal(printer.result.structuredContent.printers[0].friendly_name, "Test S5");
  assert.equal(printer.result.structuredContent.queued_jobs[0].name, "Queued test");
  const preflight = await requestProcess(child, { jsonrpc: "2.0", id: 5, method: "tools/call", params: { name: "preflight_print_action", arguments: { action: "start_print" } } });
  assert.equal(preflight.result.structuredContent.allowed, true);
  const uploadConfirmation = await requestProcess(child, { jsonrpc: "2.0", id: 6, method: "tools/call", params: { name: "create_print_confirmation", arguments: { action: "upload_gcode", file_path: gcode } } });
  const upload = await requestProcess(child, { jsonrpc: "2.0", id: 7, method: "tools/call", params: { name: "upload_gcode", arguments: { file_path: gcode, confirmation_token: uploadConfirmation.result.structuredContent.confirmation_token } } });
  assert.equal(upload.result.structuredContent.uploaded, true);
  assert.match(uploadedBody, /name="owner"/);
  assert.match(uploadedBody, /name="require_printer_name"/);
  assert.match(uploadedBody, /test-printer/);
  assert.match(uploadedBody, /generated test toolpath/);
  const reused = await requestProcess(child, { jsonrpc: "2.0", id: 71, method: "tools/call", params: { name: "upload_gcode", arguments: { file_path: gcode, confirmation_token: uploadConfirmation.result.structuredContent.confirmation_token } } });
  assert.match(reused.error.message, /missing, expired, or already used/);
  const linkdir = path.join(staged, "external");
  await (await import("node:fs/promises")).symlink(folder, linkdir, process.platform === 'win32' ? 'junction' : 'dir');
  const escaped = path.join(linkdir, "test.gcode");
  const escapeAttempt = await requestProcess(child, { jsonrpc: "2.0", id: 72, method: "tools/call", params: { name: "create_print_confirmation", arguments: { action: "upload_gcode", file_path: escaped } } });
  assert.match(escapeAttempt.error.message, /staged below/);
  const startConfirmation = await requestProcess(child, { jsonrpc: "2.0", id: 8, method: "tools/call", params: { name: "create_print_confirmation", arguments: { action: "start_print", job_uuid: "job-1" } } });
  const started = await requestProcess(child, { jsonrpc: "2.0", id: 9, method: "tools/call", params: { name: "start_print", arguments: { job_uuid: "job-1", confirmation_token: startConfirmation.result.structuredContent.confirmation_token } } });
  assert.equal(started.result.structuredContent.started, true);
  const curaConfirmation = await requestProcess(child, { jsonrpc: "2.0", id: 10, method: "tools/call", params: { name: "create_cura_confirmation", arguments: { action: "load_cura_file", file_path: gcode } } });
  const loaded = await requestProcess(child, { jsonrpc: "2.0", id: 11, method: "tools/call", params: { name: "load_cura_file", arguments: { file_path: gcode, confirmation_token: curaConfirmation.result.structuredContent.confirmation_token } } });
  assert.equal(loaded.result.structuredContent.accepted, true);
});
