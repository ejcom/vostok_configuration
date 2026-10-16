"""Реестр плат: чтение boards/<id>.board (строки KEY="значение", без исполнения кода). Формат не меняется."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import INSTALL_DIR, VostokError

# Все поля формата .board (порядок как в прежнем bash-реестре lib/boards.sh)
BOARD_KEYS = ("LABEL", "ROLE", "CHIP", "FAMILY", "MACH", "CLOCK", "APP_OFFSET", "USB", "CAN", "CAN_KIND",
              "INITIAL_PINS", "BRIDGE_INITIAL_PINS", "KATAPULT_INITIAL_PINS", "KATAPULT_LED",
              "KATAPULT_DOUBLE_RESET", "CFG", "ALIASES", "DFU_HINT", "DFU_HOW", "ELEC_PATTERN",
              "TEMPLATE", "HEAD_NAMES", "VERIFIED", "DOC", "PINOUT", "PINOUT_NOTE", "NOTE")
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
    pinout: str = ""
    pinout_note: str = ""
    note: str = ""

    def field(self, key: str) -> str:
        """Значение поля по имени из файла (``"CHIP"``), пустая строка если не задано."""
        return getattr(self, key.lower(), "")

    @property
    def alias_list(self) -> List[str]:
        """Алиасы платы (поле ALIASES через пробел)."""
        return self.aliases.split()

    @property
    def pinout_list(self) -> List[str]:
        """Пути картинок распиновки относительно pinouts/ (поле PINOUT через пробел)."""
        return self.pinout.split()


# Каталог картинок распиновки и его адрес в сети (VOSTOK_PINOUT_URL заменяет адрес, например для форка)
PINOUT_DIR_NAME = "pinouts"
PINOUT_URL_DEFAULT = "https://github.com/dmitry-sorkin/vostok_configuration/blob/main/installer/pinouts/"


def pinouts_dir() -> Path:
    """Каталог картинок распиновки (PINOUTS_DIR из окружения, иначе <install>/pinouts)."""
    return Path(os.environ.get("PINOUTS_DIR") or INSTALL_DIR / PINOUT_DIR_NAME)


def pinout_url(rel: str) -> str:
    """Веб-адрес картинки распиновки по пути относительно pinouts/ (база - VOSTOK_PINOUT_URL)."""
    base = os.environ.get("VOSTOK_PINOUT_URL") or PINOUT_URL_DEFAULT
    return base.rstrip("/") + "/" + rel


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_LINE_RE = re.compile(r"^([A-Z_]+)=(.*)$")
_ROLES = ("main", "head", "alps")
_CAN_KINDS = ("", "cmenu", "mmenu", "direct")


def _err(msg: str) -> BoardError:
    return BoardError("boards: " + msg)


def parse_board_file(id: str, path: Path) -> Board:
    """Разобрать один файл .board (без исполнения кода); тексты ошибок как в прежнем bash-реестре lib/boards.sh."""
    if not _ID_RE.match(id) or not path.is_file():
        raise _err("нет описания платы '%s' (%s)" % (id, path))
    vals: Dict[str, str] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh.read().split("\n"):
            line = line.rstrip("\r")
            if re.match(r"^\s*(#.*)?$", line):
                continue
            m = _LINE_RE.match(line)
            if not m:
                raise _err("%s: не разобрана строка: %s" % (path, line))
            key, val = m.group(1), m.group(2).rstrip()
            q = re.match(r'^"(.*)"$', val)
            if q:
                val = q.group(1)
            elif re.search(r"\s", val) or val.startswith('"'):
                raise _err("%s: значение %s надо взять в двойные кавычки" % (path, key))
            if key not in BOARD_KEYS:
                raise _err("%s: неизвестное поле %s" % (path, key))
            vals[key] = val
    for k in BOARD_REQUIRED:
        if not vals.get(k):
            raise _err("%s: не задано обязательное поле %s" % (path, k))
    if vals.get("CAN") and not vals.get("CAN_KIND"):
        raise _err("%s: для CAN нужно поле CAN_KIND" % path)
    if vals["ROLE"] not in _ROLES:
        raise _err("%s: ROLE должен быть main|head|alps" % path)
    if vals.get("CAN_KIND", "") not in _CAN_KINDS:
        raise _err("%s: CAN_KIND должен быть cmenu|mmenu|direct" % path)
    if vals["VERIFIED"] not in ("yes", "no"):
        raise _err("%s: VERIFIED должен быть yes|no" % path)
    return Board(id=id, **{k.lower(): v for k, v in vals.items()})


class Registry:
    """Каталог плат. Разобранные платы кэшируются."""

    def __init__(self, boards_dir, configs_dir=None, katapult_dir=None) -> None:
        """boards_dir - каталог *.board; configs_dir - конфиги сборки (по умолчанию <install>/configs);
        katapult_dir - конфиги katapult (по умолчанию <configs_dir>/katapult)."""
        self.boards_dir = Path(boards_dir)
        self.configs_dir = Path(configs_dir) if configs_dir else INSTALL_DIR / "configs"
        self.katapult_dir = Path(katapult_dir) if katapult_dir else self.configs_dir / "katapult"
        self._cache: Dict[str, Board] = {}

    def get(self, id: str) -> Board:
        """Загрузить плату; BoardError, если нет файла/обязательного поля/значение некорректно."""
        b = self._cache.get(id)
        if b is None:
            b = parse_board_file(id, self.boards_dir / (id + ".board"))
            self._cache[id] = b
        return b

    def ids(self) -> List[str]:
        """id всех файлов *.board (в порядке сортировки), включая неразбираемые."""
        if not self.boards_dir.is_dir():
            return []
        return sorted(p.name[:-len(".board")] for p in self.boards_dir.iterdir()
                      if p.name.endswith(".board") and p.is_file())

    def _try(self, id: str) -> Optional[Board]:
        try:
            return self.get(id)
        except BoardError:
            return None

    def list(self, role: Optional[str] = None) -> List[str]:
        """id плат (роль main|head|alps - только такие; неразбираемые платы с ролью не попадают)."""
        if not role:
            return self.ids()
        return [i for i in self.ids() if (self._try(i) or Board(i)).role == role]

    def resolve(self, name: str) -> Optional[str]:
        """id или алиас (без учёта регистра) -> id; None, если не найдено."""
        name = name.lower()
        if not name:
            return None
        if (self.boards_dir / (name + ".board")).is_file():
            return name
        for i in self.ids():
            b = self._try(i)
            if b and any(a.lower() == name for a in b.alias_list):
                return i
        return None

    def _by(self, key: str, value: str, role: Optional[str]) -> List[str]:
        res = []
        for i in self.list(role):
            b = self._try(i)
            if b and b.field(key) == value:
                res.append(i)
        return res

    def for_chip(self, chip: str, role: Optional[str] = None) -> List[str]:
        """id плат с этим чипом (stm32h723xx), опционально по роли."""
        return self._by("CHIP", chip, role)

    def for_family(self, family: str, role: Optional[str] = None) -> List[str]:
        """id плат этого семейства (h7, f4, f0 …), опционально по роли."""
        return self._by("FAMILY", family, role)

    def pinout_paths(self, id: str) -> List[Path]:
        """Абсолютные пути существующих картинок распиновки платы (из PINOUT; отсутствующие файлы отбрасываются)."""
        root = pinouts_dir()
        return [root / rel for rel in self.get(id).pinout_list if (root / rel).is_file()]

    def rank(self, id: str) -> int:
        """Порядок предложения платы (board_rank): 0 - плата гайда (board_resolve h723), 1 - VERIFIED=yes, 2 - остальные."""
        if id == self.resolve("h723"):
            return 0
        return 1 if self.get(id).verified == "yes" else 2

    def has_bridge(self, id: str) -> bool:
        """Есть ли режим USB-CAN моста: ROLE=main, заданы USB и CAN."""
        b = self.get(id)
        return b.role == "main" and bool(b.usb) and bool(b.can)

    def cfg_path(self, id: str, kind: str) -> Optional[Path]:
        """Путь к конфигу сборки: kind = usb|bridge|can|katapult; None, если такого конфига у платы нет."""
        b = self.get(id)
        if kind == "usb":
            return self.configs_dir / (b.cfg + ".config") if b.role != "head" and b.usb else None
        if kind == "bridge":
            return (self.configs_dir / (b.cfg + "-canbridge.config")
                    if b.role == "main" and b.usb and b.can else None)
        if kind == "can":
            return self.configs_dir / (b.cfg + "-can.config") if b.role == "head" else None
        if kind == "katapult":
            suffix = "-can.config" if b.role == "head" else ".config"
            return self.katapult_dir / (b.cfg + suffix)
        raise _err("board_cfg: неизвестный вид '%s'" % kind)

    def by_cfg(self, path) -> Optional[Tuple[str, str]]:
        """Файл .config (имя или путь; путь с katapult/ - конфиг katapult) -> (id, usb|bridge|can|katapult)."""
        p = str(path)
        base = os.path.basename(p)
        want_katapult = "/katapult/" in p or p.startswith("katapult/")
        for i in self.ids():
            if self._try(i) is None:
                continue
            kinds = ("katapult",) if want_katapult else ("usb", "bridge", "can")
            for kind in kinds:
                cp = self.cfg_path(i, kind)
                if cp is not None and cp.name == base:
                    return i, kind
        return None


def registry() -> Registry:
    """Реестр по окружению (BOARDS_DIR, CONFIGS_DIR, KATAPULT_CONFIGS), как в прежнем lib/boards.sh."""
    return Registry(os.environ.get("BOARDS_DIR") or INSTALL_DIR / "boards",
                    os.environ.get("CONFIGS_DIR") or None,
                    os.environ.get("KATAPULT_CONFIGS") or None)
