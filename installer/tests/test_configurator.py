"""Тесты vostok.configurator: определение железа, выбор electronics, запись конфига, модули, командная строка.

Все пути во временном каталоге; внешние программы (lsusb, ip, dfu-util) подменены FakeRunner, ввод пользователя -
подменой ui._read_tty/ui.have_tty. Реальный printer_data не затрагивается.
"""
import contextlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
INSTALLER = HERE.parent
sys.path.insert(0, str(INSTALLER))

from vostok import VostokError, cfgfile, configurator as cf, ui    # noqa: E402
from vostok.boards import Registry                                  # noqa: E402
from vostok.state import Device, DevicesFile                        # noqa: E402

FIXTURES = HERE / "fixtures"
ROOT = FIXTURES / "repo_root"
STOCK = "electronics_octopus_pro_v1.1_h723_5x2240_2xH36v1.3.cfg"
H723 = "usb-Klipper_stm32h723xx_120026000A51333231343036-if00"
ALPS1 = "usb-Klipper_stm32f072xb_AAAA00000001-if00"
ALPS2 = "usb-Klipper_stm32f072xb_AAAA00000002-if00"
REG = Registry(INSTALLER / "boards")


class FakeRunner:
    """Заглушка system.Runner: отвечает на probe() по таблице {(команда, аргументы…): (код, stdout)}."""
    dry_run = False

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []

    def run(self, cmd, **kw):
        argv = list(cmd)
        real = tuple(argv)
        self.calls.append(real)
        rc, out = self.answers.get(real, (1, ""))
        return subprocess.CompletedProcess(argv, rc, out, "")


