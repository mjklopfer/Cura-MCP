import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const pending=new Map();
const root=path.resolve(process.env.CURA_MCP_PRINT_FILE_ROOT||path.join(process.cwd(),'print_files'));
import {connectionPath} from './cura-connection.mjs';
const transforms=['move_objects','rotate_objects','scale_objects','mirror_objects'];
const sceneTargets=['center_objects','merge_objects','assign_extruder','select_objects','group_objects',
  'ungroup_objects','delete_objects','duplicate_objects','set_model_settings','reset_model_settings',
  'set_mesh_type','lay_flat','export_mesh','scale_to_fit',...transforms];
const sceneActions=new Set(['clear_scene','set_extruder_enabled','arrange_objects',...sceneTargets]);
const postActions=new Set(['add_griffin_pause','remove_post_processing_script']);
const views=['prepare','preview','monitor','post_processing','marketplace','account_sign_in','move','scale','rotate','mirror'];
const configurationKinds=['printer','material','core','quality','intent','custom_profile','create_profile',
  'update_profile','import_profile','export_profile'];
const schema={action:{type:'string',enum:['set_settings','reset_settings','slice','export_gcode','save_project','set_configuration',
    'compare_slices','manage_package','activate_extension_menu',...sceneActions,...postActions]},
  menu_item:{type:'string',description:'Exact native menu label reported by cura_extensions.'},
  variants:{type:'array',minItems:2,maxItems:5,items:{type:'object',required:['name','values'],additionalProperties:false,
    properties:{name:{type:'string',minLength:1,maxLength:80},values:{type:'object',minProperties:1,additionalProperties:false,
      properties:{layer_height:{type:'number',minimum:0.04,maximum:1},infill_sparse_density:{type:'number',minimum:0,maximum:100},
        wall_line_count:{type:'integer',minimum:0,maximum:20},top_layers:{type:'integer',minimum:0,maximum:50},
        bottom_layers:{type:'integer',minimum:0,maximum:50},speed_print:{type:'number',minimum:5,maximum:300}}}}}},
  package_action:{type:'string',enum:['install','update','remove']},
  configuration_kind:{type:'string',enum:configurationKinds},
  target_id:{type:'string',description:'Identifier returned by cura_configuration, or the new name for create_profile.'},
  vector:{type:'array',items:{type:'number',minimum:-10000,maximum:10000},minItems:3,maxItems:3,
    description:'XYZ in Cura engine axes (Y up). Delta mm, Euler degrees, positive scale factors, or mirror signs.'},
  copies:{type:'integer',minimum:1,maximum:20},
  keys:{type:'array',items:{type:'string'},minItems:1,maxItems:100,uniqueItems:true},
  mesh_type:{type:'string',enum:['normal','infill_mesh','cutting_mesh','support_mesh','anti_overhang_mesh']},
  pause_layer:{type:'integer',minimum:1,maximum:100000,description:'Zero-based G-code layer to pause before (no raft).'},
  script_index:{type:'integer',minimum:0,description:'Index from cura_extensions post_processing.active.'},
  object_ids:{type:'array',items:{type:'string'},minItems:1,maxItems:100,uniqueItems:true,description:'IDs from cura_inspect scene_nodes.'},
  enabled:{type:'boolean',description:'Enable or disable the specified Cura extruder.'},
  extruder:{type:'integer',minimum:0},values:{type:'object',additionalProperties:true},
  file_path:{type:'string'},build_plate:{type:'integer',minimum:0},
  mode:{type:'string',enum:['save','save_as'],description:'save overwrites the known current project; save_as selects a new name and/or folder.'},
  file_name:{type:'string',description:'Save As filename; .3mf is appended if omitted. No folder separators.'},
  folder:{type:'string',description:'Absolute Save As folder. Omit to use the current project folder or Cura save folder.'},
  create_folder:{type:'boolean',description:'Explicitly create a missing destination folder when executing Save As.'}};
function tool(name,description,properties,required,readOnlyHint){return {name,description,
  inputSchema:{type:'object',properties,required,additionalProperties:false},
  annotations:{readOnlyHint,destructiveHint:!readOnlyHint,openWorldHint:false}};}
