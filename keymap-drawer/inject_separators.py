#!/usr/bin/env python3
"""
Post-processes the rendered keymap SVG to inject line separators between layers.
"""

import re
import sys
from pathlib import Path


def inject_layer_separators(svg_content: str) -> str:
    """Inject a horizontal separator line at the top of each layer group after L_BASE."""
    # Pattern matching layer groups: <g transform="translate(20, Y)" class="layer-NAME">
    pattern = re.compile(r'(<g transform="translate\(20,\s*\d+\)" class="layer-([^"]+)">)')

    def replacer(match):
        full_tag = match.group(1)
        layer_name = match.group(2)
        # Skip the base layer (L_BASE) - separators only go BETWEEN layers
        if "L_BASE" in layer_name:
            return full_tag

        separator = '\n<line x1="0" y1="15" x2="1200" y2="15" class="layer-separator"/>'
        # Prevent duplicate injection
        return full_tag + separator

    # Remove existing separators if any (idempotency)
    cleaned_svg = re.sub(r'\n<line x1="0" y1="15" x2="1200" y2="15" class="layer-separator"/>', '', svg_content)
    return pattern.sub(replacer, cleaned_svg)


def main():
    svg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("keymap-drawer/molekula.svg")
    with open(svg_path, "r", encoding="utf-8") as f:
        content = f.read()

    updated = inject_layer_separators(content)

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(updated)

    print(f"Injected layer separators into {svg_path}")


if __name__ == "__main__":
    main()
