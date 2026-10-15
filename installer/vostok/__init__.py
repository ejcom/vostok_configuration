"""Пакет установщика VOSTOK (перенос с bash). Запуск: python3 -m vostok <команда>.

Здесь общие исключения: сообщение VostokError показывается пользователем (``ОШИБКА: …``), код выхода 1.
"""
from __future__ import annotations

from pathlib import Path

# Каталог установщика (родитель пакета): boards/, configs/, templates/, tools/
INSTALL_DIR = Path(__file__).resolve().parent.parent


class VostokError(Exception):
    """Ошибка, которую нужно показать пользователю и завершить работу с кодом 1."""


class FlashError(VostokError):
    """Ошибка сборки/прошивки платы."""


class UserAbort(VostokError):
    """Пользователь прервал работу (отказ, нет терминала для обязательного ответа)."""
