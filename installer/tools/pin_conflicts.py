#!/usr/bin/env python3
"""Ищет повторяющиеся пины в конфиге Klipper (printer.cfg и все его [include]): тонкая обёртка над vostok/cfgfile.py.

Запуск: python3 -I pin_conflicts.py printer.cfg
Вывод: по строке на пин, который используется в нескольких секциях:
  CONFLICT<TAB>MCU:ПИН<TAB>[секция] опция; [секция] опция
Не считаются конфликтом общие линии SPI (spi_software_*), повторы одной секции и виртуальные
концевики (probe:z_virtual_endstop).
"""
import os
import sys

sys.dont_write_bytecode = True      # -I игнорирует PYTHONDONTWRITEBYTECODE: не оставляем __pycache__ в каталоге установщика
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vostok.cfgfile import pin_conflicts_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(pin_conflicts_main(sys.argv[1:]))
