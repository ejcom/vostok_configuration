#!/usr/bin/env python3
"""Вычисляет canbus_uuid платы Klipper/katapult по UID чипа STM32 (12 байт): тонкая обёртка над vostok/can_uuid.py.

Запуск: python3 -I can_uuid.py --uid-hex 0123456789ABCDEF01234567
        python3 -I can_uuid.py --uid-file файл_с_12_байтами
Печатает 12 hex-символов (canbus_uuid). Код возврата 1 - UID некорректен.

Алгоритм как в прошивке (src/generic/canserial.c, canserial_set_uuid):
fasthash64(uid, 12, seed=0xA16231A7), первые 6 байт хеша (little-endian).
"""
import os
import sys

sys.dont_write_bytecode = True      # -I игнорирует PYTHONDONTWRITEBYTECODE: не оставляем __pycache__ в каталоге установщика
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vostok.can_uuid import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv))
