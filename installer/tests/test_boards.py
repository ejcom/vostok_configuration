"""Тесты vostok.boards: реестр из installer/boards и тексты ошибок разбора (bash-реестр lib/boards.sh удалён, сверка с ним снята)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALL = os.path.dirname(HERE)
sys.path.insert(0, INSTALL)

from vostok import VostokError, boards  # noqa: E402

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

    def test_rank_pro_wins_in_f4_families(self):
        """Регрессия слияния плат 1.7: по умолчанию в семействах F446/F429 остаётся Octopus Pro, а не Octopus без Pro / LDO."""
        from vostok import configurator
        r = boards.registry()
        self.assertEqual(r.resolve("f446"), "octopus-pro-f446")
        self.assertEqual(r.resolve("f429"), "octopus-pro-f429")
        for chip, want in (("stm32f446xx", "octopus-pro-f446"), ("stm32f429xx", "octopus-pro-f429"),
                           ("stm32h723xx", "octopus-pro-h723")):
            ids = r.for_chip(chip, "main")
            self.assertEqual(configurator.rank_main_boards(r, ids)[0], want, chip)
        f4 = configurator.rank_main_boards(r, r.for_family("f4", "main"))      # выбор по семейству (DFU без by-id)
        self.assertEqual(f4[0], "octopus-pro-f446")
        self.assertLess(f4.index("octopus-pro-f429"), f4.index("octopus-f429"))
        self.assertEqual(r.guide_ids(), ["octopus-pro-h723", "octopus-pro-f446", "octopus-pro-f429"])
        self.assertIn("octopus-f446", r.for_chip("stm32f446xx", "main"))      # конкуренты в списке есть, но не первые
        self.assertIn("octopus-f429", r.for_chip("stm32f429xx", "main"))

    def test_head_values_from_registry(self):
        """--heads: значения берутся из реестра (ROLE=head); старые значения прежние, голова без шаблона - отказ."""
        r = boards.registry()
        self.assertEqual(r.head_choices(True), ["v1.3", "v2", "ebb36-gen2", "ebb36-v1.0", "ebb42", "ebb42-gen2", "sht36-v2"])
        for old in ("v1.3", "v2", "ebb42", "none", "V2"):
            self.assertEqual(r.head_value(old), old.lower())
        self.assertEqual(r.head_value("ebb36"), "ebb42")                  # алиас ebb42 (v1.1/v1.2, G0B1)
        self.assertEqual(r.head_value("h36-v2"), "v2")
        for bad in ("alps", "octopus-pro-h723", "bogus"):
            with self.assertRaises(VostokError, msg=bad) as cm:
                r.head_value(bad)
            self.assertIn("--heads: none, v1.3, v2, ebb36-gen2, ebb36-v1.0, ebb42, ebb42-gen2, sht36-v2", str(cm.exception))
        for name, want in (("sht42", "sht36-v2"), ("ebb36-gen2", "ebb36-gen2"), ("ebb42-gen2", "ebb42-gen2")):
            self.assertEqual(r.head_value(name), want, name)            # с 1.8 у всех голов реестра есть пресет
        # голова без шаблона электроники (запись реестра с пустым TEMPLATE) по-прежнему отклоняется
        import shutil, tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        shutil.copytree(boards.INSTALL_DIR / "boards", d + "/boards")
        f = Path(d) / "boards/sht36-v2.board"
        f.write_text(f.read_text(encoding="utf-8").replace('TEMPLATE="sht36_v2"', 'TEMPLATE=""'), encoding="utf-8")
        with self.assertRaises(VostokError) as cm:
            boards.Registry(Path(d) / "boards").head_value("sht36-v2")
        self.assertIn("нет шаблона электроники", str(cm.exception))
        for i in r.head_ids(True):                                         # у голов с шаблоном файл пресета существует
            self.assertTrue((boards.INSTALL_DIR / "templates/boards" / (r.get(i).template + ".cfg")).is_file(), i)

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
