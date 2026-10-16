"""Тесты vostok.install: разбор опций, пропуск прошитых плат, порядок этапов, --check-can, итоги, загрузчик install_vostok.sh.

Прошивка, sudo и ~/printer_data не затрагиваются: внешние программы - FakeRunner, этапы подменяются.
"""
import contextlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fakes import INSTALLER, REG, FakeRunner, Sandbox  # noqa: E402
from vostok import UserAbort, VostokError, flashing, hardware, install, ui  # noqa: E402
from vostok.boards import Registry  # noqa: E402
from vostok.configurator import Hardware  # noqa: E402
from vostok.host import EnvChecks, Options, Software  # noqa: E402
from vostok.install import InstallContext  # noqa: E402
from vostok.state import Device, DevicesFile  # noqa: E402

KDIR_HEAD = ("git", "-C")


class Base(Sandbox):
    def setUp(self):
        super().setUp()
        self.runner = FakeRunner(default_rc=1)
        self.runner.on(("git", "-C", self.env.klipper_dir, "describe"), 0, "v0.12.0-1-gabc\n")
        self.version = "v0.12.0-1-gabc"

    def ctx(self, main="octopus-pro-h723", heads="none", alps=0, way="dfu", **opt) -> InstallContext:
        o = Options(**opt)
        c = InstallContext(o, self.env, REG, self.runner)
        hw = Hardware(REG, main_board=main, heads=heads, alps_count=alps, mode="usb" if heads == "none" else "bridge")
        hw.set_head_names()
        c.set_hardware(hw)
        c.res.heads_way = way
        return c

    def parse(self, *args):
        return install.parse_args(list(args), self.env, REG)


class TestParseArgs(Base):
    def test_all_options(self):
        o = self.parse("--main", "h723", "--heads", "v2", "--alps", "2", "--electronics", "e.cfg", "--config-source", "user",
                       "--drivers", "all=2209", "--reference", "none", "--modules", "all", "--only-detect", "--dry-run",
                       "--skip-software", "--skip-flash", "--skip-config", "--skip-button", "--skip-theme",
                       "--skip-board", "alps0", "--skip-board", "heads", "--reflash", "--main-flash", "katapult",
                       "--heads-flash", "can", "--check-can", "--upgrade", "-y")
        c = o.conf
        self.assertEqual((c.main, c.heads, c.alps, c.electronics, c.config_source, c.drivers, c.reference, c.modules, c.only_detect),
                         ("h723", "v2", "2", "e.cfg", "user", "all=2209", "none", "all", True))
        self.assertEqual((o.only_detect, o.dry_run, o.skip_software, o.skip_flash, o.skip_config, o.skip_button, o.skip_theme),
                         (True,) * 7)
        self.assertEqual((o.skip_boards, o.reflash, o.main_flash, o.heads_flash, o.check_can, o.upgrade, o.yes),
                         (["alps0", "heads"], True, "katapult", "can", True, True, True))
        self.assertTrue(ui.opts.yes and ui.opts.dry_run)

    def test_h36_is_alias_of_heads(self):
        self.assertEqual(self.parse("--h36", "v1.3").conf.heads, "v1.3")

    def test_defaults(self):
        o = self.parse()
        self.assertEqual((o.skip_boards, o.dry_run, o.yes, o.main_flash, o.heads_flash, o.conf.main), ([], False, False, "", "", ""))

    def test_errors(self):
        cases = [(["--main"], "--main требует аргумент"), (["--h36"], "--h36 требует аргумент"),
                 (["--skip-board"], "--skip-board требует аргумент"), (["--main", "bogus"], "--main: неизвестная плата 'bogus'"),
                 (["--heads", "x"], "--heads: none, v1.3, v2 или ebb42"),
                 (["--config-source", "x"], "--config-source: standard, user, generate или skip"),
                 (["--main-flash", "x"], "--main-flash: dfu или katapult"), (["--heads-flash", "x"], "--heads-flash: dfu или can"),
                 (["--alps", "3"], "--alps: 0, 1 или 2"), (["--skip-board", "x"], "--skip-board: alps, alps0, alps1, main или heads"),
                 (["--bogus"], "неизвестная опция: --bogus")]
        for args, msg in cases:
            with self.assertRaises(VostokError) as cm:
                self.parse(*args)
            self.assertIn(msg, str(cm.exception), args)
        self.assertIn("Использование: install_vostok.sh [опции]", self.err.getvalue())        # справка к неизвестной опции

    def test_help_version_list_are_immediate(self):
        # опции обрабатываются по порядку: до справки ошибок нет, после - не доходим
        self.assertIsNone(self.parse("-h"))
        self.assertTrue(self.out.getvalue().startswith("Использование: install_vostok.sh [опции]\n"))
        self.assertIsNone(self.parse("--main", "bogus", "-V"))        # проверки значений - после цикла, версия раньше
        self.assertIn("VOSTOK installer 1.3a", self.out.getvalue())
        self.assertIsNone(self.parse("--heads", "bogus", "--list-boards"))
        t = self.out.getvalue()
        self.assertIn("id                   chip         can  ok   название [роль] (алиасы)", t)
        self.assertIn("octopus-pro-h723     stm32h723xx  bus  yes  Octopus Pro v1.1 H723 [main] (h723)", t)
        self.assertIn("Выбор главной платы: install_vostok.sh --main <id|алиас>.", t)

    def test_usage_text_tail(self):
        self.assertTrue(install.USAGE.endswith("Переменные окружения: PRINTER_DATA, KLIPPER_DIR, KATAPULT_DIR, KIAUH_DIR, CAN_IFACE (can0).\n"))


class TestChooseHeadsFlash(Base):
    def test_variants(self):
        c = self.ctx(heads="none")
        install.choose_heads_flash(c)
        self.assertEqual(c.res.heads_way, "dfu")
        c = self.ctx(heads="v2", heads_flash="can")
        install.choose_heads_flash(c)
        self.assertEqual(c.res.heads_way, "can")
        for kw in ({"only_detect": True}, {"dry_run": True}):
            c = self.ctx(heads="v2", **kw)
            install.choose_heads_flash(c)
            self.assertEqual(c.res.heads_way, "dfu")
        ui.set_options(yes=True)
        c = self.ctx(heads="v2")
        install.choose_heads_flash(c)
        self.assertEqual(c.res.heads_way, "dfu")
        ui.set_options(yes=False)
        with mock.patch.object(ui, "have_tty", return_value=False):
            install.choose_heads_flash(c)
        self.assertEqual(c.res.heads_way, "dfu")

    def test_asks(self):
        c = self.ctx(heads="v2")
        with mock.patch.object(ui, "have_tty", return_value=True):
            with mock.patch.object(ui, "ask_choice", side_effect=lambda q, d, opts: opts[1]):
                install.choose_heads_flash(c)
            self.assertEqual(c.res.heads_way, "can")
            self.assertIn("понадобятся источник 24 В (питание Octopus и плат голов)", self.err.getvalue())
            with mock.patch.object(ui, "ask_choice", side_effect=lambda q, d, opts: opts[0]):
                install.choose_heads_flash(c)
            self.assertEqual(c.res.heads_way, "dfu")
            self.assertIn("canbus_uuid будет вычислен по UID чипа", self.out.getvalue())


