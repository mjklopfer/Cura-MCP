import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';

test('cloud tools bind explicit target and one-use confirmation, return async operation',async t=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'cura-cloud-'));
  const calls=[];
  const mock=http.createServer(async(req,res)=>{
    let text='';for await(const c of req)text+=c;
    const body=JSON.parse(text);calls.push({url:req.url,body});
    res.setHeader('content-type','application/json');
    if(req.headers['x-cura-bridge-token']!=='test-token'){res.writeHead(401);return res.end('{}');}
    res.end(JSON.stringify(req.url.endsWith('plan_cloud_connection')?
      {machine_id:body.machine_id,fingerprint:'connection-state-bound'}:req.url.endsWith('plan_cloud_print')?
      {device_id:body.device_id,device_name:'Test printer',fingerprint:'native-state-bound'}:
      {operation_id:'test-operation',status:'uploading'}));
  });
  await new Promise(r=>mock.listen(0,'127.0.0.1',r));
  t.after(()=>{mock.close();fs.rmSync(temp,{recursive:true,force:true});});
  process.env.CURA_MCP_BRIDGE_CONNECTION_PATH=path.join(temp,'connection.json');
  fs.writeFileSync(process.env.CURA_MCP_BRIDGE_CONNECTION_PATH,JSON.stringify({host:'127.0.0.1',port:mock.address().port,token:'test-token'}));
  const {handleCloudApi:call,cloudApiTools}=await import('../src/cloud-api.mjs');
  assert.equal(cloudApiTools.length,7);
  await assert.rejects(()=>call('confirm_cura_cloud_print',{}),/Explicit/);
  const plan=await call('confirm_cura_cloud_print',{device_id:'test-device'});
  await assert.rejects(()=>call('cura_cloud_print',{device_id:'other',confirmation_token:plan.confirmation_token}),/mismatched/);
  assert.equal(calls.length,1);
  const next=await call('confirm_cura_cloud_print',{device_id:'test-device'});
  const result=await call('cura_cloud_print',{device_id:'test-device',confirmation_token:next.confirmation_token});
  assert.equal(result.status,'uploading');
  assert.deepEqual(calls.at(-1).body,{device_id:'test-device',expected_fingerprint:'native-state-bound'});
  await assert.rejects(()=>call('cura_cloud_print',{device_id:'test-device',confirmation_token:next.confirmation_token}),/reused/);
  await call('cura_cloud_print_status',{operation_id:result.operation_id});
  assert.equal(calls.at(-1).url,'/v1/commands/cloud_print_status');
  await call('cura_cloud_connections',{});
  assert.equal(calls.at(-1).url,'/v1/commands/inspect_cloud_connections');
  const connect=await call('confirm_cura_cloud_connection',{machine_id:'configured-profile'});
  // Cross-action token use must fail, even where machine/device identifiers match.
  await assert.rejects(()=>call('cura_cloud_print',{device_id:'configured-profile',confirmation_token:connect.confirmation_token}),/mismatched/);
  const approved=await call('confirm_cura_cloud_connection',{machine_id:'configured-profile'});
  await call('cura_cloud_connect',{machine_id:'configured-profile',confirmation_token:approved.confirmation_token});
  assert.deepEqual(calls.at(-1).body,{machine_id:'configured-profile',expected_fingerprint:'connection-state-bound'});
  await assert.rejects(()=>call('cura_cloud_connect',{machine_id:'configured-profile',confirmation_token:approved.confirmation_token}),/reused/);
});
