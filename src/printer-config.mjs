import fs from 'node:fs';
import path from 'node:path';
import {connectionPath} from './cura-connection.mjs';
// User-local configuration is re-read on each operation, never bundled.
export function printerBaseUrl() {
  const config=process.env.CURA_MCP_PRINTER_CONFIG_PATH || path.join(path.dirname(connectionPath),'cura-mcp-printer.json');
  const value=fs.existsSync(config)?JSON.parse(fs.readFileSync(config,'utf8')).printer_origin:process.env.CURA_PRINTER_BASE_URL;
  if (!value) throw new Error('Set CURA_PRINTER_BASE_URL explicitly for printer operations.');
  let url;
  try { url=new URL(value); } catch { throw new Error('CURA_PRINTER_BASE_URL must be an HTTP(S) origin.'); }
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname!=='/')
    throw new Error('Use an HTTP(S) origin without credentials, path, query or fragment.');
  return url.origin;
}
