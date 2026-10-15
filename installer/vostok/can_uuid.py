"""canbus_uuid платы Klipper/katapult по UID чипа STM32 (12 байт): fasthash64(uid, seed=0xA16231A7), первые 6 байт."""
from __future__ import annotations

from typing import Sequence


def fasthash64(buf: bytes, seed: int) -> int:
    """fasthash64 как в прошивке (src/generic/canserial.c)."""
    raise NotImplementedError


def can_uuid(uid: bytes) -> str:
    """12 hex-символов canbus_uuid. ValueError, если UID не 12 байт или состоит из одинаковых байт 00/ff."""
    raise NotImplementedError


def main(argv: Sequence[str]) -> int:
    """CLI как у tools/can_uuid.py: ``--uid-hex HEX`` | ``--uid-file ФАЙЛ``. argv[0] - имя программы."""
    raise NotImplementedError