class TestPlan(Base):
    def test_plan_texts(self):
        c = self.ctx(main="fly-c8", heads="ebb42", alps=1, way="can")
        install.print_plan(c)
        t = self.text()
        self.assertIn("Главная плата: Mellow FLY-C8, режим: мост USB-CAN (по гайду)", t)
        self.assertIn("ВНИМАНИЕ: Mellow FLY-C8 не проверена на железе", t)
        self.assertIn("  1. ALPS левый (T0): katapult через DFU, затем Klipper", t)
        self.assertIn("  2. BTT EBB42 (обе, по очереди): katapult через DFU по USB", t)
        self.assertIn("  3. Mellow FLY-C8: katapult и Klipper по DFU (кнопки BOOT и RESET;", t)
        self.assertIn("  4. BTT EBB42 (обе, по очереди): Klipper по CAN. ВНИМАНИЕ: нужны источник 24 В", t)
        self.assertIn("  5. Прошивки собираются из", t)
        c = self.ctx(heads="v2", way="dfu")
        self.out.truncate(0)
        install.print_plan(c)
        self.assertIn("canbus_uuid плат голов и моста вычисляются по UID чипов", self.out.getvalue())


class TestSkipAlps(Base):
    def setUp(self):
        super().setUp()
        self.c = self.ctx(alps=2)
        self.touch_byid("usb-Klipper_stm32f072xb_S1-if00", "usb-Klipper_stm32f072xb_S2-if00")

    def test_candidates_order_and_dedupe(self):
        self.c.res.prev_devices = [Device("S2", "stm32f072xb.config", "usb"), Device("GONE", "stm32f072xb.config", "usb"),
                                   Device("S1", "stm32f072xb.config", "usb")]
        self.assertEqual(install.alps_candidates(self.c), ["S2", "S1"])          # порядок прошлого devices.tsv, без пропавших
        self.c.res.mcu.alps_serial[0] = "S2"
        self.assertEqual(install.alps_candidates(self.c), ["S1"])                # занятые не берутся
        self.c.res.prev_devices = []
        self.assertEqual(install.alps_candidates(self.c), ["S1"])

    def test_no_candidates_not_forced_flashes(self):
        for f in self.byid.iterdir():
            f.unlink()
        self.assertFalse(install.alps_try_skip(self.c, 0))

    def test_forced_without_device_warns(self):
        for f in self.byid.iterdir():
            f.unlink()
        self.c.opts.skip_boards = ["alps"]
        self.assertTrue(install.alps_try_skip(self.c, 1))
        self.assertIn("--skip-board: ALPS правый (T1) не найден, serial неизвестен", self.err.getvalue())
        self.assertIn("ALPS правый (T1): пропущен по --skip-board, serial неизвестен", self.c.res.skipped)

    def test_forced_with_device_takes_serial(self):
        self.c.opts.skip_boards = ["alps1"]
        self.assertFalse(install.alps_try_skip(self.c, 0))                      # alps1 относится только ко второму
        self.assertTrue(install.alps_try_skip(self.c, 1))
        self.assertEqual(self.c.res.mcu.alps_serial[1], "S1")
        self.assertEqual(self.c.res.skipped, ["ALPS правый (T1): уже прошит (S1)"])
        self.assertIn("ALPS правый (T1): пропускаю, serial S1", self.out.getvalue())

    def test_auto_skip_needs_version_and_confirmation(self):
        self.assertFalse(install.alps_try_skip(self.c, 0))                      # версии в flashed.tsv нет
        self.c.flasher.flashed.set("S1", self.version)
        with mock.patch.object(ui, "ask_yn", return_value=False) as ask:
            self.assertFalse(install.alps_try_skip(self.c, 0))
        self.assertIn("найден S1, Klipper %s уже установлен. Пропустить прошивку?" % self.version, ask.call_args[0][0])
        with mock.patch.object(ui, "ask_yn", return_value=True):
            self.assertTrue(install.alps_try_skip(self.c, 0))
        self.assertEqual(self.c.res.mcu.alps_serial[0], "S1")
        self.assertTrue((self.tmp / "devices.tsv").exists())                    # save_devices(quiet) после пропуска

    def test_reflash_disables_auto_skip_but_not_forced(self):
        self.c.flasher.flashed.set("S1", self.version)
        self.c.opts.reflash = True
        with mock.patch.object(ui, "ask_yn", side_effect=AssertionError("не должен спрашивать")):
            self.assertFalse(install.alps_try_skip(self.c, 0))
        self.c.opts.skip_boards = ["alps"]
        self.assertTrue(install.alps_try_skip(self.c, 0))                       # как в bash: --skip-board сильнее --reflash


class TestSkipHeads(Base):
    def setUp(self):
        super().setUp()
        self.c = self.ctx(heads="v2", way="dfu")
        self.c.res.prev_devices = [Device("u" * 12, "stm32g431xx-can.config", "can"), Device("v" * 12, "stm32g431xx-can.config", "can")]

    def test_none_heads_never_skips(self):
        self.assertFalse(install.heads_try_skip(self.ctx(heads="none")))

    def test_auto_dfu_way(self):
        self.assertFalse(install.heads_try_skip(self.c))                         # версий нет
        for u in ("u" * 12, "v" * 12):
            self.c.flasher.flashed.set(u, self.version)
        with mock.patch.object(ui, "ask_yn", return_value=True) as ask:
            self.assertTrue(install.heads_try_skip(self.c))
        self.assertIn("по записям прошлой установки на обеих платах Klipper", ask.call_args[0][0])
        self.assertEqual((self.c.res.mcu.head_uuid, self.c.res.heads_skip), (["u" * 12, "v" * 12], True))
        self.assertEqual(self.c.res.skipped, ["Fysetc H36 v2: уже прошиты"])

    def test_auto_can_way_needs_bus(self):
        c = self.ctx(heads="v2", way="can")
        c.res.prev_devices = self.c.res.prev_devices
        for u in ("u" * 12, "v" * 12):
            c.flasher.flashed.set(u, self.version)
        self.assertFalse(install.heads_try_skip(c))                              # can0 не поднят
        self.runner.on(("ip", "link", "show", "can0"), 0, "can0: UP")
        with mock.patch.object(c.flasher, "can_uuids", return_value=["U" * 12]):
            self.assertFalse(install.heads_try_skip(c))                          # на шине только одна
        with mock.patch.object(c.flasher, "can_uuids", return_value=["U" * 12, "v" * 12]), \
                mock.patch.object(ui, "ask_yn", return_value=True):
            self.assertTrue(install.heads_try_skip(c))

    def test_forced_and_reflash(self):
        self.c.opts.skip_boards = ["heads"]
        self.assertTrue(install.heads_try_skip(self.c))
        self.c.res.prev_devices = []
        self.c.res.heads_skip = False
        self.assertTrue(install.heads_try_skip(self.c))
        self.assertIn("--skip-board heads: UUID плат голов неизвестны", self.err.getvalue())
        self.assertIn("платы голов: пропускаю (?, ?)", self.out.getvalue())
        c = self.ctx(heads="v2", reflash=True)
        self.assertFalse(install.heads_try_skip(c))


