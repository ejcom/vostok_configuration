"""Два tsv-файла установщика: devices.tsv (ключ -> конфиг сборки, роль) и flashed.tsv (ключ -> версия). Форматы прежние."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Device:
    """Строка devices.tsv: ключ (serial или canbus_uuid), конфиг сборки (относительно configs/), роль usb|bridge|can."""
    key: str
    cfg: str
    role: str


class DevicesFile:
    """devices.tsv: ``ключ<TAB>конфиг<TAB>роль`` (пишет install, читает update/кнопка)."""

    def __init__(self, path) -> None:
        raise NotImplementedError

    def load(self) -> List[Device]:
        """Все записи; нет файла - пустой список; пустые строки и строки без ключа пропускаются."""
        raise NotImplementedError

    def save(self, devices: List[Device]) -> None:
        """Перезаписать файл целиком (каталог создаётся)."""
        raise NotImplementedError

    def lookup(self, key: str) -> Optional[Device]:
        """Первая запись с таким ключом или None (как awk в devices_lookup)."""
        raise NotImplementedError


class FlashedLog:
    """flashed.tsv: ``ключ<TAB>версия`` - что прошил установщик (для MCU вне printer.cfg)."""

    def __init__(self, path) -> None:
        raise NotImplementedError

    def get(self, key: str) -> str:
        """Последняя версия ключа или пустая строка."""
        raise NotImplementedError

    def set(self, key: str, version: str) -> None:
        """Заменить запись ключа (остальные сохраняются) атомарно: временный файл и rename."""
        raise NotImplementedError
