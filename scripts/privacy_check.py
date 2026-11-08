"""Fail closed on common publication hazards; print rules/paths, never values."""
from pathlib import Path
import argparse,json,re,sys

ROOT=Path(__file__).resolve().parents[1]
RULES={
    'personal-home-path':re.compile(r'(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s"\']+|/(?:Users|home)/[^\s/"\']+)',re.I),
    'mac-address':re.compile(r'(?<![\w:])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![\w:])',re.I),
    'uuid':re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',re.I),
    'private-key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'credential-url':re.compile(r'https?://[^\s/"\']+:[^\s/@"\']+@',re.I),
    'provider-token':re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b'),
}
IPV4=re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])')
ALLOWED_EXTENSIONS={'.md','.json','.mjs','.py','.sh','.ps1','.h','.cpp','.ino','.properties','.csv','.yml','.yaml','.toml','.txt'}
SPECIAL={'LICENSE','.gitignore','.gitattributes'}
ASCII_FIXTURES={'examples/comparison-sample.stl'}

def scan(root=ROOT):
    findings=[];count=0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(part in {'.git','__pycache__','node_modules','build'} for part in path.relative_to(root).parts):continue
        relative=path.relative_to(root).as_posix()
        if path.suffix not in ALLOWED_EXTENSIONS and path.name not in SPECIAL and relative not in ASCII_FIXTURES:
            findings.append({'file':relative,'rule':'unreviewed-file-type'});continue
        if path.name in {'connection.json','cura-mcp-bridge.json','.env'}:
            findings.append({'file':relative,'rule':'private-runtime-file'});continue
        try:text=path.read_text(encoding='utf-8')
        except UnicodeError:
            findings.append({'file':relative,'rule':'binary-file'});continue
        count+=1
        if relative in ASCII_FIXTURES and not re.fullmatch(
                r'solid comparison_sample\n(?:  facet normal [-\d ]+\n    outer loop\n'
                r'(?:      vertex [-\d ]+\n){3}    endloop\n  endfacet\n){12}'
                r'endsolid comparison_sample\n',text):
            findings.append({'file':relative,'rule':'unexpected-stl-fixture-content'})
        # The checker necessarily contains its own regex and deliberately bad URL test.
        if relative=='scripts/privacy_check.py':continue
        for name,pattern in RULES.items():
            if name=='credential-url' and relative=='tests/printer-config.test.mjs':continue
            if pattern.search(text):findings.append({'file':relative,'rule':name})
        for match in IPV4.finditer(text):
            if match.group()=='127.0.0.1':continue
            prefix=text[text.rfind('\n',0,match.start())+1:match.start()]
            # A labeled, documented firmware version is not a network destination.
            firmware_version=(match.group()=='9.0.3.0' and re.search(r'\bfirmware\b',prefix,re.I)
                              and not re.search(r'https?://[^\s]*$',prefix,re.I))
            if not firmware_version:findings.append({'file':relative,'rule':'non-loopback-ipv4'});break
    return {'files_checked':count,'findings':findings,'passed':not findings}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();result=scan(args.root)
    print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
