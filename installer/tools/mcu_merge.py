#!/usr/bin/env python3
"""Дописывает в printer.cfg недостающие секции [mcu ...] (режим «Пропустить редактирование конфига»).

Запуск: python3 -I mcu_merge.py printer.cfg blocks.txt [--dry]
        python3 -I mcu_merge.py printer.cfg --list   (только перечислить [mcu ...] конфига и его include)
        python3 -I mcu_merge.py printer.cfg --set ИМЯ UUID [--force]   (задать canbus_uuid в секции [ИМЯ] самого printer.cfg;
          значение ЗАПОЛНИТЕ или пустое заменяется, другое значение - только с --force)
blocks.txt - секции [mcu ...] прошитых плат (serial/canbus_uuid; значение ЗАПОЛНИТЕ = плата не прошита).
Остальное в конфиге не меняется. Вывод (stdout), по строке на секцию:
  OK<TAB>имя<TAB>где        секция уже есть (по значению serial/uuid или по имени с тем же значением)
  ADD<TAB>имя               секция добавлена
  DIFF<TAB>имя<TAB>опция<TAB>есть<TAB>нужно   секция есть, но значение другое: не меняем
  TODO<TAB>имя              плата не прошита, секция не добавлена
Для --set: SET<TAB>имя (записано) | SAME<TAB>имя | DIFF<TAB>имя<TAB>есть<TAB>нужно (не менялось) | NOSECTION<TAB>имя
"""
import glob
import os
import re
import sys

HDR = re.compile(r"^\s*\[([^\]]+)\]")
KEYS = ("serial", "canbus_uuid")
TODO = "ЗАПОЛНИТЕ"


def sections(text):
    """[(имя секции, {опция: значение})] без комментариев."""
    res, cur = [], None
    for ln in text.split("\n"):
        m = HDR.match(ln)
        if m:
            cur = (" ".join(m.group(1).split()), {})
            res.append(cur)
            continue
        if cur is None or ln[:1] in ("#", ";") or ":" not in ln or ln[:1] in (" ", "\t"):
            continue
        k, _, v = ln.partition(":")
        cur[1][k.strip()] = v.split(" #")[0].split("\t#")[0].strip()
    return res


def mcus(text):
    return [(n, o) for n, o in sections(text) if n == "mcu" or n.startswith("mcu ")]


def read_with_includes(path, seen=None):
    seen = seen if seen is not None else set()
    path = os.path.realpath(path)
    if path in seen or not os.path.isfile(path):
        return ""
    seen.add(path)
    text = open(path, encoding="utf-8", errors="replace").read()
    out = [text]
    for ln in text.split("\n"):
        m = re.match(r"^\s*\[include\s+([^\]]+)\]", ln)
        if m:
            for f in sorted(glob.glob(os.path.join(os.path.dirname(path), m.group(1).strip()))):
                out.append(read_with_includes(f, seen))
    return "\n".join(out)


def split_wanted(text):
    """[(имя, строки блока)] из blocks.txt."""
    res, cur = [], None
    for ln in text.split("\n"):
        m = HDR.match(ln)
        if m:
            cur = (" ".join(m.group(1).split()), [ln])
            res.append(cur)
        elif cur is not None and ln.strip():
            cur[1].append(ln)
    return res


def set_uuid(cfg_path, name, uuid, force):
    lines = open(cfg_path, encoding="utf-8").read().split("\n")
    start = None
    for i, ln in enumerate(lines):
        m = HDR.match(ln)
        if m and " ".join(m.group(1).split()) == name:
            start = i
            break
    if start is None:
        print("NOSECTION\t%s" % name)
        return
    end = start + 1
    while end < len(lines) and not HDR.match(lines[end]) and not lines[end].startswith("#*#"):
        end += 1
    idx = next((j for j in range(start + 1, end)
                if re.match(r"canbus_uuid\s*:", lines[j])), None)
    cur = ""
    if idx is not None:
        cur = lines[idx].partition(":")[2].split(" #")[0].strip()
    if idx is None and not force and any(re.match(r"serial\s*:", lines[j]) for j in range(start + 1, end)):
        print("DIFF\t%s\tserial\t%s" % (name, uuid))
        return
    if cur.lower() == uuid.lower():
        print("SAME\t%s" % name)
        return
    if cur and TODO not in cur and not force:
        print("DIFF\t%s\t%s\t%s" % (name, cur, uuid))
        return
    if idx is not None:
        lines[idx] = "canbus_uuid: %s" % uuid
    else:
        lines.insert(start + 1, "canbus_uuid: %s" % uuid)
    open(cfg_path, "w", encoding="utf-8").write("\n".join(lines))
    print("SET\t%s" % name)


def main():
    if len(sys.argv) > 4 and sys.argv[2] == "--set":
        set_uuid(sys.argv[1], sys.argv[3], sys.argv[4], "--force" in sys.argv[5:])
        return
    if len(sys.argv) > 2 and sys.argv[2] == "--list":
        for n, o in mcus(read_with_includes(sys.argv[1])):
            key = next((k for k in KEYS if o.get(k)), "")
            print("%s\t%s\t%s" % (n, key, o.get(key, "")))
        return
    cfg_path, blocks_path = sys.argv[1], sys.argv[2]
    dry = "--dry" in sys.argv[3:]
    cfg = open(cfg_path, encoding="utf-8").read()
    have = mcus(read_with_includes(cfg_path))
    by_value = {}
    for n, o in have:
        for k in KEYS:
            if o.get(k):
                by_value[(k, o[k].lower())] = n
    by_name = dict(have)
    add = []
    for name, lines in split_wanted(open(blocks_path, encoding="utf-8").read()):
        opts = sections("\n".join(lines))[0][1]
        key = next((k for k in KEYS if k in opts), None)
        val = opts.get(key, "") if key else ""
        if TODO in val:
            print("TODO\t%s" % name)
            continue
        if key and (key, val.lower()) in by_value:
            print("OK\t%s\t%s" % (name, by_value[(key, val.lower())]))
            continue
        if name in by_name:
            cur = by_name[name].get(key, "")
            print("DIFF\t%s\t%s\t%s\t%s" % (name, key, cur, val))
            continue
        add.append("\n".join(lines))
        print("ADD\t%s" % name)
    if not add or dry:
        return
    block = "\n\n".join(add) + "\n"
    lines = cfg.split("\n")
    # после последней секции [mcu...] самого printer.cfg, иначе перед первой секцией
    last_end = None
    for i, ln in enumerate(lines):
        m = HDR.match(ln)
        if m and (m.group(1).split()[0] == "mcu"):
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
    open(cfg_path, "w", encoding="utf-8").write("\n".join(new))


if __name__ == "__main__":
    main()
