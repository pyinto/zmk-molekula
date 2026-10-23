set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load
set dotenv-required

# Configuration loaded from .env
image         := env_var("ZMK_IMAGE")
board         := env_var("ZMK_BOARD")

repo_dir    := justfile_directory()
ws_dir      := repo_dir / ".zmk"
build_dir   := repo_dir / "build"
results_dir := repo_dir / "build-results"
backup_dir  := repo_dir / "backups"

# Docker run inside the isolated .zmk workspace
docker_ws_run := "docker run --rm -t -v '" + ws_dir + "':/workspace -v '" + repo_dir + "':/repo -w /workspace -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' " + image

default:
    @just --list --unsorted

# Pull the ZMK build container image
pull:
    docker pull {{image}}

# Initialize the isolated west workspace in .zmk
init:
    mkdir -p "{{ws_dir}}/.west" "{{ws_dir}}/config"
    cp "{{repo_dir}}/config/west.yml" "{{ws_dir}}/config/west.yml"
    printf '[manifest]\npath = config\nfile = west.yml\n' > "{{ws_dir}}/.west/config"

# Fetch or update ZMK and Zephyr modules inside .zmk
update:
    cp "{{repo_dir}}/config/west.yml" "{{ws_dir}}/config/west.yml"
    find "{{ws_dir}}" -name "index.lock" -delete 2>/dev/null || true
    {{docker_ws_run}} west update --fetch-opt=--filter=tree:0

# Full setup: pull container, initialize and update west modules
setup: pull init update

# Run interactive shell inside workspace container for debugging
shell:
    docker run --rm -it -v '{{ws_dir}}':/workspace -v '{{repo_dir}}':/repo -w /workspace {{image}} bash

# Generic build recipe
build artifact shield west_args="" cmake_args="":
    rm -f "{{build_dir}}/{{artifact}}/zephyr/zmk.uf2"
    {{docker_ws_run}} bash -c 'west zephyr-export >/dev/null && \
      west build -p always -s zmk/app -d /repo/build/{{artifact}} -b {{board}} {{west_args}} -- \
        -DZMK_CONFIG=/repo/config -DZMK_EXTRA_MODULES=/repo -DSHIELD="{{shield}}" {{cmake_args}}'

# Build right half (central with ZMK Studio RPC)
build-right:
    just build molekula_tws_right molekula_tws_right "-S studio-rpc-usb-uart" "-DCONFIG_ZMK_STUDIO=y"

# Build left half (peripheral)
build-left:
    just build molekula_tws_left molekula_tws_left "" "-DCONFIG_ZMK_STUDIO=y"

# Build settings reset firmware
build-reset:
    just build settings_reset settings_reset

# Build both keyboard halves and archive outputs
build-all:
    #!/usr/bin/env bash
    set -euo pipefail
    # Invalidate both halves first, including a half a failed build never reaches.
    rm -f "{{build_dir}}/molekula_tws_right/zephyr/zmk.uf2" \
          "{{build_dir}}/molekula_tws_left/zephyr/zmk.uf2"
    out="{{results_dir}}/$(date +%Y%m%d-%H%M%S)__$(git -C "{{repo_dir}}" rev-parse --short=12 HEAD)"
    mkdir -p "$out"
    {
        just build-right
        just build-left
    } 2>&1 | tee "$out/build.log"

    cp "{{build_dir}}/molekula_tws_right/zephyr/zmk.uf2" "$out/molekula_tws_right.uf2"
    cp "{{build_dir}}/molekula_tws_left/zephyr/zmk.uf2" "$out/molekula_tws_left.uf2"

    echo "Build complete. UF2 binaries saved in: $out"

# Flash existing firmware for the mounted registered half (or specify a side)
flash side="auto":
    #!/usr/bin/env bash
    set -euo pipefail

    selection=$(python3 "{{repo_dir}}/scripts/uf2_device.py" find "{{side}}" --with-side)
    IFS=$'\t' read -r selected_side detected_vol <<< "$selection"

    case "$selected_side" in
      right) fw="{{build_dir}}/molekula_tws_right/zephyr/zmk.uf2" ;;
      left)  fw="{{build_dir}}/molekula_tws_left/zephyr/zmk.uf2" ;;
      reset) fw="{{build_dir}}/settings_reset/zephyr/zmk.uf2" ;;
      *)
        echo "Usage: just flash [right | left | reset]" >&2
        exit 2
        ;;
    esac

    test -f "$fw" || {
        echo "Error: Firmware file not found: $fw" >&2
        echo "Run 'just build-$selected_side' first." >&2
        exit 1
    }

    label=$(python3 "{{repo_dir}}/scripts/uf2_device.py" label "$selected_side")
    echo "=== $label — FLASHING === $detected_vol | $fw"
    cp -X "$fw" "$detected_vol/"
    echo "=== $label — TRANSFER SUCCEEDED === $detected_vol"

flash-right:
    just flash right

flash-left:
    just flash left

flash-reset:
    just flash reset

# Flash both halves, central first; optionally rebuild with --rebuild
reflash *args:
    @python3 "{{repo_dir}}/scripts/reflash.py" {{args}}

# Register one physical half in bootloader mode (saved in local .env)
register side:
    python3 "{{repo_dir}}/scripts/uf2_device.py" register "{{side}}"

# List connected UF2 bootloader drives and their USB serial numbers
list-devices:
    python3 "{{repo_dir}}/scripts/uf2_device.py" list

# Backup currently installed firmware from UF2 bootloader drive
backup side:
    #!/usr/bin/env bash
    set -euo pipefail

    mkdir -p "{{backup_dir}}"
    detected_vol=$(python3 "{{repo_dir}}/scripts/uf2_device.py" find "{{side}}")

    target_file="{{backup_dir}}/$(date +%Y%m%d-%H%M%S)__{{side}}.uf2"
    if [ -f "$detected_vol/CURRENT.UF2" ]; then
        cp -X "$detected_vol/CURRENT.UF2" "$target_file"
        echo "Backed up current firmware to $target_file"
    else
        echo "Warning: No CURRENT.UF2 found on $detected_vol to back up."
    fi

# Clean local build outputs
clean:
    rm -rf "{{build_dir}}"

# Clean local build outputs and west workspace
clean-all: clean
    rm -rf "{{ws_dir}}"

