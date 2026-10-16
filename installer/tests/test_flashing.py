"""Тесты vostok.flashing: примитивы DFU/katapult, стратегии, меню и повтор (retry/dfu/dfuall/dfuk/skip/abort).

Внешние программы не запускаются (FakeRunner), сборка и dfu-util подменены, ~/printer_data не трогается.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fakes import INSTALLER, REG, FakeRunner, Sandbox  # noqa: E402
from vostok import FlashError, UserAbort, flashing, firmware, hardware, ui  # noqa: E402
from vostok.configurator import Hardware  # noqa: E402
from vostok.flashing import (DfuAll, DfuKlipperOnly, FlashJob, Flasher, KatapultThenKlipper, Outcome, Target,  # noqa: E402
                             flash_menu, flash_with_retry)
from vostok.host import Options, Results  # noqa: E402
from vostok.state import Device  # noqa: E402

LSUSB = ("lsusb", "-d", "0483:df11")
H723 = "usb-Klipper_stm32h723xx_AAA111-if00"


class Base(Sandbox):
    def setUp(self):
        super().setUp()
        self.runner = FakeRunner(default_rc=1)
        self.runner.on(("git", "-C", self.env.klipper_dir, "describe"), 0, "v0.12.0-1-gabc\n")
        self.opts = Options()
        self.res = Results()
        self.hw = self.make_hw()
        self.fl = Flasher(self.env, self.opts, self.hw, self.res, REG, self.runner)
        self.pauses = []
        p = mock.patch.object(ui, "pause_hw", side_effect=self._pause)
        p.start()
        self.addCleanup(p.stop)
        self.answers = []          # ответы pause_hw по очереди (по умолчанию пустая строка)

    def _pause(self, msg, allow_skip=False):
        self.pauses.append((msg, allow_skip))
        return self.answers.pop(0) if self.answers else ""

    def make_hw(self, main="octopus-pro-h723", heads="none", alps=0):
        hw = Hardware(REG, main_board=main, heads=heads, alps_count=alps, mode="usb" if heads == "none" else "bridge")
        hw.set_head_names()
        return hw

    def target(self, **kw):
        d = dict(label="Плата", chip="stm32h723xx", family="h7", klipper_cfg=INSTALLER / "configs" / "stm32h723xx.config",
                 katapult_cfg=INSTALLER / "configs" / "katapult" / "stm32h723xx.config", enter_hint="DFU, пожалуйста")
        d.update(kw)
        return Target(**d)

    def dfu_present(self, family_text="0x5200"):
        self.runner.rules.insert(0, (lambda a: tuple(a[:3]) == LSUSB, 0, "Bus 001 Device 002: ID 0483:df11\n"))
        self.runner.on(("sudo", "-n", "dfu-util", "-l"), 0, "Found DFU: [0483:df11] %s" % family_text)


class TestWaitDfu(Base):
    def test_ok(self):
        self.dfu_present()
        self.fl.wait_dfu("h7", "Плата")
        self.assertIn("DFU: STM32H7 (", self.text())

    def test_no_device_declined(self):
        with mock.patch.object(ui, "ask_yn", return_value=False):
            with self.assertRaises(FlashError):
                self.fl.wait_dfu("h7", "Плата")
        self.assertIn("устройство DFU (0483:df11) не найдено", self.err.getvalue())

    def test_no_device_then_found(self):
        state = {"n": 0}

        def lsusb(argv):
            state["n"] += 1
            return "" if state["n"] <= 20 else "Bus 1 ID 0483:df11\n"
        self.runner.on(LSUSB, 0, lsusb)
        self.runner.on(("sudo", "-n", "dfu-util", "-l"), 0, "0x5200")
        with mock.patch.object(ui, "ask_yn", return_value=True):
            self.fl.wait_dfu("h7", "Плата")
        self.assertEqual(self.pauses[0], ("Переведите Плата в DFU и нажмите Enter.", True))

    def test_two_devices_declined(self):
        self.runner.on(LSUSB, 0, "a\nb\n")
        with mock.patch.object(ui, "ask_yn", return_value=False):
            with self.assertRaises(FlashError):
                self.fl.wait_dfu("h7", "Плата")
        self.assertIn("в режиме DFU сразу 2 устройства", self.err.getvalue())

    def test_wrong_family_continue_or_decline(self):
        self.dfu_present("0x1FFFC000")      # f4
        with mock.patch.object(ui, "ask_yn", side_effect=[True]):
            self.fl.wait_dfu("h7", "Плата")           # «всё равно нужная плата»
        self.assertIn("в DFU найден чип: STM32F4", self.err.getvalue())
        with mock.patch.object(ui, "ask_yn", side_effect=[False, False]):
            with self.assertRaises(FlashError):
                self.fl.wait_dfu("h7", "Плата")


class TestKatapult(Base):
    def setUp(self):
        super().setUp()
        self.kbin = self.tmp / "katapult.bin"
        self.kbin.write_bytes(b"K")
        p = mock.patch.object(firmware, "build_katapult", return_value=str(self.kbin))
        p.start()
        self.addCleanup(p.stop)
        self.dfu_calls = []
        self.dfu_results = [True]
        p2 = mock.patch.object(firmware, "dfu_run", side_effect=self._dfu)
        p2.start()
        self.addCleanup(p2.stop)

    def _dfu(self, runner, argv, sudo=False):
        self.dfu_calls.append((list(argv), sudo))
        return self.dfu_results.pop(0) if self.dfu_results else False

    def test_guide_mass_erase_then_fallback(self):
        self.dfu_results = [False, True]
        self.dfu_present()
        self.fl.dfu_flash_katapult("guide", "k.config")
        self.assertIn("0x08000000:mass-erase:force:leave", self.dfu_calls[0][0])
        self.assertIn("0x08000000:leave", self.dfu_calls[1][0])
        self.assertTrue(all(sudo for _, sudo in self.dfu_calls))
        self.assertIn("с mass-erase не вышло", self.err.getvalue())

    def test_guide_no_fallback_when_left_dfu(self):
        self.dfu_results = [False]
        with self.assertRaises(FlashError):
            self.fl.dfu_flash_katapult("guide", "k.config")      # lsusb: 0 устройств - второй попытки нет
        self.assertEqual(len(self.dfu_calls), 1)
        self.assertIn("katapult не записан по DFU", self.err.getvalue())

    def test_make_mode(self):
        self.fl.dfu_flash_katapult("make", INSTALLER / "configs" / "katapult" / "stm32f072xb.config")
        argv, sudo = self.dfu_calls[0]
        self.assertEqual(argv[0:2], ["make", "-C"])
        self.assertIn("FLASH_DEVICE=0483:df11", argv)
        self.assertFalse(sudo)

    def test_dry_run_only_prints(self):
        self.runner.dry_run = True
        ui.set_options(dry_run=True)
        self.fl.dfu_flash_katapult("guide", "k.config")
        self.assertEqual(self.dfu_calls, [])
        self.assertIn("[dry-run] dfu-util -> " + str(self.kbin), self.out.getvalue())

    def test_build_failure_is_flash_error_with_message(self):
        from vostok import VostokError
        with mock.patch.object(firmware, "build_katapult", side_effect=VostokError("нет конфига katapult: x")):
            with self.assertRaises(FlashError):
                self.fl.dfu_flash_katapult("guide", "/x/k.config")
        self.assertIn("ОШИБКА: нет конфига katapult: x", self.err.getvalue())
        self.assertIn("сборка katapult (k) не удалась", self.err.getvalue())

    # --- enter_katapult
    def test_enter_dry_run(self):
        self.runner.dry_run = True
        ui.set_options(dry_run=True)
        t = self.target(after_hint="Снимите джампер")
        dev = self.fl.enter_katapult(t)
        self.assertEqual(dev, "%s/usb-katapult_stm32h723xx_DRYRUN-if00" % self.byid)
        self.assertEqual([p[0] for p in self.pauses], ["Плата: DFU, пожалуйста", "Снимите джампер"])

    def test_enter_skip_with_existing_katapult(self):
        self.touch_byid("usb-katapult_stm32h723xx_AAA-if00")
        self.answers = ["s"]
        dev = self.fl.enter_katapult(self.target())
        self.assertEqual(os.path.basename(dev), "usb-katapult_stm32h723xx_AAA-if00")
        self.assertEqual(self.dfu_calls, [])
        self.assertIn("Плата уже в режиме katapult", self.out.getvalue())

    def test_enter_skip_several_devices_asks(self):
        self.touch_byid("usb-katapult_stm32h723xx_AAA-if00", "usb-katapult_stm32h723xx_BBB-if00")
        self.answers = ["Ы"]
        with mock.patch.object(ui, "ask_choice", return_value="usb-katapult_stm32h723xx_BBB-if00") as ac:
            dev = self.fl.enter_katapult(self.target())
        self.assertTrue(dev.endswith("BBB-if00"))
        self.assertIn("в katapult сразу несколько плат", ac.call_args[0][0])

    def test_enter_skip_double_reset_timeout(self):
        self.answers = ["s"]
        with self.assertRaises(FlashError):
            self.fl.enter_katapult(self.target())
        self.assertIn("Пропускаю DFU: дважды быстро нажмите RESET", self.out.getvalue())
        self.assertIn("usb-katapult_stm32h723xx_* не появился", self.err.getvalue())

    def test_enter_via_dfu(self):
        self.dfu_present()
        newdev = "%s/usb-katapult_stm32h723xx_NEW-if00" % self.byid

        def flash_kat(mode, cfg):
            Path(newdev).touch()
        with mock.patch.object(self.fl, "dfu_flash_katapult", side_effect=flash_kat) as fk:
            dev = self.fl.enter_katapult(self.target(after_hint="после"))
        self.assertEqual(dev, newdev)
        fk.assert_called_once()
        self.assertEqual([p[0] for p in self.pauses], ["Плата: DFU, пожалуйста", "после"])

    def test_enter_via_dfu_katapult_never_appears(self):
        self.dfu_present()
        with mock.patch.object(self.fl, "dfu_flash_katapult"):
            with self.assertRaises(FlashError):
                self.fl.enter_katapult(self.target())
        err = self.err.getvalue()
        self.assertIn("katapult ещё не появился", err)
        self.assertIn("так и не появился", err)
        self.assertIn("Устройства: ", self.out.getvalue())


class TestKlipperFlash(Base):
    def setUp(self):
        super().setUp()
        self.bin = self.tmp / "fw.bin"
        self.bin.write_bytes(b"B")
        p = mock.patch.object(self.fl, "build_fw_safe", return_value=str(self.bin))
        p.start()
        self.addCleanup(p.stop)

    def dev(self, name="usb-katapult_stm32h723xx_ABC123-if00"):
        return str(self.byid / name)

    def test_via_katapult_usb_ok(self):
        self.runner.on(("python3", "%s/scripts/flashtool.py" % self.env.katapult_dir), 0, "Flash Success\n")
        self.touch_byid("usb-Klipper_stm32h723xx_ABC123-if00")
        out = self.fl.flash_klipper_via_katapult(self.target(), self.dev())
        self.assertEqual(out, Outcome(serial="ABC123"))
        self.assertEqual(self.fl.flashed.get("ABC123"), "v0.12.0-1-gabc")      # журнал версий пополнен
        self.assertIn("Плата прошит (serial ABC123)", self.out.getvalue())
        self.assertTrue(self.runner.kwargs[-1]["tee"] if "tee" in self.runner.kwargs[-1] else True)

    def test_via_katapult_flashtool_failure_shows_reason_and_help(self):
        self.runner.on(("python3",), 1, "Traceback\nFlashError: block 3 failed\n")
        with self.assertRaises(FlashError):
            self.fl.flash_klipper_via_katapult(self.target(), self.dev())
        err = self.err.getvalue()
        self.assertIn("причина: FlashError: block 3 failed", err)
        self.assertIn("Прошивка Klipper на Плата не удалась. katapult остаётся в плате.", err)
        self.assertIn("flashtool.py -d %s -f %s" % (self.dev(), self.bin), err)

    def test_via_katapult_device_does_not_return(self):
        self.runner.on(("python3",), 0, "")
        with mock.patch.object(hardware, "wait_for_device", return_value=False):
            with self.assertRaises(FlashError):
                self.fl.flash_klipper_via_katapult(self.target(), self.dev())
        self.assertIn("после прошивки Плата не появился usb-Klipper_stm32h723xx_ABC123-if00", self.err.getvalue())

    def test_via_katapult_bridge(self):
        self.runner.on(("python3",), 0, "")
        with mock.patch.object(hardware, "bring_up_can", return_value=True):
            out = self.fl.flash_klipper_via_katapult(self.target(bridge=1), self.dev())
        self.assertEqual(out.serial, "ABC123")
        self.assertIn("мост USB-CAN работает, can0 поднят", self.out.getvalue())
        with mock.patch.object(hardware, "bring_up_can", return_value=False):
            with self.assertRaises(FlashError):
                self.fl.flash_klipper_via_katapult(self.target(bridge=1), self.dev())
        self.assertIn("не появился рабочий интерфейс can0", self.err.getvalue())

    def test_via_katapult_dry_run(self):
        self.runner.dry_run = True
        ui.set_options(dry_run=True)
        out = self.fl.flash_klipper_via_katapult(self.target(), self.dev())
        self.assertEqual(out.serial, "ABC123".replace("ABC123", "DRYRUN"))
        self.assertIn("[dry-run] сборка stm32h723xx.config, flashtool.py -d", self.out.getvalue())


class TestDfuKlipper(Base):
    """dfu_flash_klipper: katapult+Klipper за один сеанс либо только Klipper; USB, мост, только CAN."""

    def setUp(self):
        super().setUp()
        self.bin = self.tmp / "fw.bin"
        self.bin.write_bytes(b"B")
        self.kbin = self.tmp / "build" / "katapult-stm32h723xx" / "out" / "katapult.bin"
        self.kbin.parent.mkdir(parents=True)
        self.kbin.write_bytes(b"K")
        self.cfg = self.tmp / "stm32h723xx.config"
        self.cfg.write_text('CONFIG_MCU="stm32h723xx"\nCONFIG_FLASH_APPLICATION_ADDRESS=0x8020000\n')
        self.kcfg = self.tmp / "katapult" / "stm32h723xx.config"
        self.kcfg.parent.mkdir()
        self.kcfg.write_text("")
        for name, val in (("build_fw_safe", str(self.bin)), ("build_katapult_safe", str(self.kbin)),
                          ("wait_dfu", None)):
            p = mock.patch.object(self.fl, name, return_value=val)
            p.start()
            self.addCleanup(p.stop)
        self.dfu_calls = []
        self.dfu_results = []
        p2 = mock.patch.object(firmware, "dfu_run", side_effect=self._dfu)
        p2.start()
        self.addCleanup(p2.stop)
        self.runner.on(LSUSB, 0, "Bus 1 ID 0483:df11\n")

    def _dfu(self, runner, argv, sudo=False):
        self.dfu_calls.append(" ".join(argv))
        return self.dfu_results.pop(0) if self.dfu_results else True

    def t(self, **kw):
        d = dict(klipper_cfg=self.cfg, katapult_cfg=self.kcfg)
        d.update(kw)
        return self.target(**d)

    def test_usb_with_katapult(self):
        self.dfu_results = [True, True, True]

        def pause(msg, allow_skip=False):
            self.pauses.append((msg, allow_skip))
            if "нажмите RESET на" in msg:      # после «нажмите RESET» плата появляется в by-id
                (self.byid / H723.replace("AAA111", "NEWSER")).touch()
            return ""
        with mock.patch.object(ui, "pause_hw", side_effect=pause):
            out = self.fl.dfu_flash_klipper(self.t(), with_katapult=True)
        self.assertEqual(out, Outcome(serial="NEWSER"))
        self.assertEqual(self.dfu_calls, [
            "dfu-util -a 0 -s 0x08000000:mass-erase:force -D %s -d 0483:df11" % self.kbin,
            "dfu-util -a 0 -s 0x8020000:leave -D %s -d 0483:df11" % self.bin])
        self.assertEqual(self.fl.flashed.get("NEWSER"), "v0.12.0-1-gabc")
        self.assertIn("В один сеанс запишутся katapult (0x08000000) и Klipper (по адресу 0x8020000)", self.pauses[0][0])
        self.assertIn("прошит по DFU (serial NEWSER)", self.out.getvalue())

    def test_usb_klipper_only_message_and_no_katapult_write(self):
        self.touch_byid(H723)         # прежнее устройство в by-id не считается новым
        def pause(msg, allow_skip=False):
            self.pauses.append((msg, allow_skip))
            if "нажмите RESET на" in msg:
                (self.byid / "usb-Klipper_stm32h723xx_ZZZ-if00").touch()
            return ""
        with mock.patch.object(ui, "pause_hw", side_effect=pause):
            out = self.fl.dfu_flash_klipper(self.t(), with_katapult=False)
        self.assertEqual(out.serial, "ZZZ")                      # новое устройство, а не прежнее в by-id
        self.assertEqual(len(self.dfu_calls), 1)
        self.assertIn("Katapult в начале флеша не затрагивается", self.pauses[0][0])

    def test_make_mode_writes_without_mass_erase(self):
        self.dfu_results = [True, False]
        with self.assertRaises(FlashError):
            self.fl.dfu_flash_klipper(self.t(kat_mode="make"), with_katapult=True)
        self.assertEqual(self.dfu_calls[0], "dfu-util -a 0 -s 0x08000000 -D %s -d 0483:df11" % self.kbin)
        self.assertIn("Klipper не записан по DFU", self.err.getvalue())

    def test_guide_mass_erase_fallback_and_failures(self):
        self.dfu_results = [False, True, True]
        with mock.patch.object(ui, "pause_hw", return_value=""), \
                mock.patch.object(hardware, "bring_up_can", return_value=True):
            self.fl.dfu_flash_klipper(self.t(bridge=1), with_katapult=True)
        self.assertEqual(self.dfu_calls[1], "dfu-util -a 0 -s 0x08000000 -D %s -d 0483:df11" % self.kbin)
        self.dfu_calls.clear()
        self.dfu_results = [False]
        self.runner.rules.insert(0, (lambda a: tuple(a[:3]) == LSUSB, 1, ""))     # плата вышла из DFU
        with self.assertRaises(FlashError):
            self.fl.dfu_flash_klipper(self.t(), with_katapult=True)
        self.assertIn("katapult не записан по DFU", self.err.getvalue())

    def test_left_dfu_after_katapult(self):
        self.runner.rules.insert(0, (lambda a: tuple(a[:3]) == LSUSB, 1, ""))      # после записи DFU-устройства нет
        with self.assertRaises(FlashError):
            self.fl.dfu_flash_klipper(self.t(), with_katapult=True)
        self.assertIn("после записи katapult плата вышла из DFU", self.err.getvalue())

    def test_bridge_mode_brings_up_can(self):
        with mock.patch.object(hardware, "bring_up_can", return_value=False):
            with self.assertRaises(FlashError):
                self.fl.dfu_flash_klipper(self.t(bridge=1), with_katapult=False)
        self.assertIn("после прошивки моста не появился рабочий интерфейс can0", self.err.getvalue())

    def test_head_only_can_returns_uuid(self):
        with mock.patch.object(hardware, "dfu_read_uid", return_value="aabbccddeeff"):
            out = self.fl.dfu_flash_klipper(self.t(bridge=2, family="g"), with_katapult=True)
        self.assertEqual(out, Outcome(uuid="aabbccddeeff"))
        self.assertIn("canbus_uuid по UID чипа: aabbccddeeff", self.out.getvalue())
        self.assertIn("отключите USB от Плата", self.pauses[-1][0])
        with mock.patch.object(hardware, "dfu_read_uid", return_value=""):
            out = self.fl.dfu_flash_klipper(self.t(bridge=2, family="g"), with_katapult=True)
        self.assertEqual(out.uuid, "")
        self.assertIn("UID чипа прочитать не удалось", self.err.getvalue())

    def test_missing_app_address(self):
        self.cfg.write_text('CONFIG_MCU="x"\n')
        with self.assertRaises(FlashError):
            self.fl.dfu_flash_klipper(self.t(), with_katapult=True)
        self.assertIn("нет CONFIG_FLASH_APPLICATION_ADDRESS", self.err.getvalue())

    def test_dry_run_texts(self):
        self.runner.dry_run = True
        ui.set_options(dry_run=True)
        out = self.fl.dfu_flash_klipper(self.t(bridge=2, family="g"), with_katapult=True)
        self.assertEqual(out, Outcome(serial="DRYRUN", uuid="000000000000"))
        text = self.out.getvalue()
        self.assertIn("[dry-run] dfu-util -a 0 -s 0x08000000:mass-erase:force -D stm32h723xx/katapult.bin", text)
        self.assertIn("[dry-run] dfu-util -U UID (0x1FFF7590) -> canbus_uuid", text)
        self.assertEqual(self.dfu_calls, [])


class TestMenuAndRetry(Base):
    def test_menu_mapping_and_no_tty(self):
        table = [(flashing.MENU_RETRY, "retry"), (flashing.MENU_DFU_ALL, "dfuall"), (flashing.MENU_DFU, "dfu"),
                 (flashing.MENU_DFU_K, "dfuk"), (flashing.MENU_SKIP, "skip"), (flashing.MENU_ABORT, "abort")]
        with mock.patch.object(ui, "have_tty", return_value=True):
            for ans, want in table:
                with mock.patch.object(ui, "ask_choice", return_value=ans) as ac:
                    self.assertEqual(flash_menu("Плата"), want)
                self.assertEqual(ac.call_args[0][0], "Плата: прошивка не удалась. Что делать?")
                self.assertEqual(len(ac.call_args[0][2]), 6)
            heads = [(flashing.MENU_RETRY, "retry"), (flashing.MENU_DFU_K_HEADS, "dfuk"), (flashing.MENU_SKIP, "skip"),
                     (flashing.MENU_ABORT, "abort")]
            for ans, want in heads:
                with mock.patch.object(ui, "ask_choice", return_value=ans) as ac:
                    self.assertEqual(flash_menu("Голова", "headsdfu"), want)
                self.assertEqual(len(ac.call_args[0][2]), 4)
            ui.set_options(yes=True)
            self.assertEqual(flash_menu("Плата"), "skip")                      # -y: без вопросов
        ui.set_options(yes=False)
        with mock.patch.object(ui, "have_tty", return_value=False):
            self.assertEqual(flash_menu("Плата"), "skip")                      # нет терминала

    def job(self, outcomes, start="full", menu="std"):
        """Задание со скриптованными попытками: исключение -> FlashError, иначе Outcome. Фазы пишутся в self.phases."""
        self.phases = []
        self.committed = []
        outcomes = list(outcomes)

        class S(flashing.Strategy):
            def run(s, fl, job):
                self.phases.append(job.phase)
                job.retry_phase = "klipper" if job.phase == "full" else job.phase
                r = outcomes.pop(0)
                if r == "fail":
                    raise FlashError()
                return Outcome(serial=r)
        j = FlashJob("Плата", None, start, lambda phase: S(), lambda o: self.committed.append(o.serial), menu=menu)
        return j

    def menu(self, *answers):
        return mock.patch.object(flashing, "flash_menu", side_effect=list(answers))

    def test_success_first_try_saves_devices(self):
        self.hw.mode = "usb"
        self.res.mcu.main_serial = "S1"
        j = self.job(["S1"])
        self.assertTrue(flash_with_retry(self.fl, j))
        self.assertEqual(self.committed, ["S1"])
        self.assertEqual((self.tmp / "devices.tsv").read_text(), "S1\tstm32h723xx.config\tusb\n")

    def test_retry_uses_retry_phase_then_succeeds(self):
        j = self.job(["fail", "fail", "ok"])
        with self.menu("retry", "retry"):
            self.assertTrue(flash_with_retry(self.fl, j))
        self.assertEqual(self.phases, ["full", "klipper", "klipper"])
        self.assertIn("Плата: прошивка не удалась", self.err.getvalue())

    def test_menu_dfu_dfuall_dfuk_set_phase(self):
        j = self.job(["fail", "fail", "fail", "ok"])
        with self.menu("dfu", "dfuall", "dfuk"):
            self.assertTrue(flash_with_retry(self.fl, j))
        self.assertEqual(self.phases, ["full", "full", "dfuall", "dfuk"])

    def test_start_phase_dfuall(self):
        j = self.job(["ok"], start="dfuall")
        flash_with_retry(self.fl, j)
        self.assertEqual(self.phases, ["dfuall"])

    def test_skip_records_failure_and_continues(self):
        j = self.job(["fail"])
        with self.menu("skip"):
            self.assertFalse(flash_with_retry(self.fl, j))
        self.assertEqual(self.res.failed, ["Плата: не прошита"])
        self.assertIn("Плата пропущена, продолжаю с остальными платами", self.err.getvalue())
        self.assertEqual(self.committed, [])

    def test_abort(self):
        j = self.job(["fail"])
        with self.menu("abort"):
            with self.assertRaises(UserAbort) as cm:
                flash_with_retry(self.fl, j)
        self.assertEqual(str(cm.exception), "установка прервана пользователем (Плата)")

    def test_no_tty_or_yes_skips_after_failure(self):
        j = self.job(["fail"])
        with mock.patch.object(ui, "have_tty", return_value=False):
            self.assertFalse(flash_with_retry(self.fl, j))
        self.assertEqual(self.res.failed, ["Плата: не прошита"])

    def test_flasherror_message_is_warned(self):
        class S(flashing.Strategy):
            def run(s, fl, job):
                raise FlashError("причина-1")
        j = FlashJob("Плата", None, "full", lambda p: S(), lambda o: None)
        with self.menu("skip"):
            flash_with_retry(self.fl, j)
        self.assertIn("ВНИМАНИЕ: причина-1", self.err.getvalue())

    def test_katapult_then_klipper_reuses_device_on_retry(self):
        """Плата уже в katapult, flashtool не прошёл: повтор («retry») идёт с фазы klipper, DFU заново не делается."""
        dev = self.byid / "usb-katapult_stm32h723xx_ABC-if00"
        dev.touch()
        t = self.target = Target(label="Плата", chip="stm32h723xx", family="h7", klipper_cfg=Path("a"))
        calls = {"enter": 0, "flash": 0}

        def enter(tt):
            calls["enter"] += 1
            return str(dev)

        def flash(tt, d):
            calls["flash"] += 1
            if calls["flash"] == 1:
                raise FlashError()
            return Outcome(serial="ABC")
        j = FlashJob("Плата", t, "full", lambda p: KatapultThenKlipper(), lambda o: self.committed.append(o.serial))
        self.committed = []
        with mock.patch.object(self.fl, "enter_katapult", side_effect=enter), \
                mock.patch.object(self.fl, "flash_klipper_via_katapult", side_effect=flash), self.menu("retry"):
            self.assertTrue(flash_with_retry(self.fl, j))
        self.assertEqual(calls, {"enter": 1, "flash": 2})
        self.assertEqual(self.committed, ["ABC"])
        # катапульт-устройство пропало: повтор с фазы klipper возвращается к full
        dev.unlink()
        calls.update(enter=0, flash=0)
        j = FlashJob("Плата", t, "full", lambda p: KatapultThenKlipper(), lambda o: None)
        with mock.patch.object(self.fl, "enter_katapult", side_effect=enter), \
                mock.patch.object(self.fl, "flash_klipper_via_katapult", side_effect=flash), self.menu("retry"):
            flash_with_retry(self.fl, j)
        self.assertEqual(calls["enter"], 2)

    def test_dfu_strategies_set_retry_phase(self):
        t = Target(label="П", chip="c", family="f0", klipper_cfg=Path("a"))
        j = FlashJob("П", t, "dfuall", lambda p: DfuAll(), lambda o: None)
        with mock.patch.object(self.fl, "dfu_flash_klipper", return_value=Outcome(serial="x")) as d:
            DfuAll().run(self.fl, j)
            self.assertEqual((j.retry_phase, d.call_args[1]), ("dfuall", {"with_katapult": True}))
            DfuKlipperOnly().run(self.fl, j)
            self.assertEqual((j.retry_phase, d.call_args[1]), ("dfuk", {"with_katapult": False}))


class TestDevicesAndBridge(Base):
    def test_save_devices_bridge_mode_and_quiet_merge(self):
        hw = self.make_hw(heads="v2", alps=2)
        self.fl.hw = hw
        m = self.res.mcu
        m.bridge_uuid, m.head_uuid, m.alps_serial = "b" * 12, ["1" * 12, ""], ["S1", "S2"]
        self.res.prev_devices = [Device("old", "x.config", "usb"), Device("1" * 12, "dup", "can")]
        self.fl.save_devices(quiet=True)
        text = (self.tmp / "devices.tsv").read_text()
        self.assertEqual(text.splitlines(), [
            "%s\tstm32h723xx-canbridge.config\tbridge" % ("b" * 12), "%s\tstm32g431xx-can.config\tcan" % ("1" * 12),
            "S1\tstm32f072xb.config\tusb", "S2\tstm32f072xb.config\tusb", "old\tx.config\tusb"])
        self.assertEqual(self.out.getvalue(), "")
        self.fl.save_devices()                                   # не quiet: прошлые строки не добавляются, файл выводится
        self.assertNotIn("old", (self.tmp / "devices.tsv").read_text())
        self.assertIn("S2\tstm32f072xb.config\tusb", self.out.getvalue())

    def test_save_devices_dry_run_prints_only(self):
        self.runner.dry_run = True
        ui.set_options(dry_run=True)
        self.res.mcu.main_serial = "S"
        self.fl.save_devices()
        self.assertIn("[dry-run] записал бы:\nS\tstm32h723xx.config\tusb", self.out.getvalue())
        self.assertFalse((self.tmp / "devices.tsv").exists())
        self.out.truncate(0)
        self.out.seek(0)
        self.fl.save_devices(quiet=True)
        self.assertEqual(self.out.getvalue(), "")

    def test_set_bridge_uuid(self):
        hw = self.make_hw(heads="v2")
        self.fl.hw = hw
        with mock.patch.object(hardware, "bridge_usb_serial", return_value="0123456789ABCDEF01234567"):
            self.fl.set_bridge_uuid()
        self.assertEqual(len(self.res.mcu.bridge_uuid), 12)
        self.assertEqual(self.fl.flashed.get(self.res.mcu.bridge_uuid), "v0.12.0-1-gabc")
        self.res.mcu.bridge_uuid = ""
        with mock.patch.object(hardware, "bridge_usb_serial", return_value=""):
            self.fl.set_bridge_uuid()
        self.assertEqual(self.res.mcu.bridge_uuid, "")
        self.assertIn("canbus_uuid моста вычислить не удалось", self.err.getvalue())
        self.runner.dry_run = True
        self.fl.set_bridge_uuid()
        self.assertEqual(self.res.mcu.bridge_uuid, "000000000000")
        self.fl.hw = self.make_hw()                              # режим usb - ничего не делает
        self.res.mcu.bridge_uuid = ""
        self.fl.set_bridge_uuid()
        self.assertEqual(self.res.mcu.bridge_uuid, "")

    def test_state_set_dry_run_writes_nothing(self):
        """dry-run: журнал прошивок flashed.tsv не создаётся и не меняется."""
        path = Path(self.env.cfg.state_file)
        self.runner.dry_run = True
        self.fl.state_set("000000000000")
        self.assertFalse(path.exists())
        self.runner.dry_run = False
        self.fl.state_set("REAL")
        before = path.read_text(encoding="utf-8")
        self.runner.dry_run = True
        self.fl.state_set("000000000000")
        self.fl.state_set("REAL", "other")
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_version_ok(self):
        self.fl.flashed.set("K", "v0.12.0-1-gabc-dirty")
        self.assertTrue(self.fl.version_ok("K"))                 # -dirty и «*» не мешают
        self.fl.flashed.set("K", "v0.11.0-0-gold")
        self.assertFalse(self.fl.version_ok("K"))
        self.assertFalse(self.fl.version_ok("none"))


class TestCanKlipper(Base):
    def setUp(self):
        super().setUp()
        self.fl.hw = self.make_hw(heads="v2")
        self.hw = self.fl.hw
        self.job = flashing.make_head_klipper_job(self.fl, 0)
        self.job.phase = "full"
        self.cfg_bin = self.tmp / "h.bin"
        self.cfg_bin.write_bytes(b"1")
        p = mock.patch.object(self.fl, "build_fw_safe", return_value=str(self.cfg_bin))
        p.start()
        self.addCleanup(p.stop)
        self.flash_ok = mock.patch.object(firmware, "flash_can_node", return_value=True)
        self.flash_mock = self.flash_ok.start()
        self.addCleanup(self.flash_ok.stop)

    def uuids(self, **by_app):
        return mock.patch.object(self.fl, "can_uuids", side_effect=lambda app: list(by_app.get(app, [])))

    def test_katapult_path_flashes_and_records(self):
        with self.uuids(Katapult=["aabbccddeeff"], Klipper=["AABBCCDDEEFF"]):
            out = flashing.CanKlipper().run(self.fl, self.job)
        self.assertEqual(out.uuid, "aabbccddeeff")
        self.assertEqual(self.res.mcu.head_uuid[0], "aabbccddeeff")
        self.assertEqual(self.flash_mock.call_args[0][1:4], ("can0", "aabbccddeeff", str(self.cfg_bin)))
        self.assertIn("aabbccddeeff, Application: Klipper", self.out.getvalue())

    def test_no_or_many_katapult_boards(self):
        with self.uuids(Katapult=[]):
            with self.assertRaises(FlashError):
                flashing.CanKlipper().run(self.fl, self.job)
        self.assertIn("плата katapult по CAN не найдена", self.err.getvalue())
        with self.uuids(Katapult=["a" * 12, "b" * 12]):
            with self.assertRaises(FlashError):
                flashing.CanKlipper().run(self.fl, self.job)
        self.assertIn("ожидалась одна плата в katapult на CAN, найдено: 2", self.err.getvalue())

    def test_flash_failure_and_no_klipper_answer(self):
        self.flash_mock.return_value = False
        with self.uuids(Katapult=["a" * 12]):
            with self.assertRaises(FlashError):
                flashing.CanKlipper().run(self.fl, self.job)
        self.assertIn("прошивка Fysetc H36 v2 левая (T0CB) (aaaaaaaaaaaa) не удалась", self.err.getvalue())
        self.flash_mock.return_value = True
        with self.uuids(Katapult=["a" * 12], Klipper=[]):
            flashing.CanKlipper().run(self.fl, self.job)
        self.assertIn("не отвечает как Klipper", self.err.getvalue())               # предупреждение, но не отказ

    def test_dfuall_phase_then_new_board_on_bus_excluding_bridge(self):
        self.res.mcu.bridge_uuid = "BRIDGE000000"
        self.job.phase = "dfuall"
        with mock.patch.object(self.fl, "head_dfu_all", side_effect=lambda i: self.res.head_dfu_done.__setitem__(i, True)), \
                self.uuids(Klipper=["bridge000000", "112233445566"]):
            out = flashing.CanKlipper().run(self.fl, self.job)
        self.assertEqual(self.job.retry_phase, "dfuall")
        self.assertEqual(out.uuid, "112233445566")
        self.assertTrue(self.pauses[0][0].startswith("Подключите USB-кабелем ТОЛЬКО"))
        with mock.patch.object(self.fl, "head_dfu_all"), self.uuids(Klipper=["bridge000000"]):
            self.res.head_dfu_done[0] = True
            with self.assertRaises(FlashError):
                flashing.CanKlipper().run(self.fl, self.job)
        self.assertIn("ожидалась одна новая плата с Klipper на CAN (кроме моста), найдено: 0", self.err.getvalue())


class TestMainDfuTexts(Base):
    def test_octopus_standard_and_button_boards(self):
        hw = self.make_hw("octopus-pro-h723")
        self.assertTrue(flashing.main_dfu_std(hw))
        self.assertEqual(flashing.main_dfu_short(hw), "джампер BOOT0")
        self.assertEqual(flashing.main_dfu_mode_text(hw), "установите джампер на BOOT0, нажмите RESET (кнопка на плате)")
        self.assertEqual(flashing.main_dfu_klipper_how(hw), flashing.DEFAULT_DFU_HOW)
        self.assertTrue(flashing.main_dfu_after_text(hw).startswith("Снимите джампер BOOT0 с Octopus Pro v1.1 H723"))
        for bid in ("fly-c8", "manta-m8p-v1.1", "spider-v3-h723"):
            hw = self.make_hw(bid)
            b = hw.board
            self.assertFalse(flashing.main_dfu_std(hw), bid)
            self.assertEqual(flashing.main_dfu_enter_text(hw), b.field("DFU_HINT"))
            self.assertEqual(flashing.main_dfu_klipper_how(hw), b.field("DFU_HINT"))
            self.assertIn("ДВАЖДЫ быстро нажмите RESET на " + b.label, flashing.main_dfu_after_text(hw))
            self.assertEqual(flashing.main_dfu_short(hw), "джампер или перемычка BOOT, затем RESET"
                             if b.field("DFU_HOW") == "jumper" else "кнопки BOOT и RESET")


if __name__ == "__main__":
    unittest.main()
