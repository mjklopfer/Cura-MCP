"""Exercise native cloud guards and asynchronous signals without Cura/network."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

spec=importlib.util.spec_from_file_location('cloud_ops',Path(__file__).resolve().parents[1]/'cura_plugin/CuraMcpBridge/cloud_ops.py')
cloud=importlib.util.module_from_spec(spec);spec.loader.exec_module(cloud)

class Signal:
    def __init__(self):self.callbacks=[]
    def connect(self,f):self.callbacks.append(f)
    def disconnect(self,f):self.callbacks.remove(f)
    def emit(self,*a):
        for f in self.callbacks[:]:f(*a)

class CloudOutputDevice:
    __module__='plugins.UM3NetworkPrinting.Cloud'
    active=True
    printers=[]
    def __init__(self):
        self._account=NS(isLoggedIn=True);self._progress=NS(visible=False)
        self.writeStarted=Signal();self.writeFinished=Signal();self.writeError=Signal();self.calls=0
    def getId(self):return 'test-cloud-device'
    def getName(self):return 'Test printer'
    def isConnected(self):return True
    def requestWrite(self,nodes):self.calls+=1;self.writeStarted.emit(self)

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.device=CloudOutputDevice();self.ops=cloud.CloudOperations()
        scene=NS(getRoot=lambda:'root')
        self.app=NS(getOutputDeviceManager=lambda:NS(getOutputDevices=lambda:[self.device]),
                    getController=lambda:NS(getScene=lambda:scene))
        self.context={'machine_id':'test-machine','build_plate':0,'scene_revision':'scene',
                      'post_processing_revision':'post','toolpath_sha256':'hash','slice_ready':True}
    def submit(self):
        plan=self.ops.execute(self.app,'plan_cloud_print',{'device_id':self.device.getId()},self.context)
        return self.ops.execute(self.app,'submit_cloud_print',{'device_id':self.device.getId(),
               'expected_fingerprint':plan['fingerprint']},self.context)
    def test_inventory_does_not_upload(self):
        result=self.ops.execute(self.app,'inspect_cloud',{})
        self.assertEqual(result['devices'][0]['name'],'Test printer');self.assertEqual(self.device.calls,0)
    def test_stale_slice_and_wrong_destination_fail_closed(self):
        plan=self.ops.execute(self.app,'plan_cloud_print',{'device_id':self.device.getId()},self.context)
        self.context['toolpath_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'changed'):
            self.ops.execute(self.app,'submit_cloud_print',{'device_id':self.device.getId(),'expected_fingerprint':plan['fingerprint']},self.context)
        with self.assertRaisesRegex(ValueError,'Unknown'):
            self.ops.execute(self.app,'plan_cloud_print',{'device_id':'wrong'},self.context)
        self.assertEqual(self.device.calls,0)
    def test_native_lifecycle_and_duplicate_prevention(self):
        job=self.submit();self.assertEqual(job['status'],'uploading')
        self.device.writeFinished.emit()
        status=self.ops.status(job['operation_id'])
        self.assertEqual(status['status'],'submitted_or_awaiting_approval')
        self.assertFalse(status['physical_print_started'])
        self.assertEqual(self.device.writeFinished.callbacks,[])
        with self.assertRaisesRegex(ValueError,'already submitted'):self.submit()
        self.assertEqual(self.device.calls,1)
    def test_login_slice_and_upload_guards(self):
        self.context['slice_ready']=False
        with self.assertRaisesRegex(ValueError,'finished'):self.submit()
        self.context['slice_ready']=True;self.device._account.isLoggedIn=False
        with self.assertRaisesRegex(ValueError,'logged in'):self.submit()
        self.device._account.isLoggedIn=True;self.device._progress.visible=True
        with self.assertRaisesRegex(ValueError,'in progress'):self.submit()
    def test_error_is_not_success_and_does_not_auto_retry(self):
        job=self.submit();self.device.writeError.emit()
        self.assertEqual(self.ops.status(job['operation_id'])['status'],'error')
        with self.assertRaisesRegex(ValueError,'already submitted'):self.submit()
        self.assertEqual(self.device.calls,1)

    def configured_app(self):
        class Profile:
            def __init__(self,key,name,cloud_id):self.key,self.name,self.cloud_id=key,name,cloud_id
            def getId(self):return self.key
            def getName(self):return self.name
            def getMetaDataEntry(self,key,default=None):return self.cloud_id if key=='um_cloud_cluster_id' else default
        self.profile=Profile('cloud-profile','Cloud printer',self.device.getId())
        self.local_profile=Profile('local-profile','Local printer',None)
        self.current=self.profile;self.active_output=None;self.refreshes=0
        def select(key):self.current=next(p for p in [self.profile,self.local_profile] if p.getId()==key)
        def active(key):self.active_output=self.device if key==self.device.getId() else None
        def refresh():self.refreshes+=1
        manager=NS(getOutputDevices=lambda:[self.device],getActiveDevice=lambda:self.active_output,
                   setActiveDevice=active,refreshConnections=refresh)
        self.app.getGlobalContainerStack=lambda:self.current
        self.app.getContainerRegistry=lambda:NS(findContainerStacks=lambda **k:[self.profile,self.local_profile])
        self.app.getMachineManager=lambda:NS(setActiveMachine=select)
        self.app.getOutputDeviceManager=lambda:manager

    def test_preinstalled_cloud_selection_has_no_upload_or_local_ip(self):
        self.configured_app()
        inventory=self.ops.execute(self.app,'inspect_cloud_connections',{})
        self.assertEqual(len(inventory['configured_printers']),1)
        self.assertFalse(inventory['configured_printers'][0]['requires_local_ip'])
        self.current=self.local_profile
        plan=self.ops.execute(self.app,'plan_cloud_connection',{'machine_id':'cloud-profile'})
        result=self.ops.execute(self.app,'connect_cloud',{'machine_id':'cloud-profile','expected_fingerprint':plan['fingerprint']})
        self.assertEqual(result['status'],'selected');self.assertEqual(self.refreshes,1)
        self.assertEqual(self.current.getId(),'cloud-profile');self.assertEqual(self.device.calls,0)

    def test_connection_requires_existing_profile_and_unchanged_selection(self):
        self.configured_app()
        with self.assertRaisesRegex(ValueError,'existing cloud-configured'):
            self.ops.execute(self.app,'plan_cloud_connection',{'machine_id':'local-profile'})
        plan=self.ops.execute(self.app,'plan_cloud_connection',{'machine_id':'cloud-profile'})
        self.current=self.local_profile
        with self.assertRaisesRegex(ValueError,'changed'):
            self.ops.execute(self.app,'connect_cloud',{'machine_id':'cloud-profile','expected_fingerprint':plan['fingerprint']})
        self.assertEqual(self.refreshes,0);self.assertEqual(self.device.calls,0)

    def test_connection_does_not_switch_during_native_upload(self):
        self.configured_app()
        plan=self.ops.execute(self.app,'plan_cloud_connection',{'machine_id':'cloud-profile'})
        self.device._progress.visible=True
        with self.assertRaisesRegex(ValueError,'during upload'):
            self.ops.execute(self.app,'connect_cloud',{'machine_id':'cloud-profile','expected_fingerprint':plan['fingerprint']})
        self.assertEqual(self.refreshes,0)

if __name__=='__main__':unittest.main()
