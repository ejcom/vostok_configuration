"""Настройка конфига VOSTOK (бывшие lib/vostok_config.sh и configure_vostok.sh).

Определение железа, меню источника конфига, генерация своего electronics_*.cfg, запись printer.cfg,
дополнительные модули. Один код для автономной команды ``configure`` и для этапа конфигурации установщика.

Для установщика (install.py) пригодны: ``Hardware``/``HardwareDetector`` (главная плата, платы голов,
ALPS, режим usb|bridge), ``mcu_blocks``, ``McuValues``, ``rank_main_boards`` и ``Configurator.stage_config``.
Помощники USB/DFU/CAN (byid_find, dfu_count, dfu_family, show_usb_state ...) живут в hardware.py.
Вызовы внешних программ идут через system.Runner; чтение состояния (lsusb, ip, dfu-util) выполняется и в
dry-run, как в bash.
"""
from __future__ import annotations

import glob
import http.client
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from . import INSTALL_DIR, VostokError, cfgfile, ui
from .hardware import (byid_find, can_iface_exists, dfu_count, dfu_family, serial_from_path,  # noqa: F401  (общие с install)
                       show_usb_state, usb_bridge_present)
from .boards import Board, Registry, registry as default_registry
from .electronics import ElectronicsError, GenOptions, GenResult, Generator, board_naming
from .state import DevicesFile
from .system import Runner

TODO_MARK = "ЗАПОЛНИТЕ"   # плата не прошита: Klipper сообщит об ошибке, пока заглушку не заменят
CONFIG_SOURCES = ("standard", "user", "generate", "skip")

# Дополнительные модули: (файл, название). Файл лежит в корне vostok_configuration, подключается через [include].
CFG_MODULES: List[Tuple[str, str]] = [
    ("chamber_heater.cfg", "Подогрев термокамеры (Smart Chamber Heater)"),
]

SRC_LBL_STD = "Стандартный (корень main)"
SRC_LBL_USR = "Пользовательский (user_configs)"
SRC_LBL_GEN = "Сгенерировать свой конфиг"
SRC_LBL_SKIP = "Пропустить редактирование конфига"

DRV_LABELS = [("2130", "TMC2130 (SPI)"), ("2208", "TMC2208 (UART)"), ("2209", "TMC2209 (UART)"),
              ("2240", "TMC2240 (SPI)"), ("5160", "TMC5160 / 5160T Pro (SPI, sense 0.075)"),
              ("5160plus", "TMC5160T Plus (SPI, sense 0.022)")]
DRIVER_DEFAULT_SPEC = "x=2240,w=2240,yl=2240,yr=2240,z=2240,e0=2209,e1=2209"
MOTOR_QUESTIONS = {
    "e0": "экструдера T0 (левая голова)", "e1": "экструдера T1 (правая голова)", "x": "мотора X",
    "w": "мотора W (правая голова по X)", "yl": "левого мотора Y", "yr": "правого мотора Y", "z": "мотора Z",
}

USAGE = """Использование: configure_vostok.sh [опции]

Настройка конфига принтера без установки и прошивки.

  --main ПЛАТА          главная плата: id или алиас из реестра, список: install_vostok.sh --list-boards
                        (h723, f446 и др.; иначе определит по printer.cfg/железу или спросит)
  --heads none|v1.3|v2|ebb42  платы голов по CAN (иначе определит по printer.cfg или спросит);
                        допустимы id и алиасы плат голов реестра, без шаблона электроники - отказ
  --alps 0|1|2          число датчиков ALPS (иначе определит или спросит)
  --config-source standard|user|generate|skip  источник конфига электроники: корень main, user_configs,
                        сгенерировать свой (шаблон без плат и драйверов) или пропустить редактирование
                        (только дописать недостающие [mcu] в существующий printer.cfg); иначе спросит
  --electronics ФАЙЛ    имя electronics_*.cfg из vostok_configuration (для standard/user)
  --drivers СПЕК        драйверы для generate: all=2130|2208|2209|2240|5160|5160plus или список по моторам
                        x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209 (иначе спросит; с -y как в стоке)
  --reference ФАЙЛ|none эталон для пинов и параметров. По умолчанию ваш текущий electronics-файл
                        (активный include в printer.cfg), при чистой установке стоковый main (H723).
                        none - не использовать эталон
  --modules ИМЕНА       дополнительные модули без вопроса: chamber_heater, all или none (через запятую)
  --printer-data DIR    каталог printer_data (по умолчанию ~/printer_data)
  --dry-run             показать, что будет сделано, ничего не менять
  -y, --yes             не задавать вопросов, где есть ответ по умолчанию
  -V, --version         показать версию установщика
  -h, --help            эта справка

Переменные окружения: PRINTER_DATA, VOSTOK_CFG_LOCAL (0 - всегда скачивать конфигурацию, ПУТЬ - свой каталог).
"""


# ------------------------------------------------------------------ окружение и опции

@dataclass
class Env:
    """Пути и адреса из окружения (имена и значения по умолчанию как в bash)."""
    install_dir: Path = INSTALL_DIR
    printer_data: Path = Path.home() / "printer_data"
    byid_dir: str = "/dev/serial/by-id"
    can_iface: str = "can0"
    devices_file: Path = INSTALL_DIR / "devices.tsv"
    cfg_local: str = "auto"
    cfg_tarball: str = "https://codeload.github.com/dmitry-sorkin/vostok_configuration/tar.gz/refs/heads/main"
    templates_dir: Path = INSTALL_DIR / "templates"
    log_file: Optional[Path] = None

    @classmethod
    def from_environ(cls, environ=None, install_dir: Path = INSTALL_DIR) -> "Env":
        e = os.environ if environ is None else environ
        pd = Path(e.get("PRINTER_DATA") or (Path(e.get("HOME") or Path.home()) / "printer_data"))
        return cls(
            install_dir=install_dir, printer_data=pd,
            byid_dir=e.get("BYID_DIR") or "/dev/serial/by-id",
            can_iface=e.get("CAN_IFACE") or "can0",
            devices_file=Path(e.get("DEVICES_FILE") or (install_dir / "devices.tsv")),
            cfg_local=e.get("VOSTOK_CFG_LOCAL") or "auto",
            cfg_tarball=e.get("VOSTOK_CFG_TARBALL") or cls.cfg_tarball,
            templates_dir=Path(e.get("TEMPLATES_DIR") or (install_dir / "templates")),
            log_file=Path(e["LOG_FILE"]) if e.get("LOG_FILE") else None)

    @property
    def printer_cfg_dir(self) -> Path:
        return self.printer_data / "config"

    @property
    def effective_log_file(self) -> Path:
        return self.log_file or (self.printer_data / "logs" / "vostok_configure.log")


@dataclass
class Options:
    """Опции командной строки (бывшие OPT_*); пустая строка - не задано."""
    main: str = ""
    heads: str = ""
    alps: str = ""
    config_source: str = ""
    electronics: str = ""
    drivers: str = ""
    reference: str = ""
    modules: str = ""
    only_detect: bool = False     # для install_vostok.sh --only-detect (у configure опции нет)


@dataclass
class McuValues:
    """Значения для [mcu …] новых секций (бывшие RES_*); пусто - в блоке будет ЗАПОЛНИТЕ."""
    bridge_uuid: str = ""
    main_serial: str = ""
    head_uuid: List[str] = field(default_factory=lambda: ["", ""])
    alps_serial: List[str] = field(default_factory=lambda: ["", ""])


# ------------------------------------------------------------------ железо

