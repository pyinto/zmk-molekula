#!/usr/bin/env python3
"""Give keymap-drawer glyph references explicit, portable SVG viewboxes."""

from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def normalize_glyphs(source: str) -> str:
    def normalize_defs(match):
        # Parse only defs: preserve the surrounding CSS, geometry, and formatting.
        container = ET.fromstring(
            f'<svg xmlns="{SVG}" xmlns:xlink="http://www.w3.org/1999/xlink">'
            + match.group() + '</svg>'
        )
        defs = container[0]
        changed = False
        for wrapper in defs:
            children = list(wrapper)
            if (wrapper.tag != f'{{{SVG}}}svg' or not wrapper.get('id')
                    or wrapper.get('viewBox') or len(children) != 1):
                continue
            inner = children[0]
            if inner.tag != f'{{{SVG}}}svg' or not inner.get('viewBox'):
                continue
            wrapper.tag = f'{{{SVG}}}symbol'
            wrapper.set('viewBox', inner.attrib.pop('viewBox'))
            if 'preserveAspectRatio' in inner.attrib:
                wrapper.set('preserveAspectRatio', inner.attrib.pop('preserveAspectRatio'))
            # Keep the original inner ID and styling, but remove its viewport.
            inner.tag = f'{{{SVG}}}g'
            changed = True
        return ET.tostring(defs, encoding='unicode') if changed else match.group()

    return re.sub(r'<defs\b[^>]*>.*?</defs>', normalize_defs, source, flags=re.S)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('molekula.svg')
    source = path.read_text()
    normalized = normalize_glyphs(source)
    if normalized != source:
        path.write_text(normalized)
    print(f'Normalized glyph viewboxes in {path}')


if __name__ == '__main__':
    main()
