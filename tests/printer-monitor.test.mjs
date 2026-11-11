import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

test('local monitoring returns bounded inline stills and honest time estimates without writes',async t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'cura-monitor-'));
  process.env.CURA_MCP_PRINTER_CONFIG_PATH=path.join(dir,'isolated.json');
  let mode='ok',job={name:'Test part',state:'printing',progress:.75,time_elapsed:300,time_total:500,time_estimated:600};
  let state='printing',snapshotRequests=0,secondAvailable=false;const methods=[];
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=','base64');
  let alternateCalls=0;
  const alternate=http.createServer((req,res)=>{alternateCalls++;methods.push(req.method);res.setHeader('content-type','image/png');res.end(png);});
  await new Promise(r=>alternate.listen(0,'127.0.0.1',r));
  t.after(()=>{alternate.closeAllConnections();alternate.close();});
  const server=http.createServer((req,res)=>{
    methods.push(req.method);
    if(req.url==='/api/v1/printer/status'){res.setHeader('content-type','application/json');return res.end(JSON.stringify(state));}
    if(req.url==='/api/v1/print_job'){
      if(job===null){res.statusCode=404;return res.end();}
      return res.end(JSON.stringify(job));
    }
    if(req.url==='/api/v1/camera/1/snapshot'&&!secondAvailable){res.statusCode=404;return res.end();}
    if(req.url==='/api/v1/camera/0/snapshot'||(req.url==='/api/v1/camera/1/snapshot'&&secondAvailable)){
      snapshotRequests++;
      if(mode==='foreign'){res.writeHead(302,{location:'http://example.invalid/?action=snapshot'});return res.end();}
      if(mode==='alternate'){res.writeHead(302,{location:`http://127.0.0.1:${alternate.address().port}/?action=snapshot`});return res.end();}
      if(mode==='stream'){res.writeHead(302,{location:'/?action=stream'});return res.end();}
      if(mode==='loop'){res.writeHead(302,{location:'/api/v1/camera/0/snapshot'});return res.end();}
      res.writeHead(302,{location:'/?action=snapshot'});return res.end();
    }
    if(req.url==='/?action=snapshot'){
      if(mode==='html'){res.setHeader('content-type','text/html');return res.end('<html>error</html>');}
      res.setHeader('content-type','image/png');
      if(mode==='oversize'){res.setHeader('content-length',6*1024*1024);return res.end('x');}
      if(mode==='bad_magic')return res.end('not an image');
      return res.end(png);
    }
    res.statusCode=404;res.end();
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  process.env.CURA_PRINTER_BASE_URL=`http://127.0.0.1:${server.address().port}`;
  t.after(()=>{server.closeAllConnections();server.close();fs.rmSync(dir,{recursive:true,force:true});});
  const {handlePrinterMonitor:call,monitorMcpResult}=await import('../src/printer-monitor.mjs');
  let status=await call('printer_print_status');
  assert.equal(status.remaining_seconds,200);assert.equal(status.remaining_display,'00:03:20');
  assert.equal(status.progress_percent,75);assert.ok(!('serial' in status));
  job.time_total=0;status=await call('printer_print_status');assert.equal(status.remaining_seconds,300);
  delete job.time_estimated;status=await call('printer_print_status');assert.equal(status.remaining_seconds,null);
  job.time_total=50;status=await call('printer_print_status');assert.equal(status.remaining_seconds,0);
  job.state='post_print';assert.equal((await call('printer_print_status')).remaining_seconds,0);
  job=null;assert.equal((await call('printer_print_status')).remaining_seconds,null);
  state='idle';assert.equal((await call('printer_print_status')).remaining_seconds,0);
  const image=await call('printer_camera_snapshot',{});
  const result=monitorMcpResult(image);
  assert.equal(result.content[1].type,'image');assert.equal(result.content[1].mimeType,'image/png');
  assert.equal(result.content[1].data,png.toString('base64'));
  assert.equal(result.structuredContent.byte_count,png.length);assert.ok(!('image_base64' in result.structuredContent));
  const before=snapshotRequests;
  await assert.rejects(()=>call('printer_camera_snapshot',{camera_index:-1}),/integer/);
  assert.equal(snapshotRequests,before);
  for(const [setting,message] of [['foreign',/outside/],['stream',/outside/],['loop',/excessive/],
                                  ['html',/JPEG or PNG/],['oversize',/size limit/],['bad_magic',/signature/]]){
    mode=setting;await assert.rejects(()=>call('printer_camera_snapshot'),message);
  }
  mode='ok';
  let inventory=await call('printer_camera_inventory');
  assert.deepEqual(inventory.cameras.map(c=>c.status),['available','not_exposed']);
  assert.ok(!JSON.stringify(inventory).includes('image_base64'));
  let batch=monitorMcpResult(await call('printer_camera_snapshots'));
  assert.equal(batch.content.filter(c=>c.type==='image').length,1);
  assert.ok(!batch.isError);
  secondAvailable=true;
  inventory=await call('printer_camera_inventory');
  assert.deepEqual(inventory.cameras.map(c=>c.status),['available','available']);
  batch=monitorMcpResult(await call('printer_camera_snapshots'));
  assert.equal(batch.content.filter(c=>c.type==='image').length,2);
  assert.equal(batch.structuredContent.synchronized,false);
  assert.ok(batch.content.some(c=>c.type==='text'&&c.text.startsWith('Camera 1')));
  const count=snapshotRequests;
  for(const indices of [[],[0,0],[-1],[0,1,2,3,4]])
    await assert.rejects(()=>call('printer_camera_inventory',{camera_indices:indices}),/distinct camera/);
  assert.equal(snapshotRequests,count);
  batch=monitorMcpResult(await call('printer_camera_snapshots',{camera_indices:[2,3]}));
  assert.equal(batch.isError,true);assert.equal(batch.content.filter(c=>c.type==='image').length,0);
  mode='alternate';
  await assert.rejects(()=>call('printer_camera_snapshot'),/outside/);
  assert.equal(alternateCalls,0);
  fs.writeFileSync(process.env.CURA_MCP_PRINTER_CONFIG_PATH,JSON.stringify({printer_origin:process.env.CURA_PRINTER_BASE_URL,camera_service_ports:[alternate.address().port]}));
  assert.equal((await call('printer_camera_snapshot')).mime_type,'image/png');
  assert.equal(alternateCalls,1);
  assert.ok(methods.every(m=>m==='GET'));
});
