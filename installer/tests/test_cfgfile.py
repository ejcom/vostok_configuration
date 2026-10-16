"""Тесты vostok.cfgfile. Парные проверки: старые tools/mcu_merge.py, tools/pin_conflicts.py, heredoc правки
printer.cfg и sed-функции модулей из lib/vostok_config.sh запускаются на тех же фикстурах, вывод и файлы сравниваются."""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, INSTALL)

from vostok import VostokError, cfgfile  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
ROOT = os.path.join(FIX, "repo_root")
ELEC = "electronics_octopus_pro_v1.1_h723_5x2240_2xH36v1.3.cfg"
MCU_MERGE = os.path.join(INSTALL, "tools", "mcu_merge.py")
PIN_CONFLICTS = os.path.join(INSTALL, "tools", "pin_conflicts.py")
LEGACY_REWRITE = os.path.join(FIX, "legacy_rewrite_printer_cfg.py")   # heredoc из lib/vostok_config.sh 1.3a
LEGACY_MODULES = os.path.join(FIX, "legacy_modules.sh")

BLOCKS = (
    "[mcu]\ncanbus_uuid: 821a4dc3b8eb\n\n"                                          # OK
    "[mcu T0CB]\ncanbus_uuid: ffffffffffff\n\n"                                     # DIFF
    "[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_AAAA-if00\n\n"   # ADD
    "[mcu alps_t1]\nserial: ЗАПОЛНИТЕ\n")                                           # TODO

SAVE_CONFIG = ("\n#*# <---------------------- SAVE_CONFIG ---------------------->\n"
               "#*# DO NOT EDIT THIS BLOCK OR BELOW. The contents are auto-generated.\n"
               "#*#\n#*# [extruder]\n#*# control = pid\n")


def old_tool(script, *args):
    pr = subprocess.run([sys.executable, "-I", script] + [str(a) for a in args], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, universal_newlines=True)
    return pr.returncode, pr.stdout


def lines(results):
    return "".join(r.line() + "\n" for r in results)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def tree(self, name, printer=None):
        """Каталог конфига из фикстуры repo_root (printer.cfg, printer_base.cfg, electronics)."""
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        for f in ("printer.cfg", "printer_base.cfg", ELEC):
            shutil.copy(os.path.join(ROOT, f), str(d / f))
        if printer is not None:
            (d / "printer.cfg").write_text(printer, encoding="utf-8")
        return d

    def pair(self, printer=None):
        return self.tree("old", printer), self.tree("new", printer)

    def assertSameFiles(self, a, b):
        names = sorted(p.name for p in a.iterdir() if not p.name.startswith("printer.cfg."))
        self.assertEqual(names, sorted(p.name for p in b.iterdir() if not p.name.startswith("printer.cfg.")))
        for n in names:
            self.assertEqual((a / n).read_bytes(), (b / n).read_bytes(), n)


class ParsingTest(Base):
    def test_sections_basic(self):
        text = ("junk: 1\n[mcu]\nserial: /dev/x # комм\n#c: 1\n  indented: 2\nname:\n\n"
                "[ stepper   motor_x ]\nstep_pin: !PA1\nstep_pin: PA2\n; x: y\n")
        s = cfgfile.sections(text)
        self.assertEqual([x.name for x in s], ["mcu", "stepper motor_x"])
        self.assertEqual(s[0].opts, {"serial": "/dev/x", "name": ""})
        self.assertEqual(s[1].items, [("step_pin", " !PA1"), ("step_pin", " PA2")])
        self.assertEqual(s[1].opts, {"step_pin": "PA2"})

    def test_read_with_includes(self):
        d = self.root
        (d / "printer.cfg").write_text("[include a.cfg]\n[include sub/*.cfg]\n[x]\n", encoding="utf-8")
        (d / "a.cfg").write_text("[include printer.cfg]\n[a]\n", encoding="utf-8")  # цикл
        (d / "sub").mkdir()
        (d / "sub" / "b.cfg").write_text("[b]\n", encoding="utf-8")
        (d / "sub" / "c.cfg").write_text("[c]\n", encoding="utf-8")
        names = [s.name for s in cfgfile.sections(cfgfile.read_with_includes(d / "printer.cfg"))]
        self.assertEqual(names, ["include a.cfg", "include sub/*.cfg", "x", "include printer.cfg", "a", "b", "c"])
        self.assertEqual(cfgfile.read_with_includes(d / "nosuch.cfg"), "")

    def test_list_same_as_old(self):
        old, new = self.pair()
        rc, out = old_tool(MCU_MERGE, old / "printer.cfg", "--list")
        got = "".join("%s\t%s\t%s\n" % m for m in cfgfile.list_mcus(new / "printer.cfg"))
        self.assertEqual(got, out)
        self.assertIn("mcu T0CB\tcanbus_uuid\t", got)