class TestSkipMain(Base):
    def test_usb(self):
        c = self.ctx()
        self.assertFalse(install.main_try_skip(c))                              # плат в by-id нет
        self.touch_byid("usb-Klipper_stm32h723xx_M1-if00")
        self.assertFalse(install.main_try_skip(c))                              # версии нет
        c.flasher.flashed.set("M1", self.version)
        c.res.prev_devices = [Device("M1", "spider-v3-h723.config", "usb")]       # за этим serial числится другая плата
        self.assertFalse(install.main_try_skip(c))
        c.res.prev_devices = [Device("M1", "stm32h723xx.config", "usb")]
        with mock.patch.object(ui, "ask_yn", return_value=True):
            self.assertTrue(install.main_try_skip(c))
        self.assertEqual((c.res.mcu.main_serial, c.res.skipped), ("M1", ["Octopus Pro v1.1 H723: уже прошит"]))

    def test_usb_forced(self):
        c = self.ctx(skip_boards=["main"])
        self.assertTrue(install.main_try_skip(c))
        self.assertIn("--skip-board main: usb-Klipper_stm32h723xx_* не найден, serial неизвестен", self.err.getvalue())
        self.touch_byid("usb-Klipper_stm32h723xx_M2-if00")
        c = self.ctx(skip_boards=["main"])
        self.assertTrue(install.main_try_skip(c))
        self.assertEqual(c.res.mcu.main_serial, "M2")
        c = self.ctx(skip_boards=["main"], reflash=True)
        self.assertTrue(install.main_try_skip(c))                                # forced сильнее reflash
        c = self.ctx(reflash=True)
        self.assertFalse(install.main_try_skip(c))

    def test_bridge(self):
        c = self.ctx(heads="v2")
        self.assertFalse(install.main_try_skip(c))                               # нет записи в devices.tsv
        c.res.prev_devices = [Device("b" * 12, "stm32h723xx-canbridge.config", "bridge")]
        self.assertFalse(install.main_try_skip(c))                               # can0 не поднят
        self.runner.on(("ip", "link", "show", "can0"), 0, "can0: UP")
        with mock.patch.object(c.flasher, "can_uuids", return_value=["x" * 12]):
            self.assertFalse(install.main_try_skip(c))
        with mock.patch.object(c.flasher, "can_uuids", return_value=["B" * 12]):
            self.assertFalse(install.main_try_skip(c))                           # версии нет
            c.flasher.flashed.set("b" * 12, self.version)
            with mock.patch.object(ui, "ask_yn", return_value=True):
                self.assertTrue(install.main_try_skip(c))
        self.assertEqual(c.res.mcu.bridge_uuid, "b" * 12)
        c = self.ctx(heads="v2", skip_boards=["main"])
        self.assertTrue(install.main_try_skip(c))
        self.assertIn("UUID моста неизвестен (нет devices.tsv)", self.err.getvalue())


