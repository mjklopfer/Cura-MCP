import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp, mkdir, writeFile, symlink, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

test('printer API catalog, real transport, request binding, busy-state guard and staging boundary',async t=>{
  let printerState='idle';
  const writes=[];
  const mock=createServer(async(req,res)=>{
    res.setHeader('Content-Type','application/json');
    if(req.url==='/api/v1/printer/status')return res.end(JSON.stringify(printerState));
    if(req.url==='/api/v1/printer/led'){
      if(req.method==='GET')return res.end(JSON.stringify({brightness:50,hue:0,saturation:0}));
      let body='';for await(const chunk of req)body+=chunk;
      writes.push(JSON.parse(body));res.statusCode=204;return res.end();
    }
    if(req.url==='/api/v1/print_job/state'){
      let body='';for await(const chunk of req)body+=chunk;
      writes.push(JSON.parse(body));res.statusCode=204;return res.end();
    }
    res.statusCode=404;res.end('{}');
  });
  await new Promise(resolve=>mock.listen(0,'127.0.0.1',resolve));
  t.after(()=>mock.close());
  const folder=await mkdtemp(path.join(tmpdir(),'s5-api-test-'));
  t.after(()=>rm(folder,{recursive:true,force:true}));
  const staged=path.join(folder,'staging');await mkdir(staged);
  process.env.CURA_PRINTER_BASE_URL=`http://127.0.0.1:${mock.address().port}`;
  // Never inherit a developer workstation's hot-reload printer origin file.
  process.env.CURA_MCP_PRINTER_CONFIG_PATH=path.join(folder,'isolated-printer-config.json');
  process.env.CURA_MCP_PRINT_FILE_ROOT=staged;
  const {handlePrinterApi}=await import('../src/printer-api.mjs');
  const catalog=await handlePrinterApi('printer_api_catalog',{});
  assert.equal(catalog.apis.printer.endpoints.length,94);
  assert.equal(catalog.apis.cluster.endpoints.length,36);
  const wifi = catalog.apis.printer.endpoints.find(item=>item.endpoint==='/printer/network/wifi');
  assert.deepEqual(wifi.methods,['get']);
  await assert.rejects(()=>handlePrinterApi('confirm_printer_api_write',{api:'printer',endpoint:wifi.endpoint,method:'PUT',body:{enabled:false}}),/not in the printer-provided API catalog/);
  const read=await handlePrinterApi('printer_api_read',{api:'printer',endpoint:'/printer/led'});
  assert.equal(read.http_status,200);assert.equal(read.data.brightness,50);
  await assert.rejects(()=>handlePrinterApi('printer_api_read',{api:'printer',endpoint:'/not-documented'}),/catalog/);
  await assert.rejects(()=>handlePrinterApi('printer_api_read',{api:'printer',endpoint:'/printer/heads/{head_id}',path_parameters:{head_id:'../system'}}),/Invalid path/);
  const action={api:'printer',endpoint:'/printer/led',method:'PUT',body:{brightness:60,hue:0,saturation:0}};
  const confirmation=await handlePrinterApi('confirm_printer_api_write',action);
  const written=await handlePrinterApi('printer_api_write',{...action,confirmation_token:confirmation.confirmation_token});
  assert.equal(written.http_status,204);assert.equal(writes.length,1);
  await assert.rejects(()=>handlePrinterApi('printer_api_write',{...action,confirmation_token:confirmation.confirmation_token}),/Confirmation/);
  const mismatched=await handlePrinterApi('confirm_printer_api_write',action);
  await assert.rejects(()=>handlePrinterApi('printer_api_write',{...action,body:{brightness:90},confirmation_token:mismatched.confirmation_token}),/mismatched/);
  const changed=await handlePrinterApi('confirm_printer_api_write',action);
  printerState='printing';
  await assert.rejects(()=>handlePrinterApi('printer_api_write',{...action,confirmation_token:changed.confirmation_token}),/state changed/);
  await assert.rejects(()=>handlePrinterApi('confirm_printer_api_write',{api:'printer',endpoint:'/printer/bed/temperature',method:'PUT',form:{temperature:50}}),/busy/);
  const safeLight=await handlePrinterApi('confirm_printer_api_write',action);
  assert.equal((await handlePrinterApi('printer_api_write',{...action,confirmation_token:safeLight.confirmation_token})).http_status,204);
  const pause={api:'printer',endpoint:'/print_job/state',method:'PUT',body:'pause'};
  const pauseConfirmation=await handlePrinterApi('confirm_printer_api_write',pause);
  assert.equal((await handlePrinterApi('printer_api_write',{...pause,confirmation_token:pauseConfirmation.confirmation_token})).http_status,204);
  assert.equal(writes[2],'pause');
  const outside=path.join(folder,'outside.xml');await writeFile(outside,'<test/>');
  const linkdir=path.join(staged,'external');await symlink(folder,linkdir,process.platform==='win32'?'junction':'dir');
  const linked=path.join(linkdir,'outside.xml');
  await assert.rejects(()=>handlePrinterApi('confirm_printer_api_write',{api:'printer',endpoint:'/materials',method:'POST',form:{filename:'linked.xml'},files:[{field:'file',file_path:linked}]}),/staged below/);
  assert.equal(writes.length,3);
});
