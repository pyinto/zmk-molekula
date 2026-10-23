"""Shared flash settings; environment is loaded by just from .env."""

import os
import sys
from typing import Literal, NamedTuple


class FlashConfig(NamedTuple):
    timeout_s: int
    host_side: Literal['l', 'r']

    @property
    def host(self):
        return {'l': 'left', 'r': 'right'}[self.host_side]

    def label(self, side):
        if side not in ('left', 'right'):
            return side.upper()
        return f"{side.upper()} — {'CENTRAL' if side == self.host else 'PERIPHERAL'}"


def load_config():
    raw = os.environ.get('FLASH_TIMEOUT', '')
    if not raw.isascii() or not raw.isdigit() or int(raw) <= 0:
        raise ValueError('Set FLASH_TIMEOUT in .env to a positive integer (seconds).')
    host = os.environ.get('HOST_SIDE', '')
    if host not in ('l', 'r'):
        raise ValueError('Set HOST_SIDE in .env to l or r; it must match the built central.')
    return FlashConfig(int(raw), host)


class Log:
    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr
        self.color = self.stream.isatty() and 'NO_COLOR' not in os.environ

    def _emit(self, line, level):
        if self.color:
            code = {'ERROR': '31', 'SUCCESS': '32', 'WAIT': '36'}.get(level, '0')
            line = f'\033[1;{code}m{line}\033[0m'
        print(line, file=self.stream, flush=True)

    def write(self, message, level='INFO'):
        if not message:
            print(file=self.stream, flush=True)
            return
        label = {'INFO': 'Info', 'WAIT': 'Waiting', 'SUCCESS': 'Done', 'ERROR': 'Error'}[level]
        self._emit(f'  {label:<9} {message}', level)

    def row(self, step, side, role, status, message, level='INFO'):
        self._emit(f'  {step}/2  {side.upper():<5}  {role:<10}  {status:<9}  {message}', level)

    def heading(self):
        print('\nReflash both halves — central first\n', file=self.stream, flush=True)