class TestStages(Base):
    def test_flash_main_way_selection(self):
        for opt, ans, phase in (("dfu", None, "dfuall"), ("katapult", None, "full"), ("", 0, "dfuall"), ("", 1, "full")):
            c = self.ctx(main_flash=opt)
            seen = {}
            with mock.patch.object(install, "main_try_skip", return_value=False), \
                    mock.patch.object(install, "make_main_job", side_effect=lambda fl, start: seen.setdefault("start", start)), \
                    mock.patch.object(install, "flash_with_retry") as fw, \
                    mock.patch.object(ui, "ask_choice", side_effect=lambda q, d, o: o[ans or 0]):
                install.stage_flash_main(c)
            self.assertEqual(seen["start"], phase, (opt, ans))
            fw.assert_called_once()
        self.assertIn("Режим DFU: установите джампер на BOOT0, нажмите RESET (кнопка на плате).", self.out.getvalue())
        self.assertIn("Способ: katapult по DFU, затем Klipper через katapult. Если katapult уже на плате", self.out.getvalue())

    def test_flash_main_skipped(self):
        c = self.ctx()
        with mock.patch.object(install, "main_try_skip", return_value=True), mock.patch.object(install, "flash_with_retry") as fw:
            install.stage_flash_main(c)
        fw.assert_not_called()

    def test_stage_flash_order_and_devices(self):
        order = []
        for way, names in (("dfu", ["alps", "heads_dfu", "main", "uuid_check"]),
                           ("can", ["alps", "heads_katapult", "main", "heads_klipper"])):
            c = self.ctx(heads="v2", way=way)
            order.clear()
            patches = [mock.patch.object(install, "stage_flash_" + n.replace("heads_dfu", "heads_dfu"),
                                         side_effect=lambda ctx, n=n: order.append(n))
                       for n in ("alps", "heads_dfu", "heads_katapult", "heads_klipper", "main")]
            patches.append(mock.patch.object(install, "stage_heads_uuid_check", side_effect=lambda ctx: order.append("uuid_check")))
            with mock.patch.object(c.updater, "klipper_units", return_value=[]):
                for p in patches:
                    p.start()
                try:
                    install.stage_flash(c)
                finally:
                    mock.patch.stopall()
            self.assertEqual(order, names)
            self.assertIn("== Карта устройств (%s) ==" % self.env.devices_file, self.out.getvalue())

    def test_stage_flash_stops_klipper_and_sets_rc(self):
        c = self.ctx()
        c.res.failed = ["x"]
        with mock.patch.object(c.updater, "klipper_units", return_value=["klipper.service"]), \
                mock.patch.object(c.updater, "services") as svc, \
                mock.patch.object(install, "stage_flash_alps"), mock.patch.object(install, "stage_flash_main"), \
                mock.patch.object(install, "stage_heads_uuid_check"), mock.patch.object(install, "stage_flash_heads_dfu"):
            install.stage_flash(c)
        svc.assert_called_once_with("stop")
        self.assertTrue(c.klipper_stopped)
        self.assertEqual(c.finish_rc, 1)
        # prev_devices читаются до перезаписи
        DevicesFile(self.env.devices_file).save([Device("k", "c.config", "usb")])
        c = self.ctx(dry_run=True)
        c.runner.dry_run = True
        with mock.patch.object(install, "stage_flash_alps"), mock.patch.object(install, "stage_flash_main"), \
                mock.patch.object(install, "stage_heads_uuid_check"), mock.patch.object(install, "stage_flash_heads_dfu"):
            install.stage_flash(c)
        self.assertEqual(c.res.prev_devices, [Device("k", "c.config", "usb")])

    def test_alps_stage_skips_and_flashes(self):
        c = self.ctx(alps=2)
        jobs = []
        with mock.patch.object(install, "alps_try_skip", side_effect=[True, False]), \
                mock.patch.object(install, "make_alps_job", side_effect=lambda fl, i: jobs.append(i) or i), \
                mock.patch.object(install, "flash_with_retry") as fw:
            install.stage_flash_alps(c)
        self.assertEqual(jobs, [1])
        fw.assert_called_once()
        t = self.out.getvalue()
        self.assertIn("== ALPS левый (T0) ==", t)
        self.assertEqual(t.count("Датчик ALPS подключите USB-кабелем к хосту"), 1)

    def test_heads_katapult_and_dfu_stages(self):
        c = self.ctx(heads="v1.3", way="can")
        with mock.patch.object(install, "heads_try_skip", return_value=True), mock.patch.object(install, "flash_with_retry") as fw:
            install.stage_flash_heads_katapult(c)
            install.stage_flash_heads_dfu(c)
        fw.assert_not_called()
        with mock.patch.object(install, "heads_try_skip", return_value=False), \
                mock.patch.object(install, "flash_with_retry", side_effect=[True, False]) as fw:
            install.stage_flash_heads_katapult(c)
        self.assertEqual(fw.call_count, 2)
        t = self.text()
        self.assertIn("Вариант «Klipper по CAN»", t)
        self.assertIn("katapult записан на Fysetc H36 v1.3 левая (T0CB)", t)
        self.assertNotIn("katapult записан на Fysetc H36 v1.3 правая", t)         # вторая плата пропущена пользователем
        with mock.patch.object(install, "heads_try_skip", return_value=False), mock.patch.object(install, "flash_with_retry") as fw:
            install.stage_flash_heads_dfu(c)
        self.assertEqual(fw.call_count, 2)
        self.assertIn('Прошивка "на столе": питание 24 В и CAN не нужны, достаточно USB.', self.out.getvalue())

    def test_uuid_check_stage(self):
        c = self.ctx(heads="v2", way="dfu")
        c.res.mcu.bridge_uuid = "b" * 12
        c.res.mcu.head_uuid = ["1" * 12, ""]
        c.res.head_uuid_src = ["uid", ""]
        with mock.patch.object(ui, "ask_yn", return_value=False) as ask:
            install.stage_heads_uuid_check(c)
        t = self.text()
        self.assertIn("  мост (Octopus Pro v1.1 H723): " + "b" * 12, t)
        self.assertIn("левая (T0CB): %s (вычислен по UID чипа)" % ("1" * 12), t)
        self.assertIn("правая (T1CB): не определён\n", t)
        self.assertIn("Где UUID не определён, в printer.cfg стоит ЗАПОЛНИТЕ", t)
        ask.assert_called_once()
        with mock.patch.object(ui, "ask_yn", return_value=True), mock.patch.object(install, "check_can_uuids") as chk:
            install.stage_heads_uuid_check(c)
        chk.assert_called_once()
        self.assertIsNone(install.stage_heads_uuid_check(self.ctx(heads="none")))
        self.assertIsNone(install.stage_heads_uuid_check(self.ctx(heads="v2", way="can")))

    def test_heads_klipper_stage_without_can_iface(self):
        c = self.ctx(heads="v2", way="can")
        install.stage_flash_heads_klipper(c)
        self.assertIn("интерфейса can0 нет (мост USB-CAN не работает): платы голов по CAN не прошиваю", self.err.getvalue())
        self.assertEqual(c.res.failed, ["Fysetc H36 v2: не прошиты по CAN (нет can0; прошейте Octopus и запустите установку снова)"])

    def test_heads_klipper_stage_bridge_uuid_and_boards(self):
        self.runner.on(("ip", "link", "show", "can0"), 0, "can0: UP")
        self.runner.on(("ip", "-s"), 0, "line1\nline2\n")
        c = self.ctx(heads="v2", way="can")
        flashed = []
        with mock.patch.object(c.flasher, "can_uuids", side_effect=[["a" * 12, "b" * 12], ["a" * 12], ["a" * 12] * 3]), \
                mock.patch.object(install, "flash_with_retry", side_effect=lambda fl, j: flashed.append(j.label) or True), \
                mock.patch.object(ui, "pause_hw") as pause:
            install.stage_flash_heads_klipper(c)
        self.assertEqual(c.res.mcu.bridge_uuid, "a" * 12)
        self.assertEqual(flashed, ["Fysetc H36 v2 левая (T0CB) (Klipper)", "Fysetc H36 v2 правая (T1CB) (Klipper)"])
        self.assertEqual(pause.call_count, 2)                        # «отключите кабель» при двух UUID и итоговая проверка шины
        self.assertIn("На шине устройств с Klipper: 3 (ожидается 3: Octopus и две платы голов)", self.out.getvalue())
        # не удалось определить мост
        c = self.ctx(heads="v2", way="can")
        with mock.patch.object(c.flasher, "can_uuids", return_value=[]), mock.patch.object(install, "flash_with_retry"), \
                mock.patch.object(ui, "pause_hw"):
            install.stage_flash_heads_klipper(c)
        self.assertEqual(c.res.failed, ["Octopus: UUID моста не определён (впишите canbus_uuid в [mcu] вручную)"])
        self.assertIn("ожидался один UUID на шине, найдено: 0", self.err.getvalue())

    def test_heads_klipper_stage_dry_run(self):
        c = self.ctx(heads="v2", way="can", dry_run=True)
        c.runner.dry_run = True
        ui.set_options(dry_run=True)
        install.stage_flash_heads_klipper(c)
        self.assertEqual(c.res.mcu.head_uuid, ["000000000000", "000000000001"])
        self.assertEqual(c.res.mcu.bridge_uuid, "000000000000")


class TestStartButtonTheme(Base):
    def test_start_klipper_dry_run(self):
        c = self.ctx(dry_run=True)
        c.runner.dry_run = True
        install.stage_start_klipper(c)
        self.assertIn("[dry-run] systemctl start klipper; проверка ready и версий MCU", self.out.getvalue())

    def test_start_klipper_started_or_restarted(self):
        c = self.ctx()
        c.klipper_stopped = True
        with mock.patch.object(c.updater, "services") as svc, mock.patch.object(install, "wait_moonraker", return_value=True), \
                mock.patch.object(c.updater, "wait_for_klipper", return_value=True), \
                mock.patch.object(c.updater, "verify_versions", return_value=False):
            install.stage_start_klipper(c)
        svc.assert_called_once_with("start")
        self.assertFalse(c.klipper_stopped)
        self.assertEqual(c.finish_rc, 1)                                         # версии не совпали
        c = self.ctx()
        with mock.patch.object(install, "wait_moonraker", return_value=True), mock.patch.object(c.updater, "wait_for_klipper", return_value=True), \
                mock.patch.object(c.updater, "verify_versions", return_value=True):
            install.stage_start_klipper(c)
        self.assertEqual((self.runner.systemctl_calls, c.finish_rc), ([("restart", "klipper")], 0))

    def test_start_klipper_no_moonraker_and_bench_heads(self):
        c = self.ctx()
        with mock.patch.object(install, "wait_moonraker", return_value=False):
            install.stage_start_klipper(c)
        self.assertEqual(c.finish_rc, 1)
        self.assertIn("Moonraker не отвечает: systemctl status moonraker", self.err.getvalue())
        c = self.ctx(heads="v2", way="dfu")
        with mock.patch.object(install, "wait_moonraker", return_value=True), \
                mock.patch.object(c.updater, "wait_for_klipper", return_value=False), \
                mock.patch.object(c.updater, "verify_versions", side_effect=AssertionError("не должен проверять версии")):
            install.stage_start_klipper(c)
        self.assertEqual(c.finish_rc, 0)                                         # «на столе»: шины нет - это нормально
        self.assertIn("Платы голов прошиты на столе", self.out.getvalue())
        self.assertIn("Klipper не в состоянии ready: пока платы голов недоступны по CAN", self.out.getvalue())
        c = self.ctx(heads="v2", way="dfu", check_can=True)                      # --check-can: проверяем как обычно
        with mock.patch.object(install, "wait_moonraker", return_value=True), \
                mock.patch.object(c.updater, "wait_for_klipper", return_value=False), \
                mock.patch.object(c.updater, "verify_versions", return_value=True):
            install.stage_start_klipper(c)
        self.assertEqual(c.finish_rc, 1)

    def test_button_and_theme(self):
        d = self.env.install_dir
        c = self.ctx()
        self.runner.on((str(d / "install_fluidd_button.sh"),), 1)
        self.runner.on((str(d / "install_fluidd_theme.sh"),), 0)
        install.stage_button(c)
        self.assertIn("кнопку установить не удалось; позже: %s/install_fluidd_button.sh" % d, self.err.getvalue())
        self.assertEqual(c.finish_rc, 1)
        c = self.ctx()
        install.stage_theme(c)
        self.assertEqual((self.runner.called(str(d / "install_fluidd_theme.sh"), "-y"), c.finish_rc), (1, 0))
        self.assertEqual(self.runner.called(str(d / "install_klipperscreen_theme.sh")), 0)    # нет KlipperScreen
        (self.home / "KlipperScreen" / "styles").mkdir(parents=True)
        self.runner.on((str(d / "install_klipperscreen_theme.sh"),), 1)
        install.stage_theme(c)
        self.assertEqual(c.finish_rc, 1)
        self.assertIn("тему KlipperScreen установить не удалось", self.err.getvalue())

    def test_button_and_theme_dry_run(self):
        (self.home / "KlipperScreen" / "styles").mkdir(parents=True)
        c = self.ctx(dry_run=True)
        c.runner.dry_run = True
        install.stage_button(c)
        install.stage_theme(c)
        t = self.out.getvalue()
        for s in ("install_fluidd_button.sh -y", "install_fluidd_theme.sh -y", "install_klipperscreen_theme.sh -y"):
            self.assertIn("[dry-run] %s/%s" % (self.env.install_dir, s), t)
        self.assertEqual(self.runner.calls, [])


