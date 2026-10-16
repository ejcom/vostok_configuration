#!/usr/bin/env python3
"""Генерация electronics_*.cfg: тонкая обёртка над vostok/electronics.py (прежний путь и флаги сохранены).

Запуск: python3 -I gen_electronics.py ... (то же, что python3 -m vostok.electronics ...).
"""
import os
import sys

sys.dont_write_bytecode = True      # -I игнорирует PYTHONDONTWRITEBYTECODE: не оставляем __pycache__ в каталоге установщика
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vostok.electronics import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
