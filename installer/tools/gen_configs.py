#!/usr/bin/env python3
"""Генерация конфигов сборки Klipper/katapult для install_vostok.sh и update_klipper_mcu.sh.
Параметры плат берутся из реестра boards/*.board (формат и поля - vostok/boards.py), Kconfig-строки строятся из полей.
Конфиги лежат в configs/ (Klipper) и configs/katapult/ (katapult) и уже закоммичены в каталог;
этот скрипт нужен, чтобы воспроизвести их после смены Kconfig (например, обновления Klipper)
и чтобы создать конфиги для новой платы.
Параметры исходных плат взяты из гайда https://k3d.tech/vostok/manual/electronics/firmware/.
Octopus Pro F446: гайд её не описывает; значения (12 МГц, загрузчик 32KiB, USB PA11/PA12) по схеме платы.
Katapult всегда пишется по DFU с 0x08000000, смещение приложения - стандартное для чипа (APP_OFFSET).

Использование: tools/gen_configs.py [--force] [--board ID] [--check] [--build]
  (без опций)  создать недостающие конфиги (существующие не трогает)
  --force      перезаписать существующие конфиги
  --board ID   только эта плата (id или алиас)
  --check      сгенерировать во временный каталог и сравнить с конфигами каталога по значимым ключам
               (код 1 при расхождении или отсутствии файла); ничего в каталоге не меняет
  --build      собрать каждый конфиг каталога во временном каталоге (Klipper/katapult не изменяются);
               для katapult проверяется, что katapult.bin меньше смещения приложения

Переменные окружения: KLIPPER_DIR (по умолчанию ~/klipper), KATAPULT_DIR (~/katapult), BOARDS_DIR (boards/).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True      # не оставляем __pycache__ в каталоге установщика
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vostok.boards import BoardError, Registry  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ключи, по которым --check сравнивает конфиги (остальное - версии, значения по умолчанию, шум olddefconfig)
SIGNIFICANT = re.compile(
    r"^CONFIG_(MCU|CLOCK_REF_FREQ|FLASH_APPLICATION_ADDRESS|LAUNCH_APP_ADDRESS|"
    r"STM32_[A-Z0-9_]*(CANBUS|USB|FLASH_START|APP_START|CLOCK_REF)[A-Z0-9_]*|USBSERIAL|CANBUS|USBCANBUS|"
    r"CANBUS_FREQUENCY|INITIAL_PINS|ENABLE_DOUBLE_RESET|ENABLE_LED|STATUS_LED_PIN)=")


class GenError(Exception):
    """Ошибка генерации: текст уходит в stderr, код выхода 1."""


def help_text():
    """Шапка модуля без префиксов: то же, что печатал ``sed`` в gen_configs.sh."""
    return __doc__.split("\n\n")[0] + "\n\n" + __doc__.split("\n\n")[1] + "\n\n"


def clock_hz(clock):
    """B_CLOCK: 8M|12M|25M -> Гц."""
    return int(clock[:-1] if clock.endswith("M") else clock) * 1000000


def hex_addr(app_offset):
    """0x8000000 + смещение (в hex без префикса), формат 0x%X."""
    return "0x%X" % (0x8000000 + int(app_offset, 16))


class Generator:
    """Построение и проверка конфигов сборки. reg - реестр (его configs_dir/katapult_dir - куда писать)."""

    def __init__(self, reg, klipper_dir, katapult_dir, tmp, force, out=None):
        self.reg = reg
        self.klipper_dir = klipper_dir
        self.katapult_dir = katapult_dir
        self.tmp = tmp
        self.force = force
        self.out = out if out is not None else sys.stdout

    def say(self, text):
        self.out.write(text + "\n")

    def gen(self, src, out, mcu, clk, addr, lines):
        """Записать конфиг out. Каждая заданная строка должна пережить olddefconfig: иначе Kconfig
        молча выбросил опцию (нет у чипа или зависимость не выполнена)."""
        if os.path.isfile(out) and not self.force:
            self.say("есть: " + out)
            return
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cfg = os.path.join(self.tmp, ".config")
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("".join(l + "\n" for l in lines))
        log = os.path.join(self.tmp, "make.log")
        with open(log, "w", encoding="utf-8") as lf:
            rc = subprocess.call(["make", "-C", src, "KCONFIG_CONFIG=" + cfg, "OUT=" + self.tmp + "/out/",
                                  "olddefconfig"], stdout=lf, stderr=subprocess.STDOUT)
        if rc != 0:
            with open(log, encoding="utf-8", errors="replace") as lf:
                sys.stderr.write("".join(lf.read().splitlines(True)[-20:]))
            raise GenError("olddefconfig не удался: " + out)
        with open(cfg, encoding="utf-8", errors="replace") as f:
            got = f.read().split("\n")
        if 'CONFIG_MCU="%s"' % mcu not in got:
            raise GenError("%s: CONFIG_MCU != %s" % (out, mcu))
        if "CONFIG_CLOCK_REF_FREQ=%s" % clk not in got:
            raise GenError("%s: CONFIG_CLOCK_REF_FREQ != %s" % (out, clk))
        if "CONFIG_FLASH_APPLICATION_ADDRESS=%s" % addr not in got:
            raise GenError("%s: CONFIG_FLASH_APPLICATION_ADDRESS != %s" % (out, addr))
        for line in lines:
            if line not in got:
                raise GenError("%s: Kconfig отбросил или изменил заданную опцию после olddefconfig: %s" % (out, line))
        shutil.copyfile(cfg, out)
        self.say("создан: " + out)

    @staticmethod
    def can_lines(b, mode):
        """Строки CAN платы по CAN_KIND: cmenu (мост) | mmenu (меню G0B1/H7) | direct (отдельная опция)."""
        res = []
        if mode == "bridge":
            res += ["CONFIG_STM32_USBCANBUS_%s=y" % b.usb, "CONFIG_STM32_CMENU_CANBUS_%s=y" % b.can]
        else:
            if b.can_kind == "mmenu":
                res.append("CONFIG_STM32_MMENU_CANBUS_%s=y" % b.can)
            elif b.can_kind == "direct":
                res.append("CONFIG_STM32_CANBUS_%s=y" % b.can)
            else:
                # как в bash: сообщение в stderr, строки CAN не добавляются, генерация продолжается
                sys.stderr.write("%s: CAN_KIND=%s не подходит для платы головы\n" % (b.id, b.can_kind))
                return res
        res.append("CONFIG_CANBUS_FREQUENCY=1000000")
        return res

    def gen_klipper_cfg(self, b, kind):
        out = self.reg.cfg_path(b.id, kind)
        if out is None:
            return
        lines = ["CONFIG_LOW_LEVEL_OPTIONS=y", "CONFIG_MACH_STM32=y", "CONFIG_MACH_%s=y" % b.mach,
                 "CONFIG_STM32_FLASH_START_%s=y" % b.app_offset, "CONFIG_STM32_CLOCK_REF_%s=y" % b.clock]
        pins = b.initial_pins
        if kind == "usb":
            lines.append("CONFIG_STM32_USB_%s=y" % b.usb)
        elif kind == "bridge":
            lines += self.can_lines(b, "bridge")
            pins = b.bridge_initial_pins
        elif kind == "can":
            lines += self.can_lines(b, "head")
        lines.append('CONFIG_INITIAL_PINS="%s"' % pins)
        self.gen(self.klipper_dir, str(out), b.chip, str(clock_hz(b.clock)), hex_addr(b.app_offset), lines)

    def gen_katapult_cfg(self, b):
        """katapult пишется с 0x08000000, приложение с APP_OFFSET."""
        out = self.reg.cfg_path(b.id, "katapult")
        lines = ["CONFIG_LOW_LEVEL_OPTIONS=y", "CONFIG_MACH_STM32=y", "CONFIG_MACH_%s=y" % b.mach,
                 "CONFIG_STM32_FLASH_START_0000=y", "CONFIG_STM32_CLOCK_REF_%s=y" % b.clock]
        if b.role == "head":
            lines += self.can_lines(b, "head")
        else:
            lines.append("CONFIG_STM32_USB_%s=y" % b.usb)
        lines += ["CONFIG_STM32_APP_START_%s=y" % b.app_offset, 'CONFIG_INITIAL_PINS="%s"' % b.katapult_initial_pins]
        if b.katapult_double_reset == "y":
            lines.append("CONFIG_ENABLE_DOUBLE_RESET=y")
        if b.katapult_led:
            lines += ["CONFIG_ENABLE_LED=y", 'CONFIG_STATUS_LED_PIN="%s"' % b.katapult_led]
        self.gen(self.katapult_dir, str(out), b.chip, str(clock_hz(b.clock)), "0x8000000", lines)

    def gen_all(self, ids):
        for i in ids:
            b = self.reg.get(i)
            for kind in ("usb", "bridge", "can"):
                self.gen_klipper_cfg(b, kind)
            self.gen_katapult_cfg(b)


def sig(path):
    """Значимые строки конфига, отсортированные."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return sorted(l for l in f.read().split("\n") if SIGNIFICANT.match(l))


