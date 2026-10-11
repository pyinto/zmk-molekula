#!/usr/bin/env python3
"""
Appends rotary encoder bindings to molekula.yaml for each layer
to match the 38-position physical layout in molekula.json.
"""

import sys
import yaml
from pathlib import Path

def get_encoder_bindings(layer_name: str) -> tuple[dict, dict]:
    """Return (left_knob, right_knob) bindings for a given layer."""
    if "SYM" in layer_name or "NUM" in layer_name:
        knob_l = {"t": "F14", "s": "F15"}
        knob_r = {"t": "F15", "s": "F14"}
    else:
        # BASE, CYR, ADJ, SYS: Brightness on left, Volume on right
        knob_l = {"t": "$$mdi:brightness-6$$", "s": "+", "h": "-"}
        knob_r = {"t": "$$mdi:volume-high$$", "s": "+", "h": "-"}
    return knob_l, knob_r

def main():
    yaml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("keymap-drawer/molekula.yaml")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    layers = data.get("layers", {})
    for layer_name, keys in layers.items():
        knob_l, knob_r = get_encoder_bindings(layer_name)
        if len(keys) == 36:
            keys.append(knob_l)
            keys.append(knob_r)
        elif len(keys) == 38:
            keys[36] = knob_l
            keys[37] = knob_r

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True, width=160)

    print(f"Injected encoder bindings into {yaml_path}")

if __name__ == "__main__":
    main()
