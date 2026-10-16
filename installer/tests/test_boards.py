"""Тесты vostok.boards: реестр из installer/boards и тексты ошибок разбора (bash-реестр lib/boards.sh удалён, сверка с ним снята)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, INSTALL)

from vostok import boards  # noqa: E402

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

    def test_rank(self):
        """0 - плата гайда (board_resolve h723), 1 - VERIFIED=yes, 2 - остальные."""
        r = boards.registry()
        self.assertEqual(r.rank("octopus-pro-h723"), 0)
        self.assertEqual(r.rank("manta-m8p-v2.0"), 1)
        self.assertEqual(r.rank("spider-v3-h723"), 2)
        for i in r.list("main"):
            want = 0 if i == r.resolve("h723") else (1 if r.get(i).verified == "yes" else 2)
            self.assertEqual(r.rank(i), want, i)

    def test_ebb_alias_and_verified(self):
        r = boards.registry()
        self.assertEqual(r.resolve("ebb36"), "ebb42")
        self.assertEqual(r.resolve("EBB36"), "ebb42")
        self.assertEqual(r.get("ebb42").label, "BTT EBB42/EBB36")
        for i in ("ebb42", "h36-v1.3", "h36-v2", "manta-m8p-v2.0"):
            self.assertEqual(r.get(i).verified, "yes", i)

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

    # ------------------------------------------------------------ распиновка

    def test_pinout_field_optional(self):
        self.write("good", GOOD)
        b = boards.Registry(self.dir).get("good")
        self.assertEqual((b.pinout, b.pinout_list), ("", []))
        self.write("pin", GOOD + 'PINOUT="A/p.png  B/q.pdf"\n')
        self.assertEqual(boards.Registry(self.dir).get("pin").pinout_list, ["A/p.png", "B/q.pdf"])

    def test_pinout_paths_and_url(self):
        pins = self.dir / "pins"
        (pins / "A").mkdir(parents=True)
        (pins / "A" / "p.png").write_bytes(b"x")
        self.write("pin", GOOD + 'PINOUT="A/p.png A/missing.png"\n')
        saved = {k: os.environ.get(k) for k in ("PINOUTS_DIR", "VOSTOK_PINOUT_URL")}
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        os.environ["PINOUTS_DIR"] = str(pins)
        os.environ.pop("VOSTOK_PINOUT_URL", None)
        r = boards.Registry(self.dir)
        self.assertEqual(r.pinout_paths("pin"), [pins / "A" / "p.png"])      # несуществующий файл отброшен
        self.assertEqual(boards.pinout_url("A/p.png"), boards.PINOUT_URL_DEFAULT + "A/p.png")
        os.environ["VOSTOK_PINOUT_URL"] = "https://example.org/fork/"
        self.assertEqual(boards.pinout_url("A/p.png"), "https://example.org/fork/A/p.png")

    def test_real_registry_pinouts(self):
        r = boards.registry()
        self.assertTrue(r.pinout_paths("octopus-pro-h723")[0].is_file())
        self.assertEqual(len(r.pinout_paths("ebb42")), 2)
        for i in ("alps", "spider-v3-h723"):
            self.assertEqual(r.get(i).pinout_list, [])

    def test_pinout_note_octopus_v11(self):
        from vostok import ui
        r = boards.registry()
        t = "\n".join(ui.pinout_lines(r, "octopus-pro-h723"))
        self.assertIn("онлайн: ", t)
        self.assertIn("Внимание, ", t)
        self.assertIn("HE0=PA0", t)
        self.assertNotIn("Внимание", "\n".join(ui.pinout_lines(r, "ebb42")))

    def test_pinout_lines_texts(self):
        from vostok import ui
        r = boards.registry()
        t = "\n".join(ui.pinout_lines(r, "h36-v1.3"))
        self.assertIn("Схема Fysetc H36 v1.3: ", t)
        self.assertNotIn("Распиновка", t)
        t = "\n".join(ui.pinout_lines(r, "spider-v2-f446"))
        self.assertIn("Fysetc Spider v2.x v2.3: ", t)
        self.assertIn("Fysetc Spider v2.x v2.2: ", t)
        t = "\n".join(ui.pinout_lines(r, "ebb42"))
        self.assertIn("ebb42_v1_1_v1_2: ", t)
        self.assertIn("ebb36_v1_1_v1_2: ", t)
        t = "\n".join(ui.pinout_lines(r, "spider-v3-h723"))
        self.assertIn("Fysetc Spider v3.0 H723: картинки распиновки в каталоге нет, документация: ", t)
        self.assertEqual(ui.pinout_lines(r, "alps")[0][:2], "  ")
        self.assertIn("ALPS: официального листа распиновки нет", ui.pinout_lines(r, "alps")[0])


if __name__ == "__main__":
    unittest.main()
