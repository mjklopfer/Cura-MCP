import fs from 'node:fs';
import path from 'node:path';
import {connectionPath} from './cura-connection.mjs';
// User-local configuration is re-read on each operation, never bundled.
function localConfig() {
  const config=process.env.CURA_MCP_PRINTER_CONFIG_PATH || path.join(path.dirname(connectionPath),'cura-mcp-printer.json');
  return fs.existsSync(config)?JSON.parse(fs.readFileSync(config,'utf8')):null;
}
export function printerBaseUrl() {
  const config=localConfig();
  const value=config?config.printer_origin:process.env.CURA_PRINTER_BASE_URL;
  if (!value) throw new Error('Set CURA_PRINTER_BASE_URL explicitly for printer operations.');
  let url;
  try { url=new URL(value); } catch { throw new Error('CURA_PRINTER_BASE_URL must be an HTTP(S) origin.'); }
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname!=='/')
    throw new Error('Use an HTTP(S) origin without credentials, path, query or fragment.');
  return url.origin;
}
export function cameraServicePorts() {
  const ports=localConfig()?.camera_service_ports??[8080];
  if(!Array.isArray(ports)||!ports.length||ports.length>4||new Set(ports).size!==ports.length||
     ports.some(p=>!Number.isInteger(p)||p<1||p>65535))
    throw Error('camera_service_ports must contain 1 to 4 distinct integer ports');
  return ports;
}