class MergeTest(Base):
    def test_merge_same_as_old(self):
        old, new = self.pair()
        blocks = self.root / "blocks.txt"
        blocks.write_text(BLOCKS, encoding="utf-8")
        for dry in (True, False, False):  # --dry, запись, повтор
            args = [old / "printer.cfg", blocks] + (["--dry"] if dry else [])
            rc, out = old_tool(MCU_MERGE, *args)
            self.assertEqual(rc, 0)
            res = cfgfile.merge_mcus(new / "printer.cfg", BLOCKS, dry=dry, backup=False)
            self.assertEqual(lines(res), out)
            self.assertSameFiles(old, new)
        text = (new / "printer.cfg").read_text(encoding="utf-8")
        self.assertIn("[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_AAAA-if00", text)
        self.assertNotIn("alps_t1", text)

    def test_merge_variants_same_as_old(self):
        variants = {
            "без mcu": "[include printer_base.cfg]\n\n[printer]\nkinematics: x\n" + SAVE_CONFIG,
            "mcu перед SAVE_CONFIG": "[mcu]\nserial: /dev/a\n\n\n" + SAVE_CONFIG,
            "пусто": "",
            "serial уже есть": "[mcu]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_AAAA-if00\n\n[mcu x]\nserial: /dev/y\n",
        }
        blocks = ("[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_AAAA-if00\n\n"
                  "[mcu alps_t1]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_BBBB-if00\n\n"
                  "[mcu x]\nserial: /dev/zzz\n\n[mcu q]\nfoo: 1\n")
        bpath = self.root / "blocks.txt"
        bpath.write_text(blocks, encoding="utf-8")
        for name, text in variants.items():
            with self.subTest(name):
                old, new = self.pair(text)
                rc, out = old_tool(MCU_MERGE, old / "printer.cfg", bpath)
                res = cfgfile.merge_mcus(new / "printer.cfg", blocks, backup=False)
                self.assertEqual(lines(res), out)
                self.assertSameFiles(old, new)

    def test_merge_backup(self):
        _, new = self.pair()
        res = cfgfile.merge_mcus(new / "printer.cfg", BLOCKS, dry=True)
        self.assertEqual([p.name for p in new.glob("printer.cfg.bak-*")], [])
        cfgfile.merge_mcus(new / "printer.cfg", BLOCKS)
        baks = list(new.glob("printer.cfg.bak-*"))
        self.assertEqual(len(baks), 1)
        self.assertTrue(re.match(r"^printer\.cfg\.bak-\d{8}-\d{6}$", baks[0].name))
        self.assertEqual(baks[0].read_bytes(), (Path(ROOT) / "printer.cfg").read_bytes())
        # нечего добавлять - копии не будет
        for b in baks:
            b.unlink()
        cfgfile.merge_mcus(new / "printer.cfg", BLOCKS)
        self.assertEqual(list(new.glob("printer.cfg.bak-*")), [])

    def test_set_same_as_old(self):
        old, new = self.pair()
        steps = [("mcu T1CB", "aaaaaaaaaaaa", False), ("mcu T1CB", "aaaaaaaaaaaa", True),
                 ("mcu T1CB", "aaaaaaaaaaaa", False), ("mcu nosuch", "bbbbbbbbbbbb", False),
                 ("mcu T1CB", "AAAAAAAAAAAA", False)]
        for name, uuid, force in steps:
            args = [old / "printer.cfg", "--set", name, uuid] + (["--force"] if force else [])
            rc, out = old_tool(MCU_MERGE, *args)
            res = cfgfile.set_canbus_uuid(new / "printer.cfg", name, uuid, force=force)
            self.assertEqual(res.line() + "\n", out, (name, uuid, force))
            self.assertSameFiles(old, new)
        self.assertEqual(list(new.glob("printer.cfg.bak-*")), [])

    def test_set_todo_and_serial(self):
        text = ("[mcu]\ncanbus_uuid: ЗАПОЛНИТЕ\n\n[mcu a]\nserial: /dev/x\n\n[mcu b]\nfoo: 1\n\n[mcu c]\ncanbus_uuid:  # пусто\n"
                + SAVE_CONFIG)
        old, new = self.pair(text)
        for name in ("mcu", "mcu a", "mcu b", "mcu c"):
            for force in (False, True):
                args = [old / "printer.cfg", "--set", name, "0123456789ab"] + (["--force"] if force else [])
                rc, out = old_tool(MCU_MERGE, *args)
                res = cfgfile.set_canbus_uuid(new / "printer.cfg", name, "0123456789ab", force=force)
                self.assertEqual(res.line() + "\n", out, (name, force))
                self.assertSameFiles(old, new)

    def test_set_missing_file(self):
        with self.assertRaises(VostokError):
            cfgfile.set_canbus_uuid(self.root / "nosuch.cfg", "mcu", "aaaaaaaaaaaa")


