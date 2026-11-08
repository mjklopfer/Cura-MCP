import importlib.util,json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
installer=load('install_plugin');doctor=load('check_deployment')

class DeploymentHelpersTest(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.config=self.root/'config'
    def test_plan_does_not_create_configuration(self):
        result=installer.install(self.config)
        self.assertEqual(result['mode'],'plan');self.assertFalse(self.config.exists())
    def test_install_preserves_connection_and_backs_up_existing_plugin(self):
        old=self.config/'plugins/CuraMcpBridge';old.mkdir(parents=True)
        (old/'old.txt').write_text('fixture plugin')
        connection=self.config/'cura-mcp-bridge.json';connection.write_text('fixture retained')
        with patch.object(installer,'cura_running',return_value=False):result=installer.install(self.config,True)
        self.assertEqual(connection.read_text(),'fixture retained')
        self.assertEqual((Path(result['backup'])/'old.txt').read_text(),'fixture plugin')
        self.assertTrue(all((old/name).is_file() for name in installer.PLUGIN_FILES))
    def test_active_cura_refuses_install_before_writes(self):
        with patch.object(installer,'cura_running',return_value=True):
            with self.assertRaises(RuntimeError):installer.install(self.config,True)
        self.assertFalse(self.config.exists())
    def test_doctor_suppresses_connection_values_and_does_not_connect(self):
        connection=self.root/'fixture.json'
        connection.write_text(json.dumps({'host':'127.0.0.1','port':49621,'token':'dummy-local-fixture'}))
        with patch.object(doctor.socket,'create_connection') as connect, patch.dict(os.environ,{'CURA_PRINTER_BASE_URL':''}):
            result=doctor.inspect(connection)
        connect.assert_not_called();self.assertTrue(result['token_present']);self.assertTrue(result['connection_is_loopback'])
        self.assertNotIn('dummy-local-fixture',json.dumps(result));self.assertNotIn(str(connection),json.dumps(result))
        self.assertFalse(result['printer_contacted']);self.assertFalse(result['printer_origin_configured'])
    def test_doctor_does_not_connect_to_non_loopback_connection_host(self):
        connection=self.root/'fixture.json'
        connection.write_text(json.dumps({'host':'example.invalid','port':49621,'token':'dummy-local-fixture'}))
        with patch.object(doctor.socket,'create_connection') as connect:result=doctor.inspect(connection,True)
        connect.assert_not_called();self.assertFalse(result['connection_is_loopback'])
    @unittest.skipIf(sys.platform=='win32','Bash launcher checks run on macOS/Linux CI')
    def test_macos_launcher_requires_an_origin_before_creating_staging(self):
        env=dict(os.environ,CURA_MCP_NODE=shutil.which('node'),CURA_MCP_PYTHON=sys.executable,CURA_PRINTER_BASE_URL='',CURA_MCP_PRINT_FILE_ROOT=str(self.root/'staging'))
        result=subprocess.run(['/bin/bash',str(ROOT/'scripts/run_macos.sh')],input='',capture_output=True,text=True,env=env,timeout=15)
        self.assertNotEqual(result.returncode,0);self.assertFalse((self.root/'staging').exists())
    @unittest.skipIf(sys.platform=='win32','Bash launcher checks run on macOS/Linux CI')
    def test_macos_launcher_forwards_mcp_stdio_without_printer_requests(self):
        env=dict(os.environ,CURA_MCP_NODE=shutil.which('node'),CURA_MCP_PYTHON=sys.executable,CURA_PRINTER_BASE_URL='http://example.invalid',CURA_MCP_PRINT_FILE_ROOT=str(self.root/'staging'),CURA_MCP_BRIDGE_CONNECTION_PATH=str(self.root/'not-created.json'))
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05'}},{'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]
        result=subprocess.run(['/bin/bash',str(ROOT/'scripts/run_macos.sh')],input=''.join(json.dumps(x)+'\n' for x in requests),capture_output=True,text=True,env=env,timeout=15)
        self.assertEqual(result.returncode,0)
        responses=[json.loads(line) for line in result.stdout.splitlines()]
        tool_names = {tool['name'] for tool in responses[1]['result']['tools']}
        self.assertTrue({'cura_status', 'printer_api_catalog', 'cura_comparison_status'} <= tool_names)
        self.assertFalse((self.root/'not-created.json').exists())

if __name__=='__main__':unittest.main()
