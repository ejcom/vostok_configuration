"""Реестр плат: чтение boards/<id>.board (строки KEY="значение", без исполнения кода). Формат не меняется."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from . import VostokError

# Все поля формата .board (порядок как в lib/boards.sh)
BOARD_KEYS = ("LABEL", "ROLE", "CHIP", "FAMILY", "MACH", "CLOCK", "APP_OFFSET", "USB", "CAN", "CAN_KIND",
              "INITIAL_PINS", "BRIDGE_INITIAL_PINS", "KATAPULT_INITIAL_PINS", "KATAPULT_LED",
              "KATAPULT_DOUBLE_RESET", "CFG", "ALIASES", "DFU_HINT", "DFU_HOW", "ELEC_PATTERN",
              "TEMPLATE", "HEAD_NAMES", "VERIFIED", "DOC", "NOTE")
BOARD_REQUIRED = ("LABEL", "ROLE", "CHIP", "FAMILY", "MACH", "CLOCK", "APP_OFFSET", "CFG", "VERIFIED")


class BoardError(VostokError):
    """Ошибка описания платы; текст как в bash: ``boards: …``."""


@dataclass
class Board:
    """Плата из .board: поля - строки как в файле (пустая строка = не задано)."""
    id: str
    label: str = ""
    role: str = ""
    chip: str = ""
    family: str = ""
    mach: str = ""
    clock: str = ""
    app_offset: str = ""
    usb: str = ""
    can: str = ""
    can_kind: str = ""
    initial_pins: str = ""
    bridge_initial_pins: str = ""
    katapult_initial_pins: str = ""
    katapult_led: str = ""
    katapult_double_reset: str = ""
    cfg: str = ""
    aliases: str = ""
    dfu_hint: str = ""
    dfu_how: str = ""
    elec_pattern: str = ""
    template: str = ""
    head_names: str = ""
    verified: str = ""
    doc: str = ""
    note: str = ""

    def field(self, key: str) -> str:
        """Значение поля по имени из файла (``"CHIP"``), пустая строка если не задано."""
        raise NotImplementedError


class Registry:
    """Каталог плат. Разобранные платы кэшируются."""

    def __init__(self, boards_dir, configs_dir=None, katapult_dir=None) -> None:
        """boards_dir - каталог *.board; configs_dir - конфиги сборки (по умолчанию <install>/configs);
        katapult_dir - конфиги katapult (по умолчанию <configs_dir>/katapult)."""
        raise NotImplementedError

    def get(self, id: str) -> Board:
        """Загрузить плату; BoardError, если нет файла/обязательного поля/значение некорректно."""
        raise NotImplementedError

    def ids(self) -> List[str]:
        """id всех файлов *.board (в порядке сортировки), включая неразбираемые."""
        raise NotImplementedError

    def list(self, role: Optional[str] = None) -> List[str]:
        """id плат (роль main|head|alps - только такие; неразбираемые платы с ролью не попадают)."""
        raise NotImplementedError

    def resolve(self, name: str) -> Optional[str]:
        """id или алиас (без учёта регистра) -> id; None, если не найдено."""
        raise NotImplementedError

    def for_chip(self, chip: str, role: Optional[str] = None) -> List[str]:
        """id плат с этим чипом (stm32h723xx), опционально по роли."""
        raise NotImplementedError

    def for_family(self, family: str, role: Optional[str] = None) -> List[str]:
        """id плат этого семейства (h7, f4, f0 …), опционально по роли."""
        raise NotImplementedError

    def has_bridge(self, id: str) -> bool:
        """Есть ли режим USB-CAN моста: ROLE=main, заданы USB и CAN."""
        raise NotImplementedError

    def cfg_path(self, id: str, kind: str) -> Optional[Path]:
        """Путь к конфигу сборки: kind = usb|bridge|can|katapult; None, если такого конфига у платы нет."""
        raise NotImplementedError

    def by_cfg(self, path) -> Optional[Tuple[str, str]]:
        """Файл .config (имя или путь; путь с katapult/ - конфиг katapult) -> (id, usb|bridge|can|katapult)."""
        raise NotImplementedError


def registry() -> Registry:
    """Реестр по окружению (BOARDS_DIR, CONFIGS_DIR, KATAPULT_CONFIGS), как lib/boards.sh."""
    raise NotImplementedError
