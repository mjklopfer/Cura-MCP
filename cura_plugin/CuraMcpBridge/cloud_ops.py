"""Native Cura cloud output adapter. All calls/callbacks run on Cura's main thread."""
import hashlib
import json
import time
import uuid

ACTIONS={'inspect_cloud','plan_cloud_print','submit_cloud_print','cloud_print_status',
         'inspect_cloud_connections','plan_cloud_connection','connect_cloud'}

def value(obj,name,default=None):
    item=getattr(obj,name,default)
    return item() if callable(item) else item

def cloud_devices(app):
    # Restrict writes to Cura's own cloud implementation, not arbitrary plugins.
    return [d for d in app.getOutputDeviceManager().getOutputDevices()
            if type(d).__name__=='CloudOutputDevice' and 'UM3NetworkPrinting' in type(d).__module__]

def connection_profiles(app):
    current=app.getGlobalContainerStack()
    profiles=[]
    for stack in app.getContainerRegistry().findContainerStacks(type='machine'):
        if stack.getMetaDataEntry('um_cloud_cluster_id',None):
            profiles.append({'machine_id':stack.getId(),'name':stack.getName(),
                             'active':bool(current and current.getId()==stack.getId()),
                             'connection':'cloud','requires_local_ip':False})
    return profiles

def connection_plan(app,machine_id):
    matches=[s for s in app.getContainerRegistry().findContainerStacks(type='machine')
             if s.getId()==machine_id and s.getMetaDataEntry('um_cloud_cluster_id',None)]
    if len(matches)!=1:raise ValueError('Choose an existing cloud-configured machine_id from cura_cloud_connections')
    current=app.getGlobalContainerStack();stack=matches[0]
    bound={'machine_id':stack.getId(),'name':stack.getName(),
           'cloud_id':stack.getMetaDataEntry('um_cloud_cluster_id',None),
           'current_machine':current.getId() if current else None}
    return stack,{'machine_id':stack.getId(),'name':stack.getName(),
                 'fingerprint':hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest(),
                 'requires_local_ip':False,'prints_or_uploads':False}

def describe(d):
    account=getattr(d,'_account',None)
    progress=getattr(d,'_progress',None)
    return {'device_id':d.getId(),'name':d.getName(),'connection':'cloud',
            'connected':bool(value(d,'isConnected',False)),
            'logged_in':bool(value(account,'isLoggedIn',False)),
            'active':bool(value(d,'active',False)),
            'upload_in_progress':bool(value(progress,'visible',False)),
            'printers':[{'name':value(p,'name',''),'state':value(p,'state','unknown')}
                        for p in value(d,'printers',[])],
            'status_source':'Cura cached native cloud state; no forced network refresh'}

def plan(app,device_id,context):
    matches=[d for d in cloud_devices(app) if d.getId()==device_id]
    if len(matches)!=1:raise ValueError('Unknown native cloud device; inspect cloud destinations')
    d=matches[0]; info=describe(d)
    if not all(info[k] for k in ('connected','logged_in','active')):
        raise ValueError('Cloud destination disconnected, inactive or not logged in; use Cura login manually')
    if info['upload_in_progress']:raise ValueError('Native cloud upload already in progress; inspect status')
    if getattr(d,'_uploaded_print_job',None) is not None:
        raise ValueError('Current slice already has a native cloud job; inspect printer queue instead of resending')
    if not context.get('slice_ready'):raise ValueError('A finished native slice is required')
    bound={'device_id':device_id,'device_name':info['name'],**context}
    fingerprint=hashlib.sha256(json.dumps(bound,sort_keys=True).encode()).hexdigest()
    return d,{'device_id':device_id,'device_name':info['name'],'fingerprint':fingerprint,
              'machine_id':context['machine_id'],'build_plate':context['build_plate'],
              'toolpath_sha256':context['toolpath_sha256'],'status':info}

