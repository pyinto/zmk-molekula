"""Transfer normal firmware to both registered halves, central first."""

import argparse
from pathlib import Path
import plistlib
import subprocess
import sys
import time

from flash_config import Log, load_config
import uf2_device as usb


class Reflasher:
    def __init__(self, config, root=usb.REPO, log=None):
        self.config = config
        self.root = Path(root)
        self.log = log if log is not None else Log()
        self.left_is_flashed: bool = False
        self.right_is_flashed: bool = False
        self.host_side = config.host_side
        self.saved = usb.configured()
        self.images = {side: self.root / 'build' / f'molekula_tws_{side}' / 'zephyr' / 'zmk.uf2'
                       for side in ('left', 'right')}

    def progress(self):
        completed = [side for side in ('left', 'right') if getattr(self, f'{side}_is_flashed')]
        pending = [side for side in ('left', 'right') if side not in completed]
        return f"Completed: {', '.join(completed) or 'none'}. Pending: {', '.join(pending) or 'none'}."

    def preflight(self):
        if not all(self.saved.values()) or len(set(self.saved.values())) != 2:
            raise ValueError('Register two distinct boards with just register left/right before reflashing.')
        for side, image in self.images.items():
            config_path = image.parent / '.config'
            if not image.is_file() or not image.stat().st_size or not config_path.is_file():
                raise ValueError(f'Missing firmware/configuration for {side}; run just build-all or just reflash --rebuild.')
            lines = set(config_path.read_text().splitlines())
            central = 'CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y' in lines
            if ('CONFIG_ZMK_SPLIT=y' not in lines or
                    f'CONFIG_SHIELD_MOLEKULA_TWS_{side.upper()}=y' not in lines or
                    central != (side == self.config.host)):
                raise ValueError(f'{side.upper()} firmware role/shield disagrees with HOST_SIDE={self.host_side}; correct .env or rebuild the intended firmware roles.')

    def flash_side(self, side):
        step = 1 if side == self.config.host else 2
        role = 'Central' if side == self.config.host else 'Peripheral'

        def row(status, message, level='INFO'):
            self.log.row(step, side, role, status, message, level)
        attempt = 0
        last_notice = None
        while True:
            attempt += 1
            retry = f' · attempt {attempt}' if attempt > 1 else ''
            row('WAITING', f'Double-tap reset ({self.config.timeout_s}s){retry}', 'WAIT')
            deadline = time.monotonic() + self.config.timeout_s
            while True:
                found = {}
                try:
                    found = usb.devices()
                    # Select only this stage's serial, even when both halves are mounted.
                    mount = usb.select(found, side, self.saved)
                    if mount:
                        image = self.images[side]
                        try:
                            display_image = '~/' + str(image.relative_to(Path.home()))
                        except ValueError:
                            display_image = str(image)
                        row('FLASHING', f'Copying firmware  {display_image} → {mount}')
                        subprocess.run(['cp', '-X', str(self.images[side]), str(Path(mount)) + '/'], check=True)
                        setattr(self, f'{side}_is_flashed', True)
                        row('SUCCESS', '✅ Firmware transferred!', 'SUCCESS')
                        self.log.write('')
                        return
                    last_notice = None
                except ValueError as exc:
                    # Mismatches do not count as success and never trigger a copy.
                    notice = str(exc)
                    completed = [name.upper() for name, serial in self.saved.items()
                                 if serial in found.values() and getattr(self, f'{name}_is_flashed')]
                    if completed:
                        notice += f" Already flashed: {', '.join(completed)}; will not flash again."
                    if notice != last_notice:
                        row('SKIPPED', notice, 'ERROR')
                        last_notice = notice
                except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException) as exc:
                    row('RETRY', f'{exc}', 'ERROR')
                    time.sleep(1)
                    break
                if time.monotonic() >= deadline:
                    row('TIMEOUT', 'No matching board. Retrying…', 'WAIT')
                    break
                time.sleep(1)

    def run(self):
        self.preflight()
        self.log.heading()
        for side in (self.config.host, 'left' if self.config.host == 'right' else 'right'):
            self.flash_side(side)
        self.log.write('Both firmware transfers completed 🎉🎉🎉', 'SUCCESS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild', action='store_true', help='Run just build-all before flashing')
    args = parser.parse_args()
    log = Log()
    session = None
    try:
        config = load_config()
        if sys.platform != 'darwin':
            raise ValueError('USB serial discovery currently supports macOS only.')
        if args.rebuild:
            log.write('Building both halves before reflashing.')
            subprocess.run(['just', 'build-all'], cwd=usb.REPO, check=True)
        session = Reflasher(config, log=log)
        session.run()
        return 0
    except KeyboardInterrupt:
        log.write(f'Cancelled. {session.progress() if session else "Completed: none. Pending: left, right."}', 'ERROR')
        return 130
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        log.write(str(exc), 'ERROR')
        return 1


if __name__ == '__main__':
    sys.exit(main())
