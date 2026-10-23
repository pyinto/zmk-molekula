"""Resolve macOS UF2 mounts through their parent USB device's hardware serial."""

import argparse
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time

from flash_config import load_config

REPO = Path(__file__).resolve().parents[1]
KEYS = {"right": "UF2_RIGHT_SERIAL", "left": "UF2_LEFT_SERIAL"}


def walk(node):
    yield node
    for child in node.get("IORegistryEntryChildren", []):
        yield from walk(child)


def devices():
    roots = plistlib.loads(subprocess.check_output(
        ["ioreg", "-a", "-l", "-r", "-c", "IOUSBHostDevice"]
    ))
    found = {}
    usb_devices = {
        node["IORegistryEntryID"]: node
        for tree in roots for node in walk(tree)
        if node.get("IOObjectClass") == "IOUSBHostDevice"
    }
    for root in usb_devices.values():
        # A USB hub's descendants can include other USB devices. Only collect
        # disks below this device, stopping at nested devices so serials cannot
        # accidentally be inherited from a hub.
        serial = root.get("USB Serial Number", root.get("kUSBSerialNumberString", ""))
        if not serial:
            continue

        def media(node):
            yield node
            for child in node.get("IORegistryEntryChildren", []):
                if child.get("IOObjectClass") != "IOUSBHostDevice":
                    yield from media(child)

        for node in media(root):
            disk = node.get("BSD Name")
            if not disk or not re.fullmatch(r"disk\d+(?:s\d+)*", disk):
                continue
            result = subprocess.run(["diskutil", "info", "-plist", disk], capture_output=True)
            if result.returncode:
                continue  # A bootloader can disappear while enumerating.
            mount = plistlib.loads(result.stdout).get("MountPoint")
            if mount and (Path(mount) / "INFO_UF2.TXT").is_file():
                found[mount] = str(serial).strip().upper()
    return found


def configured():
    return {side: os.environ.get(key, "").strip().upper() for side, key in KEYS.items()}


def select(found, side, saved):
    if side in ("reset", "auto"):
        matches = [mount for mount, serial in found.items() if serial in saved.values()]
    else:
        matches = [mount for mount, serial in found.items() if serial == saved[side]]
    if len(matches) > 1:
        raise ValueError("Multiple matching boards are in bootloader mode; leave only the intended board in bootloader mode.")
    if not matches and found:
        mounted = ", ".join(sorted({
            next((name for name, value in saved.items() if value == serial), "unregistered")
            for serial in found.values()
        }))
        raise ValueError(f"Mounted UF2 board(s): {mounted}; requested: {side}. No firmware was copied.")
    return matches[0] if matches else None


def save_serial(side, serial, saved):
    other = "left" if side == "right" else "right"
    if serial == saved[other]:
        raise ValueError(f"This board is already registered as {other}; use the other physical half.")
    if saved[side] and saved[side] != serial:
        raise ValueError(f"{side} already has a different serial. Remove {KEYS[side]} from .env before replacing that board.")
    path = REPO / ".env"
    content = path.read_text()
    key = KEYS[side]
    line = f'{key}="{serial}"'
    pattern = rf"(?m)^(?:export\s+)?{key}\s*=.*$"
    if re.search(pattern, content):
        content = re.sub(pattern, lambda _: line, content)
    else:
        content = content.rstrip("\n") + "\n" + line + "\n"
    path.write_text(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "register", "find", "label"])
    parser.add_argument("side", nargs="?", choices=["auto", "right", "left", "reset", "molekula_tws_right", "molekula_tws_left", "settings_reset"])
    parser.add_argument("--with-side", action="store_true", help="Print the selected side and mount separated by a tab")
    args = parser.parse_args()
    config = load_config()
    if sys.platform != "darwin":
        raise ValueError("USB serial discovery currently supports macOS only.")
    side = {"molekula_tws_right": "right", "molekula_tws_left": "left", "settings_reset": "reset"}.get(args.side, args.side)
    if args.action == "label":
        if side not in ("left", "right", "reset"):
            raise ValueError("Specify left, right, or reset for a label.")
        print(config.label(side))
        return
    saved = configured()
    if saved["right"] and saved["right"] == saved["left"]:
        raise ValueError("The two halves have the same registered serial; correct .env first.")
    if args.action == "list":
        found = devices()
        for mount, serial in sorted(found.items()):
            label = next((config.label(s) for s, value in saved.items() if value == serial), "unregistered")
            print(f"{label}: {serial}  {mount}")
        if not found:
            print("No mounted UF2 bootloaders found. Double-tap a board's reset button.")
        return
    if not side or (args.action == "register" and side in ("reset", "auto")):
        raise ValueError("Specify right or left (find also accepts auto or reset).")
    if args.action == "find" and not (any(saved.values()) if side in ("reset", "auto") else saved[side]):
        raise ValueError("Register the board first with 'just register right' or 'just register left'.")
    print(f"Waiting up to {config.timeout_s}s for {config.label(side)}. Double-tap its reset button.", file=sys.stderr)
    deadline = time.monotonic() + max(0, config.timeout_s)
    while True:
        found = devices()
        if args.action == "register":
            if len(found) > 1:
                raise ValueError("Registration needs exactly one board in bootloader mode so you can identify its physical side.")
            if found:
                mount, serial = next(iter(found.items()))
                if not re.fullmatch(r"[0-9A-F]{16}", serial):
                    raise ValueError("Expected a 16-digit nRF52 bootloader serial; refusing to register this device.")
                save_serial(side, serial, saved)
                print(f"Registered {side}: {serial} ({mount}); saved to .env")
                return
        else:
            mount = select(found, side, saved)
            if mount:
                selected_side = next(name for name, value in saved.items() if value == found[mount]) if side == "auto" else side
                print(f"{selected_side}\t{mount}" if args.with_side else mount)
                return
        if time.monotonic() >= deadline:
            raise ValueError(f"Timed out waiting for the registered {side} board. No firmware was copied.")
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, plistlib.InvalidFileException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
