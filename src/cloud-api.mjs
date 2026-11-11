import fs from 'node:fs';
import crypto from 'node:crypto';
import {connectionPath} from './cura-connection.mjs';

const pending=new Map();
function tool(name,description,properties,required,readOnlyHint){return {name,description,
  inputSchema:{type:'object',properties,required,additionalProperties:false},
  annotations:{readOnlyHint,destructiveHint:!readOnlyHint,openWorldHint:!readOnlyHint}};}
const target={device_id:{type:'string',minLength:1,description:'Exact cloud device ID from cura_cloud_devices.'}};
const machine={machine_id:{type:'string',minLength:1,description:'Existing cloud-configured printer profile ID from cura_cloud_connections.'}};
export const cloudApiTools=[
  tool('cura_cloud_connections','List preinstalled cloud printer profiles, current selection and native cloud devices. No local printer origin or fresh login required.',{},[],true),
  tool('confirm_cura_cloud_connection','Bind selection of one existing cloud printer profile; does not create a printer, log in, upload or print.',machine,['machine_id'],true),
  tool('cura_cloud_connect','Select the confirmed preinstalled printer and cloud output through Cura native connection refresh. Reuses existing login; does not upload or print.',
    {...machine,confirmation_token:{type:'string',minLength:1}},['machine_id','confirmation_token'],false),
  tool('cura_cloud_devices','Inspect native Cura cloud destinations and cached printer/job state. Does not log in, refresh the network, upload or print.',{},[],true),
  tool('confirm_cura_cloud_print','Plan submission of the current finished slice to one explicit native cloud device. Binds destination, machine, scene, toolpath and postprocessing. May queue or start automatically when executed.',target,['device_id'],true),
  tool('cura_cloud_print','Submit the confirmed current slice using Cura native cloud export/upload. Never retries automatically; poll operation status. May queue or start according to printer policy.',
    {...target,confirmation_token:{type:'string',minLength:1}},['device_id','confirmation_token'],false),
  tool('cura_cloud_print_status','Read one asynchronous native cloud submission. Completion may mean submitted or awaiting approval, not physical print start.',
    {operation_id:{type:'string',minLength:1}},['operation_id'],true)
];
async function command(name,body){
  const c=JSON.parse(fs.readFileSync(connectionPath,'utf8'));
  if(c.host!=='127.0.0.1'||!Number.isInteger(c.port)||!c.token)throw Error('Invalid loopback connection');
  const r=await fetch(`http://${c.host}:${c.port}/v1/commands/${name}`,{method:'POST',
    headers:{'X-Cura-Bridge-Token':c.token,'content-type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(8000)});
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw Error(`Cura cloud command failed (${r.status}): ${data.error||'request rejected; inspect status before retrying'}`);
  return data;
}
export async function handleCloudApi(name,args={}){
  if(name==='cura_cloud_connections')return command('inspect_cloud_connections',{});
  if(['confirm_cura_cloud_connection','cura_cloud_connect'].includes(name)){
    if(typeof args.machine_id!=='string'||!args.machine_id)throw Error('Explicit configured cloud machine_id required');
    if(name==='confirm_cura_cloud_connection'){
      const plan=await command('plan_cloud_connection',{machine_id:args.machine_id});
      const token=crypto.randomUUID();pending.set(token,{kind:'connection',plan,expires:Date.now()+300000});
      return {...plan,confirmation_token:token,expires_in_seconds:300,
        warning:'Select this configured printer profile and cloud output in Cura. Existing profile-change dialogs may appear; no print is sent.'};
    }
    const record=pending.get(args.confirmation_token);pending.delete(args.confirmation_token);
    if(!record||record.kind!=='connection'||record.expires<Date.now()||record.plan.machine_id!==args.machine_id)
      throw Error('Cloud connection confirmation missing, expired, reused or mismatched');
    return command('connect_cloud',{machine_id:args.machine_id,expected_fingerprint:record.plan.fingerprint});
  }
  if(name==='cura_cloud_devices')return command('inspect_cloud',{});
  if(name==='cura_cloud_print_status'){
    if(typeof args.operation_id!=='string'||!args.operation_id)throw Error('operation_id required');
    return command('cloud_print_status',{operation_id:args.operation_id});
  }
  if(typeof args.device_id!=='string'||!args.device_id)throw Error('Explicit cloud device_id required');
  if(name==='confirm_cura_cloud_print'){
    const plan=await command('plan_cloud_print',{device_id:args.device_id});
    const token=crypto.randomUUID();pending.set(token,{kind:'print',plan,expires:Date.now()+300000});
    return {...plan,confirmation_token:token,expires_in_seconds:300,
      warning:'Send this finished slice to the named cloud destination. It may queue or start automatically; this does not cancel an active job.'};
  }
  if(name!=='cura_cloud_print')throw Error('Unknown cloud tool');
  const record=pending.get(args.confirmation_token);pending.delete(args.confirmation_token);
  if(!record||record.kind!=='print'||record.expires<Date.now()||record.plan.device_id!==args.device_id)throw Error('Cloud confirmation missing, expired, reused or mismatched');
  return command('submit_cloud_print',{device_id:args.device_id,expected_fingerprint:record.plan.fingerprint});
}
