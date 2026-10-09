#!/usr/bin/env python3
"""Генерация electronics_*.cfg для install_vostok.sh.

Берёт шаблон без плат и драйверов (templates/electronics_blank.cfg), накладывает пресеты:
  - Octopus Pro по гайду (templates/boards/octopus_pro.cfg);
  - платы голов H36 v1.3 / v2 или EBB42 (templates/boards/<плата>.cfg);
  - драйверы моторов (templates/drivers/tmc*.cfg, пины пустые);
  - ALPS (закомментированный блок);
ток и режимы драйверов берёт из electronics_*.cfg корня репозитория (--params-cfg).

Эталон (--ref-cfg): конфиг электроники пользователя (или стоковый main при чистой установке).
Из него берутся пины моторов и драйверов на основной MCU, ток и режимы драйверов и прочие пины
основной MCU, которые есть и в сгенерированном файле. Запасной источник параметров - --main-cfg.

Результат: файл --out; в stdout строки EMPTY<TAB>[секция]<TAB>опция (пустые пины),
WARN<TAB>текст (предупреждения) и FILL<TAB>источник<TAB>число (сколько пинов откуда подставлено).
Запуск: python3 -I gen_electronics.py ...
"""
import argparse
import re
import sys
from pathlib import Path

HEADER_RE = re.compile(r"^\[(.+?)\]\s*(#.*)?$")
OPT_RE = re.compile(r"^([A-Za-z0-9_]+)\s*:")
EMPTY_PIN_RE = re.compile(r"^(\w*pin)\s*:\s*(#.*)?$")
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
DRIVER_TYPES = ("2130", "2208", "2209", "2240", "5160", "5160plus")
# Имя файла пресета в templates/drivers/ для каждого типа
DRIVER_FILES = {"2130": "tmc2130", "2208": "tmc2208", "2209": "tmc2209", "2240": "tmc2240",
                "5160": "tmc5160", "5160plus": "tmc5160t_plus"}
# Драйверы с малым током: для них предупреждаем, если ток из конфига под TMC2240 слишком велик
LOW_CURRENT = ("2130", "2208", "2209")
DRIVER_ALIASES = {"5160pro": "5160", "5160tpro": "5160", "5160tplus": "5160plus", "5160t_plus": "5160plus"}


SVERIT = "# !!! СВЕРЬТЕ СО СВОЕЙ СХЕМОЙ: пины подставлены по разъёмам Octopus Pro из конфигов репозитория (в main они на платах голов)"


class Block:
    def __init__(self, name, lines):
        self.name = name          # None - преамбула до первой секции
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
        if self.name is not None and last == 0:
            last = 0
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


TABLE_OPTS = []   # (блок, опция) пинов, подставленных из таблицы разъёмов Octopus (не из эталона)
PIN_RE = re.compile(r"^[A-Za-z]{1,2}\d+$")


def pin_id(value):
    """Пин в виде 'MCU:PIN' (MCU 'mcu' для основной платы) или None, если это не пин."""
    v = re.sub(r"^[!^~\s]+", "", value.split("#")[0].strip())
    mcu, pin = ("mcu", v)
    if ":" in v:
        mcu, pin = (x.strip() for x in v.split(":", 1))
        pin = re.sub(r"^[!^~\s]+", "", pin)
    return "%s:%s" % (mcu, pin.upper()) if PIN_RE.match(pin) else None


def resolve_table_conflicts(all_blocks):
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
    for b, key in list(TABLE_OPTS):
        i = b.find(key)
        if i is None:
            continue
        pid = pin_id(clean_value(b.lines[i]))
        others = [(bb, kk) for bb, kk in uses.get(pid, []) if bb.name != b.name]
        if pid and others:
            b.set(key, ["%s:" % key])
            warns.append("[%s] %s: пин %s из таблицы разъёмов Octopus Pro уже занят (%s), оставлен пустым - впишите свободный пин"
                         % (b.name, key, pid.split(":", 1)[1], "; ".join("[%s] %s" % (bb.name, kk) for bb, kk in others)))
    return warns


def apply_overlay(blocks, overlay, new_drivers, new_extras, note=None):
    for name, full_lines, opts in overlay:
        targets = [b for b in blocks if b.name == name]
        if not targets:
            target_list = new_drivers if name.startswith("tmc") else new_extras
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
                        TABLE_OPTS.append((b, key))
                    break
            else:
                targets[0].set(key, vl)
                if note:
                    targets[0].note = note
                    TABLE_OPTS.append((targets[0], key))


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


