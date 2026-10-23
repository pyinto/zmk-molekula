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

# Clean local build outputs
clean:
    rm -rf "{{build_dir}}"

# Clean local build outputs and west workspace
clean-all: clean
    rm -rf "{{ws_dir}}"

