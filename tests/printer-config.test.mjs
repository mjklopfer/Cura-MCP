import test from 'node:test';
import assert from 'node:assert/strict';
import {printerBaseUrl,cameraServicePorts} from '../src/printer-config.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

test('printer origin has no default and rejects credentials or URL suffixes',()=>{
  const original=process.env.CURA_PRINTER_BASE_URL;
  const originalPath=process.env.CURA_MCP_PRINTER_CONFIG_PATH;
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'cura-printer-config-'));
  process.env.CURA_MCP_PRINTER_CONFIG_PATH=path.join(temporary,'printer.json');
  try {
    delete process.env.CURA_PRINTER_BASE_URL;
    assert.throws(()=>printerBaseUrl(),/explicitly/);
    process.env.CURA_PRINTER_BASE_URL='';
    assert.throws(()=>printerBaseUrl(),/explicitly/);
    for (const value of ['file:///tmp/device','http://example.invalid/path','http://example.invalid/?key=dummy','http://example.invalid/#dummy','http://dummy:dummy@example.invalid']) {
      process.env.CURA_PRINTER_BASE_URL=value;
      assert.throws(()=>printerBaseUrl(),/origin/);
    }
    process.env.CURA_PRINTER_BASE_URL='http://example.invalid:8080/';
    assert.equal(printerBaseUrl(),'http://example.invalid:8080');
    fs.writeFileSync(process.env.CURA_MCP_PRINTER_CONFIG_PATH,JSON.stringify({printer_origin:'http://printer.invalid'}));
    assert.equal(printerBaseUrl(),'http://printer.invalid');
    fs.writeFileSync(process.env.CURA_MCP_PRINTER_CONFIG_PATH,JSON.stringify({printer_origin:'http://updated.invalid'}));
    assert.equal(printerBaseUrl(),'http://updated.invalid');
    assert.deepEqual(cameraServicePorts(),[8080]);
    fs.writeFileSync(process.env.CURA_MCP_PRINTER_CONFIG_PATH,JSON.stringify({printer_origin:'http://updated.invalid',camera_service_ports:[8080,8081]}));
    assert.deepEqual(cameraServicePorts(),[8080,8081]);
    for(const ports of [[],[0],[8080,8080],['8081'],[65536]]){
      fs.writeFileSync(process.env.CURA_MCP_PRINTER_CONFIG_PATH,JSON.stringify({printer_origin:'http://updated.invalid',camera_service_ports:ports}));
      assert.throws(()=>cameraServicePorts(),/distinct integer/);
    }
    fs.writeFileSync(process.env.CURA_MCP_PRINTER_CONFIG_PATH,'{broken');
    assert.throws(()=>printerBaseUrl());
  } finally {
    if (original===undefined) delete process.env.CURA_PRINTER_BASE_URL;
    else process.env.CURA_PRINTER_BASE_URL=original;
    if(originalPath===undefined)delete process.env.CURA_MCP_PRINTER_CONFIG_PATH;
    else process.env.CURA_MCP_PRINTER_CONFIG_PATH=originalPath;
    fs.rmSync(temporary,{recursive:true,force:true});
  }
});
