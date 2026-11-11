import importlib.util,tempfile,unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('privacy_check',Path(__file__).resolve().parents[1]/'scripts/privacy_check.py')
privacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(privacy)

class PrivacyVersionTest(unittest.TestCase):
    def check_text(self,text):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'example.md').write_text(text,encoding='utf-8')
            return privacy.scan(root)
    def test_labeled_firmware_version_is_not_an_address(self):
        version='.'.join(('9','0','3','0'))
        self.assertTrue(self.check_text('| Printer firmware | **'+version+'** |')['passed'])
    def test_version_used_as_a_network_url_is_rejected(self):
        version='.'.join(('9','0','3','0'))
        self.assertFalse(self.check_text('Firmware URL: http://'+version)['passed'])
    def test_other_network_address_is_rejected_even_beside_firmware_label(self):
        address='.'.join(map(str,(192,0,2,1)))
        self.assertFalse(self.check_text('Printer firmware endpoint: '+address)['passed'])
    def test_runtime_printer_configuration_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'cura-mcp-printer.json').write_text('{"printer_origin":"http://printer.invalid"}')
            result=privacy.scan(root)
            self.assertFalse(result['passed'])
            self.assertEqual(result['findings'][0]['rule'],'private-runtime-file')

if __name__=='__main__':unittest.main()