def do_check(reg, ids, klipper_dir, katapult_dir, tmp, root):
    """--check: сгенерировать во временный каталог и сравнить с configs/ по значимым ключам."""
    gen_configs = os.path.join(tmp, "gen", "configs")
    greg = Registry(reg.boards_dir, gen_configs, os.path.join(gen_configs, "katapult"))
    devnull = open(os.devnull, "w")
    try:
        Generator(greg, klipper_dir, katapult_dir, tmp, True, out=devnull).gen_all(ids)
    finally:
        devnull.close()
    bad = n = 0
    found = []
    for d, _, files in os.walk(gen_configs):
        found += [os.path.join(d, f) for f in files if f.endswith(".config")]
    for new in sorted(found):
        rel = os.path.relpath(new, gen_configs)
        old = os.path.join(str(reg.configs_dir), rel)
        n += 1
        if not os.path.isfile(old):
            print("НЕТ ФАЙЛА: configs/" + rel)
            bad += 1
            continue
        fo, fn = os.path.join(tmp, "sig.old"), os.path.join(tmp, "sig.new")
        for f, p in ((fo, old), (fn, new)):
            with open(f, "w", encoding="utf-8") as fh:
                fh.write("".join(l + "\n" for l in sig(p)))
        pr = subprocess.run(["diff", fo, fn], stdout=subprocess.PIPE)
        if pr.returncode == 0:
            print("совпадает: configs/" + rel)
        else:
            print("РАСХОЖДЕНИЕ: configs/%s (< каталог, > сгенерировано)" % rel)
            for l in pr.stdout.decode("utf-8", "replace").rstrip("\n").split("\n"):
                print("    " + l)
            bad += 1
    # пресет пинов главной платы (TEMPLATE) должен существовать: octopus_pro - встроенный,
    # прочие - templates/boards/main/<имя>.cfg; у плат голов (ROLE=head) TEMPLATE - templates/boards/<имя>.cfg
    for i in ids:
        b = reg.get(i)
        t = b.template
        if not t or t == "octopus_pro":
            continue
        n += 1
        sub = os.path.join("templates", "boards") if b.role == "head" else os.path.join("templates", "boards", "main")
        if os.path.isfile(os.path.join(root, sub, t + ".cfg")):
            print("совпадает: пресет пинов %s -> %s" % (i, t))
        else:
            print("НЕТ ФАЙЛА: %s/%s.cfg (TEMPLATE платы %s)" % (sub, t, i))
            bad += 1
    print("проверено: %d, расхождений: %d" % (n, bad))
    return 0 if bad == 0 else 1


