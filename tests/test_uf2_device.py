import importlib.util
import contextlib
import io
import os
import sys
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

spec = importlib.util.spec_from_file_location(
    "uf2_device", Path(__file__).resolve().parents[1] / "scripts/uf2_device.py"
)
uf2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uf2)

RIGHT = "1234567890ABCDEF"
LEFT = "FEDCBA0987654321"


class DeviceTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"FLASH_TIMEOUT": "30", "HOST_SIDE": "r"})
        env.start()
        self.addCleanup(env.stop)

    def test_discovery_uses_disk_parent_not_hub_serial_or_mount_name(self):
        def board(serial, disk, identifier):
            return {"IOObjectClass": "IOUSBHostDevice", "IORegistryEntryID": identifier,
                    "USB Serial Number": serial, "IORegistryEntryChildren": [
                        {"BSD Name": disk}]}

        tree = [{"IOObjectClass": "IOUSBHostDevice", "IORegistryEntryID": 1,
                 "USB Serial Number": "HUB", "IORegistryEntryChildren": [
                     board(RIGHT, "disk8", 2), board(LEFT, "disk9", 3)]}]

        def disk_info(command, **kwargs):
            mount = "/Volumes/XIAO-SENSE" + (" 1" if command[-1] == "disk9" else "")
            return subprocess.CompletedProcess(command, 0, plistlib.dumps({"MountPoint": mount}))

        with patch.object(uf2.subprocess, "check_output", return_value=plistlib.dumps(tree)), \
                patch.object(uf2.subprocess, "run", side_effect=disk_info), \
                patch.object(Path, "is_file", return_value=True):
            self.assertEqual(uf2.devices(), {
                "/Volumes/XIAO-SENSE": RIGHT, "/Volumes/XIAO-SENSE 1": LEFT})

    def test_selects_correct_half_with_both_mounted(self):
        mounts = {"/Volumes/XIAO-SENSE": LEFT, "/Volumes/XIAO-SENSE 1": RIGHT}
        saved = {"right": RIGHT, "left": LEFT}
        self.assertEqual(uf2.select(mounts, "right", saved), "/Volumes/XIAO-SENSE 1")
        self.assertEqual(uf2.select(mounts, "left", saved), "/Volumes/XIAO-SENSE")

    def test_wrong_or_unknown_board_is_never_selected(self):
        with self.assertRaisesRegex(ValueError, "requested: right"):
            uf2.select({"/wrong": LEFT, "/unknown": "UNKNOWN"},
                       "right", {"right": RIGHT, "left": LEFT})

    def test_auto_selects_either_half_and_preserves_mount_spaces(self):
        for side, serial in (("right", RIGHT), ("left", LEFT)):
            with self.subTest(side=side), \
                    patch.object(uf2.sys, "argv", ["uf2_device.py", "find", "auto", "--with-side"]), \
                    patch.object(uf2.sys, "platform", "darwin"), \
                    patch.object(uf2, "configured", return_value={"right": RIGHT, "left": LEFT}), \
                    patch.object(uf2, "devices", return_value={"/Volumes/XIAO-SENSE 1": serial}), \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()):
                uf2.main()
                self.assertEqual(output.getvalue(), f"{side}\t/Volumes/XIAO-SENSE 1\n")

    def test_auto_refuses_both_halves(self):
        with self.assertRaises(ValueError):
            uf2.select({"/right": RIGHT, "/left": LEFT}, "auto",
                       {"right": RIGHT, "left": LEFT})

    def test_no_mounted_board_still_waits(self):
        self.assertIsNone(uf2.select({}, "right", {"right": RIGHT, "left": LEFT}))

    def test_find_and_register_share_environment_timeout(self):
        for action in ("find", "register"):
            with self.subTest(action=action), \
                    patch.dict(os.environ, {"FLASH_TIMEOUT": "7"}), \
                    patch.object(uf2.sys, "argv", ["uf2_device.py", action, "right"]), \
                    patch.object(uf2.sys, "platform", "darwin"), \
                    patch.object(uf2, "configured", return_value={"right": RIGHT, "left": LEFT}), \
                    patch.object(uf2, "devices", return_value={}), \
                    patch.object(uf2.time, "monotonic", side_effect=[0, 8]), \
                    contextlib.redirect_stderr(io.StringIO()) as log:
                with self.assertRaisesRegex(ValueError, "Timed out"):
                    uf2.main()
                self.assertIn("7s", log.getvalue())
                self.assertIn("RIGHT — CENTRAL", log.getvalue())

    def test_wrong_half_errors_without_sleeping_or_polling_again(self):
        with patch.object(uf2.sys, "argv", ["uf2_device.py", "find", "right"]), \
                patch.object(uf2.sys, "platform", "darwin"), \
                patch.object(uf2, "configured", return_value={"right": RIGHT, "left": LEFT}), \
                patch.object(uf2, "devices", return_value={"/left": LEFT}) as discovery, \
                patch.object(uf2.time, "sleep") as sleep, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Mounted UF2 board.*left; requested: right"):
                uf2.main()
            discovery.assert_called_once()
            sleep.assert_not_called()

    def test_reset_refuses_two_registered_boards(self):
        with self.assertRaises(ValueError):
            uf2.select({"/right": RIGHT, "/left": LEFT}, "reset",
                       {"right": RIGHT, "left": LEFT})

    def test_reset_ignores_unregistered_boards(self):
        self.assertEqual(uf2.select({"/right": RIGHT, "/unknown": "UNKNOWN"},
                                   "reset", {"right": RIGHT, "left": LEFT}), "/right")

    def test_registration_preserves_environment_and_prevents_swapping(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(uf2, "REPO", Path(directory)):
            env = Path(directory) / ".env"
            env.write_text('ZMK_BOARD="seeeduino_xiao_ble"\nUF2_RIGHT_SERIAL=""\n')
            uf2.save_serial("right", RIGHT, {"right": "", "left": ""})
            self.assertEqual(env.read_text(),
                             f'ZMK_BOARD="seeeduino_xiao_ble"\nUF2_RIGHT_SERIAL="{RIGHT}"\n')
            with self.assertRaises(ValueError):
                uf2.save_serial("left", RIGHT, {"right": RIGHT, "left": ""})
            with self.assertRaises(ValueError):
                uf2.save_serial("right", LEFT, {"right": RIGHT, "left": ""})


if __name__ == "__main__":
    unittest.main()