def capture(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            res = fn(*a, **kw)
        except BaseException as e:      # noqa: B902 - возвращаем исключение вызывающему
            res = e
    return res, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._saved = (ui.opts.yes, ui.opts.dry_run, ui.opts.log_file)
        self.addCleanup(self._restore)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp = Path(self.tmpdir.name)
        self.pd = self.tmp / "pd"
        (self.pd / "config").mkdir(parents=True)
        self.byid = self.tmp / "byid"
        self.byid.mkdir()
        ui.set_options(yes=True, dry_run=False, log_file=None)

    def _restore(self):
        ui.opts.yes, ui.opts.dry_run, ui.opts.log_file = self._saved

    def env(self, **kw):
        e = cf.Env(install_dir=INSTALLER, printer_data=self.pd, byid_dir=str(self.byid), can_iface="can0",
                   devices_file=self.tmp / "devices.tsv", cfg_local=str(ROOT), cfg_tarball="file:///nonexistent",
                   templates_dir=INSTALLER / "templates")
        for k, v in kw.items():
            setattr(e, k, v)
        return e

    def touch_byid(self, *names):
        for n in names:
            (self.byid / n).touch()

    def seed_vostok(self, extra=""):
        for f in ("printer.cfg", "printer_base.cfg", "chamber_heater.cfg", STOCK):
            (self.pd / "config" / f).write_bytes((ROOT / f).read_bytes())
        if extra:
            with open(self.pd / "config" / "printer.cfg", "a", encoding="utf-8") as f:
                f.write(extra)

    def write_devices(self, rows):
        DevicesFile(self.tmp / "devices.tsv").save([Device(*r) for r in rows])

    def hw(self, main="octopus-pro-h723", heads="none", alps=0):
        hw = cf.Hardware(REG, main_board=main, heads=heads, alps_count=alps, mode="usb" if heads == "none" else "bridge")
        hw.set_head_names()
        return hw

    def detector(self, opts=None, runner=None, **envkw):
        return cf.HardwareDetector(opts or cf.Options(), self.env(**envkw), REG, runner or FakeRunner())

    def configurator(self, opts=None, hw=None, runner=None, **envkw):
        return cf.Configurator(opts or cf.Options(), self.env(**envkw), REG, hw or self.hw(), runner or FakeRunner())


class TestRank(Base):
    def test_verified_first_then_chip_desc_then_id(self):
        ids = REG.list("main")
        ranked = cf.rank_main_boards(REG, ids)
        self.assertEqual(sorted(ranked), sorted(ids))
        verified = [i for i in ranked if REG.get(i).verified == "yes"]
        self.assertEqual(ranked[:len(verified)], verified)
        self.assertEqual(ranked[0], "octopus-pro-h723")
        self.assertEqual([REG.rank(i) for i in ranked], sorted(REG.rank(i) for i in ranked))
        rest = ranked[len(verified):]
        chips = [REG.get(i).chip for i in rest]
        self.assertEqual(chips, sorted(chips, reverse=True))
        guide = REG.guide_ids()
        for chip in set(chips):                      # внутри одного чипа - сначала Octopus Pro, затем по id
            same = [i for i in rest if REG.get(i).chip == chip]
            self.assertEqual(same, sorted(same, key=lambda i: (i not in guide, i)))

    def test_guide_board_first_then_verified_then_rest(self):
        ranked = cf.rank_main_boards(REG, REG.for_chip("stm32h723xx", "main"))
        self.assertEqual(ranked, ["octopus-pro-h723", "manta-m8p-v2.0", "fly-super8-pro-h723", "kraken",
                                  "octopus-max-ez", "spider-v3-h723"])
        # плата гайда первая, даже если стоит последней во входе
        self.assertEqual(cf.rank_main_boards(REG, ["spider-v3-h723", "manta-m8p-v2.0", "octopus-pro-h723"])[0], "octopus-pro-h723")

    def test_unverified_h7_before_verified_f4_is_not_allowed(self):
        """Проверенная F4 выше непроверенной H7 (rank важнее чипа)."""
        ids = ["spider-v3-h723"] + [i for i in REG.list("main") if REG.rank(i) == 1 and REG.get(i).chip != "stm32h723xx"]
        if len(ids) > 1:
            self.assertEqual(cf.rank_main_boards(REG, ids)[-1], "spider-v3-h723")

    def test_is_single_extension_point(self):
        """main_candidates и guess_main_board берут порядок у одной функции rank_main_boards."""
        calls = []
        real = cf.rank_main_boards

        def spy(reg, ids):
            calls.append(list(ids))
            return real(reg, ids)

        with mock.patch.object(cf, "rank_main_boards", spy):
            self.touch_byid("usb-Klipper_stm32f446xx_1-if00")
            self.detector().main_candidates()
            self.configurator().guess_main_board("mcu\tserial\t/dev/serial/by-id/usb-Klipper_stm32f446xx_1-if00\n", "")
        self.assertEqual(len(calls), 2)


class TestMainBoard(Base):
    def test_main_candidates_by_chip(self):
        self.touch_byid(H723)
        self.assertEqual(self.detector().main_candidates(), ["octopus-pro-h723", "manta-m8p-v2.0", "fly-super8-pro-h723", "kraken",
                                                            "octopus-max-ez", "spider-v3-h723"])
        self.assertEqual(sorted(self.detector().main_candidates()), sorted(REG.for_chip("stm32h723xx", "main")))

    def test_main_candidates_by_dfu_family(self):
        r = FakeRunner({("lsusb", "-d", "0483:df11"): (0, "Bus 1\n"), ("sudo", "-n", "dfu-util", "-l"): (0, "0x5200")})
        self.assertEqual(self.detector(runner=r).main_candidates()[0], "octopus-pro-h723")
        r = FakeRunner({("lsusb", "-d", "0483:df11"): (0, "Bus 1\nBus 2\n"), ("sudo", "-n", "dfu-util", "-l"): (0, "0x5200")})
        self.assertEqual(self.detector(runner=r).main_candidates(), [])         # два устройства - не гадаем
        r = FakeRunner({("lsusb", "-d", "0483:df11"): (0, "Bus 1\n")})
        self.assertEqual(self.detector(runner=r).main_candidates(), [])         # семейство не определено

    def test_board_from_opt(self):
        d = self.detector()
        self.assertEqual(d.board_from_opt("H723"), "octopus-pro-h723")
        with self.assertRaises(VostokError) as cm:
            d.board_from_opt("bogus")
        self.assertIn("--main: неизвестная плата 'bogus'. Доступные: ", str(cm.exception))
        self.assertIn("octopus-pro-h723 (h723)", str(cm.exception))
        self.assertTrue(str(cm.exception).endswith("Список с описанием: install_vostok.sh --list-boards"))
        with self.assertRaises(VostokError) as cm:
            d.board_from_opt("v2")
        self.assertIn("не главная плата (h36-v2, роль head)", str(cm.exception))

    def test_prev_main_board(self):
        d = self.detector()
        self.assertEqual(d.prev_main_board(), "")
        self.write_devices([("AAAA", "stm32f072xb.config", "usb"), ("BBBB", "spider-v3-h723.config", "usb"),
                            ("CCCC", "stm32h723xx.config", "can")])
        self.assertEqual(d.prev_main_board(), "spider-v3-h723")
        self.write_devices([("AAAA", "stm32f072xb.config", "usb"), ("CCCC", "stm32h723xx.config", "can")])
        self.assertEqual(d.prev_main_board(), "")

    def test_detect_main_board_variants(self):
        hw = cf.Hardware(REG)
        # --main
        self.detector(cf.Options(main="spider-h723")).detect_main_board(hw)
        self.assertEqual((hw.main_board, hw.main), ("spider-v3-h723", "stm32h723xx"))
        # -y без железа: по умолчанию h723
        self.detector().detect_main_board(hw)
        self.assertEqual(hw.main_board, "octopus-pro-h723")
        # -y: один чип, но две платы - без прошлой платы это ошибка, в dry-run - выбор с сообщением
        self.touch_byid(H723)
        with self.assertRaises(VostokError) as cm:
            self.detector().detect_main_board(hw)
        self.assertIn("на найденном чипе возможны платы: octopus-pro-h723 manta-m8p-v2.0 fly-super8-pro-h723 kraken octopus-max-ez spider-v3-h723. Без вопросов (-y) выбрать нельзя", str(cm.exception))
        ui.opts.dry_run = True
        _, out, _ = capture(self.detector().detect_main_board, hw)
        self.assertEqual(hw.main_board, "octopus-pro-h723")
        self.assertIn("На найденном чипе возможны платы: octopus-pro-h723 manta-m8p-v2.0 fly-super8-pro-h723 kraken octopus-max-ez spider-v3-h723; выбрана octopus-pro-h723 (уточните: --main <id>)", out)
        ui.opts.dry_run = False
        # прошлая плата из devices.tsv снимает вопрос
        self.write_devices([("X", "spider-v3-h723.config", "usb")])
        _, out, _ = capture(self.detector().detect_main_board, hw)
        self.assertEqual(hw.main_board, "spider-v3-h723")
        self.assertEqual(out, "")

    def test_detect_main_board_asks(self):
        ui.opts.yes = False
        self.touch_byid(H723)
        seen = {}

        def fake_choice(q, default, options):
            seen.update(q=q, default=default, options=list(options))
            return "Fysetc Spider v3.0 H723 (spider-v3-h723)"

        hw = cf.Hardware(REG)
        with mock.patch.object(ui, "ask_choice", fake_choice):
            _, out, _ = capture(self.detector().detect_main_board, hw)
        self.assertEqual(hw.main_board, "spider-v3-h723")
        self.assertEqual(seen["q"], "Главная плата:")
        self.assertEqual(seen["default"], "Octopus Pro v1.1 H723 (octopus-pro-h723)")
        self.assertEqual(seen["options"], ["Octopus Pro v1.1 H723 (octopus-pro-h723)", "BTT Manta M8P v2.0 (manta-m8p-v2.0)",
                                           "Mellow FLY Super8 Pro H723 (fly-super8-pro-h723)", "BTT Kraken v1.0/v1.1 (kraken)",
                                           "BTT Octopus Max EZ v1.0 (octopus-max-ez)", "Fysetc Spider v3.0 H723 (spider-v3-h723)"])
        self.assertEqual(out, "")      # вопрос был - подсказки «выбрана …» нет

    def test_only_detect_without_tty(self):
        ui.opts.yes = False
        self.touch_byid(H723)
        hw = cf.Hardware(REG)
        with mock.patch.object(ui, "have_tty", lambda: False):
            capture(self.detector(cf.Options(only_detect=True)).detect_main_board, hw)
        self.assertEqual(hw.main_board, "octopus-pro-h723")

    def test_check_main_bridge(self):
        hw = self.hw("spider-v2-f446", "v2")
        with self.assertRaises(VostokError) as cm:
            self.detector().check_main_bridge(hw)
        self.assertIn("у Fysetc Spider v2.x нет USB-CAN моста", str(cm.exception))
        self.detector().check_main_bridge(self.hw("spider-v2-f446", "none"))
        self.detector().check_main_bridge(self.hw("octopus-pro-h723", "v2"))


class TestHeadsAndAlps(Base):
    def test_heads_from_option_and_guess(self):
        hw = self.hw()
        self.assertEqual(self.detector(cf.Options(heads="v1.3")).detect_heads(hw), "v1.3")
        ui.opts.yes = True
        self.assertEqual(self.detector().detect_heads(hw), "none")
        r = FakeRunner({("ip", "link", "show", "can0"): (0, "")})
        self.assertEqual(self.detector(runner=r).detect_heads(hw), "v2")
        r = FakeRunner({("lsusb", "-d", "1d50:606f"): (0, "Bus")})
        self.assertEqual(self.detector(runner=r).detect_heads(hw), "v2")

    def test_heads_menu_labels(self):
        ui.opts.yes = False
        seen = {}

        def fake_choice(q, default, options):
            seen.update(q=q, default=default, options=list(options))
            return "BTT EBB42/EBB36"

        r = FakeRunner({("ip", "link", "show", "can0"): (0, "")})
        with mock.patch.object(ui, "ask_choice", fake_choice):
            res = self.detector(runner=r).detect_heads(self.hw())
        self.assertEqual(res, "ebb42")
        self.assertEqual(seen["q"], "Платы голов по CAN (при их наличии Octopus станет мостом USB-CAN):")
        self.assertEqual(seen["default"], "Fysetc H36 v2")
        self.assertEqual(seen["options"], ["нет (пассивная плата, например fly miniAB)", "Fysetc H36 v1.3", "Fysetc H36 v2", "BTT EBB42/EBB36"])

    def test_only_detect_heads_and_alps(self):
        self.touch_byid(ALPS1, ALPS2, "usb-Klipper_stm32f072xb_AAAA00000003-if00")
        d = self.detector(cf.Options(only_detect=True))
        self.assertEqual(d.detect_alps(), 2)          # не больше двух
        self.assertEqual(self.detector(cf.Options(alps="1")).detect_alps(), 1)
        ui.opts.yes = True
        self.assertEqual(self.detector().detect_alps(), 2)       # -y: ответ по умолчанию = число найденных

    def test_detect_full(self):
        self.touch_byid(H723, ALPS1)
        hw, out, _ = capture(self.detector(cf.Options(main="h723", heads="ebb42")).detect)
        self.assertEqual((hw.main_board, hw.heads, hw.alps_count, hw.mode), ("octopus-pro-h723", "ebb42", 1, "bridge"))
        self.assertEqual(hw.head_mcu, ["T0_EBB", "T1_EBB"])
        hw, out, _ = capture(self.detector(cf.Options(main="h723", heads="none", alps="0")).detect)
        self.assertEqual(hw.mode, "usb")


class TestHardware(Base):
    def test_labels_and_names(self):
        hw = self.hw("manta-m8p-v2.0", "v1.3", 2)
        self.assertEqual(hw.main_label(), "BTT Manta M8P v2.0")
        self.assertEqual(hw.main_short(), "Manta")
        self.assertEqual(self.hw("fly-c8").main_short(), "FLY-C8")
        self.assertEqual(self.hw("spider-v3-h723").main_short(), "Spider")
        self.assertEqual(hw.head_label(), "Fysetc H36 v1.3")
        self.assertEqual(hw.head_chip(), "stm32g0b1xx")
        self.assertEqual(hw.head_cfg_name(), "stm32g0b1xx-can.config")
        self.assertEqual(hw.head_side(0), "левая (T0CB)")
        self.assertEqual(hw.head_side(1), "правая (T1CB)")
        self.assertEqual(hw.alps_side(0), "левый (T0)")
        self.assertEqual(hw.alps_side(1), "правый (T1)")
        self.assertEqual(self.hw().head_label(), "платы голов")
        self.assertEqual(self.hw().head_cfg_name(), "")
        self.assertEqual(self.hw("octopus-pro-h723", "ebb42").head_mcu, ["T0_EBB", "T1_EBB"])

    def test_cfgs(self):
        hw = self.hw("octopus-pro-h723", "v2")
        self.assertEqual(hw.klipper_cfg().name, "stm32h723xx-canbridge.config")
        self.assertEqual(hw.katapult_cfg().name, "stm32h723xx.config")
        hw.mode = "usb"
        self.assertEqual(hw.klipper_cfg().name, "stm32h723xx.config")


class TestMcuBlocks(Base):
    def test_usb_mode(self):
        res = cf.McuValues(main_serial="ABC")
        self.assertEqual(cf.mcu_blocks(self.hw(), res),
                         "[mcu]\nserial: /dev/serial/by-id/usb-Klipper_stm32h723xx_ABC-if00")
        self.assertIn("ЗАПОЛНИТЕ", cf.mcu_blocks(self.hw(), cf.McuValues()))

    def test_bridge_and_alps(self):
        res = cf.McuValues(bridge_uuid="aaaaaaaaaaaa", head_uuid=["bbbbbbbbbbbb", ""], alps_serial=["S1", ""])
        text = cf.mcu_blocks(self.hw(heads="ebb42", alps=2), res)
        self.assertEqual(text, "[mcu]\ncanbus_uuid: aaaaaaaaaaaa\n\n"
                               "[mcu T0_EBB]\ncanbus_uuid: bbbbbbbbbbbb\n\n"
                               "[mcu T1_EBB]\ncanbus_uuid: ЗАПОЛНИТЕ\n\n"
                               "[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_S1-if00\n\n"
                               "[mcu alps_t1]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_ЗАПОЛНИТЕ-if00")


# --------------------------------------------------------------------------- подсказки из printer.cfg

class TestGuess(Base):
    def test_guess_main_board_by_name_pattern_and_chip(self):
        c = self.configurator()
        self.assertEqual(c.guess_main_board("", STOCK), "octopus-pro-h723")
        self.assertEqual(c.guess_main_board("", "electronics_spider_v3_h723_5x2209.cfg"), "spider-v3-h723")
        self.assertEqual(c.guess_main_board("", "electronics_octopus_v1.1_f446_7x2209.cfg"), "octopus-pro-f446")
        # по чипу в [mcu]: проверенная плата, а прошлая плата из devices.tsv важнее
        listing = "mcu\tserial\t/dev/serial/by-id/usb-Klipper_stm32h723xx_1-if00\n"
        self.assertEqual(c.guess_main_board(listing, "custom.cfg"), "octopus-pro-h723")
        self.write_devices([("X", "spider-v3-h723.config", "usb")])
        self.assertEqual(c.guess_main_board(listing, "custom.cfg"), "spider-v3-h723")
        self.assertEqual(c.guess_main_board("", ""), "")

    def test_guess_from_printer_cfg(self):
        self.seed_vostok("\n[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_A-if00\n")
        o = cf.Options()
        self.configurator(o).guess_from_printer_cfg()
        self.assertEqual((o.main, o.heads, o.alps), ("octopus-pro-h723", "v1.3", "1"))
        # заданные опции не трогаются
        o = cf.Options(main="f446", heads="none", alps="0")
        self.configurator(o).guess_from_printer_cfg()
        self.assertEqual((o.main, o.heads, o.alps), ("f446", "none", "0"))

    def test_guess_heads_variants(self):
        base = ("[include printer_base.cfg]\n[include %s]\n" % STOCK)
        cases = {
            "[mcu T0_EBB]\ncanbus_uuid: a\n": "ebb42",
            "[mcu T0CB]\ncanbus_uuid: a\n": "v1.3",
            "[mcu]\nserial: /dev/serial/by-id/usb-Klipper_stm32h723xx_1-if00\n": "none",
            "[mcu]\ncanbus_uuid: a\n": "",
        }
        for extra, want in cases.items():
            (self.pd / "config" / "printer.cfg").write_text(base + extra, encoding="utf-8")
            o = cf.Options()
            self.configurator(o).guess_from_printer_cfg()
            self.assertEqual(o.heads, want, extra)
        (self.pd / "config" / "printer.cfg").write_text(base.replace(STOCK, "electronics_x_h723_2xH36v2.0.cfg")
                                                        + "[mcu T0CB]\ncanbus_uuid: a\n", encoding="utf-8")
        o = cf.Options()
        self.configurator(o).guess_from_printer_cfg()
        self.assertEqual(o.heads, "v2")

    def test_foreign_or_blank_cfg_gives_no_hints(self):
        (self.pd / "config" / "printer.cfg").write_bytes((FIXTURES / "kiauh_printer.cfg").read_bytes())
        o = cf.Options()
        self.configurator(o).guess_from_printer_cfg()
        self.assertEqual((o.main, o.heads, o.alps), ("", "", ""))


class TestCollectMcuState(Base):
    def test_from_printer_cfg_and_byid(self):
        self.seed_vostok("\n[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_AAAA00000001-if00\n")
        self.touch_byid(ALPS1, ALPS2)
        c = self.configurator(hw=self.hw(heads="v1.3", alps=2))
        c.collect_mcu_state()
        self.assertEqual(c.mcu.alps_serial, ["AAAA00000001", "AAAA00000002"])
        self.assertEqual(c.mcu.bridge_uuid, "821a4dc3b8eb")
        self.assertEqual(c.mcu.head_uuid, ["bcc1147e110d", "21ad41ca6772"])

    def test_usb_serial_from_byid(self):
        self.touch_byid(H723)
        c = self.configurator()
        c.collect_mcu_state()
        self.assertEqual(c.mcu.main_serial, "120026000A51333231343036")

    def test_bridge_from_devices_tsv(self):
        self.write_devices([("821a4dc3b8eb", "stm32h723xx-canbridge.config", "bridge"),
                            ("u0", "stm32g431xx-can.config", "can"), ("u1", "stm32g431xx-can.config", "can")])
        c = self.configurator(hw=self.hw(heads="v2"))
        c.collect_mcu_state()
        self.assertEqual((c.mcu.bridge_uuid, c.mcu.head_uuid), ("821a4dc3b8eb", ["u0", "u1"]))

    def test_alps_not_duplicated(self):
        self.seed_vostok("\n[mcu alps_t1]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_AAAA00000001-if00\n")
        self.touch_byid(ALPS1, ALPS2)
        c = self.configurator(hw=self.hw(alps=2))
        c.collect_mcu_state()
        # как в bash: индекс растёт с каждым устройством, уже известный serial повторно не берётся
        self.assertEqual(c.mcu.alps_serial, ["", "AAAA00000001"])


# --------------------------------------------------------------------------- electronics: выбор и эталон

class TestElectronicsChoice(Base):
    def test_elec_named_board_and_matches(self):
        c = self.configurator()
        self.assertEqual(c.elec_named_board("electronics_spider_v3_h723_7x2209.cfg"), "spider-v3-h723")
        self.assertEqual(c.elec_named_board(STOCK), "")
        self.assertTrue(c.el_matches(STOCK))
        self.assertFalse(c.el_matches("electronics_octopus_v1.1_f446_7x2209.cfg"))
        self.assertFalse(c.el_matches("electronics_spider_v3_h723_7x2209.cfg"))
        c = self.configurator(hw=self.hw(heads="ebb42"))
        self.assertFalse(c.el_matches(STOCK))
        self.assertTrue(c.el_matches("electronics_octopus_pro_v1.1_h723_5x2209_2xebb42.cfg"))

    def test_el_for_board(self):
        c = self.configurator()
        self.assertTrue(c.el_for_board(STOCK))
        self.assertTrue(c.el_for_board("my_h723_custom.cfg"))
        self.assertFalse(c.el_for_board("electronics_octopus_v1.1_f446_7x2209.cfg"))
        self.assertFalse(c.el_for_board("electronics_spider_v3_h723_7x2209.cfg"))
        self.assertTrue(c.el_for_board("whatever.cfg"))         # имя без признаков платы - свой
        self.assertFalse(self.configurator(hw=self.hw("fly-c8")).el_for_board("whatever.cfg"))   # у платы нет ELEC_PATTERN

    def test_pick_explicit_and_errors(self):
        c = self.configurator(cf.Options(electronics=STOCK))
        self.assertEqual(c.pick_electronics(ROOT, False), ("standard", STOCK))
        name = "electronics_octopus_v1.1_f446_7x2209.cfg"
        c = self.configurator(cf.Options(electronics=name))
        self.assertEqual(c.pick_electronics(ROOT, False), ("user", name))
        with self.assertRaises(VostokError) as cm:
            self.configurator(cf.Options(electronics="x.cfg")).pick_electronics(ROOT, False)
        self.assertEqual(str(cm.exception), "файл x.cfg не найден ни в корне main, ни в user_configs")
        with self.assertRaises(VostokError) as cm:
            self.configurator(cf.Options(config_source="skip")).pick_electronics(ROOT, False)
        self.assertIn("printer.cfg ещё не существует", str(cm.exception))
        for src in ("generate", "skip"):
            self.assertEqual(self.configurator(cf.Options(config_source=src)).pick_electronics(ROOT, True), (src, ""))

    def test_pick_by_source_option(self):
        c = self.configurator(cf.Options(config_source="standard"))
        self.assertEqual(c.pick_electronics(ROOT, False), ("standard", STOCK))
        empty = self.tmp / "empty"
        empty.mkdir()
        with self.assertRaises(VostokError) as cm:
            self.configurator(cf.Options(config_source="standard"), ).pick_electronics(empty, False)
        self.assertIn("в корне main нет electronics_*.cfg", str(cm.exception))
        with self.assertRaises(VostokError) as cm:
            self.configurator(cf.Options(config_source="user")).pick_electronics(empty, False)
        self.assertEqual(str(cm.exception), "в user_configs нет electronics_*.cfg")

    def test_pick_no_match_with_yes_fails(self):
        c = self.configurator(cf.Options(config_source="user"), hw=self.hw("manta-m8p-v2.0"))
        res, _, _ = capture(c.pick_electronics, ROOT, False)
        self.assertIsInstance(res, VostokError)
        cm = type("CM", (), {"exception": res})
        self.assertIn("в user нет electronics-файла под BTT Manta M8P v2.0", str(cm.exception))

    def test_pick_menu_defaults(self):
        ui.opts.yes = False
        seen = []

        def fake_choice(q, default, options):
            seen.append((q, default, list(options)))
            return default

        with mock.patch.object(ui, "ask_choice", fake_choice):
            res, out, _ = capture(self.configurator().pick_electronics, ROOT, True)
        self.assertEqual(res, ("skip", ""))
        self.assertEqual(seen[0][0], "Откуда взять конфиг?")
        self.assertEqual(seen[0][1], cf.SRC_LBL_SKIP)
        self.assertEqual(seen[0][2], [cf.SRC_LBL_STD, cf.SRC_LBL_USR, cf.SRC_LBL_GEN, cf.SRC_LBL_SKIP])
        self.assertIn("  - стандартный: корень main, поддерживается автором (%s);" % STOCK, out)
        self.assertIn("(4 шт.)", out)
        # чистая установка: по умолчанию - стандартный; плата без готового файла - генерация
        seen.clear()
        with mock.patch.object(ui, "ask_choice", fake_choice):
            res, _, _ = capture(self.configurator().pick_electronics, ROOT, False)
        self.assertEqual(res, ("standard", STOCK))
        self.assertEqual(seen[0][1], cf.SRC_LBL_STD)
        self.assertEqual(seen[1][1], STOCK)        # файл, подходящий плате
        seen.clear()
        with mock.patch.object(ui, "ask_choice", fake_choice):
            res, _, _ = capture(self.configurator(hw=self.hw("fly-c8")).pick_electronics, ROOT, False)
        self.assertEqual(res, ("generate", ""))
        self.assertEqual(seen[0][1], cf.SRC_LBL_GEN)

    def test_pick_user_file_labels(self):
        ui.opts.yes = False
        answers = iter([cf.SRC_LBL_USR, "electronics_octopus_v1.1_f446_7x2209.cfg (другая плата)"])
        seen = []

        def fake_choice(q, default, options):
            seen.append((default, list(options)))
            return next(answers)

        with mock.patch.object(ui, "ask_choice", fake_choice):
            res, _, err = capture(self.configurator().pick_electronics, ROOT, False)
        self.assertEqual(res, ("user", "electronics_octopus_v1.1_f446_7x2209.cfg"))
        self.assertIn("user_configs: конфиги ведут пользователи", err)
        self.assertEqual(seen[1][0], "electronics_octopus_pro_v1.1_h723_5x2209_2xebb42.cfg")
        self.assertIn("electronics_octopus_pro_v1.1_h723_5x2209_2xebb42.cfg", seen[1][1])

    def test_sync_head_names(self):
        f = self.tmp / "e.cfg"
        f.write_text("# T0X:PA1 в комментарии\n[x]\npin: T0_EBB:PA1\nother: T1_EBB:PB2\nmore: T0_EBB:PA9\n", encoding="utf-8")
        c = self.configurator(hw=self.hw(heads="v1.3"))
        _, _, err = capture(c.sync_head_names, f)
        self.assertEqual(c.hw.head_mcu, ["T0_EBB", "T1_EBB"])
        self.assertIn("в e.cfg платы голов называются T0_EBB и T1_EBB (по умолчанию: T0CB и T1CB); использую имена из файла", err)
        c = self.configurator(hw=self.hw(heads="none"))
        capture(c.sync_head_names, f)
        self.assertEqual(c.hw.head_mcu, ["T0CB", "T1CB"])
        f.write_text("pin: T0CB:PA1\npin2: T1CB:PA2\n", encoding="utf-8")
        c = self.configurator(hw=self.hw(heads="v2"))
        _, _, err = capture(c.sync_head_names, f)
        self.assertEqual(err, "")

    def test_find_reference(self):
        self.seed_vostok()
        c = self.configurator()
        c.cfg_state = "vostok"
        c.find_reference(ROOT)
        self.assertEqual((c.ref_cfg, c.ref_kind), (str(self.pd / "config" / STOCK), "user"))
        # --reference none / файл / несуществующий файл
        c = self.configurator(cf.Options(reference="none"))
        c.find_reference(ROOT)
        self.assertEqual((c.ref_cfg, c.ref_kind), ("", "none"))
        c = self.configurator(cf.Options(reference=str(ROOT / STOCK)))
        c.find_reference(ROOT)
        self.assertEqual(c.ref_kind, "user")
        with self.assertRaises(VostokError) as cm:
            self.configurator(cf.Options(reference="/nonexistent")).find_reference(ROOT)
        self.assertEqual(str(cm.exception), "--reference: файл не найден: /nonexistent")

    def test_find_reference_clean_install_uses_stock(self):
        c = self.configurator()
        c.cfg_state = "none"
        c.find_reference(ROOT)
        self.assertEqual((c.ref_cfg, c.ref_kind), (str(ROOT / STOCK), "stock"))
        c = self.configurator(hw=self.hw("fly-c8"))
        c.find_reference(ROOT)
        self.assertEqual((c.ref_cfg, c.ref_kind), ("", "none"))

    def test_find_reference_foreign_board_warns(self):
        self.seed_vostok()
        other = "electronics_octopus_v1.1_f446_7x2209.cfg"
        (self.pd / "config" / other).write_bytes((ROOT / "user_configs" / other).read_bytes())
        p = self.pd / "config" / "printer.cfg"
        p.write_text(p.read_text(encoding="utf-8").replace(STOCK, other), encoding="utf-8")
        c = self.configurator()
        c.cfg_state = "vostok"
        with mock.patch.object(ui, "have_tty", lambda: False):
            _, out, err = capture(c.find_reference, ROOT)
        self.assertEqual(c.ref_kind, "stock")        # без терминала вопрос не задаётся, пины чужой платы не берутся
        self.assertIn("сделан не под Octopus Pro v1.1 H723", err)
        self.assertIn("(чтобы взять: --reference %s)" % (self.pd / "config" / other), out)
        ui.opts.yes = False
        with mock.patch.object(ui, "have_tty", lambda: True), mock.patch.object(ui, "ask_yn", lambda q, d: True):
            capture(c.find_reference, ROOT)
        self.assertEqual((c.ref_kind, os.path.basename(c.ref_cfg)), ("user", other))

    def test_stock_electronics(self):
        c = self.configurator()
        self.assertEqual(c.stock_electronics(ROOT), str(ROOT / STOCK))
        self.assertEqual(c.stock_electronics(self.tmp), "")
        (self.tmp / "electronics_b.cfg").touch()
        (self.tmp / "electronics_a.cfg").touch()
        self.assertEqual(c.stock_electronics(self.tmp), str(self.tmp / "electronics_a.cfg"))


class TestDriversWizard(Base):
    def test_option_yes_and_default(self):
        c = self.configurator(cf.Options(drivers="all=5160"))
        c.drivers_wizard()
        self.assertEqual(c.drivers_spec, "all=5160")
        c = self.configurator()
        _, out, _ = capture(c.drivers_wizard)
        self.assertEqual(c.drivers_spec, cf.DRIVER_DEFAULT_SPEC)
        self.assertIn("Драйверы моторов: как в стоковом конфиге", out)

    def test_wizard_all_and_per_motor(self):
        ui.opts.yes = False
        with mock.patch.object(ui, "have_tty", lambda: True):
            answers = iter(["Все драйверы одинаковые", "TMC2209 (UART)"])
            with mock.patch.object(ui, "ask_choice", lambda q, d, o: next(answers)):
                c = self.configurator()
                capture(c.drivers_wizard)
            self.assertEqual(c.drivers_spec, "all=2209")
            asked = []
            answers = iter(["Разные драйверы", "TMC2209 (UART)", "TMC2130 (SPI)", "TMC5160 / 5160T Pro (SPI, sense 0.075)",
                            "TMC5160T Plus (SPI, sense 0.022)", "TMC2208 (UART)", "TMC2240 (SPI)", "TMC2240 (SPI)"])

            def fake(q, d, o):
                asked.append(q)
                return next(answers)

            with mock.patch.object(ui, "ask_choice", fake):
                c = self.configurator()
                _, out, _ = capture(c.drivers_wizard)
            self.assertEqual(c.drivers_spec, "e0=2209,e1=2130,x=5160,w=5160plus,yl=2208,yr=2240,z=2240")
            self.assertEqual(asked[1], "Драйвер экструдера T0 (левая голова):")
            answers = iter(["Все драйверы одинаковые", "TMC2209 (UART)"])
            with mock.patch.object(ui, "ask_choice", lambda q, d, o: next(answers)):
                _, out, _ = capture(self.configurator(hw=self.hw("manta-m8p-v2.0")).drivers_wizard)
            self.assertIn("Пины драйверов подставятся по разъёмам платы (пресет)", out)
            # с платами голов экструдеры не спрашиваем
            answers = iter(["Разные драйверы"] + ["TMC2240 (SPI)"] * 5)
            with mock.patch.object(ui, "ask_choice", lambda q, d, o: next(answers)):
                c = self.configurator(hw=self.hw(heads="v1.3"))
                _, out, _ = capture(c.drivers_wizard)
            self.assertEqual(c.drivers_spec, "x=2240,w=2240,yl=2240,yr=2240,z=2240")
            self.assertIn("Драйверы экструдеров не спрашиваю", out)


# --------------------------------------------------------------------------- запись конфига

def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


class TestStageConfig(Base):
    def run_stage(self, opts, hw=None, mcu=None, dry=False):
        ui.opts.dry_run = dry
        c = self.configurator(opts, hw)
        if mcu:
            c.mcu = mcu
        _, out, err = capture(c.stage_config)
        return c, out, err

    def test_clean_install_standard(self):
        hw = self.hw(heads="v1.3")
        mcu = cf.McuValues(bridge_uuid="821a4dc3b8eb", head_uuid=["bcc1147e110d", "21ad41ca6772"])
        c, out, err = self.run_stage(cf.Options(config_source="standard", modules="none"), hw, mcu)
        files = tree(self.pd / "config")
        self.assertEqual(files["printer_base.cfg"], (ROOT / "printer_base.cfg").read_bytes())
        self.assertEqual(files[STOCK], (ROOT / STOCK).read_bytes())
        self.assertIn("postprocessing/fast_tool_swaps.py", files)
        text = files["printer.cfg"].decode("utf-8")
        self.assertIn("[mcu]\ncanbus_uuid: 821a4dc3b8eb", text)
        self.assertIn("[include %s]" % STOCK, text)
        self.assertIn("конфигурация записана в %s (electronics: %s, источник: корень main)" % (self.pd / "config", STOCK), out)
        self.assertEqual(c.cfg_state, "none")
        self.assertFalse([f for f in files if ".bak-" in f])

    def test_existing_config_keeps_user_files(self):
        self.seed_vostok()
        (self.pd / "config" / "printer_base.cfg").write_text("# мой base\n", encoding="utf-8")
        (self.pd / "config" / "chamber_heater.cfg").unlink()
        hw = self.hw(heads="v1.3")
        mcu = cf.McuValues(bridge_uuid="821a4dc3b8eb", head_uuid=["bcc1147e110d", "21ad41ca6772"])
        c, out, _ = self.run_stage(cf.Options(config_source="generate", drivers="all=2209", modules="none"), hw, mcu)
        files = tree(self.pd / "config")
        self.assertEqual(files["printer_base.cfg"], "# мой base\n".encode("utf-8"))               # файл пользователя не тронут
        self.assertIn("chamber_heater.cfg", files)                                  # отсутствующий докопирован
        baks = sorted(f for f in files if ".bak-" in f)
        self.assertTrue(any(b.startswith("printer.cfg.bak-") for b in baks))
        name = "electronics_octopus_pro_v1.1_h723_5x2209_2xH36v1.3.cfg"
        self.assertIn(name, files)
        self.assertIn("[include %s]" % name, files["printer.cfg"].decode("utf-8"))
        self.assertIn("Прежние printer.cfg и %s сохранены как *.bak-" % name, out)
        self.assertEqual(c.cfg_state, "vostok")

    def test_foreign_cfg_is_clean_install_with_backup(self):
        (self.pd / "config" / "printer.cfg").write_bytes((FIXTURES / "kiauh_printer.cfg").read_bytes())
        c, out, err = self.run_stage(cf.Options(config_source="standard", modules="none"))
        self.assertIn("не похож на конфиг VOSTOK", err)
        self.assertIn("прежние файлы сохранены как *.bak-", err)
        files = tree(self.pd / "config")
        self.assertTrue(any(f.startswith("printer.cfg.bak-") for f in files))
        self.assertIn("[include printer_base.cfg]", files["printer.cfg"].decode("utf-8"))

    def test_dry_run_writes_nothing(self):
        self.seed_vostok()
        before = tree(self.pd / "config")
        c, out, err = self.run_stage(cf.Options(config_source="generate", drivers="all=5160", modules="all"), dry=True)
        self.assertEqual(tree(self.pd / "config"), before)
        self.assertIn("[dry-run] существующий конфиг: записал бы", out)
        self.assertIn("[dry-run] подключил бы модуль", out + err)
        self.assertIn("Сгенерирован electronics_octopus_pro_v1.1_h723_7x5160.cfg", err)

    def test_dry_run_without_local_root_prints_only_blocks(self):
        c = self.configurator(cf.Options(), cfg_local="0")
        ui.opts.dry_run = True
        _, out, _ = capture(c.stage_config)
        self.assertIn("[dry-run] взял бы конфигурацию из file:///nonexistent", out)
        self.assertTrue(out.rstrip().endswith("usb-Klipper_stm32h723xx_ЗАПОЛНИТЕ-if00"))
        self.assertEqual(os.listdir(self.pd / "config"), [])

    def test_skip_adds_missing_mcu_only(self):
        self.seed_vostok()
        hw = self.hw(heads="v1.3", alps=1)
        mcu = cf.McuValues(bridge_uuid="821a4dc3b8eb", head_uuid=["bcc1147e110d", "ffffffffffff"], alps_serial=["NEW1", ""])
        c, out, err = self.run_stage(cf.Options(config_source="skip", modules="none"), hw, mcu)
        text = (self.pd / "config" / "printer.cfg").read_text(encoding="utf-8")
        self.assertIn("usb-Klipper_stm32f072xb_NEW1-if00", text)
        self.assertIn("[mcu alps] добавлена в printer.cfg", out)
        self.assertIn("[mcu T1CB]: в конфиге canbus_uuid: 21ad41ca6772, а прошито: ffffffffffff", err)
        self.assertIn("Резервная копия: %s.bak-*" % (self.pd / "config" / "printer.cfg"), out)
        self.assertTrue(any(f.startswith("printer.cfg.bak-") for f in os.listdir(self.pd / "config")))

    def test_no_tty_existing_cfg_defaults_to_skip(self):
        self.seed_vostok()
        ui.opts.yes = False
        o = cf.Options(modules="none")
        with mock.patch.object(ui, "have_tty", lambda: False):
            c = self.configurator(o, self.hw(heads="v1.3"))
            c.mcu = cf.McuValues(bridge_uuid="821a4dc3b8eb", head_uuid=["bcc1147e110d", "21ad41ca6772"])
            capture(c.stage_config)
        self.assertEqual(o.config_source, "skip")

    def test_generate_failure_message(self):
        c = self.configurator(cf.Options(config_source="generate", drivers="all=9999", modules="none"))
        res, out, err = capture(c.stage_config)
        self.assertIsInstance(res, VostokError)
        self.assertEqual(str(res), "не удалось сгенерировать конфиг электроники")
        self.assertIn("--drivers: драйвер '9999' не из 2130/2208/2209/2240/5160/5160plus", err)

    def test_generate_clean_install_uses_stock_reference(self):
        c, out, err = self.run_stage(cf.Options(config_source="generate", drivers="all=5160", modules="none"))
        self.assertIn("Чистая установка: пины и параметры моторов берутся из стокового конфига main (%s)" % STOCK, out)
        self.assertIn("  подставлено пинов из эталона: 42", out)
        self.assertIn("  подставлено пинов экструдеров на разъёмы MOTOR4 (E0) и MOTOR5 (E1): 14", out)
        self.assertIn("  0. Пины моторов и драйверов взяты из стокового конфига main (X: MOTOR2, W: MOTOR0, YL: MOTOR3, "
                      "YR: MOTOR1, Z: MOTOR7, экструдеры: MOTOR4 и MOTOR5)", err)
        self.assertIn("       [extruder]: heater_pin", err)
        self.assertIn("пин PA2 из таблицы разъёмов Octopus Pro уже занят", err)
        self.assertIsNotNone(c.gen)
        self.assertTrue((self.pd / "config" / "electronics_octopus_pro_v1.1_h723_7x5160.cfg").is_file())

    def test_preset_board_generation(self):
        hw = self.hw("manta-m8p-v2.0")
        c, out, err = self.run_stage(cf.Options(config_source="generate", drivers="all=2209", modules="none"), hw)
        self.assertIn("Эталонного конфига нет: пины моторов и драйверов возьму из пресета платы BTT Manta M8P v2.0", out)
        self.assertIn("подставлено пинов по разъёмам BTT Manta M8P v2.0 (пресет, плата не проверена на железе):", out)
        self.assertIn("electronics_manta_m8p_v2.0_7x2209.cfg", os.listdir(self.pd / "config"))

    def test_download_path(self):
        src = self.tmp / "arch"
        shutil_copy_tree(ROOT, src / "vostok_configuration-main")
        tarball = self.tmp / "vc.tar.gz"
        with tarfile.open(tarball, "w:gz") as t:
            t.add(src / "vostok_configuration-main", arcname="vostok_configuration-main")
        c, out, err = self.run_stage(cf.Options(config_source="standard", modules="none"), self.hw(heads="v1.3"))
        self.assertTrue((self.pd / "config" / "printer.cfg").is_file())      # локальный корень
        import shutil
        shutil.rmtree(self.pd / "config")
        (self.pd / "config").mkdir()
        c = self.configurator(cf.Options(config_source="standard", modules="none"), self.hw(heads="v1.3"),
                              cfg_local="0", cfg_tarball="file://" + str(tarball))
        _, out, _ = capture(c.stage_config)
        self.assertNotIn("локального клона", out)
        self.assertEqual((self.pd / "config" / STOCK).read_bytes(), (ROOT / STOCK).read_bytes())
        self.assertTrue((self.pd / "config" / "postprocessing").is_dir())

    def test_download_errors(self):
        c = self.configurator(cf.Options(config_source="standard"), cfg_local="0", cfg_tarball="file:///nonexistent.tgz")
        res, _, _ = capture(c.stage_config)
        self.assertEqual(str(res), "не удалось скачать file:///nonexistent.tgz")
        bad = self.tmp / "bad.tgz"
        bad.write_text("не архив", encoding="utf-8")
        c = self.configurator(cf.Options(config_source="standard"), cfg_local="0", cfg_tarball="file://" + str(bad))
        res, _, _ = capture(c.stage_config)
        self.assertEqual(str(res), "не удалось распаковать конфигурацию")
        empty = self.tmp / "empty.tgz"
        with tarfile.open(empty, "w:gz") as t:
            info = tarfile.TarInfo("top/readme")
            info.size = 0
            t.addfile(info)
        c = self.configurator(cf.Options(config_source="standard"), cfg_local="0", cfg_tarball="file://" + str(empty))
        res, _, _ = capture(c.stage_config)
        self.assertEqual(str(res), "в архиве нет printer.cfg/printer_base.cfg")

    def test_tarball_path_traversal_is_skipped(self):
        evil = self.tmp / "evil.tgz"
        with tarfile.open(evil, "w:gz") as t:
            for name, data in (("top/printer.cfg", b"[a]\n"), ("top/printer_base.cfg", b"[b]\n"), ("top/../../escaped.txt", b"x"),
                               ("/abs/file", b"y")):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        dest = self.tmp / "dest"
        cf._fetch_tarball("file://" + str(evil), dest, self.tmp)
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["file", "printer.cfg", "printer_base.cfg"])   # /abs/file -> dest/file
        self.assertFalse((self.tmp / "escaped.txt").exists())
        self.assertFalse((self.tmp.parent / "escaped.txt").exists())

    def test_tarball_links_are_skipped_with_warning(self):
        arc = self.tmp / "links.tgz"
        with tarfile.open(arc, "w:gz") as t:
            data = b"[a]\n"
            info = tarfile.TarInfo("top/printer.cfg")
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
            sym = tarfile.TarInfo("top/fluidd.cfg")
            sym.type = tarfile.SYMTYPE
            sym.linkname = "../../etc/passwd"
            t.addfile(sym)
            hard = tarfile.TarInfo("top/copy.cfg")
            hard.type = tarfile.LNKTYPE
            hard.linkname = "top/printer.cfg"
            t.addfile(hard)
        dest = self.tmp / "dest_links"
        with mock.patch.object(ui, "warn") as warn:
            cf._fetch_tarball("file://" + str(arc), dest, self.tmp)
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["printer.cfg"])
        msg = warn.call_args[0][0]
        self.assertIn("пропущено ссылок", msg)
        self.assertIn("fluidd.cfg", msg)
        self.assertIn("copy.cfg", msg)

    def test_tarball_http_exception_is_reported(self):
        import http.client
        with mock.patch.object(cf.urllib.request, "urlopen", side_effect=http.client.BadStatusLine("x")):
            with self.assertRaises(VostokError) as cm:
                cf._fetch_tarball("http://example.invalid/a.tgz", self.tmp / "d", self.tmp)
        self.assertIn("не удалось скачать", str(cm.exception))

    def test_local_cfg_root(self):
        self.assertEqual(self.configurator().local_cfg_root(), ROOT)
        for mode in ("0", "no", "off"):
            self.assertIsNone(self.configurator(cfg_local=mode).local_cfg_root())
        self.assertIsNone(self.configurator(cfg_local=str(self.tmp)).local_cfg_root())
        auto = INSTALLER.parent
        want = auto if (auto / "printer.cfg").is_file() and (auto / "printer_base.cfg").is_file() else None
        self.assertEqual(self.configurator(cfg_local="auto").local_cfg_root(), want)