def _grep_val(text, key):
    m = re.search(r"^%s=(.*)$" % re.escape(key), text, re.M)
    return m.group(1) if m else ""


def do_build(reg, ids, klipper_dir, katapult_dir, tmp):
    """--build: собрать каждый конфиг каталога во временном каталоге."""
    fail = 0
    fmt = "%-20s %-9s %-13s %-9s %-11s %-11s %s%s"
    # bash-printf выравнивает заголовок по байтам, а не по символам: повторяем это (1:1 с gen_configs.sh)
    head = ["плата", "вид", "CONFIG_MCU", "CLOCK", "APP_ADDR", "CAN-пины"]
    widths = [20, 9, 13, 9, 11, 11]
    print(" ".join(h + " " * max(0, w - len(h.encode("utf-8"))) for h, w in zip(head, widths)) + " bin (байт)")
    bdir = os.path.join(tmp, "b")
    for i in ids:
        b = reg.get(i)
        for kind in ("usb", "bridge", "can", "katapult"):
            cfg = reg.cfg_path(i, kind)
            if cfg is None:
                continue
            if not cfg.is_file():
                sys.stderr.write("%s %s: нет файла %s\n" % (i, kind, cfg))
                fail = 1
                continue
            if kind == "katapult":
                src, binname = katapult_dir, "katapult.bin"
            else:
                src, binname = klipper_dir, "klipper.bin"
            shutil.rmtree(bdir, ignore_errors=True)
            os.makedirs(bdir)
            dotcfg = os.path.join(bdir, ".config")
            shutil.copyfile(str(cfg), dotcfg)
            base = ["make", "-C", src, "KCONFIG_CONFIG=" + dotcfg, "OUT=" + bdir + "/out/"]
            log = os.path.join(bdir, "log")
            with open(log, "w", encoding="utf-8") as lf:
                ok = subprocess.call(base + ["olddefconfig"], stdout=lf, stderr=subprocess.STDOUT) == 0
                if ok:
                    ok = subprocess.call(base + ["-j%d" % (os.cpu_count() or 1)], stdout=lf,
                                         stderr=subprocess.STDOUT) == 0
            if not ok:
                with open(log, encoding="utf-8", errors="replace") as lf:
                    sys.stderr.write("".join(lf.read().splitlines(True)[-25:]))
                sys.stderr.write("%s %s: сборка не удалась\n" % (i, kind))
                fail = 1
                continue
            size = os.stat(os.path.join(bdir, "out", binname)).st_size
            with open(dotcfg, encoding="utf-8", errors="replace") as f:
                text = f.read()
            m = re.search(r'^CONFIG_MCU="(.*)"$', text, re.M)
            mcu = m.group(1) if m else ""
            clk = _grep_val(text, "CONFIG_CLOCK_REF_FREQ")
            addr = _grep_val(text, "CONFIG_FLASH_APPLICATION_ADDRESS")
            m = re.search(r"^CONFIG_STM32_(?:MMENU_|CMENU_)?CANBUS_(P[A-Z0-9]+_P[A-Z0-9]+)=y", text, re.M)
            canpins = m.group(1) if m else ""
            note = ""
            off = int(b.app_offset, 16)
            if kind == "katapult":
                if not size < off:
                    note = " ОШИБКА: katapult.bin >= смещения приложения %d" % off
                    fail = 1
            else:
                flash = _grep_val(text, "CONFIG_FLASH_SIZE")
                if not size <= (int(flash, 0) if flash else 0) - off:
                    note = " ОШИБКА: klipper.bin не помещается во флеш"
                    fail = 1
            print(fmt % (i, kind, mcu, clk, addr, canpins or "-", size, note))
    return 0 if fail == 0 else 1


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    force = check = build = False
    only = ""
    reg = Registry(os.environ.get("BOARDS_DIR") or os.path.join(ROOT, "boards"), os.path.join(ROOT, "configs"))
    klipper_dir = os.environ.get("KLIPPER_DIR") or os.path.expanduser("~/klipper")
    katapult_dir = os.environ.get("KATAPULT_DIR") or os.path.expanduser("~/katapult")
    while args:
        a = args.pop(0)
        if a == "--force":
            force = True
        elif a == "--check":
            check = True
        elif a == "--build":
            build = True
        elif a == "--board":
            if not args:
                sys.stderr.write("--board: нужен id платы\n")
                return 2
            name = args.pop(0)
            only = reg.resolve(name)
            if not only:
                sys.stderr.write("неизвестная плата: %s\n" % name)
                return 2
        elif a in ("-h", "--help"):
            sys.stdout.write(help_text())
            return 0
        else:
            sys.stderr.write("неизвестный параметр: %s\n" % a)
            return 2

    tmp = tempfile.mkdtemp()
    try:
        ids = [only] if only else reg.list()
        if check:
            return do_check(reg, ids, klipper_dir, katapult_dir, tmp, ROOT)
        if build:
            return do_build(reg, ids, klipper_dir, katapult_dir, tmp)
        Generator(reg, klipper_dir, katapult_dir, tmp, force).gen_all(ids)
        return 0
    except (GenError, BoardError) as e:
        sys.stderr.write("%s\n" % e)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
