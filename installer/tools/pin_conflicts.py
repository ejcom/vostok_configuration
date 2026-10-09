#!/usr/bin/env python3
"""Ищет повторяющиеся пины в конфиге Klipper (printer.cfg и все его [include]).

Запуск: python3 -I pin_conflicts.py printer.cfg
Вывод: по строке на пин, который используется в нескольких секциях:
  CONFLICT<TAB>MCU:ПИН<TAB>[секция] опция; [секция] опция
Не считаются конфликтом общие линии SPI (spi_software_*), повторы одной секции и виртуальные
концевики (probe:z_virtual_endstop).
"""
import glob
import os
import re
import sys

HDR = re.compile(r"^\s*\[([^\]]+)\]")
SHARED = ("spi_software_sclk_pin", "spi_software_mosi_pin", "spi_software_miso_pin")


def read_with_includes(path, seen):
    path = os.path.realpath(path)
    if path in seen or not os.path.isfile(path):
        return []
    seen.add(path)
    text = open(path, encoding="utf-8", errors="replace").read()
    lines = text.split("\n")
    out = list(lines)
    for ln in lines:
        m = re.match(r"^\s*\[include\s+([^\]]+)\]", ln)
        if m:
            for f in sorted(glob.glob(os.path.join(os.path.dirname(path), m.group(1).strip()))):
                out.extend(read_with_includes(f, seen))
    return out


def norm_pin(value):
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


def main():
    lines = read_with_includes(sys.argv[1], set())
    uses = {}
    sec = None
    for ln in lines:
        m = HDR.match(ln)
        if m:
            sec = " ".join(m.group(1).split())
            continue
        if sec is None or ln[:1] in ("#", ";", " ", "\t") or ":" not in ln:
            continue
        key, _, value = ln.partition(":")
        key = key.strip()
        if not key.endswith("pin") or key in SHARED:
            continue
        pin = norm_pin(value)
        if pin:
            uses.setdefault(pin, [])
            if (sec, key) not in uses[pin]:
                uses[pin].append((sec, key))
    for pin in sorted(uses):
        secs = {s for s, _ in uses[pin]}
        if len(secs) > 1:
            print("CONFLICT\t%s\t%s" % (pin, "; ".join("[%s] %s" % su for su in uses[pin])))


if __name__ == "__main__":
    main()
