"""Два tsv-файла установщика: devices.tsv (ключ -> конфиг сборки, роль) и flashed.tsv (ключ -> версия). Форматы прежние."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Device:
    """Строка devices.tsv: ключ (serial или canbus_uuid), конфиг сборки (относительно configs/), роль usb|bridge|can."""
    key: str
    cfg: str
    role: str


def _atomic_write(path: Path, text: str) -> None:
    """Записать файл целиком через временный файл и rename (читатели не увидят усечённый файл)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)    # права прежнего файла
        except OSError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_lines(path: Path) -> List[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().split("\n")
    except OSError:
        return []


class DevicesFile:
    """devices.tsv: ``ключ<TAB>конфиг<TAB>роль`` (пишет install, читает update/кнопка)."""

    def __init__(self, path) -> None:
        self.path = Path(path)

    def load(self) -> List[Device]:
        """Все записи; нет файла - пустой список; пустые строки и строки без ключа пропускаются."""
        res = []
        for line in _read_lines(self.path):
            parts = line.split("\t")
            if not parts[0]:
                continue
            parts += [""] * (3 - len(parts))
            res.append(Device(parts[0], parts[1], parts[2]))
        return res

    def save(self, devices: List[Device]) -> None:
        """Перезаписать файл целиком атомарно (tmp + rename, каталог создаётся)."""
        _atomic_write(self.path, "".join("%s\t%s\t%s\n" % (d.key, d.cfg, d.role) for d in devices))

    def lookup(self, key: str) -> Optional[Device]:
        """Первая запись с таким ключом или None (как awk в devices_lookup)."""
        for d in self.load():
            if d.key == key:
                return d
        return None


class FlashedLog:
    """flashed.tsv: ``ключ<TAB>версия`` - что прошил установщик (для MCU вне printer.cfg)."""

    def __init__(self, path) -> None:
        self.path = Path(path)

    def get(self, key: str) -> str:
        """Последняя версия ключа или пустая строка."""
        v = ""
        for line in _read_lines(self.path):
            parts = line.split("\t")
            if parts[0] == key and len(parts) > 1 and parts[1] != "":
                v = parts[1]
        return v

    def set(self, key: str, version: str) -> None:
        """Заменить запись ключа (остальные сохраняются) атомарно: временный файл и rename."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keep = [ln for ln in _read_lines(self.path) if ln and ln.split("\t")[0] != key]
        keep.append("%s\t%s" % (key, version))
        _atomic_write(self.path, "\n".join(keep) + "\n")