def shutil_copy_tree(src, dst):
    import shutil
    shutil.copytree(str(src), str(dst), symlinks=True)


# --------------------------------------------------------------------------- модули и пины

class TestModules(Base):
    def test_module_wanted(self):
        c = self.configurator(cf.Options(modules="all"))
        self.assertTrue(c.module_wanted("chamber_heater", "L", "chamber_heater.cfg"))
        self.assertTrue(self.configurator(cf.Options(modules="x,chamber_heater")).module_wanted("chamber_heater", "L", "f"))
        self.assertFalse(self.configurator(cf.Options(modules="none")).module_wanted("chamber_heater", "L", "f"))
        self.assertFalse(self.configurator(cf.Options(modules="other")).module_wanted("chamber_heater", "L", "f"))
        self.assertFalse(self.configurator().module_wanted("chamber_heater", "L", "f"))       # -y
        ui.opts.yes = False
        with mock.patch.object(ui, "have_tty", lambda: False):
            self.assertFalse(self.configurator().module_wanted("chamber_heater", "L", "f"))
        asked = []
        with mock.patch.object(ui, "have_tty", lambda: True), mock.patch.object(ui, "ask_yn", lambda q, d: asked.append((q, d)) or True):
            self.assertTrue(self.configurator().module_wanted("chamber_heater", "Метка", "chamber_heater.cfg"))
        self.assertEqual(asked, [("Подключить дополнительный модуль: Метка (chamber_heater.cfg)?", "n")])

    def test_connects_module_with_backup(self):
        self.seed_vostok()
        (self.pd / "config" / "chamber_heater.cfg").unlink()
        c = self.configurator(cf.Options(modules="chamber_heater"))
        _, out, _ = capture(c.stage_modules, ROOT)
        self.assertIn("Модуль Подогрев термокамеры (Smart Chamber Heater) подключён: [include chamber_heater.cfg] в printer.cfg", out)
        self.assertEqual(cfgfile.module_state(self.pd / "config" / "printer.cfg", "chamber_heater.cfg"), "active")
        self.assertTrue((self.pd / "config" / "chamber_heater.cfg").is_file())
        self.assertTrue(any(f.startswith("printer.cfg.bak-") for f in os.listdir(self.pd / "config")))
        _, out, _ = capture(c.stage_modules, ROOT)
        self.assertIn("уже подключён (chamber_heater.cfg)", out)

    def test_module_not_wanted_and_missing_file(self):
        self.seed_vostok()
        _, out, _ = capture(self.configurator(cf.Options(modules="none")).stage_modules, ROOT)
        self.assertIn("не подключаю (позже: --modules chamber_heater)", out)
        (self.pd / "config" / "chamber_heater.cfg").unlink()
        _, out, err = capture(self.configurator(cf.Options(modules="all")).stage_modules, self.tmp)
        self.assertIn("файл chamber_heater.cfg не найден (ни в %s, ни в %s)" % (self.pd / "config", self.tmp), err)

    def test_no_printer_cfg(self):
        _, out, _ = capture(self.configurator().stage_modules, ROOT)
        self.assertIn("printer.cfg нет, дополнительные модули не настраиваю", out)
        ui.opts.dry_run = True
        _, out, _ = capture(self.configurator().stage_modules, ROOT)
        self.assertIn("[dry-run] после записи конфига спросил бы про дополнительные модули: chamber_heater.cfg", out)

    def make_conflict(self):
        self.seed_vostok()
        p = self.pd / "config" / "chamber_heater.cfg"
        import re
        text = re.sub(r"(?m)^(heater_pin\s*:)\s*[^#\n]+", r"\1 PA2", p.read_text(encoding="utf-8"), count=1)
        p.write_text(text, encoding="utf-8")

    def test_conflict_blocks_module_without_tty(self):
        self.make_conflict()
        c = self.configurator(cf.Options(modules="chamber_heater"))
        _, out, err = capture(c.stage_modules, ROOT)
        self.assertIn("использует пины, уже занятые вашей проводкой:", err)
        self.assertIn("не подключён из-за пересечения пинов (измените пины и подключите позже: --modules chamber_heater)", err)
        self.assertEqual(cfgfile.module_state(self.pd / "config" / "printer.cfg", "chamber_heater.cfg"), "commented")

    def test_conflict_can_be_confirmed(self):
        self.make_conflict()
        ui.opts.yes = False
        c = self.configurator(cf.Options(modules="chamber_heater"))
        with mock.patch.object(ui, "have_tty", lambda: True), mock.patch.object(ui, "ask_yn", lambda q, d: "Всё равно" in q):
            capture(c.stage_modules, ROOT)
        self.assertEqual(cfgfile.module_state(self.pd / "config" / "printer.cfg", "chamber_heater.cfg"), "active")

    def test_report_pin_conflicts(self):
        self.seed_vostok()
        c = self.configurator()
        _, out, err = capture(c.report_pin_conflicts, self.pd / "config" / "printer.cfg")
        self.assertEqual(err, "")
        p = self.pd / "config" / "printer.cfg"
        p.write_text(p.read_text(encoding="utf-8") + "\n[fan]\npin: PA2\n[led l]\nred_pin: PA2\n", encoding="utf-8")
        _, out, err = capture(c.report_pin_conflicts, p)
        self.assertIn("в конфиге есть пины, которые используются сразу в нескольких секциях (Klipper не запустится):", err)
        self.assertIn("  - mcu:PA2: ", err)
        self.assertIn("Распиновка Octopus Pro v1.1 H723:", err)
        self.assertIn("онлайн: ", err)
        capture(c.report_pin_conflicts, self.tmp / "none.cfg")        # нет файла - тихо