class CloudOperations:
    def __init__(self):
        self.jobs={}
        self.sent=set()

    def status(self,operation_id):
        if operation_id not in self.jobs:raise ValueError('Unknown cloud operation; do not automatically resend')
        return {k:v for k,v in self.jobs[operation_id].items() if k not in ('callbacks','device')}

    def execute(self,app,action,payload,context=None):
        if action=='inspect_cloud_connections':
            active=app.getOutputDeviceManager().getActiveDevice()
            return {'configured_printers':connection_profiles(app),
                    'active_output_device_id':active.getId() if active else None,
                    'devices':[describe(d) for d in cloud_devices(app)],'read_only':True}
        if action in {'plan_cloud_connection','connect_cloud'}:
            stack,result=connection_plan(app,payload.get('machine_id'))
            if action=='plan_cloud_connection':return result
            if result['fingerprint']!=payload.get('expected_fingerprint'):
                raise ValueError('Configured cloud printer or current selection changed after confirmation')
            if any(j['status'] in ('starting','uploading') for j in self.jobs.values()) or any(
                    describe(d)['upload_in_progress'] for d in cloud_devices(app)):
                raise ValueError('Do not change cloud connection during upload')
            current=app.getGlobalContainerStack()
            if current is None or current.getId()!=stack.getId():
                app.getMachineManager().setActiveMachine(stack.getId())
            current=app.getGlobalContainerStack()
            if current is None or current.getId()!=stack.getId():
                return {'status':'pending_profile_selection','machine_id':stack.getId(),
                        'detail':'Native Cura profile-change dialog or switch is pending; inspect Cura. Nothing printed.'}
            manager=app.getOutputDeviceManager()
            manager.refreshConnections()
            cluster=stack.getMetaDataEntry('um_cloud_cluster_id',None)
            devices=[d for d in cloud_devices(app) if d.getId()==cluster]
            if len(devices)!=1:
                return {'status':'connecting','machine_id':stack.getId(),
                        'detail':'Native connection refresh requested; poll cura_cloud_connections. Login, if needed, remains manual.'}
            device=devices[0]
            manager.setActiveDevice(device.getId())
            active=manager.getActiveDevice()
            return {'status':'selected' if active and active.getId()==device.getId() else 'connecting',
                    'machine_id':stack.getId(),'device':describe(device),'prints_or_uploads':False}
        if action=='inspect_cloud':return {'devices':[describe(d) for d in cloud_devices(app)],'read_only':True,
            'recent_operations':[self.status(key) for key in list(self.jobs)[-10:]]}
        if action=='cloud_print_status':return self.status(payload.get('operation_id'))
        d,result=plan(app,payload.get('device_id'),context)
        fingerprint=result['fingerprint']
        if action=='plan_cloud_print':return result
        if action!='submit_cloud_print':raise ValueError('Unknown cloud operation')
        if fingerprint!=payload.get('expected_fingerprint'):raise ValueError('Cloud destination or slice changed after confirmation')
        if fingerprint in self.sent:raise ValueError('This slice/destination was already submitted this Cura session; inspect job status instead of resending')
        if any(j['status'] in ('starting','uploading') for j in self.jobs.values()):
            raise ValueError('Bridge cloud upload already in progress')
        operation_id=str(uuid.uuid4())
        job={'operation_id':operation_id,'device_id':d.getId(),'device_name':d.getName(),
             'status':'starting','created_at':time.time(),'device':d,'callbacks':[],
             'physical_print_started':False,'toolpath_sha256':context['toolpath_sha256']}
        self.jobs[operation_id]=job
        self.sent.add(fingerprint)  # Fail closed even if native export raises or response times out.
        def finish(*_):
            job['status']='submitted_or_awaiting_approval'
            job['detail']='Native cloud write finished; check printer/queue for actual start or approval.'
            job['finished_at']=time.time()
            cleanup()
        def error(*_):
            job['status']='error'
            job['detail']='Native cloud write failed; inspect Cura and destination queue before any resend.'
            cleanup()
        def started(*_):job['status']='uploading'
        def cleanup():
            for signal,callback in job['callbacks']:
                signal.disconnect(callback)
            job['callbacks']=[]
        for signal,callback in [(d.writeStarted,started),(d.writeFinished,finish),(d.writeError,error)]:
            signal.connect(callback);job['callbacks'].append((signal,callback))
        try:
            d.requestWrite([app.getController().getScene().getRoot()])
        except Exception:
            error()
        return self.status(operation_id)
