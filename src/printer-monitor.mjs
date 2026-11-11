import {printerBaseUrl} from './printer-config.mjs';

const MAX_BYTES=5*1024*1024;
function tool(name,description,properties={}){return {name,description,
  inputSchema:{type:'object',properties,additionalProperties:false},
  annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}};}
export const printerMonitorTools=[
  tool('printer_print_status','Read current local printer/job state, progress, elapsed time and estimated remaining print time. Omits device serials and account identifiers. Never changes the printer.'),
  tool('printer_camera_snapshot','Capture one local printer webcam still as an inline MCP image. Bounded to 5 MiB; follows only same-printer snapshot redirects. Does not stream, save to disk or change the printer.',
    {camera_index:{type:'integer',minimum:0,maximum:15,default:0}})
];
async function bounded(response,limit){
  if(Number(response.headers.get('content-length'))>limit){await response.body?.cancel();throw Error('Printer response exceeds size limit');}
  const reader=response.body?.getReader();if(!reader)return Buffer.alloc(0);
  let size=0;const chunks=[];
  try{
    for(;;){const {done,value}=await reader.read();if(done)break;
      size+=value.length;if(size>limit)throw Error('Printer response exceeds size limit');chunks.push(Buffer.from(value));}
  }catch(error){await reader.cancel().catch(()=>{});throw error;}
  return Buffer.concat(chunks);
}
async function jsonGet(origin,path,optional=false){
  const response=await fetch(origin+path,{redirect:'error',signal:AbortSignal.timeout(6000)});
  if(optional&&response.status===404)return null;
  if(!response.ok)throw Error(`Printer status endpoint returned HTTP ${response.status}`);
  return JSON.parse((await bounded(response,256*1024)).toString('utf8'));
}
const duration=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0?Math.round(value):null;
function display(seconds){
  if(seconds===null)return null;
  const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;
  return [h,m,s].map(n=>String(n).padStart(2,'0')).join(':');
}
export async function readPrintStatus(){
  const origin=printerBaseUrl();
  const [state,job]=await Promise.all([jsonGet(origin,'/api/v1/printer/status'),jsonGet(origin,'/api/v1/print_job',true)]);
  const elapsed=duration(job?.time_elapsed);
  const total=duration(job?.time_total),original=duration(job?.time_estimated);
  const estimate=total>0?total:original>0?original:null;
  const terminal=job?['none','wait_cleanup','post_print'].includes(job.state):state==='idle';
  const remaining=terminal?0:estimate!==null&&elapsed!==null?Math.max(0,estimate-elapsed):null;
  const progress=typeof job?.progress==='number'&&Number.isFinite(job.progress)&&job.progress>=0&&job.progress<=1?job.progress:null;
  return {checked_at:new Date().toISOString(),printer_state:state,job_state:job?.state??null,
    job_name:job?.name??null,progress_percent:progress===null?null:Math.round(progress*1000)/10,
    elapsed_seconds:elapsed,elapsed_display:display(elapsed),remaining_seconds:remaining,remaining_display:display(remaining),
    remaining_estimate_source:terminal?'no active printing phase':total>0?'time_total minus time_elapsed':original>0?'time_estimated minus time_elapsed':'unavailable',
    estimate_note:'Printer estimate, not a deadline; cooling, cleanup and operator pauses may add time.'};
}
function safeSnapshotRedirect(location,current,origin,index){
  const next=new URL(location,current);
  const portAllowed=next.port===origin.port||next.port==='8080';
  const snapshotPath=next.pathname===`/api/v1/camera/${index}/snapshot`&&!next.search;
  const cameraPath=next.pathname==='/'&&next.searchParams.get('action')==='snapshot'&&
    [...next.searchParams.keys()].length===1;
  if(next.protocol!==origin.protocol||next.hostname!==origin.hostname||!portAllowed||next.username||next.password||next.hash||(!snapshotPath&&!cameraPath))
    throw Error('Rejected redirect outside the configured printer snapshot service');
  return next;
}
export async function readCameraSnapshot(args={}){
  const index=args.camera_index??0;
  if(!Number.isInteger(index)||index<0||index>15)throw Error('camera_index must be an integer from 0 to 15');
  const origin=new URL(printerBaseUrl());let url=new URL(`/api/v1/camera/${index}/snapshot`,origin);
  const signal=AbortSignal.timeout(8000);let response;
  for(let redirects=0;;redirects++){
    response=await fetch(url,{redirect:'manual',signal});
    if(![301,302,303,307,308].includes(response.status))break;
    const location=response.headers.get('location');await response.body?.cancel();
    if(redirects>=2||!location)throw Error('Invalid or excessive camera snapshot redirects');
    url=safeSnapshotRedirect(location,url,origin,index);
  }
  if(!response.ok){await response.body?.cancel();throw Error(`Printer camera snapshot returned HTTP ${response.status}`);}
  const type=(response.headers.get('content-type')||'').split(';')[0].trim().toLowerCase();
  if(!['image/jpeg','image/png'].includes(type)){await response.body?.cancel();throw Error('Camera did not return a JPEG or PNG still image');}
  const data=await bounded(response,MAX_BYTES);
  const valid=type==='image/jpeg'?data.length>=4&&data[0]===255&&data[1]===216&&data[2]===255:
    data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]));
  if(!valid)throw Error('Invalid camera image signature');
  return {captured_at:new Date().toISOString(),camera_index:index,mime_type:type,byte_count:data.length,image_base64:data.toString('base64')};
}
export async function handlePrinterMonitor(name,args={}){
  if(name==='printer_print_status')return readPrintStatus();
  if(name==='printer_camera_snapshot')return readCameraSnapshot(args);
  throw Error('Unknown printer monitor tool');
}
export function monitorMcpResult(payload){
  const {image_base64,...metadata}=payload;
  return {content:[{type:'text',text:JSON.stringify(metadata,null,2)},
    ...(image_base64?[{type:'image',mimeType:metadata.mime_type,data:image_base64}]:[])],structuredContent:metadata};
}
