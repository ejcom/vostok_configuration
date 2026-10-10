#!/usr/bin/env python3
"""Вычисляет canbus_uuid платы Klipper/katapult по UID чипа STM32 (12 байт).

Запуск: python3 -I can_uuid.py --uid-hex 0123456789ABCDEF01234567
        python3 -I can_uuid.py --uid-file файл_с_12_байтами
Печатает 12 hex-символов (canbus_uuid). Код возврата 1 - UID некорректен.

Алгоритм как в прошивке (src/generic/canserial.c, canserial_set_uuid):
fasthash64(uid, 12, seed=0xA16231A7), первые 6 байт хеша (little-endian).
"""
import sys

M = 0x880355F21E6D1965
MASK = (1 << 64) - 1
SEED = 0xA16231A7


def _mix(h):
    h ^= h >> 23
    h = (h * 0x2127599BF4325C37) & MASK
    h ^= h >> 47
    return h


def fasthash64(buf, seed):
    h = (seed ^ (len(buf) * M)) & MASK
    n = len(buf) // 8
    for i in range(n):
        v = int.from_bytes(buf[i * 8:i * 8 + 8], "little")
        h ^= _mix(v)
        h = (h * M) & MASK
    tail = buf[n * 8:]
    if tail:
        v = int.from_bytes(tail, "little")
        h ^= _mix(v)
        h = (h * M) & MASK
    return _mix(h)


def can_uuid(uid):
    if len(uid) != 12:
        raise ValueError("UID должен быть 12 байт, получено %d" % len(uid))
    if uid == b"\x00" * 12 or uid == b"\xff" * 12:
        raise ValueError("UID состоит из одинаковых байт (чтение не удалось)")
    return fasthash64(uid, SEED).to_bytes(8, "little")[:6].hex()


def main(argv):
    if len(argv) != 3 or argv[1] not in ("--uid-hex", "--uid-file"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if argv[1] == "--uid-hex":
            uid = bytes.fromhex(argv[2].strip())
        else:
            with open(argv[2], "rb") as f:
                uid = f.read()
        print(can_uuid(uid))
    except (ValueError, OSError) as e:
        print("can_uuid: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
