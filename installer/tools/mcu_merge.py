#!/usr/bin/env python3
"""Дописывает в printer.cfg недостающие секции [mcu ...]: тонкая обёртка над vostok/cfgfile.py (прежний путь и флаги сохранены).

Запуск: python3 -I mcu_merge.py printer.cfg blocks.txt [--dry]
        python3 -I mcu_merge.py printer.cfg --list   (только перечислить [mcu ...] конфига и его include)
        python3 -I mcu_merge.py printer.cfg --set ИМЯ UUID [--force]   (задать canbus_uuid в секции [ИМЯ] самого printer.cfg;
          значение ЗАПОЛНИТЕ или пустое заменяется, другое значение - только с --force)
Вывод (stdout), по строке на секцию: OK / ADD / DIFF / TODO; для --set: SET / SAME / DIFF / NOSECTION (поля через TAB).
"""
import os
import sys

sys.dont_write_bytecode = True      # -I игнорирует PYTHONDONTWRITEBYTECODE: не оставляем __pycache__ в каталоге установщика
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vostok.cfgfile import mcu_merge_main  # noqa: E402

if __name__ == "__main__":
    sys.exit(mcu_merge_main(sys.argv[1:]))
