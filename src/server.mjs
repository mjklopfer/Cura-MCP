#!/usr/bin/env node
/**
 * A dependency-free, stdio MCP server for the local Cura bridge plugin.
 *
 * Read status tools plus explicitly-confirmed local Cura Connect print actions.
 * Print data must be staged below CURA_MCP_PRINT_FILE_ROOT.  The write tools
 * always re-check the printer immediately before contacting it.
 */
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import crypto from "node:crypto";
import {printerApiTools, handlePrinterApi} from './printer-api.mjs';
import {curaApiTools, handleCuraApi} from './cura-api.mjs';
import {cloudApiTools, handleCloudApi} from './cloud-api.mjs';
import {printerMonitorTools, handlePrinterMonitor, monitorMcpResult} from './printer-monitor.mjs';

import {connectionPath as CONNECTION_PATH} from "./cura-connection.mjs";
import {printerBaseUrl} from "./printer-config.mjs";
const PRINT_FILE_ROOT = path.resolve(process.env.CURA_MCP_PRINT_FILE_ROOT || path.join(process.cwd(), "print_files"));
const CONFIRMATION_TTL_MS = 5 * 60_000;
const WRITE_ACTIONS = new Set(["upload_gcode", "start_print"]);
const CURA_WRITE_ACTIONS = new Set(["load_cura_file"]);
const confirmations = new Map();

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function errorResponse(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function readConnection() {
  let connection;
  try {
    connection = JSON.parse(fs.readFileSync(CONNECTION_PATH, "utf8"));
  } catch (error) {
    throw new Error(`Cura bridge connection file is unavailable at ${CONNECTION_PATH}: ${error.message}`);
  }
  if (connection.host !== "127.0.0.1" || !Number.isInteger(connection.port) || !connection.token) {
    throw new Error("Cura bridge connection file is invalid.");
  }
  return connection;
}

async function getCuraStatus() {
  const connection = readConnection();
  const response = await fetch(`http://${connection.host}:${connection.port}/v1/status`, {
    headers: { "X-Cura-Bridge-Token": connection.token },
    signal: AbortSignal.timeout(4_000)
  });
  if (!response.ok) {
    throw new Error(`Cura bridge returned HTTP ${response.status}. Is Cura running with the CuraMcpBridge plugin enabled?`);
  }
  const payload = await response.json();
  if (!payload || payload.schema_version !== 1) {
    throw new Error("Cura bridge returned an unexpected status document.");
  }
  return payload;
}

async function postCuraCommand(command, body) {
  const connection = readConnection();
  const response = await fetch(`http://${connection.host}:${connection.port}/v1/commands/${command}`, {
    method: "POST",
    headers: { "X-Cura-Bridge-Token": connection.token, "content-type": "application/json" },
    body: JSON.stringify(body), signal: AbortSignal.timeout(8_000)
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`Cura command returned HTTP ${response.status}: ${text.slice(0, 500)}`);
  return responseBody(text);
}

async function getPrinterJson(pathname) {
  const response = await fetch(`${printerBaseUrl()}${pathname}`, { signal: AbortSignal.timeout(5_000) });
  if (!response.ok) throw new Error(`Printer endpoint ${pathname} returned HTTP ${response.status}.`);
  return response.json();
}

function safeFilePath(filePath) {
  if (typeof filePath !== "string" || !filePath) throw new Error("file_path is required.");
  const resolved = path.resolve(filePath);
  const relative = path.relative(fs.realpathSync(PRINT_FILE_ROOT), fs.realpathSync(resolved));
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`file_path must be staged below ${PRINT_FILE_ROOT}.`);
  }
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) throw new Error("Staged print file does not exist.");
  if (!/\.(gcode|gcode\.gz|ufp)$/i.test(resolved)) throw new Error("Only .gcode, .gcode.gz, and .ufp files are accepted.");
  return resolved;
}

function safeCuraFilePath(filePath) {
  if (typeof filePath !== "string" || !filePath) throw new Error("file_path is required.");
  const resolved = path.resolve(filePath);
  const relative = path.relative(fs.realpathSync(PRINT_FILE_ROOT), fs.realpathSync(resolved));
  if (relative.startsWith("..") || path.isAbsolute(relative)) throw new Error(`file_path must be staged below ${PRINT_FILE_ROOT}.`);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) throw new Error("Staged Cura file does not exist.");
  if (!/\.(stl|3mf|obj|amf|x3d|gcode|ufp)$/i.test(resolved)) throw new Error("Only supported Cura model, project, G-code, or UFP files are accepted.");
  return resolved;
}

