"""Plan a user-local Cura plugin install; --apply copies only original plugin files."""
from pathlib import Path
import argparse,csv,io,json,os,shutil,subprocess,sys,tempfile,time

SOURCE=Path(__file__).resolve().parents[1]/'cura_plugin/CuraMcpBridge'
PLUGIN_FILES=('__init__.py','plugin.json','CuraMcpBridge.py','project_io.py','scene_ops.py','post_processing.py','configuration_ops.py','comparison.py')

def default_config_dir():
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/cura'/os.environ.get('CURA_MCP_CURA_VERSION','5.14')
    if sys.platform=='win32':
        return Path(os.environ.get('APPDATA',str(Path.home()/'AppData/Roaming')))/'cura'/os.environ.get('CURA_MCP_CURA_VERSION','5.14')
    raise RuntimeError('Specify --config-dir for another platform; only Windows/macOS desktop defaults are defined.')

def cura_running():
    command=['tasklist','/FO','CSV','/NH'] if sys.platform=='win32' else ['ps','-axo','comm=']
    result=subprocess.run(command,capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError('Cannot check running applications; refusing installation.')
    names=[row[0] for row in csv.reader(io.StringIO(result.stdout)) if row] if sys.platform=='win32' else result.stdout.splitlines()
    return any(Path(name.strip()).name.casefold() in {'cura','cura.exe','ultimaker-cura','ultimaker-cura.exe'} for name in names)

def install(config_dir,apply=False):
    config_dir=Path(config_dir).expanduser().resolve()
    target=config_dir/'plugins/CuraMcpBridge'
    result={'mode':'plan','plugin_target':str(target),'connection_file_changed':False,'runtime_or_credentials_changed':False}
    for name in PLUGIN_FILES:
        if not (SOURCE/name).is_file():raise RuntimeError('Plugin source is incomplete.')
    if not apply:return result
    if cura_running():raise RuntimeError('Save your project and quit Cura before installing.')
    target.parent.mkdir(parents=True,exist_ok=True)
    backup=None
    # Stage the complete copy before moving an existing plugin; back up outside plugins/.
    with tempfile.TemporaryDirectory(prefix='.cura-bridge-stage-',dir=target.parent) as temporary:
        staged=Path(temporary)/'CuraMcpBridge';staged.mkdir()
        for name in PLUGIN_FILES:shutil.copy2(SOURCE/name,staged/name)
        if target.exists():
            backup=config_dir/'bridge-plugin-backups'/('CuraMcpBridge-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()))
            backup.parent.mkdir(parents=True,exist_ok=True)
            target.rename(backup)
        try:staged.rename(target)
        except OSError:
            if backup is not None and not target.exists():backup.rename(target)
            raise
    result.update(mode='installed',backup=str(backup) if backup else None,next_step='Relaunch Cura once; start one MCP runtime from this checkout.')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir',type=Path)
    parser.add_argument('--apply',action='store_true',help='Install after verifying Cura is closed; default only shows the plan.')
    args=parser.parse_args()
    try:print(json.dumps(install(args.config_dir or default_config_dir(),args.apply),indent=2))
    except (OSError,RuntimeError,subprocess.SubprocessError):
        print('Installation refused or failed. Verify Cura is closed, source files and destination permissions; existing files are backed up before replacement.',file=sys.stderr)
        sys.exit(1)