class PinConflictsTest(Base):
    BAD = ("[include extra.cfg]\n"
           "[stepper motor_x]\nstep_pin: PA1\ndir_pin: !PA2\nenable_pin: !PB3\nstep_pin: PA9\n\n"
           "[fan]\npin: PA1\n\n"
           "[heater_bed]\nheater_pin: T0CB:PB9\nsensor_pin: PC1\n\n"
           "[spi]\nspi_software_sclk_pin: PA5\n"
           "[tmc2209 stepper_x]\nuart_pin: PB3\nspi_software_sclk_pin: PA5\n"
           "[probe]\npin: ^PC1\nz_virtual_endstop: probe:z_virtual_endstop\n"
           "[fan]\nstep_pin: PA9 # тот же пин в другой секции\n")
    EXTRA = "[extruder]\nheater_pin: T0CB:pb9\nstep_pin: PA2\n[led l]\nred_pin: probe:PA1\n"

    def check(self, d):
        rc, out = old_tool(PIN_CONFLICTS, d / "printer.cfg")
        self.assertEqual(lines(cfgfile.pin_conflicts(d / "printer.cfg")), out)
        return out

    def test_stock(self):
        out = self.check(self.tree("t"))
        self.assertEqual(out, "")

    def test_conflicts(self):
        d = self.root / "t2"
        d.mkdir()
        (d / "printer.cfg").write_text(self.BAD, encoding="utf-8")
        (d / "extra.cfg").write_text(self.EXTRA, encoding="utf-8")
        out = self.check(d)
        self.assertIn("CONFLICT\tmcu:PA1\t[stepper motor_x] step_pin; [fan] pin", out)
        self.assertIn("CONFLICT\tT0CB:PB9\t", out)
        self.assertIn("CONFLICT\tmcu:PA9\t[stepper motor_x] step_pin; [fan] step_pin", out)

    def test_missing_file(self):
        self.assertEqual(cfgfile.pin_conflicts(self.root / "nothing.cfg"), [])
        self.assertEqual(old_tool(PIN_CONFLICTS, self.root / "nothing.cfg")[1], "")

    def test_user_configs(self):
        # все пользовательские electronics из фикстуры: те же результаты, что у старой утилиты
        for f in sorted(Path(ROOT, "user_configs").glob("*.cfg")) + [Path(ROOT, "chamber_heater.cfg")]:
            d = self.root / ("u_" + f.stem)
            d.mkdir()
            shutil.copy(str(f), str(d / "printer.cfg"))
            self.check(d)