function consumeConfirmation(token, action, expected) {
  const record = confirmations.get(token);
  confirmations.delete(token);
  if (!record || record.expiresAt < Date.now()) throw new Error("Confirmation token is missing, expired, or already used.");
  if (record.action !== action || Object.entries(expected).some(([key, value]) => record[key] !== value)) {
    throw new Error("Confirmation token does not match this print action.");
  }
}

async function getPrinterStatus() {
  const [printers, printing, queued] = await Promise.all([
    getPrinterJson("/cluster-api/v1/printers/"),
    getPrinterJson("/cluster-api/v1/print_jobs/printing"),
    getPrinterJson("/cluster-api/v1/print_jobs/queued")
  ]);
  return {
    schema_version: 1,
    read_only: true,
    printers: printers.map((printer) => ({
      uuid: printer.uuid,
      unique_name: printer.unique_name,
      friendly_name: printer.friendly_name,
      machine_variant: printer.machine_variant,
      status: printer.status,
      firmware_version: printer.firmware_version,
      firmware_update_status: printer.firmware_update_status,
      configuration: printer.configuration
    })),
    printing_jobs: printing.map((job) => ({
      uuid: job.uuid,
      name: job.name,
      status: job.status,
      time_elapsed: job.time_elapsed,
      time_total: job.time_total,
      printer_uuid: job.printer_uuid
    })),
    queued_jobs: queued.map((job) => ({ uuid: job.uuid, name: job.name, status: job.status }))
  };
}

function responseBody(body) {
  if (!body) return null;
  try { return JSON.parse(body); } catch { return body; }
}

async function preflightPrintAction(action) {
  if (!WRITE_ACTIONS.has(action)) throw new Error("action must be upload_gcode or start_print.");
  const status = await getPrinterStatus();
  const printer = status.printers[0];
  const blocked = !printer || printer.status !== "idle" || printer.firmware_update_status === "update_in_progress" || status.printing_jobs.length > 0;
  if (blocked) {
    return { allowed: false, action, reason: "Printer is not safe for a write action: it must be idle, have no active job, and have no firmware update in progress." };
  }
  return { allowed: true, action, reason: "Printer is idle. A separate short-lived confirmation token is required before the write request." };
}

async function createPrintConfirmation(action, args) {
  if (!WRITE_ACTIONS.has(action)) throw new Error("action must be upload_gcode or start_print.");
  const preflight = await preflightPrintAction(action);
  if (!preflight.allowed) return preflight;
  const record = { action, expiresAt: Date.now() + CONFIRMATION_TTL_MS };
  if (action === "upload_gcode") {
    const filePath = safeFilePath(args.file_path);
    record.filePath = filePath;
  } else {
    if (typeof args.job_uuid !== "string" || !args.job_uuid) throw new Error("job_uuid is required.");
    record.jobUuid = args.job_uuid;
  }
  const token = crypto.randomUUID();
  confirmations.set(token, record);
  return { allowed: true, action, confirmation_token: token, expires_in_seconds: CONFIRMATION_TTL_MS / 1000, warning: action === "upload_gcode" ? "This will upload the staged toolpath to the printer queue. An idle printer may begin it according to its local queue policy." : "This will command the specified queued job to print." };
}

async function createCuraConfirmation(action, args) {
  if (!CURA_WRITE_ACTIONS.has(action)) throw new Error("action must be load_cura_file.");
  const status = await getCuraStatus();
  if (!status.ready) return { allowed: false, action, reason: "Cura is not ready for a workspace change." };
  const filePath = safeCuraFilePath(args.file_path);
  const token = crypto.randomUUID();
  const projectMode = args.project_mode || 'open_as_project';
  if (!['open_as_project','open_as_model'].includes(projectMode)) throw new Error('Invalid project_mode');
  confirmations.set(token, { action, filePath, projectMode, expiresAt: Date.now() + CONFIRMATION_TTL_MS });
  return { allowed: true, action, file_path:filePath, project_mode:projectMode, confirmation_token: token, expires_in_seconds: CONFIRMATION_TTL_MS / 1000, warning: "This will load the staged file into Cura. Opening a project replaces the current workspace; save it first." };
}

