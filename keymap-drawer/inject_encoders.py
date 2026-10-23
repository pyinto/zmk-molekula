#!/usr/bin/env python3
"""
Post-processes molekula.yaml:
1. Injects rotary encoder bindings for each layer.
2. Ensures activating keys for each layer are marked as 'held' (red highlight)
   while preserving the key legends from the base layer.
"""

import sys
from pathlib import Path
import yaml

HELD_KEYS_BY_LAYER = {
    "L_SYM": [34],
    "L_NUM": [31],
    "L_ADJ": [31, 34],
    "L_CYR": [35],
    "L_SYS": [31, 35],
}


def get_encoder_bindings(layer_name: str) -> tuple[dict, dict]:
    """Return (left_knob, right_knob) bindings for a given layer."""
    if "SYM" in layer_name:
        # SYM: Desk light (Color temp on left, Brightness on right)
        knob_l = {"s": "F16", "t": "$$mdi:thermometer$$", "h": "F17"}
        knob_r = {"s": "F15", "t": "$$mdi:desk-lamp$$", "h": "F14"}
    elif "NUM" in layer_name:
        # NUM: Office room light (Scenes on left, Room brightness on right)
        knob_l = {"s": "F13", "t": "$$mdi:palette$$", "h": "F18"}
        knob_r = {"s": "F19", "t": "$$mdi:ceiling-light$$", "h": "F20"}
    else:
        # BASE, ADJ, CYR, SYS: Brightness on left, Volume on right
        knob_l = {"t": "$$mdi:brightness-6$$", "s": "+", "h": "-"}
        knob_r = {"t": "$$mdi:volume-high$$", "s": "+", "h": "-"}
    return knob_l, knob_r


def main():
    yaml_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("keymap-drawer/molekula.yaml")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    layers = data.get("layers", {})
    base_keys = layers.get("L_BASE", [])

    for layer_name, keys in layers.items():
        # Inject encoders
        knob_l, knob_r = get_encoder_bindings(layer_name)
        if len(keys) == 36:
            keys.append(knob_l)
            keys.append(knob_r)
        elif len(keys) >= 38:
            keys[36] = knob_l
            keys[37] = knob_r

        # Mark activating keys as held for this layer while preserving legends from base layer
        if layer_name in HELD_KEYS_BY_LAYER:
            for idx in HELD_KEYS_BY_LAYER[layer_name]:
                if idx < len(keys):
                    base_key = base_keys[idx] if idx < len(base_keys) else None
                    if isinstance(base_key, dict):
                        held_key = dict(base_key)
                        held_key["type"] = "held"
                        keys[idx] = held_key
                    elif isinstance(base_key, str):
                        keys[idx] = {"t": base_key, "type": "held"}
                    else:
                        keys[idx] = {"type": "held"}

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True, width=160)

    print(f"Injected encoder bindings and held keys into {yaml_path}")


if __name__ == "__main__":
    main()