class TestSummary(Base):
    def test_summary_variants(self):
        c = self.ctx(heads="v2", way="dfu")
        c.res.failed = ["Плата X: не прошита"]
        c.res.skipped = ["ALPS левый (T0): уже прошит (S1)"]
        c.finish_rc = 1
        install.print_summary(c)
        t = self.text()
        self.assertIn("  1. Адаптировать electronics_*.cfg под вашу электронику", t)
        self.assertIn("(иначе поменяйте T0CB и T1CB местами)", t)
        self.assertIn("Платы голов прошиты на столе, canbus_uuid получены по UID чипов и на шине НЕ проверены.", t)
        self.assertIn("затем впишите canbus_uuid в [mcu], [mcu T0CB], [mcu T1CB].", t)
        self.assertIn("Не прошиты платы:\n  - Плата X: не прошита\n", t)
        self.assertIn("Пропущено как уже прошитое:\n  - ALPS левый (T0): уже прошит (S1)", t)
        self.assertIn("установка завершена с замечаниями (лог: %s)" % self.env.log_file, t)
        self.out.truncate(0)
        self.err.truncate(0)
        c = self.ctx()
        c.cfgr = mock.Mock(gen=object(), el_name="electronics_my.cfg")
        install.print_summary(c)
        t = self.text()
        self.assertIn("Вписать пины в сгенерированный electronics_my.cfg (поиск: ЗАПОЛНИТЕ)", t)
        self.assertIn("установка завершена", t)
        self.assertNotIn("с замечаниями", t)
        self.assertNotIn("прошиты на столе", t)