async function loadCuraFile(args) {
  const filePath = safeCuraFilePath(args.file_path);
  const projectMode = args.project_mode || 'open_as_project';
  consumeConfirmation(args.confirmation_token, "load_cura_file", { filePath, projectMode });
  const status = await getCuraStatus();
  if (!status.ready) return { accepted: false, reason: "Cura is not ready for a workspace change." };
  const result = await postCuraCommand("load_file", { file_path: filePath, project_mode:projectMode });
  return { accepted: true, file_path: filePath, bridge_response: result };
}

async function uploadGcode(args) {
  const filePath = safeFilePath(args.file_path);
  consumeConfirmation(args.confirmation_token, "upload_gcode", { filePath });
  const preflight = await preflightPrintAction("upload_gcode");
  if (!preflight.allowed) return preflight;
  const printer = (await getPrinterStatus()).printers[0];
  const form = new FormData();
  form.set("owner", "Cura MCP Bridge");
  form.set("require_printer_name", printer.unique_name || printer.friendly_name);
  const type = /\.ufp$/i.test(filePath) ? "application/x-ufp" : /\.gz$/i.test(filePath) ? "application/gzip" : "text/plain";
  form.set("file", new Blob([fs.readFileSync(filePath)], { type }), path.basename(filePath));
  const response = await fetch(`${printerBaseUrl()}/cluster-api/v1/print_jobs/`, { method: "POST", body: form, signal: AbortSignal.timeout(60_000) });
  const body = await response.text();
  if (!response.ok) throw new Error(`Printer upload returned HTTP ${response.status}: ${body.slice(0, 500)}`);
  return { uploaded: true, http_status: response.status, response: responseBody(body) };
}

async function startPrint(args) {
  if (typeof args.job_uuid !== "string" || !args.job_uuid) throw new Error("job_uuid is required.");
  consumeConfirmation(args.confirmation_token, "start_print", { jobUuid: args.job_uuid });
  const preflight = await preflightPrintAction("start_print");
  if (!preflight.allowed) return preflight;
  const response = await fetch(`${printerBaseUrl()}/cluster-api/v1/print_jobs/${encodeURIComponent(args.job_uuid)}/action`, {
    method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "print" }), signal: AbortSignal.timeout(15_000)
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`Printer start returned HTTP ${response.status}: ${body.slice(0, 500)}`);
  return { started: true, job_uuid: args.job_uuid, http_status: response.status, response: responseBody(body) };
}

const tools = [{
  name: "cura_status",
  title: "Cura status",
  description: "Check whether the local Cura bridge is ready. Printer/profile/extruder/scene fields are placeholders, not live measurements; startup deliberately avoids inspecting Cura configuration. Does not modify Cura or contact a printer.",
  inputSchema: { type: "object", properties: {}, additionalProperties: false },
  annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false }
}, {
  name: "printer_status",
  title: "UltiMaker printer status",
  description: "Read the Cura Connect printer inventory and its active and queued jobs. This tool performs no printer write.",
  inputSchema: { type: "object", properties: {}, additionalProperties: false },
  annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true }
}, {
  name: "preflight_print_action",
  title: "Preflight printer write action",
  description: "Check whether an upload or print-start operation is currently safe. It performs no write.",
  inputSchema: { type: "object", properties: { action: { type: "string", enum: ["upload_gcode", "start_print"] } }, required: ["action"], additionalProperties: false },
  annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false }
}, {
  name: "create_print_confirmation",
  title: "Confirm printer write action",
  description: "Create one short-lived token for a specific staged toolpath upload or queued-job print start after reading printer status. Performs no printer write. Show the human the target and warning before using the write tool.",
  inputSchema: { type: "object", properties: { action: { type: "string", enum: ["upload_gcode", "start_print"] }, file_path: { type: "string" }, job_uuid: { type: "string" } }, required: ["action"], additionalProperties: false },
  annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false }
}, {
  name: "upload_gcode",
  title: "Upload staged toolpath to printer queue",
  description: "Uploads one confirmed .gcode, .gcode.gz, or .ufp file from the staging folder to the selected local printer. It may start automatically if the printer queue policy permits it.",
  inputSchema: { type: "object", properties: { file_path: { type: "string" }, confirmation_token: { type: "string" } }, required: ["file_path", "confirmation_token"], additionalProperties: false },
  annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true }
}, {
  name: "start_print",
  title: "Start a queued printer job",
  description: "Commands one confirmed queued local printer job to start printing.",
  inputSchema: { type: "object", properties: { job_uuid: { type: "string" }, confirmation_token: { type: "string" } }, required: ["job_uuid", "confirmation_token"], additionalProperties: false },
  annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true }
}, {
  name: "create_cura_confirmation",
  title: "Confirm Cura workspace write",
  description: "Create a one-use confirmation token for loading one staged file into Cura. This does not modify Cura.",
  inputSchema: { type: "object", properties: { action: { type: "string", enum: ["load_cura_file"] }, file_path: { type: "string" }, project_mode:{type:"string",enum:['open_as_project','open_as_model']} }, required: ["action", "file_path"], additionalProperties: false },
  annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false }
}, {
  name: "load_cura_file",
  title: "Load staged file into Cura",
  description: "Loads one confirmed staged model, project, G-code, or UFP file into the active Cura workspace. It does not slice or send a print.",
  inputSchema: { type: "object", properties: { file_path: { type: "string" }, project_mode:{type:"string",enum:['open_as_project','open_as_model']}, confirmation_token: { type: "string" } }, required: ["file_path", "confirmation_token"], additionalProperties: false },
  annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: false }
}];