# --------------------------------------------------------------------------- командная строка

class TestCommandLine(Base):
    def parse(self, args, **envkw):
        return capture(cf.parse_args, args, self.env(**envkw), REG, FakeRunner())

    def test_help_and_version(self):
        res, out, _ = self.parse(["--help"])
        self.assertIsNone(res)
        self.assertEqual(out, cf.USAGE)
        self.assertTrue(out.startswith("Использование: configure_vostok.sh [опции]\n"))
        res, out, _ = self.parse(["-V"])
        self.assertEqual(out, "VOSTOK installer %s\n" % cf.installer_version(INSTALLER))

    def test_usage_matches_golden(self):
        golden = HERE / "golden" / "help.txt"
        if not golden.is_file():
            self.skipTest("нет golden/help.txt")
        text = golden.read_text(encoding="utf-8")
        block = text.split("@@@@ CASE help/configure_vostok\n", 1)[1].split("$ configure_vostok.sh -V", 1)[0]
        self.assertTrue(block.endswith(cf.USAGE))

    def test_errors(self):
        for args, msg in ((["--main"], "--main требует аргумент"), (["--heads"], "--heads требует аргумент"),
                          (["--printer-data"], "--printer-data требует аргумент"),
                          (["--heads", "bogus"], "--heads: none, v1.3, v2, ebb42, ebb-gen2, ebb36-v1.0, sht36-v2"),
                          (["--config-source", "x"], "--config-source: standard, user, generate или skip"),
                          (["--alps", "9"], "--alps: 0, 1 или 2"),
                          (["--no-such"], "неизвестная опция: --no-such"),
                          (["--main", "bogus"], None)):
            res, out, err = self.parse(args)
            self.assertIsInstance(res, VostokError, args)
            if msg:
                self.assertEqual(str(res), msg)
        res, out, err = self.parse(["--no-such"])
        self.assertIn("Использование: configure_vostok.sh", err)       # справка в stderr

    def test_options_parsed(self):
        res, _, _ = self.parse(["--main", "h723", "--heads", "ebb42", "--alps", "2", "--config-source", "generate",
                                "--electronics", "e.cfg", "--drivers", "all=2209", "--reference", "none",
                                "--modules", "all", "-y", "--dry-run", "--printer-data", str(self.tmp / "x")])
        o = res.opts
        self.assertEqual((o.main, o.heads, o.alps, o.config_source, o.electronics, o.drivers, o.reference, o.modules),
                         ("h723", "ebb42", "2", "generate", "e.cfg", "all=2209", "none", "all"))
        self.assertTrue(res.yes and res.dry)
        self.assertEqual(res.env.printer_data, self.tmp / "x")
        self.assertEqual(res.env.effective_log_file, self.tmp / "x" / "logs" / "vostok_configure.log")
        self.assertTrue(ui.opts.yes and ui.opts.dry_run)

    def test_main_missing_printer_data_does_not_create(self):
        # M3: опечатка в --printer-data не создаёт каталог журнала
        bad = self.tmp / "printer_dta"
        with self.assertRaises(VostokError) as cm:
            cf.main(["--printer-data", str(bad), "--dry-run", "-y"], environ={"HOME": str(self.tmp)})
        self.assertIn("нет каталога", str(cm.exception))
        self.assertFalse(bad.exists())

    def test_env_from_environ(self):
        e = cf.Env.from_environ({"PRINTER_DATA": "/p", "BYID_DIR": "/b", "CAN_IFACE": "can1", "DEVICES_FILE": "/d.tsv",
                                 "VOSTOK_CFG_LOCAL": "0", "VOSTOK_CFG_TARBALL": "u", "TEMPLATES_DIR": "/t", "LOG_FILE": "/l.log"})
        self.assertEqual((str(e.printer_data), e.byid_dir, e.can_iface, str(e.devices_file), e.cfg_local, e.cfg_tarball,
                          str(e.templates_dir), str(e.effective_log_file)), ("/p", "/b", "can1", "/d.tsv", "0", "u", "/t", "/l.log"))
        e = cf.Env.from_environ({"HOME": "/home/u"})
        self.assertEqual(str(e.printer_data), "/home/u/printer_data")
        self.assertEqual(str(e.effective_log_file), "/home/u/printer_data/logs/vostok_configure.log")
        self.assertEqual(e.byid_dir, "/dev/serial/by-id")

    def test_main_end_to_end_dry_run(self):
        self.touch_byid(H723)
        env = {"PRINTER_DATA": str(self.pd), "BYID_DIR": str(self.byid), "DEVICES_FILE": str(self.tmp / "d.tsv"),
               "VOSTOK_CFG_LOCAL": str(ROOT), "HOME": str(self.tmp)}
        rc, out, err = capture(cf.main, ["--main", "h723", "--heads", "none", "--alps", "0", "--config-source", "generate",
                                         "--drivers", "all=2209", "--modules", "none", "-y", "--dry-run"], env,
                               REG, FakeRunner())
        self.assertEqual(rc, 0, err)
        self.assertIn("== Настройка конфига VOSTOK (версия %s) ==" % cf.installer_version(INSTALLER), out)
        self.assertIn("Главная плата: Octopus Pro v1.1 H723, платы голов: нет, ALPS: 0", out)
        self.assertNotIn("Готово. Чтобы применить конфиг", out)
        self.assertEqual(os.listdir(self.pd / "config"), [])
        log = (self.pd / "logs" / "vostok_configure.log").read_text(encoding="utf-8")
        self.assertIn("configure_vostok.sh", log)