class TestCheckCan(Base):
    def setUp(self):
        super().setUp()
        self.runner.on(("ip", "link", "show", "can0"), 0, "can0: <UP> state UP")
        self.runner.on(("ip", "-s"), 0, "x\n")
        self.cfg = self.pd / "config" / "printer.cfg"
        self.cfg.write_text("[mcu]\ncanbus_uuid: %s\n\n[mcu T0CB]\ncanbus_uuid: ЗАПОЛНИТЕ\n\n[mcu T1CB]\ncanbus_uuid: ЗАПОЛНИТЕ\n"
                            % ("b" * 12))

    def c(self):
        c = self.ctx(heads="v2")
        c.res.mcu.bridge_uuid = "b" * 12
        c.res.mcu.head_uuid = ["1" * 12, "2" * 12]
        return c

    def run_check(self, c, uuids, answers=(), pauses=()):
        seq = iter(uuids)
        with mock.patch.object(c.flasher, "can_uuids", side_effect=lambda app: list(next(seq))), \
                mock.patch.object(ui, "pause_hw") as pause, mock.patch.object(ui, "ask_yn", side_effect=list(answers) or [True] * 5):
            res = install.check_can_uuids(c)
        return res, pause

    def test_all_found(self):
        c = self.c()
        res, pause = self.run_check(c, [["b" * 12, "1" * 12, "2" * 12]])
        self.assertTrue(res)
        self.assertEqual(pause.call_count, 0)
        t = self.out.getvalue()
        self.assertIn("mcu T0CB: %s найден на шине" % ("1" * 12), t)
        self.assertEqual(c.res.head_uuid_src, ["bus", "bus"])
        self.assertIn("1" * 12, self.cfg.read_text())
        self.assertIn("canbus_uuid подтверждены на шине", t)
        self.assertEqual(c.flasher.flashed.get("1" * 12), self.version)
        self.assertIn("%s\tstm32g431xx-can.config\tcan" % ("1" * 12), (self.tmp / "devices.tsv").read_text())

    def test_one_wrong_uuid_is_replaced_by_the_free_one(self):
        c = self.c()
        res, _ = self.run_check(c, [["b" * 12, "1" * 12, "9" * 12]])
        self.assertTrue(res)
        self.assertEqual(c.res.mcu.head_uuid, ["1" * 12, "9" * 12])
        self.assertIn("mcu T1CB: на шине вместо %s найден %s" % ("2" * 12, "9" * 12), self.out.getvalue())
        self.assertIn("canbus_uuid: " + "9" * 12, self.cfg.read_text())

    def test_nothing_found_and_no_free(self):
        c = self.c()
        res, _ = self.run_check(c, [[]])
        self.assertFalse(res)
        self.assertIn("mcu: %s - на шине не найден" % ("b" * 12), self.err.getvalue())

    def test_all_unknown_walks_user_through_it(self):
        c = self.ctx(heads="v2")                               # UUID нигде не записаны
        bus = ["c" * 12, "d" * 12, "e" * 12]
        res, pause = self.run_check(c, [bus, ["c" * 12], ["c" * 12, "d" * 12]])
        self.assertTrue(res)
        self.assertEqual(pause.call_count, 3)
        self.assertEqual((c.res.mcu.bridge_uuid, c.res.mcu.head_uuid), ("c" * 12, ["d" * 12, "e" * 12]))
        self.assertIn("правая голова T1CB: " + "e" * 12, self.out.getvalue())

    def test_unmatched_and_no_interface(self):
        c = self.c()
        res, _ = self.run_check(c, [["b" * 12, "7" * 12, "8" * 12, "9" * 12]])      # плат больше ожидаемого
        self.assertFalse(res)
        self.assertIn("не удалось однозначно сопоставить платы", self.err.getvalue())
        self.runner.rules.insert(0, (lambda a: tuple(a[:4]) == ("ip", "link", "show", "can0"), 1, ""))
        with mock.patch.object(hardware.time, "sleep"):
            res, _ = self.run_check(self.c(), [])
        self.assertFalse(res)
        self.assertIn("интерфейса can0 нет: мост USB-CAN не подключён к хосту или не прошит", self.err.getvalue())

    def test_dry_run(self):
        c = self.ctx(heads="v2", dry_run=True)
        c.runner.dry_run = True
        self.assertTrue(install.check_can_uuids(c))
        self.assertIn("[dry-run] canbus_query.py can0, сверка с devices.tsv, запись в printer.cfg", self.out.getvalue())

    def test_write_uuid_to_cfg_cases(self):
        c = self.c()
        install.write_uuid_to_cfg(c, "mcu", "b" * 12)
        install.write_uuid_to_cfg(c, "mcu T9", "1" * 12)
        t = self.text()
        self.assertIn("printer.cfg: [mcu] уже содержит " + "b" * 12, t)
        self.assertIn("в printer.cfg нет секции [mcu T9]: впишите canbus_uuid: " + "1" * 12 + " вручную", t)
        with mock.patch.object(ui, "ask_yn", return_value=False):
            install.write_uuid_to_cfg(c, "mcu", "f" * 12)
        self.assertIn("[mcu] оставлен без изменений, проверьте вручную", self.err.getvalue())
        with mock.patch.object(ui, "ask_yn", return_value=True):
            install.write_uuid_to_cfg(c, "mcu", "f" * 12)
        self.assertIn("canbus_uuid: " + "f" * 12, self.cfg.read_text())
        self.cfg.unlink()
        install.write_uuid_to_cfg(c, "mcu", "f" * 12)               # нет printer.cfg - тихо

    def test_check_can_main_reads_devices_and_printer_cfg(self):
        DevicesFile(self.env.devices_file).save([
            Device("b" * 12, "stm32h723xx-canbridge.config", "bridge"), Device("1" * 12, "stm32g431xx-can.config", "can"),
            Device("2" * 12, "stm32g431xx-can.config", "can"), Device("S", "stm32f072xb.config", "usb")])
        self.cfg.write_text("[mcu]\ncanbus_uuid: x\n[mcu T0_EBB]\ncanbus_uuid: y\n[mcu T1_EBB]\ncanbus_uuid: z\n")
        c = self.ctx(heads="none")
        c.hw = Hardware(REG)
        c.set_hardware(c.hw)
        seen = {}
        with mock.patch.object(install, "check_can_uuids", side_effect=lambda ctx: seen.update(
                hw=(ctx.hw.main_board, ctx.hw.heads, ctx.hw.head_mcu, ctx.hw.mode), res=(ctx.res.mcu.bridge_uuid, ctx.res.mcu.head_uuid)) or True), \
                mock.patch.object(install, "stage_start_klipper"), mock.patch.object(c.updater, "klipper_units", return_value=[]):
            install.check_can_main(c)
        self.assertEqual(seen["hw"][0], "octopus-pro-h723")
        self.assertEqual(seen["hw"][1:], ("v1.3", ["T0_EBB", "T1_EBB"], "bridge")) if seen["hw"][1] == "v1.3" else \
            self.assertEqual(seen["hw"][1:], ("v2", ["T0_EBB", "T1_EBB"], "bridge"))
        self.assertEqual(seen["res"], ("b" * 12, ["1" * 12, "2" * 12]))
        self.assertIn("проверка завершена", self.out.getvalue())

    def test_check_can_main_asks_when_nothing_known(self):
        c = self.ctx(heads="none")
        c.set_hardware(Hardware(REG))
        asked = []
        with mock.patch.object(install, "check_can_uuids", return_value=False), mock.patch.object(install, "stage_start_klipper"), \
                mock.patch.object(c.updater, "klipper_units", return_value=["klipper.service"]), \
                mock.patch.object(c.updater, "services") as svc, \
                mock.patch.object(HardwareDetector_ask(), "ask_board", side_effect=lambda q, d, ids: asked.append((q, d, ids)) or d), \
                mock.patch.object(ui, "ask_choice", return_value="ebb42"):
            install.check_can_main(c)
        self.assertEqual(asked[0][1], "octopus-pro-h723")
        self.assertNotIn("manta-m8p-v1.0", asked[0][2])            # только платы с мостом USB-CAN
        self.assertEqual((c.hw.heads, c.finish_rc, c.klipper_stopped), ("ebb42", 1, True))
        svc.assert_called_once_with("stop")
        self.assertIn("проверка завершена с замечаниями", self.err.getvalue())


def HardwareDetector_ask():
    from vostok.configurator import HardwareDetector
    return HardwareDetector


class TestRunPipeline(Base):
    """Порядок этапов run() и режимы выхода; сами этапы подменены."""

    STAGES = ("stage_preflight", "stage_packages", "stage_can", "stage_flash", "stage_config", "stage_start_klipper",
              "stage_button", "stage_theme", "print_summary", "choose_heads_flash", "print_plan")

    def run_pipeline(self, argv, answers=True, detect_heads="none"):
        o = install.parse_args(argv, self.env, REG)
        c = InstallContext(o, self.env, REG, self.runner, argv=list(argv))
        order = []
        hw = Hardware(REG, main_board="octopus-pro-h723", heads=detect_heads, mode="usb")
        patches = [mock.patch.object(install, n, side_effect=lambda *a, n=n: order.append(n)) for n in self.STAGES]
        patches += [mock.patch.object(Software, "stage_software", side_effect=lambda: order.append("stage_software")),
                    mock.patch.object(EnvChecks, "check_tools", side_effect=lambda need, after: order.append("tools%d%d" % (need, after))),
                    mock.patch.object(EnvChecks, "check_hw_requirements", side_effect=lambda h: order.append("hwreq")),
                    mock.patch.object(install.HardwareDetector, "detect", return_value=hw),
                    mock.patch.object(ui, "ask_yn", return_value=answers),
                    mock.patch.object(install.os, "geteuid", return_value=1000)]
        with contextlib.ExitStack() as st:
            for p in patches:
                st.enter_context(p)
            rc = install.run(c)
        return rc, order, c

    def test_full_run(self):
        rc, order, c = self.run_pipeline(["-y"])
        self.assertEqual(order, ["stage_preflight", "stage_packages", "stage_software", "tools11", "choose_heads_flash", "print_plan", "hwreq",
                                 "stage_can", "stage_flash", "stage_config", "stage_start_klipper", "stage_button", "stage_theme",
                                 "print_summary"])
        self.assertEqual(rc, 0)

    def test_only_detect_stops_after_plan(self):
        rc, order, _ = self.run_pipeline(["--only-detect"])
        self.assertEqual(order, ["stage_preflight", "tools10", "choose_heads_flash", "print_plan", "hwreq"])
        self.assertEqual(rc, 0)

    def test_declined_plan(self):
        rc, order, _ = self.run_pipeline([], answers=False)
        self.assertEqual(rc, 0)
        self.assertEqual(order[-1], "hwreq")
        self.assertNotIn("stage_flash", order)
        self.assertIn("отменено", self.out.getvalue())

    def test_dry_run_does_not_ask(self):
        rc, order, _ = self.run_pipeline(["--dry-run", "-y"])
        self.assertIn("stage_flash", order)

    def test_skip_flags(self):
        rc, order, _ = self.run_pipeline(["-y", "--skip-software", "--skip-flash", "--skip-button", "--skip-theme"])
        self.assertEqual(order, ["stage_preflight", "tools00", "choose_heads_flash", "print_plan", "stage_start_klipper", "print_summary"])
        self.assertIn("Прошивка пропущена (--skip-flash): serial/UUID для printer.cfg неизвестны, впишите [mcu ...] вручную",
                      self.out.getvalue())
        rc, order, _ = self.run_pipeline(["-y", "--skip-config"])
        self.assertNotIn("stage_config", order)
        self.assertIn("stage_flash", order)

    def test_check_can_flow_and_root(self):
        o = install.parse_args(["--check-can", "-y"], self.env, REG)
        c = InstallContext(o, self.env, REG, self.runner)
        with mock.patch.object(install, "check_can_main", side_effect=lambda ctx: setattr(ctx, "finish_rc", 1)) as m, \
                mock.patch.object(install.os, "geteuid", return_value=1000):
            self.assertEqual(install.run(c), 1)
        m.assert_called_once()
        self.assertEqual(self.runner.keepalive_calls, [True])
        with mock.patch.object(install.os, "geteuid", return_value=0):
            with self.assertRaises(VostokError) as cm:
                install.run(c)
        self.assertEqual(str(cm.exception), "не запускайте от root; sudo спросит пароль сам")

    def test_sudo_keepalive_only_when_changing(self):
        rc, order, c = self.run_pipeline(["--only-detect"])
        self.assertEqual(self.runner.keepalive_calls, [False])
        self.runner.keepalive_calls = []
        self.run_pipeline(["-y"])
        self.assertEqual(self.runner.keepalive_calls, [True])