def rank_main_boards(reg: Registry, ids: Sequence[str]) -> List[str]:
    """ТОЧКА РАСШИРЕНИЯ: порядок предпочтения главных плат при выборе «по умолчанию» (первая - лучшая).
    Здесь одно правило, общее для кандидатов по железу (main_candidates) и для догадки по printer.cfg
    (guess_main_board): сначала плата гайда и проверенные на железе (Registry.rank: 0 - плата гайда, 1 -
    VERIFIED=yes, 2 - остальные), при равенстве - по чипу в обратном порядке (H7 раньше F4), затем платы
    Octopus Pro (Registry.guide_ids: по умолчанию в семействе остаётся она, а не новая плата с тем же чипом), затем по id."""
    def info(i: str) -> Tuple[int, str]:
        return reg.rank(i), reg.get(i).chip

    guide = reg.guide_ids()
    res = sorted(ids)                                   # четвёртый ключ: id по возрастанию
    res.sort(key=lambda i: i not in guide)              # третий ключ: Octopus Pro раньше остальных того же чипа
    res.sort(key=lambda i: info(i)[1], reverse=True)    # второй ключ: чип по убыванию (sort устойчив)
    res.sort(key=lambda i: info(i)[0])
    return res


@dataclass
class Hardware:
    """Выбранное железо: id главной платы, платы голов (none|v1.3|v2|ebb42), число ALPS, режим usb|bridge."""
    registry: Registry = field(repr=False, compare=False)
    main_board: str = ""
    heads: str = ""
    alps_count: int = 0
    mode: str = ""
    head_mcu: List[str] = field(default_factory=lambda: ["T0CB", "T1CB"])   # имена секций [mcu …] плат голов

    # --- главная плата
    @property
    def board(self) -> Board:
        return self.registry.get(self.main_board)

    @property
    def main(self) -> str:
        """Чип главной платы (stm32h723xx …)."""
        return self.board.chip

    def set_main_board(self, board_id: str) -> None:
        self.main_board = board_id

    def main_label(self) -> str:
        return self.board.label

    def main_short(self) -> str:
        """Короткое имя платы для сообщений про мост: «Octopus», «Manta», «Spider», «FLY-C8»."""
        label = self.main_label()
        for prefix in ("BTT ", "Fysetc ", "Mellow "):
            if label.startswith(prefix):
                label = label[len(prefix):]
        return label.split(" ")[0]

    def klipper_cfg(self) -> Optional[Path]:
        return self.registry.cfg_path(self.main_board, "bridge" if self.mode == "bridge" else "usb")

    def katapult_cfg(self) -> Optional[Path]:
        return self.registry.cfg_path(self.main_board, "katapult")

    # --- платы голов
    @property
    def has_heads(self) -> bool:
        return self.heads not in ("", "none")

    def head_board_id(self, heads: Optional[str] = None) -> Optional[str]:
        h = self.heads if heads is None else heads
        if h in ("", "none"):
            return None
        return self.registry.resolve(h)

    def head_field(self, key: str) -> str:
        hid = self.head_board_id()
        return self.registry.get(hid).field(key) if hid else ""

    def set_head_names(self) -> None:
        names = (self.head_field("HEAD_NAMES") if self.has_heads else "") or "T0CB,T1CB"
        self.head_mcu = [names.split(",")[0], names.split(",")[-1]]

    def head_label(self) -> str:
        return self.head_field("LABEL") if self.has_heads else "платы голов"

    def head_chip(self) -> str:
        return self.head_field("CHIP")

    def head_dfu_hint(self) -> str:
        return self.head_field("DFU_HINT")

    def head_cfg_name(self) -> str:
        """Имя файла конфига сборки платы головы (общее для Klipper и katapult)."""
        hid = self.head_board_id()
        p = self.registry.cfg_path(hid, "can") if (self.has_heads and hid) else None
        return p.name if p else ""

    def head_side(self, i: int) -> str:
        return "левая (%s)" % self.head_mcu[0] if i == 0 else "правая (%s)" % self.head_mcu[1]

    @staticmethod
    def alps_side(i: int) -> str:
        return "левый (T0)" if i == 0 else "правый (T1)"


class HardwareDetector:
    """Определение железа: главная плата (опция, прошлый devices.tsv, подключённый чип), платы голов, ALPS."""

    def __init__(self, opts: Options, env: Env, reg: Registry, runner: Optional[Runner] = None) -> None:
        self.opts = opts
        self.env = env
        self.reg = reg
        self.runner = runner or Runner(dry_run=False)

    # --- главная плата

    def main_boards_hint(self) -> str:
        """Главные платы с алиасами для сообщений: «octopus-pro-h723 (h723), …»."""
        parts = []
        for i in self.reg.list("main"):
            al = self.reg.get(i).alias_list
            parts.append(i + (" (%s)" % ", ".join(al) if al else ""))
        return ", ".join(parts)

    def board_from_opt(self, name: str) -> str:
        """--main ИМЯ (id или алиас) -> id главной платы; на неизвестное имя - понятная ошибка."""
        bid = self.reg.resolve(name)
        if bid is None:
            raise VostokError("--main: неизвестная плата '%s'. Доступные: %s. Список с описанием: install_vostok.sh --list-boards"
                              % (name, self.main_boards_hint()))
        role = self.reg.get(bid).role
        if role != "main":
            raise VostokError("--main: '%s' - не главная плата (%s, роль %s). Доступные: %s"
                              % (name, bid, role, self.main_boards_hint()))
        return bid

    def prev_main_board(self) -> str:
        """Главная плата из прошлого devices.tsv (запись bridge/usb главной платы), иначе пусто."""
        if not self.env.devices_file.is_file():
            return ""
        for d in DevicesFile(self.env.devices_file).load():
            if d.role not in ("bridge", "usb"):
                continue
            r = self.reg.by_cfg(d.cfg)
            if r is None:
                continue
            if self.reg.get(r[0]).role == "main":
                return r[0]
        return ""

    def main_candidates(self) -> List[str]:
        """Платы-кандидаты по подключённому железу: чип из usb-*<чип>_* в by-id, иначе семейство единственного
        устройства в DFU. Порядок - rank_main_boards."""
        chips: List[str] = []
        seen = set()
        for bid in self.reg.list("main"):
            chip = self.reg.get(bid).chip
            if chip in seen:
                continue
            seen.add(chip)
            if byid_find(self.env.byid_dir, "usb-*%s_*" % chip):
                chips.append(chip)
        ids: List[str] = []
        if chips:
            for chip in chips:
                ids.extend(self.reg.for_chip(chip, "main"))
        elif dfu_count(self.runner) == 1:
            fam = dfu_family(self.runner)
            if fam != "unknown":
                ids.extend(self.reg.for_family(fam, "main"))
        return rank_main_boards(self.reg, ids)

    def ask_board(self, question: str, default_id: str, ids: Sequence[str]) -> str:
        """Выбор платы из списка id в диалоге; по умолчанию default_id."""
        labels = ["%s (%s)" % (self.reg.get(i).label, i) for i in ids]
        deflbl = ""
        for i, lbl in zip(ids, labels):
            if i == default_id:
                deflbl = lbl
        ans = ui.ask_choice(question, deflbl or labels[0], labels)
        for i, lbl in zip(ids, labels):
            if lbl == ans:
                return i
        return default_id

    def detect_main_board(self, hw: Hardware) -> None:
        if self.opts.main:
            hw.set_main_board(self.board_from_opt(self.opts.main))
            return
        cands = self.main_candidates()
        prev = self.prev_main_board()
        ids = list(cands) or self.reg.list("main")
        default = ids[0]
        if not cands:
            default = self.reg.resolve("h723") or default
            if prev:
                default = prev
        elif prev in ids:
            default = prev
        asked = False
        if self.opts.only_detect and cands and (len(cands) == 1 or not ui.have_tty()):
            chosen = default
        elif ui.opts.yes:
            chosen = default
            if len(cands) > 1 and chosen != prev and not ui.opts.dry_run:
                raise VostokError("на найденном чипе возможны платы: %s. Без вопросов (-y) выбрать нельзя, "
                                  "укажите --main <id> (список: --list-boards)" % " ".join(cands))
        else:
            chosen = self.ask_board("Главная плата:", default, ids)
            asked = True
        if not asked and len(cands) > 1 and chosen != prev:
            ui.info("На найденном чипе возможны платы: %s; выбрана %s (уточните: --main <id>)" % (" ".join(cands), chosen))
        hw.set_main_board(chosen)

    def check_main_bridge(self, hw: Hardware) -> None:
        """Плата без USB-CAN моста не подходит для схемы с платами голов: отказ до прошивки."""
        if hw.heads == "none" or self.reg.has_bridge(hw.main_board):
            return
        raise VostokError("у %s нет USB-CAN моста: платы голов по CAN к ней подключить нельзя. Нужен отдельный USB-CAN "
                          "адаптер (установщик его не поддерживает) или запуск без плат голов: --heads none" % hw.main_label())

    # --- платы голов и ALPS

    def detect_heads(self, hw: Hardware) -> str:
        guess = "none"
        if usb_bridge_present(self.runner) or can_iface_exists(self.env.can_iface, self.runner):
            guess = "v2"
        if self.opts.heads:
            return self.opts.heads
        if self.opts.only_detect:
            return guess
        none_lbl = "нет (пассивная плата, например fly miniAB)"
        head_versions = self.reg.head_choices(True)      # варианты плат голов в меню: головы реестра с шаблоном электроники
        labels = {hv: self.reg.get(hw.head_board_id(hv)).label for hv in head_versions}
        default = none_lbl if guess == "none" else labels[guess]
        ans = ui.ask_choice("Платы голов по CAN (при их наличии %s станет мостом USB-CAN):" % hw.main_short(),
                            default, [none_lbl] + [labels[hv] for hv in head_versions])
        for hv in head_versions:
            if ans == labels[hv]:
                return hv
        return "none"

    def detect_alps(self) -> int:
        guess = min(len(byid_find(self.env.byid_dir, "usb-*stm32f072xb_*")), 2)
        if self.opts.alps:
            return int(self.opts.alps)
        if self.opts.only_detect:
            return guess
        return int(ui.ask_choice("Сколько датчиков ALPS подключено по USB (0 - нет)?", str(guess), ["0", "1", "2"]))

    def detect(self) -> Hardware:
        """Определение подключённых MCU (этап «Определение подключённых MCU»)."""
        ui.step("Определение подключённых MCU")
        show_usb_state(self.runner, self.env.can_iface)
        hw = Hardware(self.reg)
        self.detect_main_board(hw)
        hw.heads = self.detect_heads(hw)
        hw.set_head_names()
        self.check_main_bridge(hw)
        hw.alps_count = self.detect_alps()
        hw.mode = "usb" if hw.heads == "none" else "bridge"
        return hw


