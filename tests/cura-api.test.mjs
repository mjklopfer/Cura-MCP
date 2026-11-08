import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,writeFile,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';

test('Cura settings, slicing and export requests stay bound to approval and machine',async t=>{
  let machine='test-s5',scene='original',post='original',configuration='original';const writes=[];
  const mock=createServer(async(req,res)=>{
    assert.equal(req.headers['x-cura-bridge-token'],'mock-secret');
    let body='';for await(const chunk of req)body+=chunk;
    const payload=JSON.parse(body);res.setHeader('content-type','application/json');
    if(req.url==='/v1/commands/inspect')return res.end(JSON.stringify({machine:{id:machine,name:'Mock S5'},
      scene_revision:scene,post_processing_revision:post,
      scene_nodes:[{id:'white',name:'White'},{id:'green',name:'Green'}]}));
    if(req.url==='/v1/commands/get_settings')return res.end(JSON.stringify({settings:{layer_height:{value:0.2}}}));
    if(req.url==='/v1/commands/inspect_configuration')return res.end(JSON.stringify({
      revision:configuration,current:{printer:{id:machine}},quality_profiles:[{id:'fine',name:'Fine'}]}));
    if(req.url==='/v1/commands/inspect_extensions')return res.end(JSON.stringify({
      marketplace:{revision:'packages-1',installed:[{id:'demo',version:'1.0.0'}]},
      extension_menus:[{plugin_id:'demo',items:['Open dialog']}]}));
    writes.push({url:req.url,payload});res.end(JSON.stringify({accepted:true}));
  });
  await new Promise(resolve=>mock.listen(0,'127.0.0.1',resolve));t.after(()=>mock.close());
  const folder=await mkdtemp(path.join(tmpdir(),'cura-state-test-'));t.after(()=>rm(folder,{recursive:true,force:true}));
  const staging=path.join(folder,'staged');await mkdir(staging);
  const connection=path.join(folder,'connection.json');
  await writeFile(connection,JSON.stringify({host:'127.0.0.1',port:mock.address().port,token:'mock-secret'}));
  process.env.CURA_MCP_BRIDGE_CONNECTION_PATH=connection;process.env.CURA_MCP_PRINT_FILE_ROOT=staging;
  const {handleCuraApi}=await import('../src/cura-api.mjs');
  assert.equal((await handleCuraApi('cura_settings',{keys:['layer_height']})).settings.layer_height.value,0.2);
  assert.equal((await handleCuraApi('cura_configuration',{})).quality_profiles[0].id,'fine');
  const action={action:'set_settings',values:{layer_height:0.15},extruder:0};
  const c=await handleCuraApi('confirm_cura_operation',action);
  assert.equal(writes.length,0);
  await handleCuraApi('cura_operation',{...action,confirmation_token:c.confirmation_token});
  assert.equal(writes.length,1);assert.equal(writes[0].payload.values.layer_height,0.15);
  await assert.rejects(()=>handleCuraApi('cura_operation',{...action,confirmation_token:c.confirmation_token}),/Confirmation/);
  const slice=await handleCuraApi('confirm_cura_operation',{action:'slice'});machine='another-printer';
  await assert.rejects(()=>handleCuraApi('cura_operation',{action:'slice',confirmation_token:slice.confirmation_token}),/machine changed/);
  await assert.rejects(()=>handleCuraApi('confirm_cura_operation',{action:'export_gcode',file_path:path.join(folder,'outside.gcode')}),/staging/);
  for(const action of [{action:'slice'},{action:'export_gcode',file_path:path.join(staging,'test.gcode'),build_plate:0}]){
    const c=await handleCuraApi('confirm_cura_operation',action);
    await handleCuraApi('cura_operation',{...action,confirmation_token:c.confirmation_token});
  }
  assert.deepEqual(writes.map(w=>w.url),['/v1/commands/set_settings','/v1/commands/slice','/v1/commands/export_gcode']);
  const profile={action:'set_configuration',configuration_kind:'quality',target_id:'fine'};
  const staleProfile=await handleCuraApi('confirm_cura_operation',profile);
  configuration='changed';
  await assert.rejects(()=>handleCuraApi('cura_operation',{...profile,confirmation_token:staleProfile.confirmation_token}),/configuration changed/);
  const approvedProfile=await handleCuraApi('confirm_cura_operation',profile);
  await handleCuraApi('cura_operation',{...profile,confirmation_token:approvedProfile.confirmation_token});
  assert.equal(writes.at(-1).payload.expected_configuration,'changed');
  await assert.rejects(()=>handleCuraApi('confirm_cura_operation',{...profile,configuration_kind:'material'}),/Invalid Cura configuration/);
  await assert.rejects(()=>handleCuraApi('confirm_cura_operation',{action:'merge_objects',object_ids:['white']}),/distinct/);
  await assert.rejects(()=>handleCuraApi('confirm_cura_operation',{action:'center_objects',object_ids:['missing']}),/Unknown scene/);
  const clear={action:'clear_scene'};
  const approved=await handleCuraApi('confirm_cura_operation',clear);
  assert.equal(approved.affected_objects.length,2);
  scene='changed';
  await assert.rejects(()=>handleCuraApi('cura_operation',{...clear,confirmation_token:approved.confirmation_token}),/scene changed/);
  assert.equal(writes.length,4);
  const assign={action:'assign_extruder',object_ids:['white'],extruder:1};
  const c2=await handleCuraApi('confirm_cura_operation',assign);
  await handleCuraApi('cura_operation',{...assign,confirmation_token:c2.confirmation_token});
  assert.deepEqual(writes.at(-1),{url:'/v1/commands/assign_extruder',
    payload:{object_ids:['white'],extruder:1,expected_scene:'changed'}});
  const move={action:'move_objects',object_ids:['white'],vector:[12,0,-5]};
  await assert.rejects(()=>handleCuraApi('confirm_cura_operation',{...move,vector:[0,1]}),/finite XYZ/);
  const moveApproval=await handleCuraApi('confirm_cura_operation',move);
  await handleCuraApi('cura_operation',{...move,confirmation_token:moveApproval.confirmation_token});
  assert.deepEqual(writes.at(-1),{url:'/v1/commands/move_objects',
    payload:{object_ids:['white'],vector:[12,0,-5],expected_scene:'changed'}});
  await assert.rejects(()=>handleCuraApi('cura_navigate',{view:'arbitrary_command'}),/Unsupported/);
  await handleCuraApi('cura_navigate',{view:'preview'});
  assert.deepEqual(writes.at(-1),{url:'/v1/commands/navigate',payload:{view:'preview'}});
  const pause={action:'add_griffin_pause',pause_layer:23};
  const c3=await handleCuraApi('confirm_cura_operation',pause);
  post='changed';
  await assert.rejects(()=>handleCuraApi('cura_operation',{...pause,confirmation_token:c3.confirmation_token}),/post-processing changed/);
  const c4=await handleCuraApi('confirm_cura_operation',pause);
  await handleCuraApi('cura_operation',{...pause,confirmation_token:c4.confirmation_token});
  assert.deepEqual(writes.at(-1),{url:'/v1/commands/add_griffin_pause',
    payload:{pause_layer:23,expected_post_processing:'changed'}});
  const compare={action:'compare_slices',variants:[
    {name:'Fine',values:{layer_height:0.1}},{name:'Normal',values:{layer_height:0.2}}]};
  const comparison=await handleCuraApi('confirm_cura_operation',compare);
  await handleCuraApi('cura_operation',{...compare,confirmation_token:comparison.confirmation_token});
  assert.deepEqual(writes.at(-1),{url:'/v1/commands/compare_slices',payload:{
    variants:compare.variants,expected_scene:'changed',expected_configuration:'changed'}});
  const remove={action:'manage_package',package_action:'remove',target_id:'demo'};
  const packageApproval=await handleCuraApi('confirm_cura_operation',remove);
  assert.equal(packageApproval.current_package.version,'1.0.0');
  await handleCuraApi('cura_operation',{...remove,confirmation_token:packageApproval.confirmation_token});
  assert.equal(writes.at(-1).payload.expected_package_state,'packages-1');
  const menu={action:'activate_extension_menu',target_id:'demo',menu_item:'Open dialog'};
  const menuApproval=await handleCuraApi('confirm_cura_operation',menu);
  await handleCuraApi('cura_operation',{...menu,confirmation_token:menuApproval.confirmation_token});
  assert.deepEqual(writes.at(-1),{url:'/v1/commands/activate_extension_menu',
    payload:{target_id:'demo',menu_item:'Open dialog'}});
});
