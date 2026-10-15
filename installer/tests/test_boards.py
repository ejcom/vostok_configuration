"""Тесты vostok.boards: реестр из installer/boards и сверка с lib/boards.sh на тех же файлах (и на сломанных)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, INSTALL)

from vostok import boards  # noqa: E402

BOARDS_SH = os.path.join(INSTALL, "lib", "boards.sh")
HAVE_BASH = shutil.which("bash") is not None and os.path.isfile(BOARDS_SH)

GOOD = '''# комментарий
LABEL="Тестовая плата"
ROLE="main"
CHIP="stm32x"
FAMILY="f4"
MACH="STM32F4"
CLOCK="8M"
APP_OFFSET="8000"
USB="PA11_PA12"
CAN="PD0_PD1"
CAN_KIND="cmenu"
CFG="stm32x"
ALIASES="Alias One two"
VERIFIED=yes
'''


def bash(script, boards_dir, configs_dir=None):
    env = dict(os.environ, BOARDS_DIR=str(boards_dir))
    if configs_dir:
        env["CONFIGS_DIR"] = str(configs_dir)
    env.pop("KATAPULT_CONFIGS", None)
    pr = subprocess.run(["bash", "-c", "source '%s'; %s" % (BOARDS_SH, script)], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return pr.returncode, pr.stdout, pr.stderr


class BoardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, name, text):
        (self.dir / (name + ".board")).write_text(text, encoding="utf-8")

    def err(self, text, name="x"):
        self.write(name, text)
        with self.assertRaises(boards.BoardError) as cm:
            boards.Registry(self.dir).get(name)
        return str(cm.exception)

    # ------------------------------------------------------------ формат

    def test_parse_good(self):
        self.write("good", GOOD)
        b = boards.Registry(self.dir).get("good")
        self.assertEqual((b.id, b.label, b.role, b.chip, b.cfg, b.verified), ("good", "Тестовая плата", "main", "stm32x", "stm32x", "yes"))
        self.assertEqual(b.alias_list, ["Alias", "One", "two"])
        self.assertEqual(b.field("CAN_KIND"), "cmenu")
        self.assertEqual(b.note, "")

    def test_errors_text(self):
        d = str(self.dir)
        self.assertEqual(self.err(GOOD + "FOO=1\n"), "boards: %s/x.board: неизвестное поле FOO" % d)
        self.assertEqual(self.err(GOOD + "NOTE=a b\n"), "boards: %s/x.board: значение NOTE надо взять в двойные кавычки" % d)
        self.assertEqual(self.err(GOOD + 'NOTE="a\n'), "boards: %s/x.board: значение NOTE надо взять в двойные кавычки" % d)
        self.assertEqual(self.err(GOOD + "мусор\n"), "boards: %s/x.board: не разобрана строка: мусор" % d)
        self.assertEqual(self.err(GOOD.replace('LABEL="Тестовая плата"\n', "")),
                         "boards: %s/x.board: не задано обязательное поле LABEL" % d)
        self.assertEqual(self.err(GOOD.replace('CAN_KIND="cmenu"\n', "")),
                         "boards: %s/x.board: для CAN нужно поле CAN_KIND" % d)
        self.assertEqual(self.err(GOOD.replace('ROLE="main"', 'ROLE="zzz"')),
                         "boards: %s/x.board: ROLE должен быть main|head|alps" % d)
        self.assertEqual(self.err(GOOD.replace('"cmenu"', '"zzz"')),
                         "boards: %s/x.board: CAN_KIND должен быть cmenu|mmenu|direct" % d)
        self.assertEqual(self.err(GOOD.replace("VERIFIED=yes", "VERIFIED=maybe")),
                         "boards: %s/x.board: VERIFIED должен быть yes|no" % d)

    def test_missing_and_bad_id(self):
        r = boards.Registry(self.dir)
        for bad in ("nosuch", "Bad", "../x", ""):
            with self.assertRaises(boards.BoardError) as cm:
                r.get(bad)
            self.assertTrue(str(cm.exception).startswith("boards: нет описания платы '%s'" % bad))

    def test_crlf_and_comments(self):
        self.write("crlf", GOOD.replace("\n", "\r\n") + "   # хвост\r\n\r\n")
        self.assertEqual(boards.Registry(self.dir).get("crlf").label, "Тестовая плата")

    # ------------------------------------------------------------ реестр

    def test_real_registry(self):
        r = boards.registry()
        mains = r.list("main")
        self.assertIn("octopus-pro-h723", mains)
        self.assertEqual(len(r.ids()), len(list((Path(INSTALL) / "boards").glob("*.board"))))
        for i in r.ids():  # все платы реестра разбираются
            self.assertEqual(r.get(i).id, i)
        self.assertEqual(r.resolve("H723"), "octopus-pro-h723")
        self.assertIsNone(r.resolve("nosuch"))
        self.assertIsNone(r.resolve(""))
        self.assertTrue(r.has_bridge("octopus-pro-h723"))
        self.assertFalse(r.has_bridge("alps"))
        self.assertEqual(r.by_cfg("stm32h723xx-canbridge.config"), ("octopus-pro-h723", "bridge"))
        self.assertEqual(r.by_cfg("/a/b/katapult/stm32h723xx.config"), ("octopus-pro-h723", "katapult"))
        self.assertIsNone(r.by_cfg("nosuch.config"))
        with self.assertRaises(boards.BoardError):
            r.cfg_path("alps", "zzz")

    def test_cfg_path_kinds(self):
        r = boards.registry()
        cfgs = Path(INSTALL) / "configs"
        self.assertEqual(r.cfg_path("octopus-pro-h723", "usb"), cfgs / "stm32h723xx.config")
        self.assertEqual(r.cfg_path("octopus-pro-h723", "bridge"), cfgs / "stm32h723xx-canbridge.config")
        self.assertIsNone(r.cfg_path("octopus-pro-h723", "can"))
        self.assertEqual(r.cfg_path("octopus-pro-h723", "katapult"), cfgs / "katapult" / "stm32h723xx.config")
        heads = r.list("head")
        self.assertTrue(heads)
        self.assertIsNone(r.cfg_path(heads[0], "usb"))
        self.assertTrue(str(r.cfg_path(heads[0], "can")).endswith("-can.config"))
        self.assertTrue(str(r.cfg_path(heads[0], "katapult")).endswith("-can.config"))

    # ------------------------------------------------------------ парные проверки с bash

    @unittest.skipUnless(HAVE_BASH, "нужен bash")
    def test_same_as_bash_real_boards(self):
        bdir = Path(INSTALL) / "boards"
        r = boards.Registry(bdir)
        # один запуск bash (подключение lib/boards.sh разбирает все платы - это медленно)
        script = r"""