# ------------------------------------------------------------------ блоки [mcu …]

def mcu_blocks(hw: Hardware, res: McuValues) -> str:
    """Текст секций [mcu …] для прошитых (или ожидаемых) плат; не прошитая плата получает ЗАПОЛНИТЕ."""
    out: List[str] = []
    if hw.mode == "bridge":
        out.append("[mcu]\ncanbus_uuid: %s\n\n" % (res.bridge_uuid or TODO_MARK))
        for i in (0, 1):
            out.append("[mcu %s]\ncanbus_uuid: %s\n\n" % (hw.head_mcu[i], res.head_uuid[i] or TODO_MARK))
    else:
        out.append("[mcu]\nserial: /dev/serial/by-id/usb-Klipper_%s_%s-if00\n\n" % (hw.main, res.main_serial or TODO_MARK))
    for i in range(hw.alps_count):
        out.append("[mcu alps%s]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_%s-if00\n\n"
                   % ("_t1" if i == 1 else "", res.alps_serial[i] or TODO_MARK))
    return "".join(out).rstrip("\n")


def _echo(text: str) -> None:
    """Вывод в stdout без записи в журнал (printf в bash)."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def _eecho(text: str) -> None:
    """Вывод в stderr без цвета и без журнала (printf … >&2 в bash)."""
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def print_pinouts(reg: Registry, hw: Hardware) -> None:
    """Блок «Распиновка ваших плат» для итога: главная плата, плата головы и ALPS (если есть)."""
    ids = [hw.main_board]
    hid = hw.head_board_id()
    if hid and hid not in ids:
        ids.append(hid)
    if hw.alps_count > 0:
        ids.extend(reg.list("alps")[:1])
    lines = [ln for bid in ids for ln in ui.pinout_lines(reg, bid)]
    if lines:
        ui.info("")
        ui.info("Распиновка ваших плат (сверьте проводку по схеме):")
        for ln in lines:
            ui.info(ln)


def _first_include(printer_cfg: Path) -> str:
    """Первый ``[include electronics_*.cfg]`` самого printer.cfg (без разбора вложенных include)."""
    try:
        with open(printer_cfg, encoding="utf-8", errors="replace") as f:
            for ln in f.read().split("\n"):
                m = re.match(r"^\s*\[include\s+(electronics_[^\]]*\.cfg)\]", ln)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


def _fetch_tarball(url: str, dest_root: Path, workdir: Path) -> None:
    """Скачать архив конфигурации и распаковать его в dest_root без верхнего каталога (``--strip-components=1``)."""
    tarball = workdir / "vostok_configuration.tar.gz"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(tarball, "wb") as out:
            shutil.copyfileobj(resp, out)
    except (OSError, ValueError, http.client.HTTPException) as e:     # URLError, HTTPError, таймаут - подклассы OSError
        ui.log("загрузка %s: %s" % (url, e))
        raise VostokError("не удалось скачать %s" % url)
    dest_root.mkdir(parents=True, exist_ok=True)
    try:
        links = []
        with tarfile.open(tarball, "r:*") as tar:
            for m in tar.getmembers():
                parts = [p for p in m.name.split("/") if p not in ("", ".")]
                if len(parts) < 2 or ".." in parts:
                    continue          # верхний каталог архива и небезопасные пути пропускаются
                if m.issym() or m.islnk():
                    links.append("/".join(parts[1:]))    # ссылки не создаём (могут вести за пределы каталога)
                    continue
                if not (m.isfile() or m.isdir()):
                    continue
                m.name = "/".join(parts[1:])
                tar.extract(m, str(dest_root))
        if links:
            shown = ", ".join(links[:5]) + (" и ещё %d" % (len(links) - 5) if len(links) > 5 else "")
            ui.warn("в архиве конфигурации пропущено ссылок (символических/жёстких): %d (%s); они не созданы" % (len(links), shown))
    except (tarfile.TarError, OSError, EOFError):
        raise VostokError("не удалось распаковать конфигурацию")


def _copy_tree(src: Path, dst_parent: Path) -> None:
    """``cp -r src dst_parent/``: каталог копируется внутрь dst_parent, существующие файлы перезаписываются."""
    shutil.copytree(str(src), str(dst_parent / src.name), symlinks=True, dirs_exist_ok=True, copy_function=shutil.copy)


# ------------------------------------------------------------------ конфигуратор

class Configurator:
    """Сбор значений [mcu], выбор/генерация electronics, запись printer.cfg и модули (бывший stage_config)."""

    def __init__(self, opts: Options, env: Env, reg: Registry, hw: Hardware, runner: Optional[Runner] = None) -> None:
        self.opts = opts
        self.env = env
        self.reg = reg
        self.hw = hw
        self.runner = runner or Runner(dry_run=False)
        self.mcu = McuValues()
        self.cfg_state = ""                  # none|blank|foreign|vostok: состояние printer.cfg (ставит stage_config)
        self.ref_cfg = ""                    # эталон для пинов (путь) и его вид user|stock|none
        self.ref_kind = "none"
        self.gen: Optional[GenResult] = None   # результат генерации (None - генератор не запускался)
        self.drivers_spec = ""
        self.el_src = ""                     # standard|user|generate|skip
        self.el_name = ""
        self.show_pinouts = True             # выводить блок «Распиновка ваших плат» в конце (install_vostok.sh - в своём итоге)

    @property
    def printer_cfg(self) -> Path:
        return self.env.printer_cfg_dir / "printer.cfg"

    # --- вспомогательное

    def _board_field(self, key: str) -> str:
        return self.hw.board.field(key)

    def _prev_devices(self):
        return DevicesFile(self.env.devices_file).load() if self.env.devices_file.is_file() else []

    def prev_keys(self, cfg_name: str) -> List[str]:
        """Ключи (serial/uuid) из devices.tsv прошлого запуска для конфига сборки, по порядку."""
        return [d.key for d in self._prev_devices() if d.cfg == cfg_name] if cfg_name else []

    def elec_named_board(self, fname: str) -> str:
        """Плата, для которой генератор создал electronics-файл с таким именем (electronics_<id с _>_…); у плат
        со старыми именами (CFG == чип, Octopus) имя файла другое и они сюда не попадают. Пусто - нет такой."""
        for bid in self.reg.list("main"):
            b = self.reg.get(bid)
            if b.cfg != b.chip and fname.startswith("electronics_%s_" % b.cfg.replace("-", "_")):
                return bid
        return ""

    def el_for_board(self, fname: str) -> bool:
        """Электроника с таким именем сделана под выбранную плату? Имя содержит ELEC_PATTERN платы или часть имени
        файла, которую даёт генератор. Файл другой известной платы - нет. Имя без признаков какой-либо платы
        у платы с ELEC_PATTERN считается своим."""
        named = self.elec_named_board(fname)
        if named:
            return named == self.hw.main_board
        pat = self._board_field("ELEC_PATTERN")
        if pat and pat in fname:
            return True
        if not pat:
            return False
        for bid in self.reg.list("main"):
            other = self.reg.get(bid).elec_pattern
            if other and bid != self.hw.main_board and other in fname:
                return False
        return True

    def el_matches(self, fname: str) -> bool:
        """Подходит ли файл под выбранные главную плату и платы голов."""
        chip_pat = self._board_field("ELEC_PATTERN")
        if not (chip_pat and chip_pat in fname):
            return False
        named = self.elec_named_board(fname)
        if named and named != self.hw.main_board:
            return False
        head_pat = self.hw.head_field("ELEC_PATTERN") if self.hw.has_heads else ""
        return not head_pat or head_pat in fname

    # --- подсказки из printer.cfg (configure_vostok.sh)

    def guess_main_board(self, mcu_list: str, inc: str) -> str:
        """Главная плата по существующему конфигу: имя electronics-файла (ELEC_PATTERN платы или её id с _),
        затем чип из [mcu] (прошлая плата из devices.tsv, иначе лучшая по rank_main_boards). Пусто - не нашли."""
        named = self.elec_named_board(inc)
        if named:
            return named
        main_ids = self.reg.list("main")
        for bid in main_ids:
            pat = self.reg.get(bid).elec_pattern
            if pat and pat in inc:
                return bid
        prev = HardwareDetector(self.opts, self.env, self.reg, self.runner).prev_main_board()
        for bid in main_ids:
            chip = self.reg.get(bid).chip
            if chip not in mcu_list:
                continue
            if prev and self.reg.get(prev).chip == chip:
                return prev
            ranked = rank_main_boards(self.reg, self.reg.for_chip(chip, "main"))
            return ranked[0] if ranked else ""
        return ""

    def guess_from_printer_cfg(self) -> None:
        """Подсказки по железу из существующего printer.cfg: заполняет main/heads/alps, только если не заданы."""
        cfg = self.printer_cfg
        if cfgfile.cfg_state(cfg) != "vostok":
            return        # пустой или чужой printer.cfg (например, пример KIAUH) не источник подсказок
        mcus = self._list_mcus(cfg)
        text = "".join("%s\t%s\t%s\n" % m for m in mcus)
        names = [m[0] for m in mcus]
        inc = _first_include(cfg)
        if not self.opts.main:
            self.opts.main = self.guess_main_board(text, inc)
        if not self.opts.heads:
            if any(n.startswith("mcu T0_EBB") for n in names):
                self.opts.heads = "ebb42"
            elif any(n.startswith("mcu T0CB") for n in names):
                self.opts.heads = "v2" if ("H36v2" in inc or "h36v2" in inc) else "v1.3"
            elif text and "can" not in text.lower():
                self.opts.heads = "none"
        if not self.opts.alps and text:
            self.opts.alps = str(min(sum(1 for n in names if n.startswith("mcu alps")), 2))

    @staticmethod
    def _list_mcus(cfg: Path) -> List[Tuple[str, str, str]]:
        try:
            return cfgfile.list_mcus(cfg)
        except (VostokError, OSError):
            return []

    def collect_mcu_state(self) -> None:
        """Значения [mcu …] для новых секций: из printer.cfg, затем из devices.tsv и /dev/serial/by-id.
        Чего нет - остаётся пустым (в блоке будет ЗАПОЛНИТЕ, такие секции в printer.cfg не добавляются)."""
        hw, res = self.hw, self.mcu
        mcus = self._list_mcus(self.printer_cfg) if cfgfile.cfg_state(self.printer_cfg) == "vostok" else []
        for name, key, val in mcus:
            if name == "mcu":
                if key == "canbus_uuid":
                    res.bridge_uuid = val
                else:
                    res.main_serial = serial_from_path(val)
            elif name == "mcu " + hw.head_mcu[0]:
                res.head_uuid[0] = val
            elif name == "mcu " + hw.head_mcu[1]:
                res.head_uuid[1] = val
            elif name == "mcu alps":
                res.alps_serial[0] = serial_from_path(val)
            elif name == "mcu alps_t1":
                res.alps_serial[1] = serial_from_path(val)
        byid = self.env.byid_dir
        if hw.mode == "usb" and not res.main_serial:
            found = byid_find(byid, "usb-Klipper_%s_*" % hw.main)
            if found:
                res.main_serial = serial_from_path(found[0])
        if hw.mode == "bridge":
            if not res.bridge_uuid:
                p = self.reg.cfg_path(hw.main_board, "bridge")
                keys = self.prev_keys(p.name if p else "")
                res.bridge_uuid = keys[0] if keys else ""
            if not res.head_uuid[0] or not res.head_uuid[1]:
                keys = self.prev_keys(hw.head_cfg_name()) + ["", ""]
                res.head_uuid[0] = res.head_uuid[0] or keys[0]
                res.head_uuid[1] = res.head_uuid[1] or keys[1]
        for i, f in enumerate(byid_find(byid, "usb-Klipper_stm32f072xb_*")):
            s = serial_from_path(f)
            if i < hw.alps_count and not res.alps_serial[i] and s not in res.alps_serial:
                res.alps_serial[i] = s

    def blocks(self) -> str:
        return mcu_blocks(self.hw, self.mcu)

    # --- драйверы и генерация

    def drv_pick(self, question: str) -> str:
        """Тип драйвера по вопросу: 2130|2208|2209|2240|5160|5160plus (по умолчанию 2240)."""
        labels = [lbl for _, lbl in DRV_LABELS]
        ans = ui.ask_choice(question, dict(DRV_LABELS)["2240"], labels)
        for kind, lbl in DRV_LABELS:
            if lbl == ans:
                return kind
        return "2240"

    def drivers_wizard(self) -> None:
        """Пошаговый выбор драйверов: «все одинаковые» или по каждому мотору. Результат в drivers_spec."""
        if self.opts.drivers:
            self.drivers_spec = self.opts.drivers
            return
        if ui.opts.yes or not ui.have_tty():
            self.drivers_spec = DRIVER_DEFAULT_SPEC
            ui.info("Драйверы моторов: как в стоковом конфиге (%s). Другие задаются опцией --drivers." % self.drivers_spec)
            return
        ui.info("")
        tmpl = self._board_field("TEMPLATE")
        if tmpl and tmpl != "octopus_pro":
            ui.info("Драйверы моторов. Пины драйверов подставятся по разъёмам платы (пресет), ток и режимы берутся из стокового конфига.")
        else:
            ui.info("Драйверы моторов. Пины драйверов останутся пустыми, ток и режимы берутся из стокового конфига.")
        if self.hw.heads != "none":
            ui.info("Драйверы экструдеров не спрашиваю: на платах голов распаян TMC2209, он берётся из пресета платы.")
        same_lbl, diff_lbl = "Все драйверы одинаковые", "Разные драйверы"
        mode = ui.ask_choice("Какие драйверы стоят на плате?", same_lbl, [same_lbl, diff_lbl])
        if mode == same_lbl:
            self.drivers_spec = "all=%s" % self.drv_pick("Тип драйверов:")
            return
        motors = ["x", "w", "yl", "yr", "z"]
        if self.hw.heads == "none":
            motors = ["e0", "e1"] + motors
        self.drivers_spec = ",".join("%s=%s" % (m, self.drv_pick("Драйвер %s:" % MOTOR_QUESTIONS[m])) for m in motors)

    def stock_electronics(self, root: Path) -> str:
        """Стоковый main-файл электроники (для платы с ELEC_PATTERN=_h723_ - с _h723_ в имени) из корня конфигов."""
        files = sorted(f for f in glob.glob(os.path.join(glob.escape(str(root)), "electronics_*.cfg")) if os.path.isfile(f))
        if self._board_field("ELEC_PATTERN") == "_h723_":
            for f in files:
                if "_h723_" in os.path.basename(f):
                    return f
        return files[0] if files else ""

    def find_reference(self, root: Path) -> None:
        """Эталон для подстановки пинов и параметров: свой конфиг пользователя (активный include electronics_*.cfg
        в printer.cfg) всегда основа (если он не от другой платы); стоковый main - только при чистой установке,
        для платы с ELEC_PATTERN=_h723_. Результат: ref_cfg (путь или пусто) и ref_kind (user|stock|none)."""
        self.ref_cfg, self.ref_kind = "", "none"
        ref = self.opts.reference
        if ref == "none":
            return
        if ref:
            if not os.path.isfile(ref):
                raise VostokError("--reference: файл не найден: %s" % ref)
            self.ref_cfg, self.ref_kind = ref, "user"
            return
        cfg = self.printer_cfg
        if cfg.is_file() and (self.cfg_state or "vostok") == "vostok":
            inc = _first_include(cfg)
            user_file = self.env.printer_cfg_dir / inc
            if inc and user_file.is_file():
                if self.el_for_board(inc):
                    self.ref_cfg, self.ref_kind = str(user_file), "user"
                    return
                ui.warn("Ваш текущий конфиг электроники %s сделан не под %s: пины моторов и драйверов в нём, скорее "
                        "всего, другие." % (inc, self.hw.main_label()))
                if ui.have_tty() and ui.ask_yn("Взять пины и параметры из %s?" % inc, "n"):
                    self.ref_cfg, self.ref_kind = str(user_file), "user"
                    return
                ui.info("Пины из %s не берутся (чтобы взять: --reference %s)" % (inc, user_file))
        if self._board_field("ELEC_PATTERN") == "_h723_":
            stock = self.stock_electronics(root)
            if stock:
                self.ref_cfg, self.ref_kind = stock, "stock"

    def _gen_naming(self) -> Tuple[str, str]:
        """(название платы, часть имени файла) для генератора: старые имена (CFG == чип) - из electronics,
        остальные - название платы и её id с «_»."""
        b = self.hw.board
        if b.cfg == b.chip:
            alias = b.alias_list[0] if b.alias_list else ""
            name, fname = board_naming(self.reg, alias)
            if not name:
                _eecho("для платы %r нужны --board-name и --board-file" % alias)
                raise VostokError("не удалось сгенерировать конфиг электроники")
            return name, fname
        return b.label, self.hw.main_board.replace("-", "_")

    def gen_custom_electronics(self, root: Path, outdir: Path) -> str:
        """Генерирует electronics_*.cfg по шаблону; возвращает имя файла (по образцу user_configs)."""
        hw = self.hw
        main_std = self.stock_electronics(root)
        self.find_reference(root)
        if not self.env.templates_dir.is_dir():
            raise VostokError("нет каталога шаблонов: %s" % self.env.templates_dir)
        template = self._board_field("TEMPLATE")
        octopus_extruders = octopus_heads = False
        if template == "octopus_pro":
            octopus_extruders = self._board_field("ELEC_PATTERN") == "_h723_"
            octopus_heads = hw.heads == "none"
        board_name, board_file = self._gen_naming()
        if self.ref_kind == "user":
            ui.info("Основа - ваш текущий конфиг электроники: %s (пины и параметры берутся из него)" % self.ref_cfg)
        elif self.ref_kind == "stock":
            ui.info("Чистая установка: пины и параметры моторов берутся из стокового конфига main (%s)"
                    % os.path.basename(self.ref_cfg))
        elif template and template != "octopus_pro":
            ui.info("Эталонного конфига нет: пины моторов и драйверов возьму из пресета платы %s" % hw.main_label())
        else:
            ui.info("Эталонного конфига нет: пины моторов и драйверов останутся пустыми")
        gen_opts = GenOptions(
            templates=str(self.env.templates_dir), board_name=board_name, board_file=board_file,
            ref_cfg=self.ref_cfg, main_cfg=main_std, octopus_extruders=octopus_extruders, octopus_heads=octopus_heads,
            heads=hw.heads, head_template=hw.head_field("TEMPLATE") if hw.has_heads else "",
            head_names="%s,%s" % (hw.head_mcu[0], hw.head_mcu[1]), alps=hw.alps_count,
            drivers=self.drivers_spec, template=template or "none", out_dir=str(outdir))
        try:
            self.gen = Generator(gen_opts).generate()
        except (ElectronicsError, OSError) as e:
            _eecho(str(e))
            raise VostokError("не удалось сгенерировать конфиг электроники")
        g = self.gen
        ui.ok("конфиг электроники сгенерирован: %s (драйверы: %s)" % (g.name, self.drivers_spec))
        fill_messages = (
            ("ref", "  подставлено пинов из эталона: %d"),
            ("octopus", "  подставлено пинов экструдеров на разъёмы MOTOR4 (E0) и MOTOR5 (E1): %d"),
            ("board", "  подставлено пинов по разъёмам %s (пресет, плата не проверена на железе): %%d" % hw.main_label()),
        )
        for src, fmt in fill_messages:
            if g.fill.get(src, 0) > 0:
                ui.info(fmt % g.fill[src])
        return g.name

    def print_gen_warnings(self, fname: str) -> None:
        """Итоговые предупреждения после генерации: пустые пины, откуда взяты пины, что проверить."""
        g = self.gen
        empty = g.empty if g else []
        n = len(empty)
        if n > 0:
            ui.warn("Сгенерирован %s: Klipper не запустится, пока вы не впишете пины." % fname)
        else:
            ui.warn("Сгенерирован %s: пустых пинов нет, но проверьте проводку и параметры." % fname)
        tmpl = self._board_field("TEMPLATE")
        if self.ref_kind == "user":
            _eecho("  0. Пины и параметры взяты из вашего конфига (%s): проверьте, что драйверы стоят в тех же разъёмах."
                   % os.path.basename(self.ref_cfg))
        elif self.ref_kind == "none":
            if tmpl and tmpl != "octopus_pro":
                _eecho("  0. Пины взяты по разъёмам %s (таблица в шапке файла, плата не проверена на железе): сверьте с "
                       "проводкой, знаки dir_pin проверьте после запуска." % self.hw.main_label())
                ui.pinout_hint(self.reg, self.hw.main_board, "     ", _eecho)
        elif self.ref_kind == "stock":
            _eecho("  0. Пины моторов и драйверов взяты из стокового конфига main (X: MOTOR2, W: MOTOR0, YL: MOTOR3, "
                   "YR: MOTOR1, Z: MOTOR7%s): проверьте, что драйверы стоят в этих разъёмах."
                   % (", экструдеры: MOTOR4 и MOTOR5" if self.hw.heads == "none" else ""))
        if n > 0:
            _eecho("  1. Впишите пины по схеме СВОЕЙ платы (пустых пинов: %d). Они помечены ЗАПОЛНИТЕ:" % n)
            ui.pinout_hint(self.reg, self.hw.main_board, "     ", _eecho)
            lines: List[str] = []
            sec = None
            for s, opt in empty:
                if s != sec:
                    sec = s
                    lines.append("       [%s]: %s" % (s, opt))
                else:
                    lines[-1] += ", %s" % opt
            _eecho("\n".join(lines))
        _eecho("  2. Проверьте параметры моторов (run_current, stealthchop_threshold, interpolate): они взяты из эталонного "
               "конфига (по умолчанию ваш; для чистой установки стоковый main под TMC2240),\n"
               "     у вашего драйвера и мотора они могут быть другими. sense_resistor выставлен по документации BTT "
               "(5160 и 5160T Pro 0.075, 5160T Plus 0.022, 2130/2208/2209 0.110); если у вас другой модуль, исправьте.\n"
               "  3. Проверьте направления моторов (знак ! у dir_pin) и full_steps_per_rotation после первого запуска.\n"
               "  4. Если используете chamber_heater.cfg, проверьте, что его пины не пересекаются с вашей проводкой.")
        for w in (g.all_warnings() if g else []):
            ui.warn(w)

    # --- слияние [mcu] и выбор electronics

    def merge_mcus_into_cfg(self, cfg: Path, blocks_text: str, dry: bool) -> None:
        """Режим «Пропустить редактирование конфига»: дописывает недостающие [mcu …] в существующий printer.cfg."""
        results = cfgfile.merge_mcus(cfg, blocks_text, dry=dry, backup=True)
        added = False
        for r in results:
            a = r.args
            if r.kind == "ADD":
                added = added or not dry
                ui.ok("[%s] добавлена в %s%s" % (r.name, cfg.name, " (dry-run: запись не выполнена)" if dry else ""))
            elif r.kind == "OK":
                ui.info("[%s] уже есть в конфиге%s" % (r.name, " (%s)" % a[0] if a and a[0] else ""))
            elif r.kind == "DIFF":
                ui.warn("[%s]: в конфиге %s: %s, а прошито: %s. Файл не менял, проверьте вручную"
                        % (r.name, a[0], a[1], a[2]))
            elif r.kind == "TODO":
                ui.warn("[%s]: плата не прошита, секцию не добавляю" % r.name)
        if added:
            ui.info("Резервная копия: %s.bak-*" % cfg)

    def pick_electronics(self, root: Path, allow_skip: bool) -> Tuple[str, str]:
        """Выбор electronics_*.cfg: сначала источник (корень main или user_configs), затем файл.
        Возвращает (источник standard|user|generate|skip, имя файла или "")."""
        std = sorted(os.path.basename(f) for f in glob.glob(os.path.join(glob.escape(str(root)), "electronics_*.cfg"))
                     if os.path.isfile(f))
        usr = sorted(os.path.basename(f) for f in glob.glob(os.path.join(glob.escape(str(root)), "user_configs", "electronics_*.cfg"))
                     if os.path.isfile(f))
        if not (std or usr or (root / "installer" / "templates").is_dir() or (self.env.install_dir / "templates").is_dir()):
            raise VostokError("в архиве нет electronics_*.cfg")
        wanted = self.opts.electronics
        if wanted:      # явно заданный файл: ищем в обоих каталогах
            if wanted in std:
                return "standard", wanted
            if wanted in usr:
                return "user", wanted
            raise VostokError("файл %s не найден ни в корне main, ни в user_configs" % wanted)
        src = self._ask_source(std, usr, allow_skip)
        if src in ("skip", "generate"):
            return src, ""
        if src == "standard" and not std:
            raise VostokError("в корне main нет electronics_*.cfg; используйте --config-source user")
        if src == "user" and not usr:
            raise VostokError("в user_configs нет electronics_*.cfg")
        names = std
        if src != "standard":
            names = usr
            ui.warn("user_configs: конфиги ведут пользователи. Перед использованием сверьте схему подключения в начале "
                    "файла с вашей проводкой: неверная схема может вывести электронику из строя.")
        labels = [f if self.el_matches(f) else "%s (другая плата)" % f for f in names]
        default = next((lbl for f, lbl in zip(names, labels) if self.el_matches(f)), "")
        if not default:
            if ui.opts.yes:
                raise VostokError("в %s нет electronics-файла под %s: выберите файл вручную или используйте "
                                  "--config-source generate" % (src, self.hw.main_label()))
            default = labels[0]
        ans = ui.ask_choice("Файл электроники (распиновка плат):", default, labels)
        for f, lbl in zip(names, labels):
            if lbl == ans:
                return src, f
        raise VostokError("файл электроники не выбран")

    def _ask_source(self, std: List[str], usr: List[str], allow_skip: bool) -> str:
        """Источник конфига: из --config-source или из меню."""
        if self.opts.config_source:
            if self.opts.config_source == "skip" and not allow_skip:
                raise VostokError("--config-source skip: printer.cfg ещё не существует, пропускать нечего")
            return self.opts.config_source
        labs = ([SRC_LBL_STD] if std else []) + ([SRC_LBL_USR] if usr else []) + [SRC_LBL_GEN]
        if allow_skip:
            labs.append(SRC_LBL_SKIP)
        def_src = "user"
        any_match = False
        for f in std:
            if self.el_matches(f):
                def_src, any_match = "standard", True
        for f in usr:
            if self.el_matches(f):
                any_match = True
        if not std:
            def_src = "user"
        if not usr:
            def_src = "standard"
        # ни один готовый файл не сделан под эту плату: по умолчанию свой конфиг, чужую распиновку не предлагаем
        if allow_skip:
            def_lbl = SRC_LBL_SKIP
        elif not any_match:
            def_lbl = SRC_LBL_GEN
        elif def_src == "standard" and std:
            def_lbl = SRC_LBL_STD
        elif usr:
            def_lbl = SRC_LBL_USR
        else:
            def_lbl = SRC_LBL_GEN
        ui.info("")
        ui.info("Конфиг электроники можно взять из репозитория vostok_configuration:")
        if std:
            ui.info("  - стандартный: корень main, поддерживается автором (%s);" % " ".join(std))
        if usr:
            ui.info("  - пользовательский: каталог user_configs, конфиги пользователей (%d шт.), могут не совпадать с документацией;" % len(usr))
        ui.info("  - сгенерировать свой: шаблон без плат и драйверов + пресеты найденных плат, пины драйверов и моторов вы впишете сами;")
        if allow_skip:
            ui.info("  - пропустить: printer.cfg уже есть, будут дописаны только недостающие секции [mcu ...].")
        ans = ui.ask_choice("Откуда взять конфиг?", def_lbl, labs)
        return {SRC_LBL_USR: "user", SRC_LBL_GEN: "generate", SRC_LBL_SKIP: "skip"}.get(ans, "standard")

    def sync_head_names(self, file: Path) -> None:
        """Имена секций [mcu …] плат голов берём из electronics-файла (он ссылается на них как T0CB:PA1, T0_EBB:PB3 …)."""
        hw = self.hw
        if hw.heads == "none":
            return
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        found = set()
        for ln in text.split("\n"):
            if re.match(r"^\s*#", ln):
                continue
            found.update(m[:-1] for m in re.findall(r"\bT[01][A-Za-z0-9_]+:", ln))
        names = sorted(found)
        n0 = next((n for n in names if n.startswith("T0")), "")
        n1 = next((n for n in names if n.startswith("T1")), "")
        if n0 and n1 and (n0 != hw.head_mcu[0] or n1 != hw.head_mcu[1]):
            ui.warn("в %s платы голов называются %s и %s (по умолчанию: %s и %s); использую имена из файла"
                    % (file.name, n0, n1, hw.head_mcu[0], hw.head_mcu[1]))
            hw.head_mcu = [n0, n1]

    # --- запись конфигурации

    def local_cfg_root(self) -> Optional[Path]:
        """Каталог с printer.cfg/printer_base.cfg/electronics_*.cfg; None - нужно скачать."""
        mode = self.env.cfg_local
        if mode in ("0", "no", "off"):
            return None
        root = self.env.install_dir.parent if mode == "auto" else Path(mode)
        return root if (root / "printer.cfg").is_file() and (root / "printer_base.cfg").is_file() else None

    def _config_root(self, local_root: Optional[Path], tmp: Path) -> Path:
        if local_root:
            ui.info("Конфигурация берётся из локального клона: %s" % local_root)
            return local_root
        cfg_root = tmp / "src"
        _fetch_tarball(self.env.cfg_tarball, cfg_root, tmp)
        if not ((cfg_root / "printer.cfg").is_file() and (cfg_root / "printer_base.cfg").is_file()):
            raise VostokError("в архиве нет printer.cfg/printer_base.cfg")
        return cfg_root

    def _report_cfg_state(self) -> None:
        d = self.env.printer_cfg_dir
        if self.cfg_state == "vostok":
            ui.info("%s/printer.cfg уже существует: заменю только электронику, остальное оставлю как есть" % d)
        elif self.cfg_state == "blank":
            ui.warn("%s/printer.cfg пустой: считаю это чистой установкой (всё из main)" % d)
        elif self.cfg_state == "foreign":
            ui.warn("%s/printer.cfg не похож на конфиг VOSTOK (нет [include printer_base.cfg]): считаю это чистой "
                    "установкой (всё из main), прежний файл сохраню в *.bak" % d)

    def stage_config(self) -> None:
        """Этап «Конфигурация принтера»: выбор источника, генерация, запись файлов, модули, проверка пинов."""
        ui.step("Конфигурация принтера")
        blocks = self.blocks()
        local_root = self.local_cfg_root()
        self.cfg_state = cfgfile.cfg_state(self.printer_cfg)
        has_cfg = self.cfg_state == "vostok"      # существующий конфиг: меняем только электронику; иначе чистая установка
        dry = ui.opts.dry_run
        if dry and not local_root:
            ui.info("[dry-run] взял бы конфигурацию из %s, скопировал printer.cfg, printer_base.cfg, chamber_heater.cfg, "
                    "electronics_*.cfg, postprocessing/ в %s" % (self.env.cfg_tarball, self.env.printer_cfg_dir))
            _echo(blocks)
            return
        with tempfile.TemporaryDirectory(prefix="vostok-cfg-") as tmp_s:
            tmp = Path(tmp_s)
            cfg_root = self._config_root(local_root, tmp)
            self._report_cfg_state()
            # Без терминала и без --config-source существующий конфиг не трогаем (только дописываем [mcu])
            if has_cfg and not self.opts.config_source and not ui.opts.yes and not ui.have_tty():
                self.opts.config_source = "skip"
            self.el_src, self.el_name = self.pick_electronics(cfg_root, has_cfg)
            if self.el_src == "skip":
                self.merge_mcus_into_cfg(self.printer_cfg, blocks, dry)
                self.stage_modules(cfg_root)
                return
            if self.el_src == "generate":
                self.drivers_wizard()
                self.el_name = self.gen_custom_electronics(cfg_root, tmp)
                src_dir = tmp
            else:
                src_dir = cfg_root / "user_configs" if self.el_src == "user" else cfg_root
                self.sync_head_names(src_dir / self.el_name)
            blocks = self.blocks()
            if dry:
                self._dry_run_report(has_cfg, blocks)
                self.stage_modules(cfg_root)
                return
            self._write_config(cfg_root, src_dir, has_cfg, blocks)
            self.stage_modules(cfg_root)
        self._finish_config()

    def _dry_run_report(self, has_cfg: bool, blocks: str) -> None:
        el = self.el_name
        if has_cfg:
            ui.info("[dry-run] существующий конфиг: записал бы %s (источник: %s) и заменил в printer.cfg только [mcu ...] и "
                    "[include electronics_...]; printer.cfg и %s сохранились бы как *.bak-<дата>; printer_base.cfg, "
                    "chamber_heater.cfg, postprocessing/ не тронул бы (докопировал только отсутствующие)"
                    % (el, self.el_src, el))
        else:
            ui.info("[dry-run] чистая установка: записал бы в %s из main printer.cfg, printer_base.cfg, chamber_heater.cfg, "
                    "postprocessing/ и %s (источник: %s)" % (self.env.printer_cfg_dir, el, self.el_src))
            if self.cfg_state != "none":
                ui.info("[dry-run] прежние файлы сохранились бы как *.bak-<дата>")
        _echo(blocks)
        if self.gen:
            self.print_gen_warnings(el)

    def _write_config(self, cfg_root: Path, src_dir: Path, has_cfg: bool, blocks: str) -> None:
        """Копирование файлов в printer_data/config с резервными копиями и правка printer.cfg."""
        dst = self.env.printer_cfg_dir
        el = self.el_name
        try:
            dst.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            if has_cfg:
                for f in ("printer.cfg", el):
                    cfgfile.backup_file(dst / f, stamp)
                ui.info("Прежние printer.cfg и %s сохранены как *.bak-%s" % (el, stamp))
                # существующий конфиг: файлы пользователя не трогаем, докладываем только отсутствующие
                for f in ("printer_base.cfg", "chamber_heater.cfg"):
                    if (cfg_root / f).is_file() and not (dst / f).exists():
                        shutil.copy(str(cfg_root / f), str(dst))
                if (cfg_root / "postprocessing").is_dir() and not (dst / "postprocessing").is_dir():
                    _copy_tree(cfg_root / "postprocessing", dst)
                shutil.copy(str(src_dir / el), str(dst))
            else:
                for f in ("printer.cfg", "printer_base.cfg", "chamber_heater.cfg", el):
                    cfgfile.backup_file(dst / f, stamp)
                if self.cfg_state != "none":
                    ui.warn("прежние файлы сохранены как *.bak-%s" % stamp)
                shutil.copy(str(cfg_root / "printer_base.cfg"), str(dst))
                if (cfg_root / "chamber_heater.cfg").is_file():
                    shutil.copy(str(cfg_root / "chamber_heater.cfg"), str(dst))
                shutil.copy(str(src_dir / el), str(dst))
                if (cfg_root / "postprocessing").is_dir():
                    _copy_tree(cfg_root / "postprocessing", dst)
                shutil.copy(str(cfg_root / "printer.cfg"), str(dst))
        except OSError as e:
            raise VostokError("не удалось записать конфигурацию в %s: %s" % (dst, e))
        # В готовый printer.cfg: заменить набор [mcu ...] и строку [include electronics_...]. SAVE_CONFIG и остальное
        # не меняется. Существующий printer.cfg пользователя берётся из каталога конфига, при чистой установке - из main.
        cfgfile.rewrite_printer_cfg(dst / "printer.cfg", el, blocks)

    def _finish_config(self) -> None:
        """Итог после записи: сообщение, предупреждения генератора, пересечения пинов."""
        el = self.el_name
        source = {"user": "user_configs", "generate": "сгенерирован"}.get(self.el_src, "корень main")
        ui.ok("конфигурация записана в %s (electronics: %s, источник: %s)" % (self.env.printer_cfg_dir, el, source))
        if self.gen:
            self.print_gen_warnings(el)
        elif self.hw.heads == "none":
            ui.warn("в %s могут быть включены платы голов по CAN. Без них адаптируйте этот файл под вашу проводку "
                    "(гайд, раздел «Конфигурация», п. 3)" % el)
        self.report_pin_conflicts(self.printer_cfg)
        if self.show_pinouts:
            print_pinouts(self.reg, self.hw)

    # --- пины и модули

    @staticmethod
    def _conflicts(cfg: Path) -> List[str]:
        try:
            return [r.line() for r in cfgfile.pin_conflicts(cfg)]
        except (VostokError, OSError):
            return []

    @staticmethod
    def _print_conflicts(lines: Sequence[str]) -> None:
        for ln in lines:
            parts = ln.split("\t")
            _eecho("  - %s: %s" % (parts[1], parts[2] if len(parts) > 2 else ""))

    def report_pin_conflicts(self, cfg: Path) -> None:
        """Повторяющиеся пины в конфиге: печатает предупреждения."""
        if not cfg.is_file():
            return
        lines = self._conflicts(cfg)
        if not lines:
            return
        ui.warn("в конфиге есть пины, которые используются сразу в нескольких секциях (Klipper не запустится):")
        self._print_conflicts(lines)
        ui.pinout_hint(self.reg, self.hw.main_board, "  ", _eecho)

    def module_wanted(self, name: str, label: str, file: str) -> bool:
        """Ответ на вопрос про модуль. --modules: all|none|имена через запятую (без .cfg)."""
        listed = self.opts.modules.split(",")
        if "all" in listed or name in listed:
            return True
        if "none" in listed:
            return False
        if self.opts.modules or ui.opts.yes or not ui.have_tty():
            return False
        return ui.ask_yn("Подключить дополнительный модуль: %s (%s)?" % (label, file), "n")

    def new_module_conflicts(self, file: str, src: Path) -> List[str]:
        """Пересечения пинов, которые появятся после подключения модуля (сравнение конфига с модулем и без него)."""
        with tempfile.TemporaryDirectory(prefix="vostok-mod-") as td:
            tmpcfg = Path(td)
            for f in glob.glob(os.path.join(glob.escape(str(self.env.printer_cfg_dir)), "*.cfg")):
                shutil.copy(f, str(tmpcfg))
            if not (self.env.printer_cfg_dir / file).exists():
                shutil.copy(str(src), str(tmpcfg / file))
            before = self._conflicts(tmpcfg / "printer.cfg")
            cfgfile.module_add_include(tmpcfg / "printer.cfg", file)
            after = self._conflicts(tmpcfg / "printer.cfg")
        return sorted(ln for ln in set(after) if ln and ln not in set(before))

    def stage_modules(self, root: Path) -> None:
        """Спрашивает про каждый дополнительный модуль, проверяет пересечения пинов с вашей проводкой и подключает."""
        cfg = self.printer_cfg
        dst = self.env.printer_cfg_dir
        dry = ui.opts.dry_run
        if dry and not cfg.is_file():
            ui.info("[dry-run] после записи конфига спросил бы про дополнительные модули: %s"
                    % " ".join(f for f, _ in CFG_MODULES))
            return
        if not cfg.is_file():
            ui.info("printer.cfg нет, дополнительные модули не настраиваю")
            return
        backed_up = False
        for file, label in CFG_MODULES:
            name = file[:-len(".cfg")] if file.endswith(".cfg") else file
            if cfgfile.module_state(cfg, file) == "active":
                ui.info("Модуль %s: уже подключён (%s)" % (label, file))
                continue
            src = dst / file
            if not src.is_file():
                src = root / file
            if not src.is_file():
                ui.warn("модуль %s: файл %s не найден (ни в %s, ни в %s)" % (label, file, dst, root))
                continue
            if not self.module_wanted(name, label, file):
                ui.info("Модуль %s: не подключаю (позже: --modules %s)" % (label, name))
                continue
            new = self.new_module_conflicts(file, src)
            if new:
                ui.warn("модуль %s использует пины, уже занятые вашей проводкой:" % label)
                self._print_conflicts(new)
                if ui.opts.yes or not ui.have_tty():
                    ui.warn("модуль %s не подключён из-за пересечения пинов (измените пины и подключите позже: --modules %s)"
                            % (label, name))
                    continue
                if not ui.ask_yn("Всё равно подключить %s (пины придётся поменять вручную)?" % file, "n"):
                    ui.info("Модуль %s не подключён" % label)
                    continue
            if dry:
                ui.info("[dry-run] подключил бы модуль %s (%s)" % (label, file))
                continue
            if not backed_up:
                cfgfile.backup_file(cfg)
                backed_up = True
            if not (dst / file).exists():
                shutil.copy(str(src), str(dst / file))
            cfgfile.module_add_include(cfg, file)
            ui.ok("Модуль %s подключён: [include %s] в printer.cfg" % (label, file))


# ------------------------------------------------------------------ командная строка

def installer_version(install_dir: Path = INSTALL_DIR) -> str:
    """Версия установщика: первая строка файла VERSION без пробелов (``неизвестна``, если файла нет)."""
    try:
        with open(install_dir / "VERSION", encoding="utf-8") as f:
            v = "".join(f.readline().split())
    except OSError:
        v = ""
    return v or "неизвестна"


class _Parsed:
    """Результат разбора командной строки: опции, окружение, флаги ui."""

    def __init__(self, opts: Options, env: Env, yes: bool, dry: bool) -> None:
        self.opts, self.env, self.yes, self.dry = opts, env, yes, dry


_VALUE_OPTIONS = {"--main": "main", "--heads": "heads", "--alps": "alps", "--config-source": "config_source",
                  "--electronics": "electronics", "--drivers": "drivers", "--reference": "reference",
                  "--modules": "modules"}


def parse_args(argv: Sequence[str], env: Env, reg: Registry, runner: Optional[Runner] = None) -> Optional[_Parsed]:
    """Разбор опций configure_vostok.sh. None - уже напечатана справка/версия (код 0). Ошибки - VostokError."""
    opts = Options()
    yes = dry = False
    args = list(argv)
    ui.set_options(False, False, env.effective_log_file)
    i = 0
    while i < len(args):
        a = args[i]
        if a in _VALUE_OPTIONS:
            if i + 1 >= len(args):
                raise VostokError("%s требует аргумент" % a)
            setattr(opts, _VALUE_OPTIONS[a], args[i + 1])
            i += 1
        elif a == "--printer-data":
            if i + 1 >= len(args):
                raise VostokError("--printer-data требует аргумент")
            env.printer_data = Path(args[i + 1])
            env.log_file = None
            ui.set_options(yes, dry, env.effective_log_file)
            i += 1
        elif a == "--dry-run":
            dry = True
        elif a in ("-y", "--yes"):
            yes = True
        elif a in ("-V", "--version"):
            print("VOSTOK installer %s" % installer_version(env.install_dir))
            return None
        elif a in ("-h", "--help"):
            sys.stdout.write(USAGE)
            return None
        else:
            sys.stderr.write(USAGE)
            raise VostokError("неизвестная опция: %s" % a)
        i += 1
    if opts.main:
        HardwareDetector(opts, env, reg, runner).board_from_opt(opts.main)
    if opts.heads:
        opts.heads = reg.head_value(opts.heads)      # допустимые головы - из реестра (ROLE=head), значение каноническое
    if opts.config_source not in ("",) + CONFIG_SOURCES:
        raise VostokError("--config-source: standard, user, generate или skip")
    if opts.alps not in ("", "0", "1", "2"):
        raise VostokError("--alps: 0, 1 или 2")
    ui.set_options(yes, dry, env.effective_log_file)
    return _Parsed(opts, env, yes, dry)


def main(argv: Optional[Sequence[str]] = None, environ=None, reg: Optional[Registry] = None,
         runner: Optional[Runner] = None) -> int:
    """Команда ``configure``: настройка конфига принтера без установки и прошивки (configure_vostok.sh)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    env = Env.from_environ(environ)
    reg = reg or default_registry()
    parsed = parse_args(argv, env, reg, runner)
    if parsed is None:
        return 0
    opts = parsed.opts
    version = installer_version(env.install_dir)
    if not env.printer_data.is_dir():      # проверка до создания каталога журнала: опечатка в пути не создаёт каталог
        raise VostokError("нет каталога %s (укажите --printer-data)" % env.printer_data)
    ui.log("=== configure_vostok.sh %s: %s ===" % (version, " ".join(argv)))
    ui.step("Настройка конфига VOSTOK (версия %s)" % version)
    ui.info("Каталог конфига: %s" % env.printer_cfg_dir)

    probe_runner = runner or Runner(dry_run=False)
    # hw ещё не определено: конфигуратору для подсказок нужна только плата, поэтому создаём временное железо
    cfgr = Configurator(opts, env, reg, Hardware(reg), probe_runner)
    cfgr.guess_from_printer_cfg()
    hw = HardwareDetector(opts, env, reg, probe_runner).detect()
    cfgr.hw = hw
    ui.info("Главная плата: %s, платы голов: %s, ALPS: %d"
            % (hw.main_label(), "нет" if hw.heads == "none" else hw.head_label(), hw.alps_count))
    cfgr.collect_mcu_state()
    cfgr.stage_config()
    if not parsed.dry:
        ui.info("")
        ui.info("Готово. Чтобы применить конфиг, перезапустите Klipper (Fluidd: RESTART/FIRMWARE_RESTART или sudo systemctl restart klipper).")
    return 0