class TestWrapper(unittest.TestCase):
    """Обёртка configure_vostok.sh: --help/-V/ошибки идут через python3 -m vostok configure."""

    def run_wrapper(self, *args):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        return subprocess.run([str(INSTALLER / "configure_vostok.sh")] + list(args), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True, env=env)

    def test_help_version_errors(self):
        p = self.run_wrapper("--help")
        self.assertEqual((p.returncode, p.stdout), (0, cf.USAGE))
        p = self.run_wrapper("-V")
        self.assertEqual((p.returncode, p.stdout), (0, "VOSTOK installer %s\n" % cf.installer_version(INSTALLER)))
        p = self.run_wrapper("--no-such-option")
        self.assertEqual(p.returncode, 1)
        self.assertTrue(p.stderr.startswith("Использование: configure_vostok.sh"))
        self.assertTrue(p.stderr.rstrip().endswith("ОШИБКА: неизвестная опция: --no-such-option"))

    def test_wrapper_is_thin(self):
        text = (INSTALLER / "configure_vostok.sh").read_text(encoding="utf-8")
        self.assertIn('PYTHONPATH="$INSTALL_DIR${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 exec python3 -m vostok configure "$@"', text)
        self.assertNotIn("python3 -I", text)
        self.assertLess(len(text.splitlines()), 30)


if __name__ == "__main__":
    unittest.main()
