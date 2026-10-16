"""Разбор и правка конфигов Klipper: include, секции, [mcu] (бывший mcu_merge.py), пины (pin_conflicts.py),
правка printer.cfg (heredoc stage_config), модули, состояние printer.cfg, атомарная запись с .bak.

Один read_with_includes и один разбор секций вместо трёх (mcu_merge, pin_conflicts, heredoc).
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import VostokError

TODO_MARK = "ЗАПОЛНИТЕ"
MCU_KEYS = ("serial", "canbus_uuid")

HDR = re.compile(r"^\s*\[([^\]]+)\]")
# общие линии программного SPI не считаются конфликтом пинов
SHARED_PINS = ("spi_software_sclk_pin", "spi_software_mosi_pin", "spi_software_miso_pin")


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
        return "\t".join((self.kind, self.name) + tuple(self.args))


def _read_text(path) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise VostokError("не удалось прочитать %s: %s" % (path, e))


def read_with_includes(path, seen=None) -> str:
    """Текст файла и всех его ``[include …]`` (маски glob, рекурсивно, каждый файл один раз)."""
    seen = seen if seen is not None else set()
    path = os.path.realpath(str(path))
    if path in seen or not os.path.isfile(path):
        return ""
    seen.add(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    out = [text]
    for ln in text.split("\n"):
        m = re.match(r"^\s*\[include\s+([^\]]+)\]", ln)
        if m:
            for f in sorted(glob.glob(os.path.join(os.path.dirname(path), m.group(1).strip()))):
                out.append(read_with_includes(f, seen))
    return "\n".join(out)


def _name(raw: str) -> str:
    return " ".join(raw.split())


def sections(text: str) -> List[Section]:
    """Разобрать текст на секции без комментариев; единственный разбор для merge/pin_conflicts."""
    res: List[Section] = []
    cur: Optional[Section] = None
    for ln in text.split("\n"):
        m = HDR.match(ln)
        if m:
            cur = Section(_name(m.group(1)))
            res.append(cur)
            continue
        if cur is None or ln[:1] in ("#", ";") or ":" not in ln or ln[:1] in (" ", "\t"):
            continue
        k, _, v = ln.partition(":")
        k = k.strip()
        cur.items.append((k, v))
        cur.opts[k] = v.split(" #")[0].split("\t#")[0].strip()
    return res


def _mcus(secs: List[Section]) -> List[Section]:
    return [s for s in secs if s.name == "mcu" or s.name.startswith("mcu ")]


def list_mcus(cfg_path) -> List[Tuple[str, str, str]]:
    """[(имя секции [mcu …], ключ serial|canbus_uuid или "", значение)] с учётом include (``mcu_merge.py --list``)."""
    res = []
    for s in _mcus(sections(read_with_includes(cfg_path))):
        key = next((k for k in MCU_KEYS if s.opts.get(k)), "")
        res.append((s.name, key, s.opts.get(key, "")))
    return res


def _split_wanted(text: str) -> List[Tuple[str, List[str]]]:
    res: List[Tuple[str, List[str]]] = []
    cur = None
    for ln in text.split("\n"):
        m = HDR.match(ln)
        if m:
            cur = (_name(m.group(1)), [ln])
            res.append(cur)
        elif cur is not None and ln.strip():
            cur[1].append(ln)
    return res


def merge_mcus(cfg_path, blocks_text: str, dry: bool = False, backup: bool = True) -> List[Result]:
    """Дописать в printer.cfg недостающие [mcu …] из blocks_text. Результаты OK/ADD/DIFF/TODO как у mcu_merge.py.
    dry - только анализ. backup - перед записью сделать .bak-<дата> (только если есть что дописать)."""
    cfg = _read_text(cfg_path)
    have = _mcus(sections(read_with_includes(cfg_path)))
    by_value: Dict[Tuple[str, str], str] = {}
    for s in have:
        for k in MCU_KEYS:
            if s.opts.get(k):
                by_value[(k, s.opts[k].lower())] = s.name
    by_name = {s.name: s.opts for s in have}
    results: List[Result] = []
    add: List[str] = []
    for name, lines in _split_wanted(blocks_text):
        opts = sections("\n".join(lines))[0].opts
        key = next((k for k in MCU_KEYS if k in opts), None)
        val = opts.get(key, "") if key else ""
        if TODO_MARK in val:
            results.append(Result("TODO", name))
            continue
        if key and (key, val.lower()) in by_value:
            results.append(Result("OK", name, (by_value[(key, val.lower())],)))
            continue
        if name in by_name:
            cur = by_name[name].get(key, "")
            results.append(Result("DIFF", name, (str(key), cur, val)))
            continue
        add.append("\n".join(lines))
        results.append(Result("ADD", name))
    if not add or dry:
        return results
    block = "\n\n".join(add) + "\n"
    lines = cfg.split("\n")
    # после последней секции [mcu...] самого printer.cfg, иначе перед первой секцией
    last_end = None
    for i, ln in enumerate(lines):
        m = HDR.match(ln)
        if m and m.group(1).split() and m.group(1).split()[0] == "mcu":
            j = i + 1
            while j < len(lines) and not HDR.match(lines[j]) and not lines[j].startswith("#*#"):
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1
            last_end = j
    if last_end is None:
        last_end = next((i for i, ln in enumerate(lines) if HDR.match(ln) or ln.startswith("#*#")), len(lines))
        new = lines[:last_end] + [block.rstrip("\n"), ""] + lines[last_end:]
    else:
        new = lines[:last_end] + ["", block.rstrip("\n")] + lines[last_end:]
    atomic_write(cfg_path, "\n".join(new), backup=backup)
    return results


def set_canbus_uuid(cfg_path, name: str, uuid: str, force: bool = False, backup: bool = False) -> Result:
    """Задать canbus_uuid в секции [name] самого printer.cfg: SET | SAME | DIFF | NOSECTION (как ``mcu_merge.py --set``).
    ЗАПОЛНИТЕ или пустое значение заменяется, другое - только с force."""
    lines = _read_text(cfg_path).split("\n")
    start = None
    for i, ln in enumerate(lines):
        m = HDR.match(ln)
        if m and _name(m.group(1)) == name:
            start = i
            break
    if start is None:
        return Result("NOSECTION", name)
    end = start + 1
    while end < len(lines) and not HDR.match(lines[end]) and not lines[end].startswith("#*#"):
        end += 1
    idx = next((j for j in range(start + 1, end) if re.match(r"canbus_uuid\s*:", lines[j])), None)
    cur = ""
    if idx is not None:
        cur = lines[idx].partition(":")[2].split(" #")[0].strip()
    if idx is None and not force and any(re.match(r"serial\s*:", lines[j]) for j in range(start + 1, end)):
        return Result("DIFF", name, ("serial", uuid))
    if cur.lower() == uuid.lower():
        return Result("SAME", name)
    if cur and TODO_MARK not in cur and not force:
        return Result("DIFF", name, (cur, uuid))
    if idx is not None:
        lines[idx] = "canbus_uuid: %s" % uuid
    else:
        lines.insert(start + 1, "canbus_uuid: %s" % uuid)
    atomic_write(cfg_path, "\n".join(lines), backup=backup)
    return Result("SET", name)


def _norm_pin(value: str) -> Optional[str]:
    v = value.split("#")[0].strip()
    if not v or ":" in v and v.split(":", 1)[0].strip() == "probe":
        return None
    v = re.sub(r"^[!^~\s]+", "", v)
    if ":" in v:
        mcu, pin = (x.strip() for x in v.split(":", 1))
        pin = re.sub(r"^[!^~\s]+", "", pin)
    else:
        mcu, pin = "mcu", v
    if not re.match(r"^[A-Za-z]{1,2}\d+$", pin):
        return None
    return "%s:%s" % (mcu, pin.upper())


def pin_conflicts(cfg_path) -> List[Result]:
    """Пины, занятые несколькими секциями (printer.cfg с include): Result("CONFLICT", "MCU:ПИН", (описание,)).
    Не считаются общие линии spi_software_*, повторы одной секции и виртуальные концевики (probe:…)."""
    uses: Dict[str, List[Tuple[str, str]]] = {}
    for sec in sections(read_with_includes(cfg_path)):
        for key, value in sec.items:
            if not key.endswith("pin") or key in SHARED_PINS:
                continue
            pin = _norm_pin(value)
            if pin:
                lst = uses.setdefault(pin, [])
                if (sec.name, key) not in lst:
                    lst.append((sec.name, key))
    res = []
    for pin in sorted(uses):
        if len({s for s, _ in uses[pin]}) > 1:
            res.append(Result("CONFLICT", pin, ("; ".join("[%s] %s" % su for su in uses[pin]),)))
    return res


def cfg_state(path) -> str:
    """none (нет файла) | blank (пусто или только комментарии) | foreign (нет [include printer_base.cfg]) | vostok."""
    if not os.path.isfile(str(path)):
        return "none"
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    if all(re.match(r"^\s*(#.*)?$", ln) for ln in lines):
        return "blank"
    if any(re.match(r"^\s*\[include\s+printer_base\.cfg\]", ln) for ln in lines):
        return "vostok"
    return "foreign"


def rewrite_printer_text(text: str, electronics: str, blocks_text: str) -> str:
    """Заменить в тексте printer.cfg набор [mcu …] блоками blocks_text и строку [include electronics_*.cfg].
    Секции [mcu …] убираются целиком (до следующего заголовка или SAVE_CONFIG), блоки встают на место первой;
    комментарии перед следующим заголовком остаются. Нет include электроники - ставится после printer_base.cfg."""
    src = text.split("\n")
    blocks = blocks_text.rstrip("\n").split("\n")
    hdr = re.compile(r"\s*(\[|#\*#)")
    out: List[str] = []
    i = 0
    inserted = has_inc = False
    while i < len(src):
        line = src[i]
        if re.match(r"\s*\[mcu(\s+[^\]]+)?\]", line):
            if not inserted:
                out.extend(blocks + [""])
                inserted = True
            i += 1
            body: List[str] = []
            while i < len(src) and not hdr.match(src[i]):
                body.append(src[i])
                i += 1
            keep: List[str] = []
            while body and body[-1].lstrip().startswith("#"):
                keep.insert(0, body.pop())
            out.extend(keep)
            continue
        if re.match(r"\s*\[include\s+electronics_.*\.cfg\]", line):
            tail = line.split("]", 1)[1]
            line = "[include %s]%s" % (electronics, tail)
            has_inc = True
        out.append(line)
        i += 1
    if not has_inc:
        for k, ln in enumerate(out):
            if re.match(r"\s*\[include\s+printer_base\.cfg\]", ln):
                out.insert(k + 1, "[include %s]" % electronics)
                break
    if not inserted:
        out = blocks + [""] + out
    return "\n".join(out)


def rewrite_printer_cfg(path, electronics: str, blocks_text: str, backup: bool = False) -> None:
    """rewrite_printer_text для файла (SAVE_CONFIG и остальное не меняется). Резервную копию stage_config
    делает сам (printer.cfg и electronics вместе, одной меткой), поэтому по умолчанию backup=False."""
    atomic_write(path, rewrite_printer_text(_read_text(path), electronics, blocks_text), backup=backup)


def module_state(cfg_path, file: str) -> str:
    """Модуль подключён через [include файл] в printer.cfg: active | commented | none."""
    f = re.escape(file)
    lines = _read_text(cfg_path).split("\n")
    if any(re.match(r"^[ \t]*\[include[ \t]+%s\]" % f, ln) for ln in lines):
        return "active"
    if any(re.match(r"^[ \t]*#[ \t]*\[include[ \t]+%s\]" % f, ln) for ln in lines):
        return "commented"
    return "none"


def module_add_include(cfg_path, file: str, backup: bool = False) -> None:
    """Раскомментировать готовую строку, иначе поставить [include файл] после include электроники
    (или перед блоком SAVE_CONFIG, или в конец файла)."""
    text = _read_text(cfg_path)
    f = re.escape(file)
    lines = text.split("\n")
    if module_state(cfg_path, file) == "commented":
        pat = re.compile(r"^([ \t]*)#[ \t]*(\[include[ \t]+%s\])" % f)
        new = "\n".join(pat.sub(r"\1\2", ln) for ln in lines)
    else:
        el = next((k for k, ln in enumerate(lines)
                   if re.match(r"^[ \t]*\[include[ \t]+electronics_[^\]]*\]", ln)), None)
        sv = next((k for k, ln in enumerate(lines) if ln.startswith("#*# <")), None)
        if el is not None:
            lines.insert(el + 1, "[include %s]" % file)
            new = "\n".join(lines)
        elif sv is not None:
            lines[sv:sv] = ["[include %s]" % file, ""]
            new = "\n".join(lines)
        else:
            new = text + "\n[include %s]\n" % file
    atomic_write(cfg_path, new, backup=backup)


def backup_file(path, stamp: Optional[str] = None) -> Optional[Path]:
    """Копия ``<path>.bak-<ГГГГММДД-ЧЧММСС>`` (с правами и временем); None, если файла нет."""
    p = Path(path)
    if not p.is_file():
        return None
    dst = p.with_name("%s.bak-%s" % (p.name, stamp or time.strftime("%Y%m%d-%H%M%S")))
    try:
        shutil.copy2(str(p), str(dst))
    except OSError as e:
        raise VostokError("не удалось сделать резервную копию %s: %s" % (p, e))
    return dst


def atomic_write(path, text: str, backup: bool = True) -> Optional[Path]:
    """Записать файл атомарно (временный файл + rename, права сохраняются); backup - сначала .bak-<дата>.
    Возвращает путь копии или None."""
    p = Path(os.path.realpath(str(path)))  # symlink не заменяем, правим его цель
    bak = backup_file(p) if backup else None
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if p.exists():
            shutil.copymode(str(p), tmp)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, str(p))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return bak


# ------------------------------------------------------------------ командная строка (tools/mcu_merge.py, tools/pin_conflicts.py)

def mcu_merge_main(argv: List[str]) -> int:
    """CLI прежнего tools/mcu_merge.py (argv без имени программы):
    ``printer.cfg blocks.txt [--dry]`` | ``printer.cfg --list`` | ``printer.cfg --set ИМЯ UUID [--force]``.
    Вывод - строки Result.line() (поля через TAB); .bak не создаётся, как у прежнего скрипта."""
    import sys
    if len(argv) > 3 and argv[1] == "--set":
        print(set_canbus_uuid(argv[0], argv[2], argv[3], force="--force" in argv[4:], backup=False).line())
        return 0
    if len(argv) > 1 and argv[1] == "--list":
        for n, key, val in list_mcus(argv[0]):
            print("%s\t%s\t%s" % (n, key, val))
        return 0
    if len(argv) < 2:
        sys.stderr.write("использование: mcu_merge.py printer.cfg blocks.txt [--dry] | --list | --set ИМЯ UUID [--force]\n")
        return 2
    blocks = _read_text(argv[1])
    for r in merge_mcus(argv[0], blocks, dry="--dry" in argv[2:], backup=False):
        print(r.line())
    return 0


def pin_conflicts_main(argv: List[str]) -> int:
    """CLI прежнего tools/pin_conflicts.py: ``printer.cfg``; по строке CONFLICT на пин, занятый несколькими секциями."""
    import sys
    if not argv:
        sys.stderr.write("использование: pin_conflicts.py printer.cfg\n")
        return 2
    for r in pin_conflicts(argv[0]):
        print(r.line())
    return 0