class TestMain(Base):
    def test_exit_codes_and_klipper_hint(self):
        with mock.patch.object(install, "run", return_value=3), mock.patch.object(install, "Env") as E:
            E.from_environ.return_value = self.env
            self.assertEqual(install.main(["-y"]), 3)
        with mock.patch.object(install, "Env") as E:
            E.from_environ.return_value = self.env
            self.assertEqual(install.main(["-h"]), 0)
            self.assertEqual(install.main(["--list-boards"]), 0)

        def boom(ctx):
            ctx.klipper_stopped = True
            raise UserAbort("установка прервана пользователем (X)")
        with mock.patch.object(install, "run", side_effect=boom), mock.patch.object(install, "Env") as E:
            E.from_environ.return_value = self.env
            self.assertEqual(install.main(["-y"]), 1)
        self.assertIn("ОШИБКА: установка прервана пользователем (X)", self.err.getvalue())
        self.assertIn("Klipper остановлен. После устранения проблемы запустите установку снова или: sudo systemctl start klipper",
                      self.err.getvalue())
        self.assertLess(self.err.getvalue().index("ОШИБКА"), self.err.getvalue().index("Klipper остановлен"))

    def test_hint_only_when_stopped_and_failed(self):
        with mock.patch.object(install, "run", return_value=1), mock.patch.object(install, "Env") as E:
            E.from_environ.return_value = self.env
            install.main(["-y"])
        self.assertNotIn("Klipper остановлен", self.err.getvalue())


class TestScenarioRealRunner(Base):
    """Прошивка главной платы настоящим Runner: вместо внешних программ - заглушки в PATH (sudo просто запускает команду)."""

    def setUp(self):
        super().setUp()
        import shutil
        self.stubs = self.tmp / "stubs"
        self.stubs.mkdir()
        self.calls = self.tmp / "calls.log"
        self.configs = self.tmp / "configs"
        shutil.copytree(str(INSTALLER / "configs"), str(self.configs))
        self.reg = Registry(INSTALLER / "boards", self.configs)
        self.env = self.make_env(CONFIGS_DIR=str(self.configs))
        fl = Path(self.env.katapult_dir) / "scripts"
        fl.mkdir(parents=True)
        (fl / "flashtool.py").write_text("import sys\nopen(%r, 'a').write('flashtool ' + ' '.join(sys.argv[1:]) + '\\n')\n" % str(self.calls))
        self.dfu_fails = self.tmp / "dfu_fails"
        log = str(self.calls)
        self.stub("sudo", 'echo "sudo $*" >> %s\nexec "$@"' % log)
        self.stub("lsusb", 'echo "Bus 001 Device 002: ID 0483:df11 STMicroelectronics"')
        self.stub("dfu-util", 'echo "dfu-util $*" >> %s\nif [ "$1" = "-l" ]; then echo "Found DFU: [0483:df11] 0x5200"; exit 0; fi\n'
                              'if [ -e %s ]; then echo "Error"; exit 74; fi\necho "Download done."' % (log, self.dfu_fails))
        self.stub("make", 'for a in "$@"; do case $a in OUT=*) out=${a#OUT=};; esac; done\n'
                          'case "$*" in *-j*) mkdir -p "$out"; echo BIN > "$out/klipper.bin"; echo KBIN > "$out/katapult.bin";; esac')
        self.stub("git", 'echo "v0.12.0-1-gabc"')
        self.stub("ip", "exit 1")
        p = mock.patch.dict(os.environ, {"PATH": "%s:%s" % (self.stubs, os.environ["PATH"])})
        p.start()
        self.addCleanup(p.stop)

    def stub(self, name, body):
        f = self.stubs / name
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)

    def pause_hook(self, create):
        def pause(msg, allow_skip=False):
            for needle, files in create.items():
                if needle in msg:
                    for fn in files:
                        (self.byid / fn).touch()
            return ""
        return mock.patch.object(ui, "pause_hw", side_effect=pause)

    def context(self, **opt):
        ui.set_options(yes=True, dry_run=False)
        c = InstallContext(Options(yes=True, **opt), self.env, self.reg, install.Runner())
        hw = Hardware(self.reg, main_board="octopus-pro-h723", heads="none", alps_count=0, mode="usb")
        hw.set_head_names()
        c.set_hardware(hw)
        return c

    def test_main_dfu_all_session(self):
        c = self.context()
        with self.pause_hook({"нажмите RESET на": ["usb-Klipper_stm32h723xx_NEWSER-if00"]}):
            flashing.flash_with_retry(c.flasher, flashing.make_main_job(c.flasher, "dfuall"))
        self.assertEqual(c.res.mcu.main_serial, "NEWSER")
        log = self.calls.read_text()
        self.assertIn("dfu-util -a 0 -s 0x08000000:mass-erase:force -D %s/katapult-stm32h723xx/out/katapult.bin -d 0483:df11" % self.env.cfg.build_dir, log)
        self.assertIn("dfu-util -a 0 -s 0x8020000:leave -D %s/stm32h723xx-v0.12.0-1-gabc.bin -d 0483:df11" % self.env.cfg.firmware_dir, log)
        self.assertEqual((self.tmp / "devices.tsv").read_text(), "NEWSER\tstm32h723xx.config\tusb\n")
        self.assertEqual((self.tmp / "flashed.tsv").read_text(), "NEWSER\tv0.12.0-1-gabc\n")
        self.assertEqual(c.res.failed, [])

    def test_main_katapult_then_klipper(self):
        c = self.context()
        files = ["usb-katapult_stm32h723xx_KSER-if00", "usb-Klipper_stm32h723xx_KSER-if00"]
        with self.pause_hook({"ДВАЖДЫ быстро нажмите RESET": files}):
            self.assertTrue(flashing.flash_with_retry(c.flasher, flashing.make_main_job(c.flasher, "full")))
        self.assertEqual(c.res.mcu.main_serial, "KSER")
        log = self.calls.read_text()
        self.assertIn("dfu-util -R -a 0 -s 0x08000000:mass-erase:force:leave -D", log)
        self.assertIn("flashtool -d %s/usb-katapult_stm32h723xx_KSER-if00 -f %s/stm32h723xx-v0.12.0-1-gabc.bin"
                      % (self.byid, self.env.cfg.firmware_dir), log)
        self.assertEqual((self.tmp / "flashed.tsv").read_text(), "KSER\tv0.12.0-1-gabc\n")

    def test_dfu_failure_with_yes_skips_board_and_continues(self):
        self.dfu_fails.touch()                       # dfu-util не пишет «Download done»
        c = self.context()
        with self.pause_hook({}):
            self.assertFalse(flashing.flash_with_retry(c.flasher, flashing.make_main_job(c.flasher, "dfuall")))
        self.assertEqual(c.res.failed, ["Octopus Pro v1.1 H723: не прошита"])
        self.assertIn("katapult не записан по DFU (нет 'Download done')", self.err.getvalue())
        self.assertFalse((self.tmp / "devices.tsv").exists())

    def test_make_failure_is_reported_not_raised(self):
        self.stub("make", 'echo "boom" >&2; exit 2')
        c = self.context()
        with self.pause_hook({}):
            self.assertFalse(flashing.flash_with_retry(c.flasher, flashing.make_main_job(c.flasher, "dfuall")))
        err = self.err.getvalue()
        self.assertIn("ОШИБКА: olddefconfig katapult (stm32h723xx) не удался", err)
        self.assertIn("сборка katapult (stm32h723xx) не удалась", err)
        self.assertIn("boom", err)                                              # хвост make.log

    def test_can_uuids_and_bring_up_with_real_runner(self):
        self.stub("ip", 'echo "ip $*" >> %s\nif [ "$1 $2 $3" = "link show can0" ]; then echo "3: can0: <NOARP,UP> state UP"; exit 0; fi\n'
                        'exit 0' % self.calls)
        kd = Path(self.env.klipper_dir) / "scripts"
        kd.mkdir(parents=True)
        (kd / "canbus_query.py").write_text("print('Found canbus_uuid=0123456789ab, Application: Klipper')\n")
        env = Path(self.env.klippy_env) / "bin"
        env.mkdir(parents=True)
        (env / "python").symlink_to(sys.executable)
        c = self.context()
        self.assertEqual(c.flasher.can_uuids("Klipper"), ["0123456789ab"])
        self.assertTrue(hardware.bring_up_can(c.runner, "can0"))