def clean_value(line):
    """Значение опции из строки 'key: value # комментарий'."""
    return line.split(":", 1)[1].split("#")[0].strip()


def main_mcu_pin(value):
    """Пин основной MCU (без префикса другой MCU вида T0CB:PA8) и не пустой."""
    return bool(value) and ":" not in value


SOCKET_KEYS = ("cs_pin", "uart_pin")
SPI_KEYS = ("spi_software_sclk_pin", "spi_software_mosi_pin", "spi_software_miso_pin")
STEP_KEYS = ("step_pin", "dir_pin", "enable_pin")
# SPI-пины Octopus Pro общие для всех драйверных разъёмов
OCTOPUS_SPI = {"spi_software_sclk_pin": "PA5", "spi_software_mosi_pin": "PA7", "spi_software_miso_pin": "PA6"}


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
            sys.exit("--drivers: неизвестный мотор %r" % k)
        if v not in DRIVER_TYPES:
            sys.exit("--drivers: драйвер %r не из %s" % (v, "/".join(DRIVER_TYPES)))
    return drv


def render(blocks):
    out = []
    for b in blocks:
        if b.note:
            # комментарий ставим перед заголовком секции, после пустой строки предыдущего блока
            while out and not out[-1].strip():
                out.pop()
            out.extend(["", b.note])
        out.extend(b.lines)
    return "\n".join(out)


BOARD_NAMES = {"h723": "BigTreeTech Octopus Pro v1.1 H723", "f446": "BigTreeTech Octopus Pro F446"}
# Имя файла по образцу user_configs: electronics_<плата>_<чип>_<N>x<драйвер>[_<N>x<драйвер>]_[2x<головы>].cfg
BOARD_FILE = {"h723": "octopus_pro_v1.1_h723", "f446": "octopus_pro_v1.0_f446"}
DRIVER_TOKEN = {"2130": "2130", "2208": "2208", "2209": "2209", "2240": "2240", "5160": "5160", "5160plus": "5160tplus"}
DRIVER_TITLE = {"2130": "tmc2130", "2208": "tmc2208", "2209": "tmc2209", "2240": "tmc2240", "5160": "tmc5160", "5160plus": "tmc5160 (T Plus)"}
HEAD_FILE = {"v1.3": "2xH36v1.3", "v2": "2xH36v2.0", "ebb42": "2xebb42"}
HEAD_TITLE = {"none": "нет (головы подключены к Octopus)", "v1.3": "2x Fysetc H36 v1.3", "v2": "2x Fysetc H36 v2.0", "ebb42": "2x BTT EBB42"}


def driver_groups(drv, needed):
    """[(число, тип)] по убыванию числа, затем по типу; считаются моторы, у которых драйвер выбран пользователем."""
    cnt = {}
    for m in needed:
        cnt[drv[m]] = cnt.get(drv[m], 0) + 1
    return sorted(((n, d) for d, n in cnt.items()), key=lambda x: (-x[0], x[1]))


