"""Генерация electronics_*.cfg (бывший tools/gen_electronics.py) для конфигуратора.

Берёт шаблон без плат и драйверов (templates/electronics_blank.cfg), накладывает пресеты:
  - Octopus Pro по гайду (templates/boards/octopus_pro.cfg);
  - пресет другой главной платы (templates/boards/main/<имя>.cfg, секции @@TABLE@@ @@BASE@@ @@MOTORS@@ @@EXTRUDERS@@ @@HEADS@@);
  - платы голов H36 v1.3 / v2 или EBB42 (templates/boards/<плата>.cfg);
  - драйверы моторов (templates/drivers/tmc*.cfg, пины пустые);
  - ALPS (закомментированный блок);
ток и режимы драйверов берёт из electronics_*.cfg корня репозитория (main_cfg).

Эталон (ref_cfg): конфиг электроники пользователя (или стоковый main при чистой установке).
Из него берутся пины моторов и драйверов на основной MCU, ток и режимы драйверов и прочие пины
основной MCU, которые есть и в сгенерированном файле. Запасной источник параметров - main_cfg.

Состояние одного прогона (пины из таблицы разъёмов, текст предупреждения, название платы) живёт в
объекте Generator, а не в глобальных переменных. Результат: файл out и GenResult (имя, число подставленных
пинов, пустые пины, предупреждения). Командная строка прежняя (``python3 -m vostok.electronics …``):
в stdout строки NAME / WARN / FILL / EMPTY, как у tools/gen_electronics.py.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import VostokError

HEADER_RE = re.compile(r"^\[(.+?)\]\s*(#.*)?$")
OPT_RE = re.compile(r"^([A-Za-z0-9_]+)\s*:")
EMPTY_PIN_RE = re.compile(r"^(\w*pin)\s*:\s*(#.*)?$")
PIN_RE = re.compile(r"^[A-Za-z]{1,2}\d+$")
TODO = "ЗАПОЛНИТЕ"

MOTORS = {
    "x": "stepper motor_x", "w": "stepper motor_w", "yl": "stepper motor_yl",
    "yr": "stepper motor_yr", "z": "stepper motor_z",
    "e0": "extruder", "e1": "extruder1",
}
MOTOR_TITLE = {"x": "X", "w": "W", "yl": "Y левый", "yr": "Y правый", "z": "Z", "e0": "экструдер T0", "e1": "экструдер T1"}
# Параметры по умолчанию, если в electronics-файле main нет нужной секции (значения стокового конфига)
DEFAULT_PARAMS = {
    "x": {"run_current": "1.6", "stealthchop_threshold": "0", "interpolate": "False"},
    "w": {"run_current": "1.6", "stealthchop_threshold": "0", "interpolate": "False"},
    "yl": {"run_current": "1.6", "stealthchop_threshold": "0", "interpolate": "False"},
    "yr": {"run_current": "1.6", "stealthchop_threshold": "0", "interpolate": "False"},
    "z": {"run_current": "1.2", "stealthchop_threshold": "999999", "interpolate": "True"},
    "e0": {"run_current": "0.9", "stealthchop_threshold": "0", "interpolate": "false"},
    "e1": {"run_current": "0.7", "stealthchop_threshold": "0", "interpolate": "false"},
}
PARAM_KEYS = ("run_current", "stealthchop_threshold", "interpolate")
DRIVER_TYPES = ("2130", "2160", "2208", "2209", "2240", "5160", "5160plus")
# Имя файла пресета в templates/drivers/ для каждого типа
DRIVER_FILES = {"2130": "tmc2130", "2160": "tmc2160", "2208": "tmc2208", "2209": "tmc2209", "2240": "tmc2240",
                "5160": "tmc5160", "5160plus": "tmc5160t_plus"}
# Драйверы с малым током: для них предупреждаем, если ток из конфига под TMC2240 слишком велик
LOW_CURRENT = ("2130", "2208", "2209")
DRIVER_ALIASES = {"5160pro": "5160", "5160tpro": "5160", "5160tplus": "5160plus", "5160t_plus": "5160plus"}

SOCKET_KEYS = ("cs_pin", "uart_pin")
SPI_KEYS = ("spi_software_sclk_pin", "spi_software_mosi_pin", "spi_software_miso_pin")
STEP_KEYS = ("step_pin", "dir_pin", "enable_pin")
# SPI-пины Octopus Pro общие для всех драйверных разъёмов
OCTOPUS_SPI = {"spi_software_sclk_pin": "PA5", "spi_software_mosi_pin": "PA7", "spi_software_miso_pin": "PA6"}

# Пометка секций с пинами «из таблицы разъёмов»: для Octopus Pro (конфиги репозитория) и для пресета другой платы
SVERIT_OCTOPUS = ("# !!! СВЕРЬТЕ СО СВОЕЙ СХЕМОЙ: пины подставлены по разъёмам Octopus Pro из конфигов репозитория "
                  "(в main они на платах голов)")
SVERIT_PRESET = ("# !!! СВЕРЬТЕ СО СВОЕЙ СХЕМОЙ: пины подставлены по разъёмам %s из пресета VOSTOK "
                 "(плата не проверена на железе)")

DRIVER_TOKEN = {"2130": "2130", "2160": "2160", "2208": "2208", "2209": "2209", "2240": "2240", "5160": "5160", "5160plus": "5160tplus"}
DRIVER_TITLE = {"2130": "tmc2130", "2160": "tmc2160", "2208": "tmc2208", "2209": "tmc2209", "2240": "tmc2240", "5160": "tmc5160",
                "5160plus": "tmc5160 (T Plus)"}
HEAD_FILE = {"v1.3": "2xH36v1.3", "v2": "2xH36v2.0", "ebb42": "2xebb42"}
HEAD_TITLE = {"none": "нет (головы подключены к Octopus)", "v1.3": "2x Fysetc H36 v1.3", "v2": "2x Fysetc H36 v2.0",
              "ebb42": "2x BTT EBB42"}
# Головы, которые были до реестра голов: имена файла/заголовка и значения --heads прежние. Допустимые значения --heads
# и пресеты (поле TEMPLATE платы с ROLE=head) берутся из реестра; для остальных голов имена строятся по значению.
HEADS_CHOICES = ("none", "v1.3", "v2", "ebb42")

# Платы со старыми именами файлов (в реестре CFG == CHIP, Octopus Pro): название в шапке и часть имени файла
# по образцу user_configs. Полей NAME/FILE в формате .board нет (формат не меняется), поэтому значения здесь,
# а сама плата находится через реестр (id или алиас h723/f446). У остальных плат имена передаёт вызывающий:
# название - LABEL, часть файла - id с «_» вместо «-».
LEGACY_BOARD_NAMES = {
    "octopus-pro-h723": ("BigTreeTech Octopus Pro v1.1 H723", "octopus_pro_v1.1_h723"),
    "octopus-pro-f446": ("BigTreeTech Octopus Pro F446", "octopus_pro_v1.0_f446"),
}


class ElectronicsError(VostokError):
    """Ошибка генерации (прежний ``sys.exit("текст")`` генератора): текст идёт в stderr как есть."""


class ElectronicsUsageError(ElectronicsError):
    """Неверные аргументы (прежний ``ap.error``): командная строка отвечает кодом 2 и справкой."""


# ------------------------------------------------------------------ разбор шаблонов

class Block:
    """Секция конфига: заголовок и строки; name None - преамбула до первой секции."""

    def __init__(self, name, lines):
        self.name = name
        self.lines = lines        # строки блока, первая - заголовок (кроме преамбулы)
        self.note = None          # комментарий-предупреждение перед блоком (СВЕРЬТЕ ...)

    def find(self, key):
        for i, ln in enumerate(self.lines):
            m = OPT_RE.match(ln)
            if m and m.group(1) == key:
                return i
        return None

    def set(self, key, value_lines):
        """value_lines: строки значения (первая 'key: v', остальные - продолжение с отступом)."""
        i = self.find(key)
        if i is not None:
            j = i + 1
            while j < len(self.lines) and self.lines[j][:1] in (" ", "\t") and self.lines[j].strip():
                j += 1
            self.lines[i:j] = value_lines
            return
        # вставка после последней строки опции блока (до хвостовых пустых строк и баннеров)
        last = 0
        for k, ln in enumerate(self.lines):
            if OPT_RE.match(ln) or (ln[:1] in (" ", "\t") and ln.strip() and k > 0):
                last = k
        self.lines[last + 1:last + 1] = value_lines


def norm(name):
    return " ".join(name.split())


def split_blocks(text):
    blocks, cur = [], Block(None, [])
    for ln in text.split("\n"):
        m = HEADER_RE.match(ln)
        if m:
            blocks.append(cur)
            cur = Block(norm(m.group(1)), [ln])
        else:
            cur.lines.append(ln)
    blocks.append(cur)
    return blocks


def parse_options(lines):
    """[(ключ, [строки значения])] из строк секции (без заголовка); комментарии и пустые строки пропускаются."""
    out = []
    for ln in lines:
        if OPT_RE.match(ln):
            out.append((OPT_RE.match(ln).group(1), [ln.rstrip()]))
        elif ln[:1] in (" ", "\t") and ln.strip() and out:
            out[-1][1].append(ln.rstrip())
    return out


def parse_overlay(text, subst):
    """Секции пресета: [(имя, строки секции с заголовком, [(ключ, строки)])]."""
    for k, v in subst.items():
        text = text.replace("{" + k + "}", v)
    res = []
    for b in split_blocks(text):
        if b.name is None:
            continue
        body = b.lines[1:]
        while body and not body[-1].strip():
            body.pop()
        res.append((b.name, [b.lines[0]] + body, parse_options(body)))
    return res


def load_preset(text):
    """Пресет главной платы: {'TABLE': текст, 'BASE': ..., 'MOTORS': ..., 'EXTRUDERS': ..., 'HEADS': ...};
    шапка до первого маркера отбрасывается."""
    parts = re.split(r"^@@([A-Z]+)@@[ \t]*$", text, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def clean_value(line):
    """Значение опции из строки 'key: value # комментарий'."""
    return line.split(":", 1)[1].split("#")[0].strip()


def main_mcu_pin(value):
    """Пин основной MCU (без префикса другой MCU вида T0CB:PA8) и не пустой."""
    return bool(value) and ":" not in value


def pin_id(value):
    """Пин в виде 'MCU:PIN' (MCU 'mcu' для основной платы) или None, если это не пин."""
    v = re.sub(r"^[!^~\s]+", "", value.split("#")[0].strip())
    mcu, pin = ("mcu", v)
    if ":" in v:
        mcu, pin = (x.strip() for x in v.split(":", 1))
        pin = re.sub(r"^[!^~\s]+", "", pin)
    return "%s:%s" % (mcu, pin.upper()) if PIN_RE.match(pin) else None


def preset_motor_pins(preset, with_extruders):
    """Из секций MOTORS/EXTRUDERS пресета: ({мотор: {step/dir/enable}}, {мотор: пин разъёма драйвера}, {spi-опция: пин})."""
    by_sec = {v: k for k, v in MOTORS.items()}
    by_short = {v.replace("stepper ", ""): k for k, v in MOTORS.items()}
    step, sock, spi = {}, {}, {}
    for key in ("MOTORS", "EXTRUDERS") if with_extruders else ("MOTORS",):
        for b in split_blocks(preset.get(key, "")):
            if b.name is None:
                continue
            opts = {k: clean_value(vl[0]) for k, vl in parse_options(b.lines[1:])}
            m = re.match(r"^socket (.+)$", b.name)
            if b.name == "spi":
                spi.update(opts)
            elif m and m.group(1) in by_short:
                sock[by_short[m.group(1)]] = opts.get("pin", "")
            elif b.name in by_sec:
                step[by_sec[b.name]] = opts
            else:
                raise ElectronicsError("пресет: неизвестная секция [%s] в @@%s@@" % (b.name, key))
    return step, sock, spi


def read_params(cfg_path):
    """Параметры [tmcXXXX ...] из стандартного electronics-файла: {мотор: {опция: значение}}."""
    res = {}
    if not cfg_path or not Path(cfg_path).is_file():
        return res
    inv = {v: k for k, v in MOTORS.items()}
    for b in split_blocks(Path(cfg_path).read_text(encoding="utf-8")):
        m = re.match(r"^tmc\d+ (.+)$", b.name or "")
        if not m or m.group(1) not in inv:
            continue
        d = {}
        for key, vl in parse_options(b.lines[1:]):
            if key in PARAM_KEYS:
                d[key] = vl[0].split(":", 1)[1].split("#")[0].strip()
        res[inv[m.group(1)]] = d
    return res


def read_reference(cfg_path):
    """Эталонный electronics-файл: пины и параметры на основной MCU.
    {'step': {мотор: {опция: значение}}, 'drv': {мотор: {опция: значение}}, 'other': {(секция, опция): значение}}."""
    res = {"step": {}, "drv": {}, "other": {}}
    if not cfg_path or not Path(cfg_path).is_file():
        return res
    inv = {v: k for k, v in MOTORS.items()}
    merged = {}   # секции с одним именем (например, два [extruder]) объединяются
    for b in split_blocks(Path(cfg_path).read_text(encoding="utf-8")):
        if b.name is None:
            continue
        d = merged.setdefault(b.name, {})
        for key, vl in parse_options(b.lines[1:]):
            d[key] = clean_value(vl[0])
    for name, vals in merged.items():
        m = re.match(r"^tmc\d+ (.+)$", name)
        if name in inv:
            motor = inv[name]
            for k in STEP_KEYS:
                if main_mcu_pin(vals.get(k, "")):
                    res["step"].setdefault(motor, {})[k] = vals[k]
            for k, v in vals.items():
                if k.endswith("pin") and k not in STEP_KEYS and main_mcu_pin(v):
                    res["other"][(name, k)] = v
        elif m:
            motor = inv.get(m.group(1))
            if motor is None:
                continue
            sock = next((vals[k] for k in SOCKET_KEYS if main_mcu_pin(vals.get(k, ""))), "")
            if sock:
                d = {"socket": sock}
                for k in SPI_KEYS:
                    if main_mcu_pin(vals.get(k, "")):
                        d[k] = vals[k]
                res["drv"][motor] = d
        else:
            for k, v in vals.items():
                if k.endswith("pin") and main_mcu_pin(v):
                    res["other"][(name, k)] = v
    return res


def parse_drivers(spec, heads):
    """Строка ``all=2240,e0=2209,…`` -> {мотор: тип драйвера}; heads - платы голов есть (e0/e1 не нужны)."""
    drv = {}
    for part in filter(None, (spec or "").split(",")):
        k, _, v = part.partition("=")
        k, v = k.strip(), v.strip().lower().replace("tmc", "").replace("-", "").replace(" ", "")
        v = DRIVER_ALIASES.get(v, v)
        if k == "all":
            for m in MOTORS:
                if not (heads and m in ("e0", "e1")):
                    drv[m] = v
        elif k in MOTORS:
            drv[k] = v
        else:
            raise ElectronicsError("--drivers: неизвестный мотор %r" % k)
        if v not in DRIVER_TYPES:
            raise ElectronicsError("--drivers: драйвер %r не из %s" % (v, "/".join(DRIVER_TYPES)))
    return drv


def render(blocks, collapse_notes=False):
    out, prev_note = [], None
    for b in blocks:
        note_shown = b.note and not (collapse_notes and b.note == prev_note)
        prev_note = b.note
        if note_shown:
            # комментарий ставим перед заголовком секции, после пустой строки предыдущего блока
            while out and not out[-1].strip():
                out.pop()
            out.extend(["", b.note])
        out.extend(b.lines)
    return "\n".join(out)


def driver_groups(drv, needed):
    """[(число, тип)] по убыванию числа, затем по типу; считаются моторы, у которых драйвер выбран пользователем."""
    cnt = {}
    for m in needed:
        cnt[drv[m]] = cnt.get(drv[m], 0) + 1
    return sorted(((n, d) for d, n in cnt.items()), key=lambda x: (-x[0], x[1]))


def config_name(board_file, heads, groups):
    """Имя файла по образцу user_configs: electronics_<плата>_<N>x<драйвер>[_<N>x<драйвер>][_2x<головы>].cfg"""
    parts = ["electronics", board_file] + ["%dx%s" % (n, DRIVER_TOKEN[d]) for n, d in groups]
    if heads != "none":
        parts.append(HEAD_FILE.get(heads, "2x" + heads))
    return "_".join(parts) + ".cfg"


def board_naming(registry, main: str) -> Tuple[str, str]:
    """(название платы для шапки, часть имени файла) для платы со старыми именами по id/алиасу из реестра
    (h723, f446); ("", "") для остальных - им имена задаёт вызывающий (--board-name/--board-file)."""
    bid = registry.resolve(main) if registry is not None else None
    return LEGACY_BOARD_NAMES.get(bid, ("", "")) if bid else ("", "")


# ------------------------------------------------------------------ генератор

@dataclass
class GenOptions:
    """Параметры одного прогона (аргументы прежнего gen_electronics.py)."""
    templates: str
    board_name: str
    board_file: str
    ref_cfg: str = ""            # эталон: свой electronics-файл пользователя или стоковый main
    main_cfg: str = ""           # стоковый main-файл: запасной источник тока и режимов драйверов
    octopus_extruders: bool = False
    octopus_heads: bool = False
    heads: str = "none"
    head_template: str = ""      # пресет голов templates/boards/<имя>.cfg (поле TEMPLATE платы головы); пусто - прежний по heads
    head_names: str = "T0CB,T1CB"
    alps: int = 0
    drivers: str = ""
    template: str = "octopus_pro"   # octopus_pro | none | имя файла из templates/boards/main/ без .cfg
    out: str = ""                # выходной файл (иначе имя по образцу user_configs в out_dir)
    out_dir: str = ""


@dataclass
class GenResult:
    """Итог генерации: имя и путь файла, FILL-счётчики, пустые пины (секция без скобок, опция), предупреждения."""
    name: str
    path: Path
    fill: Dict[str, int]
    empty: List[Tuple[str, str]]
    table_warn: Optional[str] = None     # предупреждение про пины из таблицы разъёмов (идёт первым)
    warns: List[str] = field(default_factory=list)

    def all_warnings(self) -> List[str]:
        """Все WARN в порядке вывода генератора."""
        return ([self.table_warn] if self.table_warn else []) + list(self.warns)

    def protocol(self) -> List[str]:
        """Строки stdout прежнего gen_electronics.py: NAME, WARN (таблица), FILL×3, EMPTY…, WARN…"""
        out = ["NAME\t%s" % self.name]
        if self.table_warn:
            out.append("WARN\t%s" % self.table_warn)
        out.extend("FILL\t%s\t%d" % (src, n) for src, n in self.fill.items())
        out.extend("EMPTY\t[%s]\t%s" % (sec, opt) for sec, opt in self.empty)
        out.extend("WARN\t%s" % w for w in self.warns)
        return out


class Generator:
    """Один прогон генерации electronics_*.cfg. Состояние прогона (table_opts, sverit, table_src) - поля объекта."""

    def __init__(self, opts: GenOptions) -> None:
        self.o = opts
        self.t = Path(opts.templates)
        self.table_opts: List[Tuple[Block, str]] = []   # (блок, опция) пинов из таблицы разъёмов (не из эталона)
        self.table_src = "Octopus Pro"   # плата, по разъёмам которой подставлены пины (для текстов предупреждений)
        self.sverit = SVERIT_OCTOPUS
        self.mainp: Optional[Dict[str, str]] = None
        self.sense: Dict[str, str] = {}
        self.head_warn = ""          # предупреждение пресета головы (строка «# СВЕРЬТЕ: …» в шапке)
        self.octopus_heads = opts.octopus_heads
        self.octopus_extruders = opts.octopus_extruders
        self.has_heads = opts.heads != "none"
        self.drv: Dict[str, str] = {}
        self.needed: List[str] = []
        self.blocks: List[Block] = []
        self.new_drivers: List[Block] = []
        self.new_extras: List[Block] = []
        self.sverit_sections = False
        self.filled = {"ref": 0, "octopus": 0, "board": 0}

    # --- публичный вход

    def generate(self) -> GenResult:
        """Собрать файл и записать его; ElectronicsError при неверных параметрах или шаблонах."""
        self._load_main_preset()
        self._parse_driver_spec()
        self._load_blank_template()
        self._apply_presets()
        ref = read_reference(self.o.ref_cfg)
        params = self._read_driver_params()
        drv_blocks, warns = self._driver_blocks(params)
        self._fill_pins(ref, drv_blocks)
        self._replace_other_pins(ref)
        text, groups = self._render(drv_blocks, warns)
        out_lines, empty = self._mark_empty_pins(text)
        name = self.o.out and Path(self.o.out).name or config_name(self.o.board_file, self.o.heads, groups)
        out_path = Path(self.o.out) if self.o.out else Path(self.o.out_dir or ".") / name
        out_path.write_text("\n".join(out_lines), encoding="utf-8")
        return GenResult(name, out_path, dict(self.filled), empty, self._table_warning(), warns)

    # --- подготовка

    def _load_main_preset(self) -> None:
        o = self.o
        if o.template not in ("octopus_pro", "none"):
            pf = self.t / "boards/main" / (o.template + ".cfg")
            if not re.fullmatch(r"[A-Za-z0-9_.]+", o.template) or not pf.is_file():
                raise ElectronicsUsageError("нет пресета платы %r (ожидается %s)" % (o.template, pf))
            self.mainp = load_preset(pf.read_text(encoding="utf-8"))
            # SENSE: «мотор: sense_resistor» для плат со встроенными драйверами (Kraken)
            self.sense = {k.strip(): v.strip() for k, _, v in
                          (ln.partition(":") for ln in self.mainp.get("SENSE", "").splitlines()
                           if ln.strip() and not ln.lstrip().startswith("#"))}
        if o.template == "none" or self.mainp:
            self.octopus_heads = self.octopus_extruders = False
        if self.mainp:
            self.table_src = o.board_name
            self.sverit = SVERIT_PRESET % o.board_name

    def _parse_driver_spec(self) -> None:
        self.drv = parse_drivers(self.o.drivers, self.has_heads)
        self.needed = [m for m in MOTORS if not (self.has_heads and m in ("e0", "e1"))]
        missing = [m for m in self.needed if m not in self.drv]
        if missing:
            raise ElectronicsError("--drivers: не задан драйвер для %s" % ",".join(missing))

    def _load_blank_template(self) -> None:
        text = self._read_template("electronics_blank.cfg")
        if self.mainp:
            stub = "# (впишите свою распиновку)         |                   |"
            if text.count(stub) != 1:
                raise ElectronicsError("electronics_blank.cfg: не найдена строка таблицы разъёмов")
            rows = []
            for ln in self.mainp.get("TABLE", "").strip("\n").split("\n"):
                if ln.startswith("H|"):
                    if self.has_heads:
                        continue
                    ln = ln[2:]
                if ln.strip():
                    rows.append(ln)
            text = text.replace(stub, "\n".join(rows))
        self.blocks = split_blocks(text)

    def _read_template(self, rel: str) -> str:
        return (self.t / rel).read_text(encoding="utf-8")

    def _apply_presets(self) -> None:
        o = self.o
        if o.template == "octopus_pro":
            self.apply_overlay(parse_overlay(self._read_template("boards/octopus_pro.cfg"), {}))
        if self.mainp:
            self.apply_overlay(parse_overlay(self.mainp.get("BASE", ""), {}), note=self.sverit)
        if self.mainp and not self.has_heads:
            self.apply_overlay(parse_overlay(self.mainp.get("HEADS", ""), {}), note=self.sverit)
            self.sverit_sections = True
        elif not self.has_heads and self.octopus_heads and (self.t / "boards/octopus_heads.cfg").is_file():
            self.apply_overlay(parse_overlay(self._read_template("boards/octopus_heads.cfg"), {}), note=self.sverit)
            self.sverit_sections = True
        if self.has_heads:
            names = o.head_names.split(",")
            preset = self._read_template("boards/%s.cfg" % (o.head_template or ("h36_" + o.heads if o.heads != "ebb42" else "ebb42")))
            parts = re.split(r"^@@T([01])@@\s*$", preset, flags=re.M)
            m_warn = re.search(r"^# СВЕРЬТЕ: (.+)$", parts[0], flags=re.M)
            self.head_warn = m_warn.group(1).strip() if m_warn else ""
            # parts: [шапка, '0', текст T0, '1', текст T1]
            for idx in range(1, len(parts), 2):
                n = int(parts[idx])
                self.apply_overlay(parse_overlay(parts[idx + 1], {"M": names[n]}))

    def apply_overlay(self, overlay, note=None) -> None:
        """Наложить секции пресета на блоки шаблона; note помечает секции с пинами из таблицы разъёмов."""
        for name, full_lines, opts in overlay:
            targets = [b for b in self.blocks if b.name == name]
            if not targets:
                target_list = self.new_drivers if name.startswith("tmc") else self.new_extras
                existing = [b for b in target_list if b.name == name]
                if existing:
                    for key, vl in opts:
                        existing[0].set(key, vl)
                else:
                    target_list.append(Block(name, list(full_lines)))
                continue
            for key, vl in opts:
                for b in targets:
                    if b.find(key) is not None:
                        b.set(key, vl)
                        if note:
                            b.note = note
                            self.table_opts.append((b, key))
                        break
                else:
                    targets[0].set(key, vl)
                    if note:
                        targets[0].note = note
                        self.table_opts.append((targets[0], key))

    # --- драйверы

    def _read_driver_params(self):
        """Ток и режимы драйверов: стоковый main, поверх него эталон."""
        params = read_params(self.o.main_cfg)
        for m_, d_ in read_params(self.o.ref_cfg).items():
            params.setdefault(m_, {}).update(d_)
        return params

    def _driver_blocks(self, params):
        """Блоки драйверов (пустые пины из шаблона + параметры из эталона/стока) и предупреждения про ток."""
        warns = []
        drv_blocks = list(self.new_drivers)         # из пресетов голов (драйвер экструдера)
        for m in self.needed:
            d = self.drv[m]
            sec = MOTORS[m]
            tpl = self._read_template("drivers/%s.cfg" % DRIVER_FILES[d]).replace("{SEC}", sec)
            drv_blocks.extend(b for b in split_blocks(tpl) if b.name is not None)
            cur = params.get(m, DEFAULT_PARAMS[m])["run_current"]
            if d in LOW_CURRENT and float(cur) > 1.2 and m not in ("e0", "e1"):
                warns.append("%s: драйвер TMC%s, а run_current %s взят из конфига под TMC2240; уменьшите ток (обычно 0.8-1.2 А)"
                             % (MOTOR_TITLE[m], d, cur))
        for b in drv_blocks:
            m = re.match(r"^tmc\d+ (.+)$", b.name)
            motor = next((k for k, v in MOTORS.items() if v == m.group(1)), None) if m else None
            if motor is None:
                continue
            p = dict(DEFAULT_PARAMS[motor])
            p.update(params.get(motor, {}))
            if m and b.name.startswith("tmc2209") and motor in ("e0", "e1"):
                p["interpolate"] = "false"
            for key in PARAM_KEYS:
                if b.find(key) is None:
                    b.set(key, ["%s: %s" % (key, p[key])])
            sense = self.sense.get(motor)
            if sense and b.find("sense_resistor") is not None:
                b.set("sense_resistor", ["sense_resistor: %s" % sense])
        return drv_blocks, warns

    # --- пины моторов и драйверов

    def _extruder_templates(self):
        """Пины экструдеров без плат голов: (источник, {'step','socket'}, spi по умолчанию)."""
        ext_tpl = {"step": {}, "socket": {}}
        ext_src, spi_default = "octopus", (OCTOPUS_SPI if self.o.template == "octopus_pro" else {})
        if self.mainp:
            ext_src = "board"
            ext_tpl["step"], ext_tpl["socket"], spi_default = preset_motor_pins(self.mainp, not self.has_heads)
        tpl_path = self.t / "boards/octopus_extruders.cfg"
        if self.octopus_extruders and not self.has_heads and tpl_path.is_file():
            for b in split_blocks(tpl_path.read_text(encoding="utf-8")):
                if b.name in ("extruder", "extruder1"):
                    motor = "e0" if b.name == "extruder" else "e1"
                    ext_tpl["step"][motor] = {k: clean_value(vl[0]) for k, vl in parse_options(b.lines[1:])}
                elif b.name in ("socket extruder", "socket extruder1"):
                    motor = "e0" if b.name == "socket extruder" else "e1"
                    for key, vl in parse_options(b.lines[1:]):
                        if key == "pin":
                            ext_tpl["socket"][motor] = clean_value(vl[0])
        return ext_src, ext_tpl, spi_default

    def _put(self, block_list, name, key, value, src) -> bool:
        for blk in block_list:
            if blk.name == name and blk.find(key) is not None:
                blk.set(key, ["%s: %s" % (key, value)])
                self.filled[src] += 1
                if src in ("octopus", "board") and block_list is self.blocks:
                    blk.note = self.sverit
                    self.table_opts.append((blk, key))
                return True
        return False

    def _fill_pins(self, ref, drv_blocks) -> None:
        """Пины моторов и драйверов: сначала эталон, затем (экструдеры без голов) таблица разъёмов."""
        ext_src, ext_tpl, spi_default = self._extruder_templates()
        for m in self.needed:
            sec = MOTORS[m]
            src = "ref"
            steps = ref["step"].get(m)
            if not steps and m in ext_tpl["step"]:
                steps, src = ext_tpl["step"][m], ext_src
            for k, v in (steps or {}).items():
                if k in STEP_KEYS:
                    self._put(self.blocks, sec, k, v, src)
            dsrc = "ref"
            dd = ref["drv"].get(m)
            if not dd and ext_tpl["socket"].get(m):
                dd, dsrc = {"socket": ext_tpl["socket"][m]}, ext_src
            if not dd:
                continue
            for b in drv_blocks:
                if b.name.split(" ", 1)[1:] != [sec] or not re.match(r"^tmc\d+ ", b.name):
                    continue
                if b.find("cs_pin") is not None:     # SPI-драйвер
                    self._put(drv_blocks, b.name, "cs_pin", dd["socket"], dsrc)
                    for k in SPI_KEYS:
                        v = dd.get(k) or spi_default.get(k)
                        if v:
                            self._put(drv_blocks, b.name, k, v, dsrc)
                else:
                    self._put(drv_blocks, b.name, "uart_pin", dd["socket"], dsrc)

    def _replace_other_pins(self, ref) -> None:
        """Прочие пины основной MCU: значения эталона заменяют пресет Octopus (пины плат голов не трогаем)."""
        for (sec, key), v in ref["other"].items():
            for blk in self.blocks + self.new_extras:
                if blk.name != sec or blk.find(key) is None:
                    continue
                cur = clean_value(blk.lines[blk.find(key)])
                if cur == "" or main_mcu_pin(cur):
                    blk.set(key, ["%s: %s" % (key, v)])
                    self.filled["ref"] += 1
                    self.table_opts[:] = [(tb, tk) for tb, tk in self.table_opts if not (tb is blk and tk == key)]
                break

    def resolve_table_conflicts(self, all_blocks):
        """Пин из таблицы разъёмов, который уже занят другой секцией (эталон, мотор), оставляем пустым и сообщаем."""
        uses = {}
        for b in all_blocks:
            for ln in b.lines:
                m = OPT_RE.match(ln)
                if m and m.group(1).endswith("pin") and m.group(1) not in SPI_KEYS:
                    pid = pin_id(clean_value(ln))
                    if pid:
                        uses.setdefault(pid, []).append((b, m.group(1)))
        warns = []
        for b, key in list(self.table_opts):
            i = b.find(key)
            if i is None:
                continue
            pid = pin_id(clean_value(b.lines[i]))
            others = [(bb, kk) for bb, kk in uses.get(pid, []) if bb.name != b.name]
            if pid and others:
                b.set(key, ["%s:" % key])
                warns.append("[%s] %s: пин %s из таблицы разъёмов %s уже занят (%s), оставлен пустым - впишите свободный пин"
                             % (b.name, key, pid.split(":", 1)[1], self.table_src,
                                "; ".join("[%s] %s" % (bb.name, kk) for bb, kk in others)))
        return warns

    # --- сборка текста

    @staticmethod
    def _blocks_text(block_list) -> List[str]:
        """Блоки через пустую строку (хвостовые пустые строки блока отбрасываются)."""
        res: List[str] = []
        for b in block_list:
            body = list(b.lines)
            while body and not body[-1].strip():
                body.pop()
            res.extend(body + [""])
        return res

    def _render(self, drv_blocks, warns):
        """Итоговый текст файла и группы драйверов; к warns добавляются предупреждения про занятые пины.
        Тексты драйверов и extras собираются ДО разрешения конфликтов (как в прежнем генераторе): пустым
        оставляется только пин в основных секциях."""
        o = self.o
        drv_text = self._blocks_text(drv_blocks)
        extras_text = self._blocks_text(self.new_extras)
        if o.alps > 0:
            alps = self._read_template("boards/alps.cfg").replace("{N}", str(o.alps)).rstrip("\n")
            extras_text.extend(["#########################################################",
                                "# ALPS", "#########################################################", alps, ""])
        warns.extend(self.resolve_table_conflicts(self.blocks + self.new_extras + drv_blocks))
        groups = driver_groups(self.drv, self.needed)
        result = render(self.blocks, collapse_notes=bool(self.mainp))
        heads_title = HEAD_TITLE.get(o.heads, "2x " + o.heads)
        if not self.has_heads and o.template != "octopus_pro":
            heads_title = "нет (головы подключены к основной плате)"
        result = (result.replace("{BOARD}", o.board_name).replace("{HEADS}", heads_title)
                  .replace("{DRIVERS}", ", ".join("%dx %s" % (n, DRIVER_TITLE[d]) for n, d in groups)
                           + (" (драйверы экструдеров на платах голов)" if self.has_heads else "")))
        result = result.replace(";;DRIVERS;;", "\n".join(drv_text).rstrip("\n"))
        result = result.replace(";;EXTRAS;;", "\n".join(extras_text).rstrip("\n"))
        return result.rstrip("\n") + "\n", groups

    @staticmethod
    def _mark_empty_pins(text):
        """Пустые пины помечаем ЗАПОЛНИТЕ и перечисляем: (строки файла, [(секция, опция)])."""
        out_lines, cur, empty = [], None, []
        for ln in text.split("\n"):
            h = HEADER_RE.match(ln)
            if h:
                cur = norm(h.group(1))
            mm = EMPTY_PIN_RE.match(ln)
            if mm:
                empty.append((cur, mm.group(1)))
                ln = "%s: # %s: пин по схеме вашей платы" % (mm.group(1), TODO)
            out_lines.append(ln)
        return out_lines, empty

    def _table_warning(self) -> Optional[str]:
        base = self._main_table_warning()
        if not self.head_warn:
            return base
        return "%s; %s" % (base, self.head_warn) if base else self.head_warn

    def _main_table_warning(self) -> Optional[str]:
        if not (self.sverit_sections or self.filled["octopus"] or self.filled["board"]):
            return None
        secs = [b.name for b in self.blocks if b.note]
        what = ("Пины по разъёмам %s (пресет VOSTOK, плата не проверена на железе)" % self.o.board_name if self.mainp
                else "Пины из таблицы разъёмов Octopus Pro (конфиги репозитория, не main)")
        return ("%s, сверьте со своей схемой подключения: " % what
                + ", ".join("[%s]" % s_ for s_ in dict.fromkeys(secs)))


# ------------------------------------------------------------------ командная строка

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="gen_electronics.py")
    ap.add_argument("--templates", required=True)
    ap.add_argument("--ref-cfg", default="", help="эталонный electronics-файл (свой конфиг пользователя или стоковый main)")
    ap.add_argument("--main-cfg", default="", help="стоковый main-файл: запасной источник тока и режимов драйверов")
    ap.add_argument("--octopus-extruders", action="store_true",
                    help="без плат голов взять пины моторов экструдеров из templates/boards/octopus_extruders.cfg, если их нет в эталоне")
    ap.add_argument("--heads", default="none",
                    help="none или плата головы из реестра (id или алиас, ROLE=head; нужен шаблон электроники, поле TEMPLATE)")
    ap.add_argument("--head-names", default="T0CB,T1CB")
    ap.add_argument("--alps", type=int, default=0)
    ap.add_argument("--drivers", default="")
    ap.add_argument("--main", default="h723", help="id или алиас платы из реестра boards/ (h723, f446 - платы со старыми именами)")
    ap.add_argument("--board-name", default="", help="название платы для заголовка (иначе запасное для h723/f446)")
    ap.add_argument("--board-file", default="", help="часть имени файла (иначе запасная для h723/f446)")
    ap.add_argument("--template", default="octopus_pro",
                    help="пресет пинов главной платы: octopus_pro (v1.1 по гайду), none (без пинов, --octopus-* игнорируются) "
                         "или имя файла из templates/boards/main/ без .cfg")
    ap.add_argument("--out", default="", help="выходной файл (иначе имя по образцу user_configs в каталоге --out-dir)")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--octopus-heads", action="store_true",
                    help="без плат голов взять пины голов (нагреватель, термистор, вентилятор, концевики X/W, зонд) с разъёмов Octopus Pro")
    return ap


def main(argv: Optional[Sequence[str]] = None, registry=None) -> int:
    """Командная строка прежнего gen_electronics.py: файл в --out/--out-dir, протокол NAME/WARN/FILL/EMPTY в stdout.
    Коды: 0 - готово, 1 - ошибка параметров или шаблонов (текст в stderr), 2 - неверные аргументы (argparse)."""
    ap = _build_parser()
    a = ap.parse_args(None if argv is None else list(argv))
    if registry is None:
        from .boards import registry as _registry
        registry = _registry()
    try:
        heads = a.heads if a.heads == "none" else registry.head_value(a.heads)
    except VostokError as e:
        ap.error(str(e))
    head_template = registry.get(registry.resolve(heads)).template if heads != "none" else ""
    legacy_name, legacy_file = board_naming(registry, a.main)
    board_name = a.board_name or legacy_name
    board_file = a.board_file or legacy_file
    if not board_name or not board_file:
        ap.error("для платы %r нужны --board-name и --board-file" % a.main)
    opts = GenOptions(
        templates=a.templates, board_name=board_name, board_file=board_file, ref_cfg=a.ref_cfg, main_cfg=a.main_cfg,
        octopus_extruders=a.octopus_extruders, octopus_heads=a.octopus_heads, heads=heads,
        head_template=head_template,
        head_names=a.head_names, alps=a.alps, drivers=a.drivers, template=a.template, out=a.out, out_dir=a.out_dir)
    try:
        res = Generator(opts).generate()
    except ElectronicsUsageError as e:
        ap.error(str(e))
    except ElectronicsError as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    for line in res.protocol():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
