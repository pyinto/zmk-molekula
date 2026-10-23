# zmk-molekula

[Molekula2](https://github.com/zzeneg/molekula) ZMK firmware and keymap, configured for TWS with a **right central** and left peripheral. Supports ZMK Studio.

[![Current Molekula TWS keymap](./keymap-drawer/molekula.svg)](./keymap-drawer/molekula.svg)

## Setup

Requires Docker (OrbStack or Docker Desktop), [just](https://github.com/casey/just), [uv](https://docs.astral.sh/uv/), and Python 3. USB detection and flashing use macOS tools.

```bash
cp .env.example .env
just setup
```

Keep `HOST_SIDE="r"` for the current firmware. See `.env.example` for settings and `just --list` for all commands.

## Build and flash

Register each half once: connect **only that half**, double-tap reset to mount its UF2 bootloader, then run the matching command:

```bash
just register right
just register left
```

Registration saves each board's USB serial in the gitignored `.env`.

```bash
just reflash --rebuild   # build both halves, update SVG, then flash right followed by left
just reflash             # flash existing builds
```

Follow the prompts to connect each half and double-tap reset. Failed attempts retry until success or Ctrl+C.

For separate build and flash steps:

```bash
just build-all           # build both halves, then update SVG
just flash               # automatically select the mounted registered half
```

If both halves are mounted, use `just flash right` or `just flash left`. Flashing uses existing files in `build/`; rebuild after keymap or configuration changes. Build logs and firmware copies are archived in `build-results/`.

Settings reset is separate: run `just build-reset`, then `just flash-reset` with only the intended registered half in bootloader mode.

## Keymap drawing

Both build commands above regenerate the SVG after both firmware builds succeed. To render it separately:

```bash
just draw
```

The drawing workflow also updates the SVG when keymap or drawing inputs change. See the [justfile](./justfile) for individual builds, backups, device listing, and other commands.