async function handle(request) {
  if (request.jsonrpc !== "2.0" || typeof request.method !== "string") {
    throw new Error("Invalid JSON-RPC request.");
  }
  if (request.method === "notifications/initialized") return null;
  if (request.method === "initialize") {
    return {
      protocolVersion: request.params?.protocolVersion || "2025-06-18",
      capabilities: { tools: {} },
      serverInfo: { name: "cura-mcp-bridge", version: "0.1.12" }
    };
  }
  if (request.method === "tools/list") return { tools: [...tools, ...printerApiTools, ...curaApiTools, ...cloudApiTools, ...printerMonitorTools] };
  if (request.method === "tools/call") {
    if (printerMonitorTools.some(tool => tool.name === request.params?.name)) {
      return monitorMcpResult(await handlePrinterMonitor(request.params.name, request.params.arguments || {}));
    }
    if (cloudApiTools.some(tool => tool.name === request.params?.name)) {
      const payload = await handleCloudApi(request.params.name, request.params.arguments || {});
      return {content:[{type:'text',text:JSON.stringify(payload,null,2)}],structuredContent:payload,
        isError:!!payload.error || payload.status==='error'};
    }
    if (curaApiTools.some(tool => tool.name === request.params?.name)) {
      const payload = await handleCuraApi(request.params.name, request.params.arguments || {});
      if (request.params.name === 'cura_snapshot' && payload.image_png) {
        return {content:[{type:'image',mimeType:'image/png',data:payload.image_png}]};
      }
      return {content:[{type:'text',text:JSON.stringify(payload,null,2)}],structuredContent:payload,isError:!!payload.error};
    }
    if (printerApiTools.some(tool => tool.name === request.params?.name)) {
      const payload = await handlePrinterApi(request.params.name, request.params.arguments || {});
      return {content:[{type:'text',text:JSON.stringify(payload,null,2)}],structuredContent:payload,
        isError:!!payload.error || (payload.http_status !== undefined && payload.http_status >= 400)};
    }
    if (!["cura_status", "printer_status", "preflight_print_action", "create_print_confirmation", "upload_gcode", "start_print", "create_cura_confirmation", "load_cura_file"].includes(request.params?.name)) {
      return { content: [{ type: "text", text: `Unknown tool: ${request.params?.name || "(missing)"}` }], isError: true };
    }
    const name = request.params.name;
    const args = request.params.arguments || {};
    const status = name === "cura_status" ? await getCuraStatus()
      : name === "printer_status" ? await getPrinterStatus()
      : name === "preflight_print_action" ? await preflightPrintAction(args.action)
      : name === "create_print_confirmation" ? await createPrintConfirmation(args.action, args)
      : name === "upload_gcode" ? await uploadGcode(args)
      : name === "start_print" ? await startPrint(args)
      : name === "create_cura_confirmation" ? await createCuraConfirmation(args.action, args)
      : await loadCuraFile(args);
    return {
      content: [{ type: "text", text: JSON.stringify(status, null, 2) }],
      structuredContent: status
    };
  }
  throw new Error(`Method not found: ${request.method}`);
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", async (line) => {
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    send(errorResponse(null, -32700, "Parse error"));
    return;
  }
  if (request.id === undefined) {
    try { await handle(request); } catch { /* Notifications have no response. */ }
    return;
  }
  try {
    send({ jsonrpc: "2.0", id: request.id, result: await handle(request) });
  } catch (error) {
    send(errorResponse(request.id, -32000, error.message));
  }
});
