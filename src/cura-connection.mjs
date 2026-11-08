import os from 'node:os';
import path from 'node:path';

const version = process.env.CURA_MCP_CURA_VERSION || '5.14';
if (!/^\d+\.\d+$/.test(version)) throw new Error('CURA_MCP_CURA_VERSION must be major.minor');
const configRoot = process.platform === 'darwin'
  ? path.join(os.homedir(), 'Library', 'Application Support')
  : process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');

export const connectionPath = process.env.CURA_MCP_BRIDGE_CONNECTION_PATH ||
  path.join(configRoot, 'cura', version, 'cura-mcp-bridge.json');
