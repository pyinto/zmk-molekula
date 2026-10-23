import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location(
    'normalize_glyphs', Path(__file__).resolve().parents[1] / 'keymap-drawer/normalize_glyphs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NS = {'s': module.SVG}


class GlyphTests(unittest.TestCase):
    def test_preserves_references_geometry_and_style(self):
        source = '''<svg xmlns="http://www.w3.org/2000/svg"><defs>
<svg id="mdi:test"><svg id="original" viewBox="0 0 24 24" fill="red" preserveAspectRatio="xMidYMid meet"><path d="M1 2L3 4"/></svg></svg>
</defs><style>.key {fill: blue;}</style><g transform="translate(10,20)"><use href="#mdi:test" width="25" height="25"/></g></svg>'''
        result = module.normalize_glyphs(source)
        root = ET.fromstring(result)
        symbol = root.find('.//s:symbol', NS)
        self.assertEqual(symbol.get('id'), 'mdi:test')
        self.assertEqual(symbol.get('viewBox'), '0 0 24 24')
        self.assertEqual(symbol.get('preserveAspectRatio'), 'xMidYMid meet')
        inner = symbol.find('s:g', NS)
        self.assertEqual(inner.get('id'), 'original')
        self.assertEqual(inner.get('fill'), 'red')
        self.assertEqual(inner.find('s:path', NS).get('d'), 'M1 2L3 4')
        self.assertEqual(source[source.index('<style>'):], result[result.index('<style>'):])
        self.assertEqual(module.normalize_glyphs(result), result)

    def test_existing_valid_definitions_unchanged(self):
        for defs in ('<symbol id="ok" viewBox="0 0 24 24"><path d="M1 1"/></symbol>',
                     '<svg id="ok" viewBox="0 0 24 24"><path d="M1 1"/></svg>'):
            source = f'<svg xmlns="{module.SVG}"><defs>{defs}</defs></svg>'
            self.assertEqual(module.normalize_glyphs(source), source)


if __name__ == '__main__':
    unittest.main()
