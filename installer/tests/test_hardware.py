"""Тесты vostok.hardware: by-id, DFU (lsusb/dfu-util), UID чипа, мост USB-CAN, шина CAN, ядро."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from vostok import hardware, ui  # noqa: E402
from vostok.boards import Registry  # noqa: E402
from vostok.system import Runner  # noqa: E402

INSTALLER = Path(os.path.dirname(HERE))
REG = Registry(INSTALLER / "boards")


class FakeRunner:
    """Заглушка Runner: отвечает по таблице {argv-кортеж: (код, stdout)}; пишет вызовы."""
    dry_run = False

    def __init__(self, answers=None, dry_run=False):
        self.answers, self.calls, self.dry_run = answers or {}, [], dry_run

    def run(self, cmd, **kw):
        argv = list(cmd)
        if kw.get("sudo"):
            argv = ["sudo"] + argv
        self.calls.append((tuple(argv), kw))
        rc, out = self.answers.get(tuple(argv), (1, ""))
        if kw.get("stdout_file") is not None and out:
            Path(kw["stdout_file"]).write_text(out, encoding="utf-8")
        return subprocess.CompletedProcess(argv, rc, out, "")


def capture(fn, *a, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        res = fn(*a, **kw)
    return res, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp = Path(self.tmpdir.name)
        saved = (ui.opts.yes, ui.opts.dry_run, ui.opts.log_file)
        self.addCleanup(lambda: setattr(ui, "opts", ui.opts) or ui.set_options(*saved))
        ui.set_options(yes=True, dry_run=False, log_file=None)


class TestProbes(Base):
    def test_byid_find_sorted_and_skips_broken_links(self):
        for n in ("usb-b_stm32f072xb_2-if00", "usb-a_stm32f072xb_1-if00"):
            (self.tmp / n).touch()
        os.symlink("/nonexistent", self.tmp / "usb-c_stm32f072xb_3-if00")
        found = hardware.byid_find(self.tmp, "usb-*stm32f072xb_*")
        self.assertEqual([os.path.basename(f) for f in found], ["usb-a_stm32f072xb_1-if00", "usb-b_stm32f072xb_2-if00"])
        self.assertEqual(hardware.byid_find(self.tmp / "nope", "*"), [])

    def test_serial_from_path(self):
        self.assertEqual(hardware.serial_from_path("/dev/serial/by-id/usb-Klipper_stm32h723xx_ABC123-if00"), "ABC123")
        self.assertEqual(hardware.serial_from_path("usb-Other_x_1-if00"), "")

    def test_dfu_count_and_family(self):
        r = FakeRunner({("lsusb", "-d", "0483:df11"): (0, "Bus 1 ID 0483:df11\nBus 1 ID 0483:df11\n")})
        self.assertEqual(hardware.dfu_count(r), 2)
        for text, fam in (("@Option Bytes /0x1FFFF800/", "f0"), ("0x1fffc000", "f4"), ("x 0x5200201C", "h7"),
                          ("0x1FFF7800", "g"), ("", "unknown")):
            r = FakeRunner({("sudo", "-n", "dfu-util", "-l"): (0, text)})
            self.assertEqual(hardware.dfu_family(r), fam, text)
        r = FakeRunner({("dfu-util", "-l"): (0, "0x1FFFC000")})
        self.assertEqual(hardware.dfu_family(r), "f4")

    def test_queries_run_readonly_and_quiet(self):
        r = FakeRunner()
        hardware.dfu_count(r)
        kw = r.calls[0][1]
        self.assertTrue(kw["readonly"] and kw["quiet"])

    def test_family_name_and_uid_addr(self):
        self.assertEqual(hardware.family_name(REG, "zz"), "не определён")
        self.assertTrue(hardware.family_name(REG, "h7").startswith("STM32H7 ("))
        self.assertIn("Octopus Pro v1.1 H723", hardware.family_name(REG, "h7"))
        self.assertEqual([hardware.uid_addr(f) for f in ("f0", "f4", "h7", "g", "x")],
                         ["0x1FFFF7AC", "0x1FFF7A10", "0x1FF1E800", "0x1FFF7590", ""])

    def test_show_usb_state(self):
        r = FakeRunner({("lsusb", "-d", "0483:df11"): (0, "x\n"), ("lsusb", "-d", "1d50:606f"): (0, "Bus"),
                        ("ip", "-br", "link", "show", "can0"): (0, "can0  UP  <NOARP,UP>\n")})
        _, out = capture(hardware.show_usb_state, r, "can0")
        self.assertIn("Устройства в /dev/serial/by-id:", out)
        self.assertIn("Устройств в режиме DFU (0483:df11): 1", out)
        self.assertIn("Найден мост USB-CAN Klipper (1d50:606f); интерфейс can0: UP", out)
        _, out = capture(hardware.show_usb_state, FakeRunner(), "can0")
        self.assertNotIn("мост", out)


class TestUid(Base):
    def test_dfu_read_uid(self):
        # настоящий UID из tests/test_can_uuid: 12 байт -> canbus_uuid
        uid = bytes(range(1, 13))

        class R(FakeRunner):
            def run(self, cmd, **kw):
                self.calls.append((tuple(cmd), kw))
                argv = list(cmd)
                Path(argv[argv.index("-U") + 1]).write_bytes(uid)
                return subprocess.CompletedProcess(cmd, 0, "", "")

        from vostok import can_uuid
        r = R()
        self.assertEqual(hardware.dfu_read_uid(r, "h7"), can_uuid.can_uuid(uid))
        argv, kw = r.calls[0]
        self.assertIn("0x1FF1E800:12:force", argv)
        self.assertTrue(kw["sudo"])
        self.assertEqual(hardware.dfu_read_uid(r, "zz"), "")

    def test_dfu_read_uid_failures_and_dry_run(self):
        self.assertEqual(hardware.dfu_read_uid(FakeRunner({}), "f4"), "")       # dfu-util не удался
        _, out = capture(lambda: hardware.dfu_read_uid(FakeRunner(dry_run=True), "g"))
        self.assertIn("[dry-run] dfu-util -U UID (0x1FFF7590) -> canbus_uuid", out)
        res, _ = capture(hardware.dfu_read_uid, FakeRunner(dry_run=True), "g")
        self.assertEqual(res, "000000000000")

        class R(FakeRunner):
            def run(self, cmd, **kw):
                argv = list(cmd)
                Path(argv[argv.index("-U") + 1]).write_bytes(b"\xff" * 12)    # чтение не удалось
                return subprocess.CompletedProcess(cmd, 0, "", "")
        self.assertEqual(hardware.dfu_read_uid(R(), "f4"), "")

    def test_bridge_usb_serial(self):
        for name, vid, pid, ser in (("1-1", "1d50", "606e", "WRONG"), ("1-2", "1d50", "606f", "0123456789ABCDEF01234567")):
            d = self.tmp / name
            d.mkdir()
            (d / "idVendor").write_text(vid + "\n")
            (d / "idProduct").write_text(pid + "\n")
            (d / "serial").write_text(ser + "\n")
        self.assertEqual(hardware.bridge_usb_serial(str(self.tmp)), "0123456789ABCDEF01234567")
        self.assertEqual(hardware.bridge_usb_serial(str(self.tmp / "none")), "")


class TestCan(Base):
    def test_kernel_can_support(self):
        cfg = self.tmp / "k"
        cfg.write_text("CONFIG_CAN=y\nCONFIG_CAN_RAW=m\nCONFIG_CAN_GS_USB=m\n")
        self.assertEqual(hardware.kernel_can_support(str(cfg)), 0)
        cfg.write_text("CONFIG_CAN=y\nCONFIG_CAN_RAW=m\n# CONFIG_CAN_GS_USB is not set\n")
        self.assertEqual(hardware.kernel_can_support(str(cfg)), 1)
        # конфига нет, модулей нет - неизвестно
        with mock.patch.object(hardware.os, "access", return_value=False), \
                mock.patch.object(hardware.os.path, "isdir", return_value=False), \
                mock.patch.object(hardware.glob, "glob", return_value=[]):
            self.assertEqual(hardware.kernel_can_support(""), 2)
            with mock.patch.object(hardware.glob, "glob", return_value=["/lib/modules/x/gs_usb.ko"]):
                self.assertEqual(hardware.kernel_can_support(""), 0)

    def test_can_uuids_parse(self):
        kat = ("python3", "/k/scripts/flashtool.py", "-i", "can0", "-q")
        kl = ("/e/bin/python", "/kl/scripts/canbus_query.py", "can0")
        r = FakeRunner({
            kat: (0, "Detected UUID: aabbccddeeff, Application: Katapult\nDetected UUID: 112233445566, Application: Klipper\n"),
            kl: (0, "Found canbus_uuid=0123456789ab, Application: Klipper\nFound canbus_uuid=ffffffffffff, Application: Katapult\n"),
        })
        kw = dict(katapult_dir="/k", klippy_env="/e", klipper_dir="/kl", iface="can0")
        self.assertEqual(hardware.can_uuids(r, "Katapult", **kw), ["aabbccddeeff"])
        self.assertEqual(hardware.can_uuids(r, "Klipper", **kw), ["0123456789ab"])
        self.assertTrue(r.calls[0][1]["readonly"])
        self.assertEqual(hardware.can_uuids(FakeRunner(), "Klipper", **kw), [])

    def test_bring_up_can(self):
        ip_show = ("ip", "link", "show", "can0")
        r = FakeRunner({ip_show: (0, "3: can0: <NOARP,UP> state UP"),
                        ("sudo", "ip", "link", "set", "can0", "txqueuelen", "128"): (0, "")})
        self.assertTrue(hardware.bring_up_can(r, "can0"))
        self.assertNotIn(("sudo", "ip", "link", "set", "can0", "up", "type", "can", "bitrate", "1000000"),
                         [c[0] for c in r.calls])           # уже поднят: только txqueuelen
        # интерфейс есть, но не UP: поднимаем; ip link up не удался - False
        state = {"up": False}

        class R(FakeRunner):
            def run(self, cmd, **kw):
                argv = (["sudo"] if kw.get("sudo") else []) + list(cmd)
                self.calls.append((tuple(argv), kw))
                if argv[:4] == ["ip", "link", "show", "can0"]:
                    return subprocess.CompletedProcess(argv, 0, "can0: state %s" % ("UP" if state["up"] else "DOWN"), "")
                if "bitrate" in argv:
                    state["up"] = True
                return subprocess.CompletedProcess(argv, 0, "", "")
        r = R()
        self.assertTrue(hardware.bring_up_can(r, "can0"))
        self.assertIn(("sudo", "ip", "link", "set", "can0", "up", "type", "can", "bitrate", "1000000"), [c[0] for c in r.calls])
        with mock.patch.object(hardware.time, "sleep"):
            self.assertFalse(hardware.bring_up_can(FakeRunner(), "can0"))     # интерфейса нет

    def test_check_can_health(self):
        r = FakeRunner({("ip", "-s", "-d", "link", "show", "can0"): (0, "1: can0: state ERROR-ACTIVE\n2\n3\n4\n")})
        res, out = capture(hardware.check_can_health, r, "can0")
        self.assertTrue(res)
        self.assertEqual(out, "1: can0: state ERROR-ACTIVE\n2\n3\n")
        r = FakeRunner({("ip", "-s", "-d", "link", "show", "can0"): (0, "can0: state BUS-OFF\n")})
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertFalse(hardware.check_can_health(r, "can0"))
        self.assertIn("CAN в состоянии BUS-OFF", err.getvalue())


class TestRealRunner(Base):
    def test_run_quiet_hides_stderr_and_missing_command(self):
        rc, out = hardware.run_quiet(["sh", "-c", "echo out; echo err >&2; exit 4"])
        self.assertEqual((rc, out), (4, "out\n"))
        self.assertEqual(hardware.run_quiet(["no-such-cmd-xyz"])[0], 127)
        # dry-run: запрос всё равно выполняется
        self.assertEqual(hardware.run_quiet(["echo", "x"], Runner(dry_run=True)), (0, "x\n"))

    def test_ifup_only_prints_in_dry_run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hardware.ifup("can0", Runner(dry_run=True))
        self.assertEqual(out.getvalue(), "[dry-run] sudo -n ifup can0\n")


if __name__ == "__main__":
    unittest.main()
