import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / 'scripts/prd_notes.py'
SCAN = ROOT / 'scripts/prd_scan.py'

class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.html = self.root / 'source.html'
        self.html.write_text('<html><body><button data-prd-anchor="action:save">保存</button><input id="amount"></body></html>', encoding='utf-8')
        self.scan = self.root / 'scan.json'
        self.notes = self.root / 'notes.json'
        self.run_cli(SCAN, self.html, '-o', self.scan)
        self.run_cli(NOTES, 'init', '--scan', self.scan, '-o', self.notes)

    def run_cli(self, *args, code=0):
        r = subprocess.run([sys.executable, "-X", "utf8", *map(str, args)], capture_output=True, encoding='utf-8')
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r

    def patch(self, data):
        p = self.root / 'patch.json'
        p.write_text(json.dumps(data), encoding='utf-8')
        self.run_cli(NOTES, 'merge', '--notes', self.notes, '--patch', p, '--overwrite')

    def test_array_patch_and_custom_selector_survive(self):
        self.patch([{'anchor':'custom:one', 'css':'#amount', 'func':'金额'}])
        self.patch({'notes':[{'anchor':'custom:one','css':'input#amount'}]})
        data = json.loads(self.notes.read_text(encoding='utf-8'))
        self.assertEqual(next(n for n in data['notes'] if n['anchor']=='custom:one')['css'],'input#amount')

    def test_check_fails_missing_and_ack_clears_changed(self):
        self.run_cli(NOTES,'check','--notes',self.notes,'--scan',self.scan,code=1)
        self.patch([{'anchor':'action:save','req':'FR-01','func':'保存','rules':['按权限保存'], 'edges':['失败不迁移'],'status':'confirmed'}])
        self.run_cli(NOTES,'check','--notes',self.notes,'--scan',self.scan)
        self.html.write_text(self.html.read_text(encoding='utf-8').replace('data-prd-anchor=', 'title="changed" data-prd-anchor='), encoding='utf-8')
        self.run_cli(SCAN,self.html,'-o',self.scan)
        self.run_cli(NOTES,'check','--notes',self.notes,'--scan',self.scan,code=1)
        self.run_cli(NOTES,'ack','--notes',self.notes,'--scan',self.scan,'--anchor','action:save')
        self.run_cli(NOTES,'check','--notes',self.notes,'--scan',self.scan)

    def test_injection_escapes_script_and_is_idempotent(self):
        self.patch([{'anchor':'custom:one','css':'#amount','func':'</script><script>alert(1)</script>'}])
        original = self.html.read_bytes()
        out, out2 = self.root/'copy.html', self.root/'copy2.html'
        self.run_cli(NOTES,'inject',self.html,'--notes',self.notes,'-o',out)
        self.run_cli(NOTES,'inject',out,'--notes',self.notes,'-o',out2)
        generated = out2.read_text(encoding='utf-8')
        self.assertEqual(generated.count('id="prd-annotator-js"'),1)
        self.assertIn('\\u003c/script>',generated)
        self.assertIn('"css": "#amount"',generated)
        self.assertEqual(original,self.html.read_bytes())
        self.run_cli(NOTES,'inject',self.html,'--notes',self.notes,'-o',self.html,code=1)

    def test_deprecated_and_control_ids(self):
        scan = json.loads(self.scan.read_text(encoding='utf-8'))
        self.assertIn('control:amount',[e['anchor'] for e in scan['elements']])
        self.patch({'notes':[{'anchor':'custom:gone'}], 'deleted':['custom:gone']})
        r = self.run_cli(NOTES,'check','--notes',self.notes,'--scan',self.scan,code=1)
        self.assertNotIn('custom:gone',r.stdout)

    def test_duplicate_explicit_anchor_rejected(self):
        self.html.write_text('<button data-prd-anchor="action:x"></button><button data-prd-anchor="action:x"></button>',encoding='utf-8')
        self.run_cli(SCAN,self.html,'-o',self.scan,code=1)

if __name__ == '__main__':
    unittest.main()
