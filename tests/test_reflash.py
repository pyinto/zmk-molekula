import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import flash_config as config
import reflash

SAVED = {'left': 'LEFT_SERIAL', 'right': 'RIGHT_SERIAL'}


class ConfigTests(unittest.TestCase):
    def test_config_validation(self):
        for timeout, host, valid in [('30', 'l', True), ('30', 'r', True),
                                     ('', 'r', False), ('0', 'r', False),
                                     ('-1', 'r', False), ('1.5', 'r', False),
                                     ('30', '', False), ('30', 'left', False)]:
            with self.subTest(timeout=timeout, host=host), patch.dict(
                    os.environ, {'FLASH_TIMEOUT': timeout, 'HOST_SIDE': host}, clear=True):
                if valid:
                    self.assertEqual(config.load_config(), config.FlashConfig(30, host))
                else:
                    with self.assertRaises(ValueError):
                        config.load_config()

    def test_logging_plain_and_no_color(self):
        stream = io.StringIO()
        config.Log(stream).write('RIGHT — CENTRAL — FLASHING')
        self.assertNotIn('\033', stream.getvalue())
        self.assertIn('Info', stream.getvalue())
        with patch.object(stream, 'isatty', return_value=True), patch.dict(os.environ, {'NO_COLOR': ''}):
            self.assertFalse(config.Log(stream).color)


class ReflashTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'repo with spaces'
        self.output = io.StringIO()
        self.saved_patch = patch.object(reflash.usb, 'configured', return_value=SAVED.copy())
        self.saved_patch.start()
        self.addCleanup(self.saved_patch.stop)
        self.sleeps = patch.object(reflash.time, 'sleep')
        self.sleeps.start()
        self.addCleanup(self.sleeps.stop)
        self.prepare('r')

    def prepare(self, host):
        for side in SAVED:
            directory = self.root / 'build' / f'molekula_tws_{side}' / 'zephyr'
            directory.mkdir(parents=True, exist_ok=True)
            (directory / 'zmk.uf2').write_bytes(b'UF2 test fixture')
            central = side == {'l': 'left', 'r': 'right'}[host]
            (directory / '.config').write_text(
                f'CONFIG_SHIELD_MOLEKULA_TWS_{side.upper()}=y\nCONFIG_ZMK_SPLIT=y\n' +
                ('CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y\n' if central else '# CONFIG_ZMK_SPLIT_ROLE_CENTRAL is not set\n'))

    def session(self, host='r'):
        return reflash.Reflasher(config.FlashConfig(30, host), self.root, config.Log(self.output))

    def test_both_host_orders_and_simultaneous_mounts(self):
        for host, order in [('r', ['right', 'left']), ('l', ['left', 'right'])]:
            self.prepare(host)
            session = self.session(host)
            with patch.object(reflash.usb, 'devices', return_value={
                    '/Volumes/XIAO 1': SAVED['left'], '/Volumes/XIAO': SAVED['right']}), \
                    patch.object(reflash.subprocess, 'run') as copy:
                session.run()
                actual = [Path(c.args[0][2]).parents[1].name for c in copy.call_args_list]
                self.assertEqual(actual, [f'molekula_tws_{s}' for s in order])
                self.assertTrue(session.left_is_flashed and session.right_is_flashed)
                self.assertEqual(copy.call_args_list[order.index('left')].args[0][-1], '/Volumes/XIAO 1/')

    def test_unknown_wrong_completed_and_duplicate_mounts_are_not_copied(self):
        session = self.session()
        discoveries = [
            {'/unknown': 'OTHER'}, {'/left': SAVED['left']},
            {'/a': SAVED['right'], '/b': SAVED['right']}, {'/right': SAVED['right']},
            {'/right': SAVED['right']}, {'/right': SAVED['right']}, {'/left': SAVED['left']}]
        with patch.object(reflash.usb, 'devices', side_effect=discoveries), \
                patch.object(reflash.subprocess, 'run') as copy:
            session.run()
            self.assertEqual(copy.call_count, 2)
        log = self.output.getvalue()
        self.assertEqual(log.count('Already flashed: RIGHT'), 1)
        self.assertIn('unregistered', log)
        self.assertIn('Multiple matching', log)

    def test_copy_and_discovery_failures_retry_without_advancing(self):
        session = self.session()
        copies = []
        def transfer(command, **kwargs):
            copies.append(command)
            if len(copies) == 1:
                self.assertFalse(session.right_is_flashed)
                self.assertFalse(session.left_is_flashed)
                raise subprocess.CalledProcessError(1, command)
        with patch.object(reflash.usb, 'devices', side_effect=[
                OSError('USB temporarily unavailable'), {'/right': SAVED['right']},
                {'/right': SAVED['right']}, {'/left': SAVED['left']}]), \
                patch.object(reflash.subprocess, 'run', side_effect=transfer):
            session.run()
        self.assertEqual(len(copies), 3)
        self.assertEqual(copies[0], copies[1])

    def test_timeout_retries_and_reports_unchanged_progress(self):
        session = self.session()
        with patch.object(reflash.time, 'monotonic', side_effect=[0, 31, 32, 33]), \
                patch.object(reflash.usb, 'devices', side_effect=[{}, {'/right': SAVED['right']}, {'/left': SAVED['left']}]), \
                patch.object(reflash.subprocess, 'run'):
            session.run()
        self.assertIn('TIMEOUT', self.output.getvalue())
        self.assertIn('attempt 2', self.output.getvalue())

    def test_preflight_role_and_missing_file_errors(self):
        with self.assertRaisesRegex(ValueError, 'HOST_SIDE'):
            self.session('l').preflight()
        session = self.session()
        session.images['left'].unlink()
        with self.assertRaisesRegex(ValueError, 'Missing firmware'):
            session.preflight()
        self.prepare('r')
        (session.images['right'].parent / '.config').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing firmware'):
            session.preflight()

    def test_preflight_requires_distinct_registrations(self):
        for saved in ({'left': '', 'right': 'R'}, {'left': 'R', 'right': 'R'}):
            session = self.session()
            session.saved = saved
            with self.assertRaisesRegex(ValueError, 'distinct'):
                session.preflight()

    def test_rebuild_and_interrupt_exit_statuses(self):
        for rebuild_fails, interrupted, expected in [(False, False, 0), (True, False, 1), (False, True, 130)]:
            with self.subTest(expected=expected), \
                    patch.object(reflash.sys, 'argv', ['reflash.py', '--rebuild']), \
                    patch.object(reflash.sys, 'platform', 'darwin'), \
                    patch.object(reflash, 'load_config', return_value=config.FlashConfig(30, 'r')), \
                    patch.object(reflash.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'just') if rebuild_fails else None) as build, \
                    patch.object(reflash.Reflasher, 'run', side_effect=KeyboardInterrupt if interrupted else None) as run, \
                    contextlib.redirect_stderr(io.StringIO()) as log:
                self.assertEqual(reflash.main(), expected)
                build.assert_called_once_with(['just', 'build-all'], cwd=reflash.usb.REPO, check=True)
                self.assertEqual(run.call_count, 0 if rebuild_fails else 1)
                if interrupted:
                    self.assertIn('Completed: none. Pending: left, right.', log.getvalue())

    def test_interrupt_summary_preserves_completed_side(self):
        session = self.session()
        with patch.object(reflash.usb, 'devices', side_effect=[{'/right': SAVED['right']}, KeyboardInterrupt]), \
                patch.object(reflash.subprocess, 'run'):
            with self.assertRaises(KeyboardInterrupt):
                session.run()
        self.assertEqual(session.progress(), 'Completed: right. Pending: left.')


if __name__ == '__main__':
    unittest.main()