class StateAndRewriteTest(Base):
    def heredoc(self):
        return Path(LEGACY_REWRITE).read_text(encoding="utf-8")

    def old_rewrite(self, path, el, blocks):
        bpath = path.parent / "blocks.tmp"
        bpath.write_text(blocks, encoding="utf-8")
        pr = subprocess.run([sys.executable, "-I", "-", str(path), el, str(bpath)], input=self.heredoc(),
                            universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        bpath.unlink()
        self.assertEqual(pr.returncode, 0, pr.stderr)

    def test_cfg_state(self):
        d = self.root
        cases = {"vostok": "# x\n[include printer_base.cfg]\n", "vostok2": "  [include   printer_base.cfg]  # c\n",
                 "foreign": "[include mainsail.cfg]\n[mcu]\nserial: /dev/x\n", "blank": "", "blank2": "\n  \n# c\n  # d\n",
                 "foreign2": "# [include printer_base.cfg]\n[mcu]\n"}
        want = {}
        for n, text in cases.items():
            (d / n).write_text(text, encoding="utf-8")
            sh = ("cfg_state() { [[ -f $1 ]] || { echo none; return 0; }\n"
                  "if ! grep -Eqv '^[[:space:]]*(#.*)?$' \"$1\"; then echo blank\n"
                  "elif grep -Eq '^[[:space:]]*\\[include[[:space:]]+printer_base\\.cfg\\]' \"$1\"; then echo vostok\n"
                  "else echo foreign; fi; }; cfg_state \"$1\"")
            want[n] = subprocess.run(["bash", "-c", sh, "bash", str(d / n)], stdout=subprocess.PIPE,
                                     universal_newlines=True).stdout.strip()
            self.assertEqual(cfgfile.cfg_state(d / n), want[n], n)
        self.assertEqual(cfgfile.cfg_state(d / "nosuch"), "none")
        self.assertEqual(cfgfile.cfg_state(os.path.join(FIX, "kiauh_printer.cfg")), "foreign")
        self.assertEqual(cfgfile.cfg_state(os.path.join(ROOT, "printer.cfg")), "vostok")
        self.assertEqual(sorted(set(want.values())), ["blank", "foreign", "vostok"])

    def test_rewrite_same_as_heredoc(self):
        blocks = ("[mcu]\ncanbus_uuid: aaaaaaaaaaaa\n\n[mcu T0CB]\ncanbus_uuid: bbbbbbbbbbbb\n\n"
                  "[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_X-if00\n\n")
        newel = "electronics_octopus_pro_v1.1_h723_5x2209_2xebb42.cfg"
        sources = {
            "vostok": Path(ROOT, "printer.cfg").read_text(encoding="utf-8"),
            "vostok+save": Path(ROOT, "printer.cfg").read_text(encoding="utf-8") + SAVE_CONFIG,
            "foreign": Path(FIX, "kiauh_printer.cfg").read_text(encoding="utf-8"),
            "без include электроники": "[include printer_base.cfg]\n\n[mcu]\nserial: /dev/x\n# про T0\n[mcu T0CB]\ncanbus_uuid: 1\n# коммент\n\n[printer]\nx: 1\n",
            "нет mcu": "# шапка\n[include printer_base.cfg]\n[include electronics_old.cfg] # c\n[printer]\n" + SAVE_CONFIG,
            "пусто": "",
            "mcu перед SAVE_CONFIG": "[printer]\na: 1\n[mcu]\nserial: /dev/x\n" + SAVE_CONFIG,
        }
        for blk in (blocks, blocks.rstrip("\n")):
            for name, text in sources.items():
                with self.subTest(name):
                    old = self.root / "old" / name.replace(" ", "_").replace("/", "_")
                    new = self.root / "new" / name.replace(" ", "_").replace("/", "_")
                    old.parent.mkdir(exist_ok=True)
                    new.parent.mkdir(exist_ok=True)
                    old.write_text(text, encoding="utf-8")
                    new.write_text(text, encoding="utf-8")
                    self.old_rewrite(old, newel, blk)
                    cfgfile.rewrite_printer_cfg(new, newel, blk)
                    self.assertEqual(new.read_bytes(), old.read_bytes())
                    self.assertEqual(cfgfile.rewrite_printer_text(text, newel, blk), old.read_text(encoding="utf-8"))
        self.assertEqual(list((self.root / "new").glob("*.bak-*")), [])

    def test_rewrite_result_sane(self):
        text = (Path(ROOT) / "printer.cfg").read_text(encoding="utf-8")
        out = cfgfile.rewrite_printer_text(text, "electronics_x.cfg", "[mcu]\ncanbus_uuid: cccccccccccc\n")
        self.assertEqual(out.count("[include electronics_x.cfg] # Файл с конфигурацией электроники"), 1)
        self.assertEqual([m for m in re.findall(r"^\[mcu[^\]]*\]", out, re.M)], ["[mcu]"])
        self.assertIn("cccccccccccc", out)
        self.assertNotIn("bcc1147e110d", out)


class ModulesTest(Base):
    FUNCS = None

    def bash_funcs(self):
        return Path(LEGACY_MODULES).read_text(encoding="utf-8")

    def old(self, func, cfg, name):
        pr = subprocess.run(["bash", "-c", self.bash_funcs() + "\n" + func + ' "$1" "$2"', "bash", str(cfg), name],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(pr.returncode, 0, pr.stderr)
        return pr.stdout.strip()

    TEXTS = {
        "после electronics": "[include printer_base.cfg]\n[include electronics_a.cfg] # c\n[printer]\nx: 1\n",
        "закомментирован": "[include printer_base.cfg]\n[include electronics_a.cfg]\n  #  [include chamber_heater.cfg] # п\n[printer]\n",
        "активен": "[include printer_base.cfg]\n[include chamber_heater.cfg]\n[printer]\n",
        "SAVE_CONFIG без include": "[printer]\nx: 1\n" + SAVE_CONFIG,
        "в конец": "[printer]\nx: 1\n",
        "в конец без перевода строки": "[printer]\nx: 1",
        "пусто": "",
        "две electronics": "[include electronics_a.cfg]\n[include electronics_b.cfg]\n#*# <\n",
    }

    def test_state_and_add_same_as_bash(self):
        for name, text in self.TEXTS.items():
            with self.subTest(name):
                old = self.root / "o.cfg"
                new = self.root / "n.cfg"
                old.write_text(text, encoding="utf-8")
                new.write_text(text, encoding="utf-8")
                self.assertEqual(cfgfile.module_state(new, "chamber_heater.cfg"),
                                 self.old("module_state", old, "chamber_heater.cfg"))
                if "активен" in name:
                    continue
                self.old("module_add_include", old, "chamber_heater.cfg")
                cfgfile.module_add_include(new, "chamber_heater.cfg")
                self.assertEqual(new.read_bytes(), old.read_bytes())
                self.assertEqual(cfgfile.module_state(new, "chamber_heater.cfg"), "active")

    def test_state_dot_is_literal(self):
        # намеренное отличие от bash: точка в имени файла экранируется (grep -E считал её любым символом)
        p = self.root / "p.cfg"
        p.write_text("# [include chamber_heaterXcfg]\n", encoding="utf-8")
        self.assertEqual(cfgfile.module_state(p, "chamber_heater.cfg"), "none")
        self.assertEqual(self.old("module_state", p, "chamber_heater.cfg"), "commented")

    def test_add_include_stock(self):
        _, new = self.pair()
        old, _ = self.pair()
        self.old("module_add_include", old / "printer.cfg", "chamber_heater.cfg")
        cfgfile.module_add_include(new / "printer.cfg", "chamber_heater.cfg", backup=True)
        self.assertEqual((old / "printer.cfg").read_bytes(), (new / "printer.cfg").read_bytes())
        self.assertEqual(len(list(new.glob("printer.cfg.bak-*"))), 1)


class AtomicWriteTest(Base):
    def test_backup_and_mode(self):
        p = self.root / "a.cfg"
        p.write_text("старое\n", encoding="utf-8")
        os.chmod(str(p), 0o640)
        bak = cfgfile.atomic_write(p, "новое\n")
        self.assertEqual(p.read_text(encoding="utf-8"), "новое\n")
        self.assertEqual(bak.read_text(encoding="utf-8"), "старое\n")
        self.assertTrue(re.match(r"^a\.cfg\.bak-\d{8}-\d{6}$", bak.name))
        self.assertEqual(stat.S_IMODE(os.stat(str(p)).st_mode), 0o640)
        self.assertEqual(sorted(x.name for x in self.root.iterdir()), sorted(["a.cfg", bak.name]))

    def test_no_backup_and_new_file(self):
        p = self.root / "b.cfg"
        self.assertIsNone(cfgfile.atomic_write(p, "x"))
        self.assertIsNone(cfgfile.atomic_write(p, "y", backup=False))
        self.assertEqual(p.read_text(encoding="utf-8"), "y")
        self.assertEqual([x.name for x in self.root.iterdir()], ["b.cfg"])

    def test_symlink_target_updated(self):
        real = self.root / "real.cfg"
        real.write_text("1", encoding="utf-8")
        link = self.root / "link.cfg"
        link.symlink_to(real)
        cfgfile.atomic_write(link, "2", backup=False)
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_text(encoding="utf-8"), "2")

    def test_backup_file_stamp(self):
        p = self.root / "c.cfg"
        self.assertIsNone(cfgfile.backup_file(p))
        p.write_text("z", encoding="utf-8")
        self.assertEqual(cfgfile.backup_file(p, "20260101-000000").name, "c.cfg.bak-20260101-000000")


if __name__ == "__main__":
    unittest.main()