def config_name(main, heads, groups):
    parts = ["electronics", BOARD_FILE[main]] + ["%dx%s" % (n, DRIVER_TOKEN[d]) for n, d in groups]
    if heads != "none":
        parts.append(HEAD_FILE[heads])
    return "_".join(parts) + ".cfg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--templates", required=True)
    ap.add_argument("--ref-cfg", default="", help="эталонный electronics-файл (свой конфиг пользователя или стоковый main)")
    ap.add_argument("--main-cfg", default="", help="стоковый main-файл: запасной источник тока и режимов драйверов")
    ap.add_argument("--octopus-extruders", action="store_true",
                    help="без плат голов взять пины моторов экструдеров из templates/boards/octopus_extruders.cfg, если их нет в эталоне")
    ap.add_argument("--heads", default="none", choices=["none", "v1.3", "v2", "ebb42"])
    ap.add_argument("--head-names", default="T0CB,T1CB")
    ap.add_argument("--alps", type=int, default=0)
    ap.add_argument("--drivers", default="")
    ap.add_argument("--main", default="h723", choices=["h723", "f446"])
    ap.add_argument("--out", default="", help="выходной файл (иначе имя по образцу user_configs в каталоге --out-dir)")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--octopus-heads", action="store_true",
                    help="без плат голов взять пины голов (нагреватель, термистор, вентилятор, концевики X/W, зонд) с разъёмов Octopus Pro")
    a = ap.parse_args()

    t = Path(a.templates)
    names = a.head_names.split(",")
    drv = parse_drivers(a.drivers, a.heads != "none")
    needed = [m for m in MOTORS if not (a.heads != "none" and m in ("e0", "e1"))]
    missing = [m for m in needed if m not in drv]
    if missing:
        sys.exit("--drivers: не задан драйвер для %s" % ",".join(missing))

    text = (t / "electronics_blank.cfg").read_text(encoding="utf-8")
    blocks = split_blocks(text)
    new_drivers, new_extras = [], []

    apply_overlay(blocks, parse_overlay((t / "boards/octopus_pro.cfg").read_text(encoding="utf-8"), {}), new_drivers, new_extras)

    if a.heads == "none" and a.octopus_heads and (t / "boards/octopus_heads.cfg").is_file():
        apply_overlay(blocks, parse_overlay((t / "boards/octopus_heads.cfg").read_text(encoding="utf-8"), {}),
                      new_drivers, new_extras, note=SVERIT)
        sverit_sections = True
    else:
        sverit_sections = False

    if a.heads != "none":
        preset = (t / ("boards/%s.cfg" % ("h36_" + a.heads if a.heads != "ebb42" else "ebb42"))).read_text(encoding="utf-8")
        parts = re.split(r"^@@T([01])@@\s*$", preset, flags=re.M)
        # parts: [шапка, '0', текст T0, '1', текст T1]
        for idx in range(1, len(parts), 2):
            n = int(parts[idx])
            apply_overlay(blocks, parse_overlay(parts[idx + 1], {"M": names[n]}), new_drivers, new_extras)

    # Драйверы: пустые пины из шаблона драйвера + параметры из эталона (запасной вариант - main)
    ref = read_reference(a.ref_cfg)
    params = read_params(a.main_cfg)
    params_ref = read_params(a.ref_cfg)
    for m_, d_ in params_ref.items():
        params.setdefault(m_, {}).update(d_)
    warns = []
    drv_blocks = list(new_drivers)         # из пресетов голов (драйвер экструдера)
    for m in needed:
        d = drv[m]
        sec = MOTORS[m]
        tpl = (t / ("drivers/%s.cfg" % DRIVER_FILES[d])).read_text(encoding="utf-8").replace("{SEC}", sec)
        drv_blocks.extend(b for b in split_blocks(tpl) if b.name is not None)
        if d in LOW_CURRENT and float(params.get(m, DEFAULT_PARAMS[m])["run_current"]) > 1.2 and m not in ("e0", "e1"):
            warns.append("%s: драйвер TMC%s, а run_current %s взят из конфига под TMC2240; уменьшите ток (обычно 0.8-1.2 А)"
                         % (MOTOR_TITLE[m], d, params.get(m, DEFAULT_PARAMS[m])["run_current"]))
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
    # Пины моторов и драйверов: сначала эталон, затем (экструдеры без голов) таблица разъёмов Octopus
    filled = {"ref": 0, "octopus": 0}
    ext_tpl = {"step": {}, "socket": {}}
    tpl_path = t / "boards/octopus_extruders.cfg"
    if a.octopus_extruders and a.heads == "none" and tpl_path.is_file():
        for b in split_blocks(tpl_path.read_text(encoding="utf-8")):
            if b.name in ("extruder", "extruder1"):
                motor = "e0" if b.name == "extruder" else "e1"
                ext_tpl["step"][motor] = {k: clean_value(vl[0]) for k, vl in parse_options(b.lines[1:])}
            elif b.name in ("socket extruder", "socket extruder1"):
                motor = "e0" if b.name == "socket extruder" else "e1"
                for key, vl in parse_options(b.lines[1:]):
                    if key == "pin":
                        ext_tpl["socket"][motor] = clean_value(vl[0])

    def put(block_list, name, key, value, src):
        for blk in block_list:
            if blk.name == name and blk.find(key) is not None:
                blk.set(key, ["%s: %s" % (key, value)])
                filled[src] += 1
                if src == "octopus" and block_list is blocks:
                    blk.note = SVERIT
                    TABLE_OPTS.append((blk, key))
                return True
        return False

    for m in needed:
        sec = MOTORS[m]
        src = "ref"
        steps = ref["step"].get(m)
        if not steps and m in ext_tpl["step"]:
            steps, src = ext_tpl["step"][m], "octopus"
        for k, v in (steps or {}).items():
            if k in STEP_KEYS:
                put(blocks, sec, k, v, src)
        dsrc = "ref"
        dd = ref["drv"].get(m)
        if not dd and ext_tpl["socket"].get(m):
            dd, dsrc = {"socket": ext_tpl["socket"][m]}, "octopus"
        if not dd:
            continue
        for b in drv_blocks:
            if b.name.split(" ", 1)[1:] != [sec] or not re.match(r"^tmc\d+ ", b.name):
                continue
            spi = b.find("cs_pin") is not None
            if spi:
                put(drv_blocks, b.name, "cs_pin", dd["socket"], dsrc)
                for k in SPI_KEYS:
                    v = dd.get(k) or OCTOPUS_SPI[k]
                    put(drv_blocks, b.name, k, v, dsrc)
            else:
                put(drv_blocks, b.name, "uart_pin", dd["socket"], dsrc)

    # Прочие пины основной MCU: значения эталона заменяют пресет Octopus (пины плат голов не трогаем)
    for (sec, key), v in ref["other"].items():
        for blk in blocks + new_extras:
            if blk.name != sec or blk.find(key) is None:
                continue
            cur = clean_value(blk.lines[blk.find(key)])
            if cur == "" or main_mcu_pin(cur):
                blk.set(key, ["%s: %s" % (key, v)])
                filled["ref"] += 1
                TABLE_OPTS[:] = [(tb, tk) for tb, tk in TABLE_OPTS if not (tb is blk and tk == key)]
            break

    # блоки драйверов отделяем пустой строкой
    drv_text = []
    for b in drv_blocks:
        body = list(b.lines)
        while body and not body[-1].strip():
            body.pop()
        drv_text.extend(body + [""])
    extras_text = []
    for b in new_extras:
        body = list(b.lines)
        while body and not body[-1].strip():
            body.pop()
        extras_text.extend(body + [""])
    if a.alps > 0:
        alps = (t / "boards/alps.cfg").read_text(encoding="utf-8").replace("{N}", str(a.alps)).rstrip("\n")
        extras_text.extend(["#########################################################",
                            "# ALPS", "#########################################################", alps, ""])

    warns.extend(resolve_table_conflicts(blocks + new_extras + drv_blocks))
    groups = driver_groups(drv, needed)
    name = a.out and Path(a.out).name or config_name(a.main, a.heads, groups)
    result = render(blocks)
    result = (result.replace("{BOARD}", BOARD_NAMES[a.main]).replace("{HEADS}", HEAD_TITLE[a.heads])
              .replace("{DRIVERS}", ", ".join("%dx %s" % (n, DRIVER_TITLE[d]) for n, d in groups)
                       + ("" if a.heads == "none" else " (драйверы экструдеров на платах голов)")))
    result = result.replace(";;DRIVERS;;", "\n".join(drv_text).rstrip("\n"))
    result = result.replace(";;EXTRAS;;", "\n".join(extras_text).rstrip("\n"))
    result = result.rstrip("\n") + "\n"

    # Пустые пины: помечаем и перечисляем
    out_lines, cur, empty = [], None, []
    for ln in result.split("\n"):
        h = HEADER_RE.match(ln)
        if h:
            cur = norm(h.group(1))
        mm = EMPTY_PIN_RE.match(ln)
        if mm:
            empty.append((cur, mm.group(1)))
            ln = "%s: # %s: пин по схеме вашей платы" % (mm.group(1), TODO)
        out_lines.append(ln)
    out_path = Path(a.out) if a.out else Path(a.out_dir or ".") / name
    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print("NAME\t%s" % name)
    if sverit_sections or filled["octopus"]:
        secs = [b.name for b in blocks if b.note]
        print("WARN\tПины из таблицы разъёмов Octopus Pro (конфиги репозитория, не main), сверьте со своей схемой подключения: "
              + ", ".join("[%s]" % s_ for s_ in dict.fromkeys(secs)))
    for src, n in filled.items():
        print("FILL\t%s\t%d" % (src, n))
    for sec, opt in empty:
        print("EMPTY\t[%s]\t%s" % (sec, opt))
    for w in warns:
        print("WARN\t%s" % w)


if __name__ == "__main__":
    main()