class TestLoader(unittest.TestCase):
    """install_vostok.sh - тонкий загрузчик: python3 при отсутствии, затем exec python3 -m vostok install."""

    def setUp(self):
        import tempfile
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name)
        self.bin = self.d / "bin"
        self.bin.mkdir()
        # минимум утилит, нужных самому загрузчику
        for name in ("bash", "dirname", "readlink", "env", "chmod"):
            real = subprocess.run(["bash", "-c", "command -v %s" % name], stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
            os.symlink(real, self.bin / name)

    def stub(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/bash\n" + body + "\n")
        p.chmod(0o755)

    def run_loader(self, *args, env_extra=None):
        env = {"PATH": str(self.bin), "HOME": str(self.d)}
        env.update(env_extra or {})
        return subprocess.run([str(self.bin / "bash"), str(INSTALLER / "install_vostok.sh")] + list(args), env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def test_exec_python_module_with_pythonpath(self):
        self.stub("python3", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "ARGS: $*"\necho "PP=$PYTHONPATH DB=$PYTHONDONTWRITEBYTECODE"')
        r = self.run_loader("--dry-run", "-y", "--main", "h723")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ARGS: -m vostok install --dry-run -y --main h723", r.stdout)
        self.assertIn("PP=%s DB=1" % INSTALLER, r.stdout)

    def test_symlink_invocation_resolves_install_dir(self):
        self.stub("python3", 'if [ "$1" = "-c" ]; then exit 0; fi\necho "PP=$PYTHONPATH"')
        link = self.d / "link.sh"
        os.symlink(INSTALLER / "install_vostok.sh", link)
        r = subprocess.run([str(self.bin / "bash"), str(link)], env={"PATH": str(self.bin)}, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True)
        self.assertIn("PP=%s" % INSTALLER, r.stdout)

    def test_no_python_readonly_modes_do_not_install(self):
        self.stub("sudo", 'echo "SUDO $*" >> %s/sudo.log' % self.d)
        self.stub("apt-get", "exit 0")
        for flag in ("--dry-run", "--only-detect", "--help", "--list-boards", "-V"):
            r = self.run_loader(flag)
            self.assertEqual(r.returncode, 1, flag)
            self.assertIn("ОШИБКА: нужен python3 (в режимах --dry-run/--only-detect/справка он не устанавливается", r.stderr)
        self.assertFalse((self.d / "sudo.log").exists())

    def test_no_python_installs_it_with_sudo_apt(self):
        log = self.d / "apt.log"
        self.stub("sudo", 'echo "sudo $*" >> %s\nif [ "$1" = apt-get ] && [ "$2" = install ]; then\n'
                          '  printf \'#!/bin/bash\\nif [ "$1" = "-c" ]; then exit 0; fi\\necho PY-OK "$@"\\n\' > %s/python3; chmod +x %s/python3\nfi' % (log, self.bin, self.bin))
        self.stub("apt-get", "exit 0")
        r = self.run_loader("-y")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(log.read_text().splitlines(), ["sudo apt-get update", "sudo apt-get install -y python3 python3-venv"])
        self.assertIn("python3 не установлен: ставлю python3 и python3-venv", r.stdout)
        self.assertIn("PY-OK -m vostok install -y", r.stdout)

    def test_no_python_no_apt_or_install_failure(self):
        r = self.run_loader("-y")
        self.assertEqual(r.returncode, 1)
        self.assertIn("apt-get не найден", r.stderr)
        self.stub("apt-get", "exit 0")
        self.stub("sudo", "exit 0")
        r = self.run_loader("-y")
        self.assertIn("не удалось установить python3", r.stderr)

    def test_old_python_is_rejected(self):
        self.stub("python3", 'if [ "$1" = "-c" ]; then exit 1; fi\necho "Python 3.6.9"')
        r = self.run_loader("-y")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ОШИБКА: python3 слишком старый, нужен 3.8 или новее", r.stderr)

    def test_loader_is_thin_and_has_no_legacy_sources(self):
        text = (INSTALLER / "install_vostok.sh").read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 80)
        for bad in ("source ", "lib/", "update_klipper_mcu.sh", "vostok_config.sh", "BASH_SOURCE[0]\" == "):
            self.assertNotIn(bad, text, bad)
        self.assertTrue(os.access(INSTALLER / "install_vostok.sh", os.X_OK))
        self.assertIn('PYTHONPATH="$INSTALL_DIR" PYTHONDONTWRITEBYTECODE=1 exec python3 -m vostok install "$@"', text)


if __name__ == "__main__":
    unittest.main()
