"""Report local deployment checks without printing paths, tokens or the printer origin."""
from pathlib import Path
import argparse,json,os,shutil,socket,subprocess,sys
from urllib.parse import urlsplit

def connection_default():
    configured=os.environ.get('CURA_MCP_BRIDGE_CONNECTION_PATH')
    if configured:return Path(configured).expanduser()
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/cura'/os.environ.get('CURA_MCP_CURA_VERSION','5.14')/'cura-mcp-bridge.json'
    return Path(os.environ.get('APPDATA',str(Path.home()/'AppData/Roaming')))/'cura'/os.environ.get('CURA_MCP_CURA_VERSION','5.14')/'cura-mcp-bridge.json'

def inspect(connection,check_listener=False):
    result={'platform':sys.platform,'python_compatible':sys.version_info>=(3,10),'connection_file_exists':connection.is_file(),'connection_parseable':False,'token_present':False,'connection_is_loopback':False,'port_valid':False,'listener_checked':check_listener,'printer_origin_configured':bool(os.environ.get('CURA_PRINTER_BASE_URL'))}
    node=os.environ.get('CURA_MCP_NODE') or shutil.which('node')
    if not node:
        node=next((p for p in ['/opt/homebrew/bin/node','/usr/local/bin/node','/usr/bin/node'] if Path(p).is_file()),None)
    result['node_found']=bool(node);result['node_compatible']=False
    if node:
        try:
            version=subprocess.run([node,'--version'],capture_output=True,text=True,timeout=5)
            result['node_compatible']=version.returncode==0 and int(version.stdout.strip().lstrip('v').split('.')[0])>=20
        except (OSError,ValueError,subprocess.SubprocessError):pass
    try:
        if connection.stat().st_size>65536:raise ValueError('oversize connection file')
        data=json.loads(connection.read_text(encoding='utf-8'))
        result['connection_parseable']=isinstance(data,dict)
        result['token_present']=isinstance(data.get('token'),str) and bool(data['token'])
        result['connection_is_loopback']=data.get('host') in {'127.0.0.1','localhost','::1'}
        result['port_valid']=type(data.get('port')) is int and 1<=data['port']<=65535
        if check_listener and result['connection_is_loopback'] and result['port_valid']:
            try:
                with socket.create_connection((data['host'],data['port']),timeout=1):result['listener_accepts_tcp']=True
            except OSError:result['listener_accepts_tcp']=False
    except (OSError,ValueError,TypeError,AttributeError):pass
    configured=os.environ.get('CURA_PRINTER_BASE_URL','')
    try:
        origin=urlsplit(configured)
        result['printer_origin_valid']=bool(configured and origin.scheme in {'http','https'} and origin.hostname and not origin.username and not origin.password and not origin.query and not origin.fragment and origin.path in {'','/'})
    except ValueError:result['printer_origin_valid']=False
    result['printer_contacted']=False;result['os_credential_store_read']=False
    result['note']='TCP reachability does not prove Cura readiness or a running MCP client; this tool never contacts the printer.'
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-file',type=Path)
    parser.add_argument('--check-listener',action='store_true',help='Open/close one loopback TCP connection without sending a command.')
    args=parser.parse_args();result=inspect(args.connection_file or connection_default(),args.check_listener)
    print(json.dumps(result,indent=2))
