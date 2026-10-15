"""Разбор и правка конфигов Klipper: include, секции, [mcu] (бывший mcu_merge.py), пины (pin_conflicts.py),
правка printer.cfg (heredoc stage_config), модули, состояние printer.cfg, атомарная запись с .bak."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TODO_MARK = "ЗАПОЛНИТЕ"
MCU_KEYS = ("serial", "canbus_uuid")


@dataclass
class Section:
    """Секция конфига: имя (пробелы схлопнуты), опции по порядку (ключ, исходное значение) и словарь opts
    (значение без комментария ``# …``, при повторе ключа побеждает последнее)."""
    name: str
    items: List[Tuple[str, str]] = field(default_factory=list)
    opts: Dict[str, str] = field(default_factory=dict)


@dataclass
class Result:
    """Строка результата: kind (OK|ADD|DIFF|TODO|SET|SAME|NOSECTION|CONFLICT), имя/пин и остальные поля."""
    kind: str
    name: str
    args: Tuple[str, ...] = ()

    def line(self) -> str:
        """Строка в формате старых утилит: поля через TAB."""
        raise NotImplementedError


def read_with_includes(path, seen=None) -> str:
    """Текст файла и всех его ``[include …]`` (маски glob, рекурсивно, каждый файл один раз)."""
    raise NotImplementedError


def sections(text: str) -> List[Section]:
    """Разобрать текст на секции без комментариев; единственный разбор для merge/pin_conflicts."""
    raise NotImplementedError


def list_mcus(cfg_path) -> List[Tuple[str, str, str]]:
    """[(имя секции [mcu …], ключ serial|canbus_uuid или "", значение)] с учётом include (``mcu_merge.py --list``)."""
    raise NotImplementedError


def merge_mcus(cfg_path, blocks_text: str, dry: bool = False, backup: bool = True) -> List[Result]:
    """Дописать в printer.cfg недостающие [mcu …] из blocks_text. Результаты OK/ADD/DIFF/TODO как у mcu_merge.py.
    dry - только анализ. backup - перед записью сделать .bak-<дата>."""
    raise NotImplementedError


def set_canbus_uuid(cfg_path, name: str, uuid: str, force: bool = False, backup: bool = False) -> Result:
    """Задать canbus_uuid в секции [name] самого printer.cfg: SET | SAME | DIFF | NOSECTION (как ``mcu_merge.py --set``).
    ЗАПОЛНИТЕ или пустое значение заменяется, другое - только с force."""
    raise NotImplementedError


def pin_conflicts(cfg_path) -> List[Result]:
    """Пины, занятые несколькими секциями (printer.cfg с include): Result("CONFLICT", "MCU:ПИН", (описание,))."""
    raise NotImplementedError


def cfg_state(path) -> str:
    """none (нет файла) | blank (пусто или только комментарии) | foreign (нет [include printer_base.cfg]) | vostok."""
    raise NotImplementedError


def rewrite_printer_text(text: str, electronics: str, blocks_text: str) -> str:
    """Заменить в тексте printer.cfg набор [mcu …] блоками blocks_text и строку [include electronics_*.cfg]."""
    raise NotImplementedError


def rewrite_printer_cfg(path, electronics: str, blocks_text: str, backup: bool = False) -> None:
    """rewrite_printer_text для файла (SAVE_CONFIG и остальное не меняется)."""
    raise NotImplementedError


def module_state(cfg_path, file: str) -> str:
    """Модуль подключён через [include файл] в printer.cfg: active | commented | none."""
    raise NotImplementedError


def module_add_include(cfg_path, file: str, backup: bool = False) -> None:
    """Раскомментировать готовую строку, иначе поставить [include файл] после include электроники
    (или перед блоком SAVE_CONFIG, или в конец файла)."""
    raise NotImplementedError


def backup_file(path, stamp: Optional[str] = None) -> Optional[Path]:
    """Копия ``<path>.bak-<ГГГГММДД-ЧЧММСС>`` (с правами и временем); None, если файла нет."""
    raise NotImplementedError


def atomic_write(path, text: str, backup: bool = True) -> Optional[Path]:
    """Записать файл атомарно (временный файл + rename, права сохраняются); backup - сначала .bak-<дата>.
    Возвращает путь копии или None."""
    raise NotImplementedError