export const curaApiTools=[
  tool('cura_comparison_status','Read the latest Cura slice comparison, optionally verifying its ID.',{comparison_id:{type:'string'}},[],true),
  tool('cura_comparison_cancel','Cancel the named comparison and restore its temporary settings.',{comparison_id:{type:'string'}},['comparison_id'],false),
  tool('cura_layers','Read layer markers, feature types and tool changes from the active sliced build plate.',
    {first_layer:{type:'integer',minimum:-1000},limit:{type:'integer',minimum:1,maximum:200}},[],true),
  tool('cura_estimates','Read current sliced duration and material estimates for the active plate.',{},[],true),
  tool('cura_snapshot','Capture a native isometric model image of the active build plate.',{},[],true),
  tool('cura_configuration','List configured printers, compatible materials and cores, quality presets, and custom profiles.',{},[],true),
  tool('cura_extensions','List active Cura plugins, stages, toolbar tools, and available and active post-processing scripts.',{},[],true),
  tool('cura_navigate','Switch to a Cura stage, open Post Processing or Marketplace, or select a native transform tool. Does not edit the scene.',{view:{type:'string',enum:views}},['view'],false),
  tool('cura_inspect','Read the Cura machine, extruder states, scene object IDs and assignments, and slice state on its main thread.',{},[],true),
  tool('cura_settings','Read effective global or extruder settings. Omit keys to list available setting keys; provide at most 200 keys for values.',{keys:{type:'array',items:{type:'string'}},extruder:{type:'integer',minimum:0}},[],true),
  tool('confirm_cura_operation','Prepare a five-minute one-use confirmation for Cura settings, scene actions, slicing, G-code export or project save. Scene actions bind current object state. Show the changes before executing.',schema,['action'],false),
  tool('cura_operation','Apply an approved Cura workspace operation. Project saves return an operation_id; poll cura_project_save_status for completion. Never prints or uploads automatically.',{...schema,confirmation_token:{type:'string'}},['action','confirmation_token'],false),
  tool('cura_project_save_status','Read completion, validated archive size/hash or failure for a project save. A running response is not a completed save.',{operation_id:{type:'string'}},['operation_id'],true),
  tool('cura_path_info','Inspect one absolute path from Cura itself: existence, type, readability, resolved path and OS error. Does not return file contents.',{file_path:{type:'string'}},['file_path'],true)
];
function normalized(args){
  const {confirmation_token,...request}=args;
  if(!schema.action.enum.includes(request.action))throw new Error('Unknown Cura action');
  if(request.action==='compare_slices'&&(
      Object.keys(request).some(key=>!['action','variants'].includes(key))||
      !Array.isArray(request.variants)||request.variants.length<2||request.variants.length>5))
    throw new Error('Provide 2 to 5 named slice variants');
  if(request.action==='activate_extension_menu'&&(
    Object.keys(request).some(key=>!['action','target_id','menu_item'].includes(key))||
    [request.target_id,request.menu_item].some(value=>typeof value!=='string'||!value.trim()||value.length>200)))
    throw new Error('Provide the exact extension ID and menu label');
  if(request.action==='manage_package'){
    const {package_action:operation,target_id:target,file_path:filename}=request;
    const remove=operation==='remove';
    if(!schema.package_action.enum.includes(operation)||typeof target!=='string'||!target.trim()||target.length>200||
       Object.keys(request).some(key=>!['action','package_action','target_id',...(remove?[]:['file_path'])].includes(key)))
      throw new Error('Provide an exact package ID and a supported package operation');
    if(!remove){
      if(typeof filename!=='string'||!path.isAbsolute(filename)||!filename.toLowerCase().endsWith('.curapackage'))
        throw new Error('Provide a staged .curapackage file');
      const resolved=fs.realpathSync(filename);
      const relative=path.relative(fs.realpathSync(root),resolved);
      const info=fs.statSync(resolved);
      if(!relative||relative.startsWith('..')||path.isAbsolute(relative)||!info.isFile()||info.size>100_000_000)
        throw new Error('Use a package file up to 100 MB inside the staging folder');
      request.file_path=resolved;
      request.package_sha256=crypto.createHash('sha256').update(fs.readFileSync(resolved)).digest('hex');
    }
  }
  if(request.action==='set_configuration'){
    const {configuration_kind:kind,target_id:target,extruder}=request;
    const needsSlot=['material','core'].includes(kind);
    const importing=kind==='import_profile';
    const fileOperation=importing||kind==='export_profile';
    const allowed=['action','configuration_kind',...(importing?[]:['target_id']),
      ...(needsSlot?['extruder']:[]),...(fileOperation?['file_path']:[])];
    if(!configurationKinds.includes(kind)||(!importing&&(typeof target!=='string'||!target.trim()||target.length>256))||
       Object.keys(request).some(key=>!allowed.includes(key))||
       (needsSlot&&(!Number.isInteger(extruder)||extruder<0)))throw new Error('Invalid Cura configuration arguments');
    if(!importing)request.target_id=target.trim();
    if(fileOperation){
      if(typeof request.file_path!=='string'||!path.isAbsolute(request.file_path)||!request.file_path.endsWith('.curaprofile'))
        throw new Error('Provide an absolute .curaprofile path');
      const resolved=importing?fs.realpathSync(request.file_path):
        path.join(fs.realpathSync(path.dirname(request.file_path)),path.basename(request.file_path));
      const relative=path.relative(fs.realpathSync(root),resolved);
      if(!relative||relative.startsWith('..')||path.isAbsolute(relative))throw new Error('Use a profile file below the staging folder');
      if(!importing&&fs.existsSync(resolved))throw new Error('Profile export requires a new file');
      if(importing){
        const info=fs.statSync(resolved);
        if(!info.isFile()||info.size>10_000_000)throw new Error('Profile must be a file up to 10 MB');
        request.profile_sha256=crypto.createHash('sha256').update(fs.readFileSync(resolved)).digest('hex');
      }
      request.file_path=resolved;
    }
  }else if(request.configuration_kind!==undefined||(request.target_id!==undefined&&
      !['manage_package','activate_extension_menu'].includes(request.action))){
    throw new Error('Unexpected Cura configuration arguments');
  }
  if(postActions.has(request.action)){
    const field=request.action==='add_griffin_pause'?'pause_layer':'script_index';
    if(Object.keys(request).some(key=>!['action',field].includes(key))||
       !Number.isInteger(request[field])||request[field]<(field==='pause_layer'?1:0)||
       (field==='pause_layer'&&request[field]>100000))throw new Error('Invalid post-processing arguments');
  }else if(request.pause_layer!==undefined||request.script_index!==undefined){
    throw new Error('Unexpected post-processing arguments');
  }
  if(sceneActions.has(request.action)){
    const targets=sceneTargets.includes(request.action);
    const slot=['assign_extruder','set_extruder_enabled'].includes(request.action);
    const transform=transforms.includes(request.action);
    const duplicate=request.action==='duplicate_objects';
    const meshExport=request.action==='export_mesh';
    const modelField={set_model_settings:'values',reset_model_settings:'keys',set_mesh_type:'mesh_type'}[request.action];
    const keys=['action',...(targets?['object_ids']:[]),...(slot?['extruder']:[]),
      ...(request.action==='set_extruder_enabled'?['enabled']:[]),...(transform?['vector']:[]),
      ...(duplicate?['copies']:[]),...(modelField?[modelField]:[]),...(meshExport?['file_path']:[])];
    if(Object.keys(request).some(key=>!keys.includes(key)))throw new Error('Unexpected scene operation arguments');
    const ids=request.object_ids;
    if(targets && (!Array.isArray(ids)||ids.length<(['merge_objects','group_objects'].includes(request.action)?2:1)||
       ids.length>100||new Set(ids).size!==ids.length||ids.some(id=>typeof id!=='string'||!id)))
      throw new Error('Provide distinct scene object IDs');
    if(slot && (!Number.isInteger(request.extruder)||request.extruder<0))throw new Error('Provide a zero-based extruder index');
    if(transform && (!Array.isArray(request.vector)||request.vector.length!==3||
       request.vector.some(value=>!Number.isFinite(value)||Math.abs(value)>10000)))
      throw new Error('Provide three finite XYZ components within +/-10000');
    if(request.action==='scale_objects'&&request.vector.some(value=>value<=0))throw new Error('Scale multipliers must be positive');
    if(request.action==='mirror_objects'&&(!request.vector.includes(-1)||request.vector.some(value=>![-1,1].includes(value))))
      throw new Error('Use -1 for mirrored axes and 1 for other axes');
    if(duplicate&&(!Number.isInteger(request.copies)||request.copies<1||request.copies>20))throw new Error('Provide between 1 and 20 copies');
    if(modelField&&ids.length!==1)throw new Error('Choose one individual mesh');
    if(modelField==='mesh_type'&&!schema.mesh_type.enum.includes(request.mesh_type))throw new Error('Choose a supported mesh type');
    if(modelField==='keys'&&(!Array.isArray(request.keys)||!request.keys.length||request.keys.length>100||
       request.keys.some(key=>typeof key!=='string'||!key)))throw new Error('Provide 1 to 100 setting keys');
    if(modelField==='values'&&(!request.values||typeof request.values!=='object'||Array.isArray(request.values)||
       !Object.keys(request.values).length||Object.keys(request.values).length>100))throw new Error('Provide 1 to 100 setting values');
    if(request.action==='set_extruder_enabled' && typeof request.enabled!=='boolean')throw new Error('Provide enabled as a boolean');
  }
  if(request.action==='set_settings' && (!request.values || !Object.keys(request.values).length))throw new Error('Provide settings values');
  if(request.action==='reset_settings'&&(
    Object.keys(request).some(key=>!['action','keys','extruder'].includes(key))||
    !Array.isArray(request.keys)||!request.keys.length||request.keys.length>100||
    request.keys.some(key=>typeof key!=='string'||!key)||
    (request.extruder!==undefined&&(!Number.isInteger(request.extruder)||request.extruder<0))))
    throw new Error('Provide 1 to 100 reset keys and an optional zero-based extruder');
  if(['export_gcode','export_mesh'].includes(request.action)){
    const extension=request.action==='export_gcode'?'.gcode':'.stl';
    if(typeof request.file_path!=='string'||!path.isAbsolute(request.file_path)||!request.file_path.toLowerCase().endsWith(extension))
      throw new Error(`Absolute ${extension} output path required`);
    const resolved=path.resolve(request.file_path);
    const parent=fs.realpathSync(path.dirname(resolved));
    const relative=path.relative(fs.realpathSync(root),parent);
    if(relative.startsWith('..') || path.isAbsolute(relative) || fs.existsSync(resolved))throw new Error('Export must create a new file below the staging folder');
    request.file_path=path.join(parent,path.basename(resolved));
  }
  return request;
}
async function command(name,body){
  const c=JSON.parse(fs.readFileSync(connectionPath,'utf8'));
  if(c.host!=='127.0.0.1' || !Number.isInteger(c.port) || !c.token)throw new Error('Invalid loopback connection');
  const response=await fetch(`http://${c.host}:${c.port}/v1/commands/${name}`,{method:'POST',
    headers:{'X-Cura-Bridge-Token':c.token,'content-type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(8000)});
  const result=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(`Cura command ${name} returned HTTP ${response.status}: ${result.error || 'request rejected'}`);
  return result;
}
function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value && typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export async function handleCuraApi(name,args){
  if(name==='cura_comparison_status')return command('comparison_status',args);
  if(name==='cura_comparison_cancel')return command('cancel_comparison',args);
  if(name==='cura_layers')return command('inspect_layers',args);
  if(name==='cura_estimates')return command('inspect_estimates',{});
  if(name==='cura_snapshot')return command('snapshot',{});
  if(name==='cura_configuration')return command('inspect_configuration',{});
  if(name==='cura_extensions')return command('inspect_extensions',{});
  if(name==='cura_navigate'){
    if(!views.includes(args.view))throw new Error('Unsupported Cura navigation target');
    return command('navigate',{view:args.view});
  }
  if(name==='cura_inspect')return command('inspect',{});
  if(name==='cura_settings')return command('get_settings',args);
  if(name==='cura_project_save_status')return command('project_save_status',args);
  if(name==='cura_path_info')return command('path_info',args);
  let request=normalized(args);
  if(request.action==='save_project'){
    if(request.file_path || request.values || request.extruder!==undefined || request.build_plate!==undefined)throw new Error('Project save uses mode, file_name and folder, not file_path/settings');
    const {action,...options}=request;
    request={action,...await command('plan_project_save',options)};
  }
  const fingerprint=canonical(request);
  const state=await command('inspect',{});
  const machine=state.machine.id;
  const configuration=['set_configuration','reset_settings','compare_slices'].includes(request.action)?await command('inspect_configuration',{}):undefined;
  if(configuration&&(!configuration.revision||configuration.current?.printer?.id!==machine))
    throw new Error('Active Cura machine changed during inspection; inspect again');
  const scene=(sceneActions.has(request.action)||request.action==='compare_slices')?state.scene_revision:undefined;
  const packages=request.action==='manage_package'?(await command('inspect_extensions',{})).marketplace:undefined;
  if(request.action==='manage_package'&&!packages?.revision)throw new Error('Package inventory unavailable');
  if(request.action==='activate_extension_menu'){
    const available=(await command('inspect_extensions',{})).extension_menus;
    if(!available?.some(menu=>menu.plugin_id===request.target_id&&menu.items.includes(request.menu_item)))
      throw new Error('Unknown extension menu action; inspect Cura extensions again');
  }
  const post=(postActions.has(request.action)||request.action==='export_gcode')?state.post_processing_revision:undefined;
  if(postActions.has(request.action)&&!post)throw new Error('Post Processing is unavailable; update and restart Cura');
  if(sceneActions.has(request.action)){
    if(typeof scene!=='string'||!scene)throw new Error('Installed Cura plugin does not support scene operations; update and restart Cura');
    const known=new Set(state.scene_nodes.map(node=>node.id));
    if(request.object_ids?.some(id=>!known.has(id)))throw new Error('Unknown scene object ID; inspect Cura again');
  }
  if(name==='confirm_cura_operation'){
    const token=crypto.randomUUID();pending.set(token,{fingerprint,machine,scene,post,configuration:configuration?.revision,
      packages:packages?.revision,expires:Date.now()+300000});
    return {confirmation_token:token,expires_in_seconds:300,machine:state.machine,request,
      ...(scene?{affected_objects:state.scene_nodes.filter(node=>['clear_scene','arrange_objects'].includes(request.action)||request.object_ids?.includes(node.id))}:{}),
      ...(configuration?{current_configuration:configuration.current,has_unsaved_profile_overrides:configuration.has_unsaved_profile_overrides}:{}),
      ...(packages?{current_package:packages.installed.find(item=>item.id===request.target_id)??null,
        restart_required:true}:{}),
      warning:request.action==='activate_extension_menu'
        ?'Approve this exact Cura extension action. The extension controls its effects and any subsequent dialogs.'
        :'Approve these exact Cura workspace changes before execution. No physical print is started.'};
  }
  const record=pending.get(args.confirmation_token);pending.delete(args.confirmation_token);
  if(!record || record.expires<Date.now() || record.fingerprint!==fingerprint || record.machine!==machine)throw new Error('Confirmation missing, expired, reused, mismatched or active Cura machine changed');
  if(record.scene!==scene)throw new Error('Cura scene changed after confirmation; inspect again');
  if(record.post!==post)throw new Error('Cura post-processing changed after confirmation; inspect again');
  if(record.configuration!==configuration?.revision)throw new Error('Cura configuration changed after confirmation; inspect again');
  if(record.packages!==packages?.revision)throw new Error('Cura package state changed after confirmation; inspect again');
  const {action,...body}=request;
  return command(action,{...body,...(scene?{expected_scene:scene}:{}),...(post?{expected_post_processing:post}:{}),
    ...(packages?{expected_package_state:packages.revision}:{}),
    ...(configuration?{expected_configuration:configuration.revision}:{})});
}
