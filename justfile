set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load
set dotenv-required

# Configuration loaded from .env
image         := env_var("ZMK_IMAGE")
board         := env_var("ZMK_BOARD")
uf2_volumes   := env_var("UF2_VOLUMES")
flash_timeout := env_var("FLASH_TIMEOUT")

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
    {{docker_ws_run}} bash -c 'west zephyr-export >/dev/null && \
      west build -p auto -s zmk/app -d /repo/build/{{artifact}} -b {{board}} {{west_args}} -- \
        -DZMK_CONFIG=/repo/config -DZMK_EXTRA_MODULES=/repo -DSHIELD="{{shield}}" {{cmake_args}}'

# Build right half (central with ZMK Studio RPC)
build-right:
    just build molekula_tws_right molekula_tws_right "-S studio-rpc-usb-uart" "-DCONFIG_ZMK_STUDIO=y"

# Build left half (peripheral)
build-left:
    just build molekula_tws_left molekula_tws_left "-S studio-rpc-usb-uart" "-DCONFIG_ZMK_STUDIO=y"

# Build settings reset firmware
build-reset:
    just build settings_reset settings_reset

# Build all firmware targets and archive outputs
build-all:
    #!/usr/bin/env bash
    set -euo pipefail
    out="{{results_dir}}/$(date +%Y%m%d-%H%M%S)__$(git -C "{{repo_dir}}" rev-parse --short=12 HEAD)"
    mkdir -p "$out"
    {
        just build-right
        just build-left
        just build-reset
    } 2>&1 | tee "$out/build.log"

    cp "{{build_dir}}/molekula_tws_right/zephyr/zmk.uf2" "$out/molekula_tws_right.uf2"
    cp "{{build_dir}}/molekula_tws_left/zephyr/zmk.uf2" "$out/molekula_tws_left.uf2"
    cp "{{build_dir}}/settings_reset/zephyr/zmk.uf2" "$out/settings_reset.uf2"

    echo "Build complete. UF2 binaries saved in: $out"

# Flash firmware to a connected board half (waits for UF2 bootloader drive)
flash side:
    #!/usr/bin/env bash
    set -euo pipefail

    case "{{side}}" in
      right|molekula_tws_right) fw="{{build_dir}}/molekula_tws_right/zephyr/zmk.uf2" ;;
      left|molekula_tws_left)   fw="{{build_dir}}/molekula_tws_left/zephyr/zmk.uf2" ;;
      reset|settings_reset)     fw="{{build_dir}}/settings_reset/zephyr/zmk.uf2" ;;
      *)
        echo "Usage: just flash right | left | reset" >&2
        exit 2
        ;;
    esac

    test -f "$fw" || {
        echo "Error: Firmware file not found: $fw" >&2
        echo "Run 'just build-{{side}}' first." >&2
        exit 1
    }

    echo "Waiting up to {{flash_timeout}}s for UF2 volume. Please double-tap the reset button on the board..."
    detected_vol=""
    for _ in $(seq {{flash_timeout}}); do
        for cand in {{uf2_volumes}}; do
            if [ -d "$cand" ]; then
                detected_vol="$cand"
                break 2
            fi
        done
        sleep 1
    done

    if [ -z "$detected_vol" ]; then
        echo "Error: Timed out waiting for UF2 volume (searched: {{uf2_volumes}})" >&2
        exit 1
    fi

    echo "Found volume: $detected_vol. Copying firmware..."
    cp -X "$fw" "$detected_vol/" || true
    echo "Flashed successfully to $detected_vol"

flash-right:
    just flash right

flash-left:
    just flash left

flash-reset:
    just flash reset

# Backup currently installed firmware from UF2 bootloader drive
backup side:
    #!/usr/bin/env bash
    set -euo pipefail

    mkdir -p "{{backup_dir}}"
    echo "Waiting up to {{flash_timeout}}s for UF2 volume. Please double-tap the reset button on the board..."
    detected_vol=""
    for _ in $(seq {{flash_timeout}}); do
        for cand in {{uf2_volumes}}; do
            if [ -d "$cand" ]; then
                detected_vol="$cand"
                break 2
            fi
        done
        sleep 1
    done

    if [ -z "$detected_vol" ]; then
        echo "Error: Timed out waiting for UF2 volume (searched: {{uf2_volumes}})" >&2
        exit 1
    fi

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

# -----------------------------------------------------------------------------
# Keymap Visualization
# -----------------------------------------------------------------------------
kd_dir           := repo_dir / "keymap-drawer"
kd_config        := kd_dir / "config.yaml"
kd_css           := kd_dir / "config.css"
kd_merged_config := kd_dir / "config-merged.yaml"
kd_base          := kd_dir / "molekula_base.yaml"
kd_keymap        := repo_dir / "boards" / "shields" / "molekula_tws" / "molekula_tws.keymap"
kd_layout_json   := kd_dir / "molekula.json"
kd_yaml          := kd_dir / "molekula.yaml"
kd_svg           := kd_dir / "molekula.svg"

# Prepare merged config with embedded CSS styles
draw-config:
    #!/usr/bin/env bash
    set -euo pipefail
    temp_css=$(mktemp)
    sed 's/^/    /' "{{kd_css}}" > "$temp_css"
    awk '/svg_extra_style: \|/ {print; while(getline < "'"$temp_css"'") print; next} 1' "{{kd_config}}" > "{{kd_merged_config}}"
    rm -f "$temp_css"

# Parse keymap to YAML
parse-keymap: draw-config
    uvx --from keymap-drawer keymap -c "{{kd_merged_config}}" parse -b "{{kd_base}}" -z "{{kd_keymap}}" -o "{{kd_yaml}}"

# Draw keymap SVG
draw: parse-keymap
    uvx --from keymap-drawer keymap -c "{{kd_merged_config}}" draw -j "{{kd_layout_json}}" "{{kd_yaml}}" -o "{{kd_svg}}"
    rm -f "{{kd_merged_config}}"
    @echo "Generated {{kd_svg}}"

# Open rendered SVG in default viewer / browser
show-keymap: draw
    firefox "{{kd_svg}}"