for id in $(boards_list); do
    board_load $id
    for k in @KEYS@; do v=B_$k; printf 'F\t%s\t%s\t%s\n' $id $k "${!v}"; done
    if board_has_bridge $id; then printf 'H\t%s\t1\n' $id; else printf 'H\t%s\t0\n' $id; fi
    for kind in usb bridge can katapult; do
        if p=$(board_cfg $id $kind 2>/dev/null); then
            printf 'C\t%s\t%s\t%s\n' $id $kind "$p"
            if [[ $kind == katapult ]]; then q=katapult/$(basename $p); else q=$(basename $p); fi
            printf 'B\t%s\t%s\t%s\n' $id $kind "$(board_by_cfg $q)"
        else
            printf 'C\t%s\t%s\t-\n' $id $kind
        fi
    done
done
for role in main head alps; do printf 'L\t%s\t%s\n' $role "$(boards_list $role | tr '\n' ' ')"; done
for chip in $(for i in $(boards_list); do board_field $i CHIP; done | sort -u); do
    printf 'K\t%s\t%s\t%s\n' $chip "$(boards_for_chip $chip | tr '\n' ' ')" "$(boards_for_chip $chip main | tr '\n' ' ')"
done
for fam in $(for i in $(boards_list); do board_field $i FAMILY; done | sort -u); do
    printf 'M\t%s\t%s\n' $fam "$(boards_for_family $fam | tr '\n' ' ')"
done
for n in h723 H723 alps octopus-pro-f446 zzz; do printf 'R\t%s\t%s\n' $n "$(board_resolve $n)"; done
printf 'A\t%s\n' "$(boards_list | tr '\n' ' ')"
""".replace("@KEYS@", " ".join(boards.BOARD_KEYS))
        rc, out, err = bash(script, bdir)
        self.assertEqual(rc, 0, err)
        seen = {"F": 0, "C": 0, "B": 0}
        for line in out.split("\n"):
            if not line:
                continue
            row = line.split("\t")
            t = row[0]
            if t == "F":
                row += [""] * (4 - len(row))
                self.assertEqual(r.get(row[1]).field(row[2]), row[3], "%s.%s" % (row[1], row[2]))
                seen["F"] += 1
            elif t == "H":
                self.assertEqual(r.has_bridge(row[1]), row[2] == "1", row[1])
            elif t == "C":
                got = r.cfg_path(row[1], row[2])
                self.assertEqual(str(got) if got else "-", row[3], row[1:3])
                seen["C"] += 1
            elif t == "B":
                got = r.cfg_path(row[1], row[2])
                q = ("katapult/" + got.name) if row[2] == "katapult" else got.name
                self.assertEqual("%s %s" % r.by_cfg(q), row[3], row[1:3])
                seen["B"] += 1
            elif t == "L":
                self.assertEqual(r.list(row[1]), row[2].split(), row[1])
            elif t == "K":
                self.assertEqual(r.for_chip(row[1]), row[2].split())
                self.assertEqual(r.for_chip(row[1], "main"), row[3].split())
            elif t == "M":
                self.assertEqual(r.for_family(row[1]), row[2].split())
            elif t == "R":
                self.assertEqual(r.resolve(row[1]), row[2] or None, row[1])
            elif t == "A":
                self.assertEqual(r.ids(), row[1].split())
        self.assertGreater(seen["F"], 300)
        self.assertGreater(seen["B"], 20)

    @unittest.skipUnless(HAVE_BASH, "нужен bash")
    def test_same_errors_as_bash(self):
        cases = [GOOD + "FOO=1\n", GOOD + "NOTE=a b\n", GOOD + 'NOTE="a\n', GOOD + "мусор\n",
                 GOOD.replace('LABEL="Тестовая плата"\n', ""), GOOD.replace('CAN_KIND="cmenu"\n', ""),
                 GOOD.replace('ROLE="main"', 'ROLE="zzz"'), GOOD.replace('"cmenu"', '"zzz"'),
                 GOOD.replace("VERIFIED=yes", "VERIFIED=maybe")]
        for n, text in enumerate(cases):
            self.write("x", text)
            rc, _, berr = bash("board_load x", self.dir)
            self.assertEqual(rc, 1)
            with self.assertRaises(boards.BoardError) as cm:
                boards.Registry(self.dir).get("x")
            self.assertEqual(str(cm.exception), berr.strip(), n)
        rc, _, berr = bash("board_load nosuch", self.dir)
        with self.assertRaises(boards.BoardError) as cm:
            boards.Registry(self.dir).get("nosuch")
        self.assertEqual(str(cm.exception), berr.strip())


if __name__ == "__main__":
    unittest.main()
