"""Тесты vostok.update / firmware / hardware: режимы update_klipper_mcu.sh без реальной прошивки.

Всё в временных каталогах; sudo, systemctl и flashtool не вызываются (подменены), ~/printer_data не трогается.
"""
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.dirname(HERE)
sys.path.insert(0, INSTALLER)

from vostok import VostokError, firmware, hardware, system, ui, update  # noqa: E402
from vostok.state import FlashedLog  # noqa: E402

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL=os.devnull)


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd)] + list(args), env=GIT_ENV, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout.strip()


def capture():
    """(stdout, stderr) как StringIO-ы для contextlib."""
    return io.StringIO(), io.StringIO()


class FakeMoon:
    """Подмена update.Moonraker: готовые ответы."""

    def __init__(self, ok=True, sections=(), versions=None, print_state="standby", info=None):
        self.ok = ok
        self.sections = list(sections)
        self.versions = versions or {}
        self._print_state = print_state
        self.info = info or [{"state": "ready"}]
        self.calls = 0

    def fetch(self, path):
        return "{}" if self.ok else None

    def mcu_sections(self):
        return list(self.sections) if self.ok else []

    def mcu_versions(self, names):
        return dict(self.versions)

    def print_state(self):
        return self._print_state

    def printer_info(self, key):
        d = self.info[min(self.calls, len(self.info) - 1)]
        if key == "state":
            self.calls += 1
        return d.get(key, "")


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        ui.set_options(False, False, None)
        self.addCleanup(ui.set_options, False, False, None)
        self.byid = self.d / "byid"
        self.byid.mkdir()
        self.cfg = update.Config.from_env({
            "HOME": str(self.d / "home"), "BYID_DIR": str(self.byid), "KLIPPER_DIR": str(self.d / "klipper"),
            "PRINTER_DATA": str(self.d / "pd"), "FIRMWARE_DIR": str(self.d / "fw"), "BUILD_DIR": str(self.d / "build"),
            "DEVICES_FILE": str(self.d / "devices.tsv"), "KATAPULT_DIR": str(self.d / "katapult"),
            "KLIPPY_ENV": str(self.d / "env"), "KIAUH_DIR": str(self.d / "kiauh"),
            "CONFIGS_DIR": os.path.join(INSTALLER, "configs"), "BOARDS_DIR": os.path.join(INSTALLER, "boards")})
        patcher = mock.patch.object(update.time, "sleep", lambda s: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(hardware.time, "sleep", lambda s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def touch(self, name):
        p = self.byid / name
        p.write_text("")
        return str(p)

    def updater(self, moon=None, **opts):
        return update.Updater(self.cfg, update.Options(**opts), moon=moon or FakeMoon())


class ParseArgsTest(unittest.TestCase):
    def parse(self, args, tty=True):
        with mock.patch.object(update.sys, "stdin") as stdin:
            stdin.isatty.return_value = tty
            return update.parse_args(args)

    def test_flags(self):
        o = self.parse(["--list", "--no-update", "--no-flash", "--force-flash", "--ignore-moonraker", "-y"])
        self.assertTrue(o.list_only and o.force_flash and o.ignore_moonraker and o.assume_yes)
        self.assertFalse(o.do_update or o.do_flash or o.git_update)
        self.assertTrue(self.parse(["--git-update"]).git_update)

    def test_git_update_without_tty(self):
        self.assertTrue(self.parse([], tty=False).git_update)
        self.assertFalse(self.parse([], tty=True).git_update)

    def test_help_and_version(self):
        out, err = capture()
        with contextlib.redirect_stdout(out):
            self.assertIsNone(self.parse(["-h"]))
        self.assertEqual(out.getvalue(), update.USAGE)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertIsNone(self.parse(["--version"]))
        self.assertTrue(out.getvalue().startswith("VOSTOK installer "))

    def test_unknown_option(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(VostokError) as cm:
                self.parse(["--bogus"])
        self.assertEqual(str(cm.exception), "неизвестная опция: --bogus")
        self.assertEqual(err.getvalue(), update.USAGE)


class HelpersTest(unittest.TestCase):
    def test_norm_version(self):
        n = firmware.norm_version
        self.assertEqual(n("v0.12.0-1-gabc"), "v0.12.0-1-gabc")
        self.assertEqual(n("v0.12.0-1-gabc-dirty*"), "v0.12.0-1-gabc")
        self.assertEqual(n("?"), "?")

    def test_pad_by_bytes(self):
        # printf %-Ns в bash считает байты UTF-8
        self.assertEqual(update._pad("абв", 10), "абв" + " " * 4)
        self.assertEqual(update._pad("(не в printer.cfg)", 20), "(не в printer.cfg)")
        self.assertEqual(update._pad("mcu", 5), "mcu  ")

    def test_by_id(self):
        p = "/dev/serial/by-id/usb-Klipper_stm32h723xx_120026000A51333231343036-if00"
        self.assertEqual(hardware.by_id_chip(p), "stm32h723xx")
        self.assertEqual(hardware.by_id_serial(p), "120026000A51333231343036")
        self.assertEqual(hardware.by_id_chip("/x/usb-katapult_stm32f072xb_A-if00"), "")
        self.assertEqual(hardware.by_id_chip("usb-Klipper_a_b_c-if01"), "a_b")


class MoonrakerTest(unittest.TestCase):
    """Moonraker через urllib: настоящий HTTP-сервер на 127.0.0.1."""

    @classmethod
    def setUpClass(cls):
        routes = {
            "/server/info": {"result": {}},
            "/printer/objects/query?configfile=settings": {"result": {"status": {"configfile": {"settings": {
                "mcu": {"serial": "/dev/x", "canbus_uuid": None}, "mcu T0CB": {"canbus_uuid": "abc"},
                "printer": {"kinematics": "x"}, "mcu_extra": {"serial": "no"}}}}}},
            "/printer/objects/query?mcu&mcu%20T0CB": {"result": {"status": {"mcu": {"mcu_version": "v1"},
                                                                          "mcu T0CB": {"x": 1}}}},
            "/printer/objects/query?print_stats": {"result": {"status": {"print_stats": {"state": "paused"}}}},
            "/printer/info": {"result": {"state": "shutdown", "state_message": "oops"}},
        }

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/broken":
                    body = b"not json"
                elif self.path in routes:
                    body = json.dumps(routes[self.path]).encode()
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        cls.url = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_queries(self):
        m = update.Moonraker(self.url)
        self.assertIsNotNone(m.fetch("/server/info"))
        self.assertIsNone(m.fetch("/nope"))          # HTTP 404 = ошибка, как curl -f
        self.assertIsNone(m.get_json("/broken"))     # не JSON
        m.ok = True
        self.assertEqual(m.mcu_sections(), [("mcu", "/dev/x", ""), ("mcu T0CB", "", "abc")])
        self.assertEqual(m.mcu_versions(["mcu", "mcu T0CB"]), {"mcu": "v1"})
        self.assertEqual(m.mcu_versions([]), {})
        self.assertEqual(m.print_state(), "paused")
        self.assertEqual(m.printer_info("state"), "shutdown")
        self.assertEqual(m.printer_info("state_message"), "oops")
        m.ok = False
        self.assertEqual(m.mcu_sections(), [])

    def test_http_exception_gives_none(self):
        import http.client
        m = update.Moonraker(self.url)
        with mock.patch.object(update.urllib.request, "urlopen", side_effect=http.client.BadStatusLine("x")):
            self.assertIsNone(m.fetch("/server/info"))

    def test_unreachable(self):
        m = update.Moonraker("http://127.0.0.1:1", timeout=1)
        self.assertIsNone(m.fetch("/server/info"))
        self.assertEqual(m.print_state(), "")
        self.assertEqual(m.printer_info("state"), "")

    def test_check_moonraker_modes(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        cfg = update.Config.from_env({"HOME": d, "MOONRAKER_URL": "http://127.0.0.1:1"})
        u = update.Updater(cfg, update.Options(), moon=update.Moonraker(cfg.moonraker_url, timeout=1))
        with self.assertRaises(VostokError) as cm:
            u.check_moonraker()
        self.assertIn("Moonraker недоступен (http://127.0.0.1:1)", str(cm.exception))
        u.opts.ignore_moonraker = True
        with contextlib.redirect_stderr(io.StringIO()):
            u.check_moonraker()
        self.assertFalse(u.moon.ok)
        u.check_not_printing()   # без Moonraker не проверяется

    def test_check_not_printing(self):
        for state, dies in (("printing", True), ("paused", True), ("standby", False), ("", False)):
            u = update.Updater(update.Config.from_env({"HOME": "/nonexistent"}), update.Options(),
                               moon=FakeMoon(print_state=state))
            if dies:
                with self.assertRaises(VostokError):
                    u.check_not_printing()
            else:
                u.check_not_printing()


class DiscoverTest(BaseTest):
    def test_discover(self):
        main = self.touch("usb-Klipper_stm32h723xx_MAIN0001-if00")
        extra = self.touch("usb-Klipper_stm32f072xb_EXTRA001-if00")
        self.touch("usb-katapult_stm32f446xx_BOOT0001-if00")
        (self.d / "devices.tsv").write_text("T0UUID\tstm32g0b1xx-can.config\tcan\n", encoding="utf-8")
        moon = FakeMoon(sections=[("mcu", main, ""), ("mcu T0CB", "", "T0UUID"), ("mcu T1CB", "", "NOCFG"),
                                  ("mcu ghost", str(self.byid / "usb-Klipper_x_NO-if00"), "")],
                        versions={"mcu": "v1-0-gaaa", "mcu T0CB": "v1-0-gbbb"})
        u = self.updater(moon)
        FlashedLog(self.cfg.state_file).set("EXTRA001", "v1-0-gaaa-dirty")
        with mock.patch.object(hardware, "can_iface_up", return_value=True), \
                contextlib.redirect_stderr(io.StringIO()):
            u.discover_mcus()
        names = [(m.name, m.chip, m.version, m.order, bool(m.cfg)) for m in u.mcus]
        self.assertEqual(names, [
            ("mcu", "stm32h723xx", "v1-0-gaaa", update.ORDER_MAIN, True),
            ("mcu T0CB", "stm32g0b1xx", "v1-0-gbbb", update.ORDER_EXTRA, True),
            ("(не в printer.cfg)", "stm32f072xb", "v1-0-gaaa-dirty*", update.ORDER_USB, True)])
        self.assertEqual(u.mcus[1].uuid, "T0UUID")
        self.assertEqual(u.mcus[2].path, extra)
        self.assertTrue(any(s.startswith("mcu T1CB: CAN (canbus_uuid NOCFG), нет конфига сборки") for s in u.skipped))
        self.assertTrue(any("mcu ghost: устройство" in s and "не найдено" in s for s in u.skipped))
        self.assertTrue(any("usb-katapult_stm32f446xx_BOOT0001-if00: устройство в режиме загрузчика katapult" in s
                            for s in u.skipped))

    def test_can_iface_down_and_bridge_order(self):
        (self.d / "devices.tsv").write_text("BR1\tstm32h723xx-canbridge.config\tbridge\n", encoding="utf-8")
        u = self.updater(FakeMoon(sections=[("mcu", "", "BR1")]))
        with mock.patch.object(hardware, "can_iface_up", return_value=False):
            u.discover_mcus()
        self.assertEqual(u.mcus, [])
        self.assertIn("интерфейс can0 не поднят (ip link show can0)", u.skipped[0])
        with mock.patch.object(hardware, "can_iface_up", return_value=True):
            u.discover_mcus()
        m = u.mcus[0]
        self.assertTrue(m.is_bridge)
        self.assertEqual((m.order, m.path, m.chip), (update.ORDER_MAIN, "CAN can0 BR1", "stm32h723xx"))

    def test_stale_devices_entry_ignored(self):
        # запись devices.tsv с конфигом под другой чип не должна подсунуть чужую прошивку
        self.touch("usb-Klipper_stm32f072xb_SER1-if00")
        (self.d / "devices.tsv").write_text("SER1\tstm32h723xx.config\tusb\n", encoding="utf-8")
        u = self.updater(FakeMoon(ok=False))
        u.discover_mcus()
        self.assertEqual(os.path.basename(u.mcus[0].cfg), "stm32f072xb.config")

    def test_ambiguous_chip_warns(self):
        self.touch("usb-Klipper_stm32h723xx_UNKNOWN1-if00")
        u = self.updater(FakeMoon(ok=False))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            u.discover_mcus()
        self.assertIn("на чипе stm32h723xx бывают разные платы; беру stm32h723xx.config", err.getvalue())

    def test_print_mcus_table(self):
        self.touch("usb-Klipper_stm32f072xb_S1-if00")
        u = self.updater(FakeMoon(ok=False))
        u.discover_mcus()
        out = io.StringIO()
        with mock.patch.object(update.Updater, "host_version", return_value="v1-0-gabc"), \
                contextlib.redirect_stdout(out):
            u.print_mcus()
        lines = out.getvalue().split("\n")
        self.assertEqual(lines[0], "Версия хоста: v1-0-gabc")
        # заголовок как в golden-эталоне bash (ширины в байтах UTF-8)
        self.assertEqual(lines[1], "MCU                  чип        версия               конфиг сборки устройство")
        self.assertTrue(lines[2].startswith("(не в printer.cfg) stm32f072xb   ? "))


class FlowTest(BaseTest):
    """Порядок действий run(): обновление, остановка, сборка, прошивка 1->2->3 (мост последним), запуск."""

    def make_updater(self, mcus, pending=1, **opts):
        u = self.updater(**opts)
        events = []
        u.preflight = lambda: None
        u.discover_mcus = lambda: setattr(u, "mcus", mcus)
        u.print_mcus = lambda: None
        u.host_version = lambda: "v1-0-gnew"
        u.pending_commits = lambda: pending
        u.update_host = lambda: events.append("kiauh")
        u.update_host_git = lambda: events.append("git")
        u.services = lambda a: events.append("services " + a)
        u.wait_for_klipper = lambda: True
        u.verify_versions = lambda: True
        u._git = lambda *a: (0, "c1 one\nc2 two\n")
        u.flash_all = lambda ordered: events.append("flash " + ",".join(m.name for m in ordered))
        patcher = mock.patch.object(firmware, "build_firmware",
                                    side_effect=lambda cfg, chip, **kw: events.append("build " + chip)
                                    or kw["built"].__setitem__(cfg, "/fw/" + chip))
        patcher.start()
        self.addCleanup(patcher.stop)
        return u, events

    def mcu(self, name, order, uuid="", bridge=False, version="v0"):
        return update.Mcu(name=name, path="/dev/" + name, chip="chip_" + name, serial=name, cfg="/c/%s.config" % name,
                          version=version, order=order, uuid=uuid, is_bridge=bridge)

    def test_flash_order_bridge_last_git_mode(self):
        ms = [self.mcu("main", 3), self.mcu("bridge", 3, "U", True), self.mcu("extra", 2), self.mcu("usb", 1)]
        u, ev = self.make_updater(ms, assume_yes=True, git_update=True)
        ui.set_options(True, False, None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(u.run(), 0)
        self.assertEqual(ev[:3], ["services stop", "git", "build chip_main"])
        self.assertEqual(ev[-2:], ["flash usb,extra,main,bridge", "services start"])
        self.assertEqual(ev.count("services stop"), 1)
        self.assertIn("Новых коммитов: 1", out.getvalue())

    def test_kiauh_mode_stops_only_before_flash(self):
        u, ev = self.make_updater([self.mcu("main", 3)], assume_yes=True)
        ui.set_options(True, False, None)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(u.run(), 0)
        self.assertEqual(ev, ["kiauh", "build chip_main", "services stop", "flash main", "services start"])

    def test_no_flash_and_no_update_modes(self):
        ui.set_options(True, False, None)
        u, ev = self.make_updater([self.mcu("main", 3)], assume_yes=True, git_update=True, do_flash=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(u.run(), 0)
        self.assertEqual(ev, ["services stop", "git", "services start"])
        u, ev = self.make_updater([self.mcu("main", 3, version="v1-0-gold")], assume_yes=True, do_update=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(u.run(), 0)
        self.assertEqual(ev, ["build chip_main", "services stop", "flash main", "services start"])

    def test_up_to_date_and_force_flash(self):
        ui.set_options(True, False, None)
        cur = self.mcu("main", 3, version="v1-0-gnew-dirty*")
        u, ev = self.make_updater([cur], pending=0, assume_yes=True, do_update=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(u.run(), 0)
        self.assertEqual(ev, [])
        self.assertIn("всё актуально: хост v1-0-gnew, прошивки MCU совпадают", out.getvalue())
        u, ev = self.make_updater([cur], pending=0, assume_yes=True, do_update=False, force_flash=True)
        with contextlib.redirect_stdout(io.StringIO()):
            u.run()
        self.assertIn("flash main", ev)

    def test_only_lagging_mcu_flashed(self):
        ui.set_options(True, False, None)
        ms = [self.mcu("a", 2, version="v1-0-gnew"), self.mcu("b", 2, version="v0")]
        u, ev = self.make_updater(ms, pending=0, assume_yes=True, do_update=False)
        with contextlib.redirect_stdout(io.StringIO()):
            u.run()
        self.assertIn("flash b", ev)
        self.assertNotIn("a", [e.split()[-1] for e in ev if e.startswith("flash")])

    def test_list_stops_before_update(self):
        u, ev = self.make_updater([self.mcu("main", 3)], list_only=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(u.run(), 0)
        self.assertEqual(ev, [])

    def test_confirm_declined_and_no_tty(self):
        u, ev = self.make_updater([self.mcu("main", 3)])
        out = io.StringIO()
        with mock.patch.object(ui, "_read_tty", return_value="n"), mock.patch.object(ui, "have_tty", return_value=True), \
                contextlib.redirect_stdout(out):
            self.assertEqual(u.run(), 0)
        self.assertEqual(ev, [])
        self.assertIn("отменено", out.getvalue())
        with mock.patch.object(ui, "have_tty", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(VostokError) as cm:
                u.run()
        self.assertEqual(str(cm.exception), "нет терминала для подтверждения, используйте -y")

    def test_mismatch_returns_1(self):
        ui.set_options(True, False, None)
        u, ev = self.make_updater([self.mcu("main", 3)], assume_yes=True)
        u.verify_versions = lambda: False
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(u.run(), 1)


class FlashTest(BaseTest):
    def test_flash_usb_failure_stops_klipper_off(self):
        u = self.updater()
        m = update.Mcu("mcu", "/dev/x", "stm32h723xx", "S1", cfg="/c", order=3)
        u.built["/c"] = "/fw/x.bin"
        err = io.StringIO()
        with mock.patch.object(firmware, "flash_usb", return_value=False), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(VostokError) as cm:
                u.flash_all([m])
        self.assertEqual(str(cm.exception), "прошивка mcu не удалась")
        self.assertIn("Прошивка mcu не удалась. Klipper НЕ запущен.", err.getvalue())
        self.assertIn("flashtool.py -d /dev/serial/by-id/usb-katapult_... -f /fw/x.bin", err.getvalue())

    def test_flash_usb_success_writes_journal(self):
        dev = self.touch("usb-Klipper_stm32f072xb_S1-if00")
        u = self.updater()
        m = update.Mcu("alps", dev, "stm32f072xb", "S1", cfg="/c", order=2)
        u.built["/c"] = "/fw/x.bin"
        u.host_version = lambda: "v1-0-gnew"
        calls = []
        with mock.patch.object(firmware, "flash_usb", side_effect=lambda *a, **k: calls.append(a[1:3]) or True), \
                contextlib.redirect_stdout(io.StringIO()):
            u.flash_all([m])
        self.assertEqual(calls, [(dev, "/fw/x.bin")])
        self.assertEqual(FlashedLog(self.cfg.state_file).get("S1"), "v1-0-gnew")

    def test_device_not_back(self):
        u = self.updater()
        m = update.Mcu("alps", str(self.byid / "gone"), "stm32f072xb", "S1", cfg="/c")
        u.built["/c"] = "/b"
        with mock.patch.object(firmware, "flash_usb", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(VostokError) as cm:
                u.flash_all([m])
        self.assertIn("после прошивки alps не вернулось устройство", str(cm.exception))

    def test_can_node_failure_message(self):
        u = self.updater()
        m = update.Mcu("T0CB", "CAN can0 U1", "stm32g0b1xx", "U1", cfg="/c", uuid="U1")
        u.built["/c"] = "/b.bin"
        err = io.StringIO()
        with mock.patch.object(firmware, "flash_can_node", return_value=False), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(VostokError):
                u.flash_all([m])
        self.assertIn("Прошивка T0CB по CAN не удалась. Klipper НЕ запущен.", err.getvalue())
        self.assertIn("повтор: python3 %s/scripts/flashtool.py -i can0 -u U1 -f /b.bin" % self.cfg.katapult_dir,
                      err.getvalue())

    def test_bridge_uses_byid_dir_from_config(self):
        """Исправление: katapult-устройство моста ищется в BYID_DIR, а не в жёстком /dev/serial/by-id."""
        katapult = self.touch("usb-katapult_stm32h723xx_BR-if00")
        u = self.updater()
        m = update.Mcu("mcu", "CAN can0 BR", "stm32h723xx", "BR", cfg="/c", uuid="BR", is_bridge=True, order=3)
        seen = []
        with mock.patch.object(firmware, "request_bootloader_can", return_value=True), \
                mock.patch.object(firmware, "flashtool", side_effect=lambda k, a, r=None: seen.append(a) or True), \
                mock.patch.object(hardware, "wait_for_can_iface", return_value=True), \
                mock.patch.object(hardware, "can_iface_up", return_value=True):
            self.assertTrue(u.flash_can(m, "/b.bin"))
        self.assertEqual(seen, [["-d", katapult, "-f", "/b.bin"]])

    def test_bridge_timeout_and_iface_missing(self):
        u = self.updater()
        m = update.Mcu("mcu", "CAN can0 BR", "stm32h723xx", "BR", cfg="/c", uuid="BR", is_bridge=True)
        err = io.StringIO()
        with mock.patch.object(firmware, "request_bootloader_can", return_value=True), contextlib.redirect_stderr(err):
            self.assertFalse(u.flash_can(m, "/b"))
        self.assertIn("мост не перешёл в katapult за 20 с (usb-katapult_stm32h723xx_*)", err.getvalue())
        self.touch("usb-katapult_stm32h723xx_BR-if00")
        err = io.StringIO()
        with mock.patch.object(firmware, "request_bootloader_can", return_value=True), \
                mock.patch.object(firmware, "flashtool", return_value=True), \
                mock.patch.object(hardware, "wait_for_can_iface", return_value=False), contextlib.redirect_stderr(err):
            self.assertFalse(u.flash_can(m, "/b"))
        self.assertIn("интерфейс can0 не появился после прошивки моста", err.getvalue())

    def test_bridge_ifup_when_down(self):
        self.touch("usb-katapult_stm32h723xx_BR-if00")
        u = self.updater()
        m = update.Mcu("mcu", "CAN can0 BR", "stm32h723xx", "BR", cfg="/c", uuid="BR", is_bridge=True)
        with mock.patch.object(firmware, "request_bootloader_can", return_value=True), \
                mock.patch.object(firmware, "flashtool", return_value=True), \
                mock.patch.object(hardware, "wait_for_can_iface", return_value=True), \
                mock.patch.object(hardware, "can_iface_up", return_value=False), \
                mock.patch.object(hardware, "ifup") as ifup:
            self.assertTrue(u.flash_can(m, "/b"))
        ifup.assert_called_once_with("can0")


class FakeRunner:
    def __init__(self, stdout="v0.12.0-1-gabcdef0\n", rc=0):
        self.stdout, self.rc, self.calls = stdout, rc, []

    dry_run = False

    def run(self, cmd, **kw):
        self.calls.append(list(cmd))
        if cmd[0] == "make":      # make в тестах - заглушка из PATH (запускается по-настоящему), describe - подделка
            return system.Runner(dry_run=False).run(cmd, **kw)
        return subprocess.CompletedProcess(cmd, self.rc, self.stdout, "")


class FirmwareTest(BaseTest):
    def fake_make(self, ok_mcu="chip_x", fail_on=None):
        bindir = self.d / "bin"
        bindir.mkdir(exist_ok=True)
        script = bindir / "make"
        script.write_text("""#!/usr/bin/env bash
for a in "$@"; do case $a in KCONFIG_CONFIG=*) cfg=${a#KCONFIG_CONFIG=};; OUT=*) out=${a#OUT=};; esac; done
echo "make $*"
case "$*" in *%s*) echo "ошибка сборки" >&2; exit 2;; esac
case "$*" in *-j*) mkdir -p "$out"; printf 'BIN' > "$out/klipper.bin";; esac
echo "CONFIG_NEW=y" >> "$cfg"
""" % (fail_on or "NEVERMATCH"))
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        patcher = mock.patch.dict(os.environ, {"PATH": str(bindir) + os.pathsep + os.environ["PATH"]})
        patcher.start()
        self.addCleanup(patcher.stop)

    def conf(self, chip):
        p = self.d / "chip_x.config"
        p.write_text('CONFIG_MCU="%s"\n' % chip, encoding="utf-8")
        return str(p)

    def build(self, cfg, chip="chip_x", built=None):
        return firmware.build_firmware(cfg, chip, klipper_dir=self.d / "klipper", build_dir=self.d / "build",
                                       firmware_dir=self.d / "fw", built={} if built is None else built,
                                       runner=FakeRunner())

    def test_build_ok_and_cache(self):
        self.fake_make()
        cfg, built = self.conf("chip_x"), {}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            binp = self.build(cfg, built=built)
            self.assertEqual(self.build(cfg, built=built), binp)   # из кэша, повторно не собирается
        self.assertEqual(binp, str(self.d / "fw" / "chip_x-v0.12.0-1-gabcdef0.bin"))
        self.assertEqual(Path(binp).read_bytes(), b"BIN")
        self.assertIn("CONFIG_NEW=y", Path(cfg).read_text(encoding="utf-8"))   # olddefconfig записан обратно
        self.assertEqual(out.getvalue().count("сборка chip_x ..."), 1)
        self.assertIn("собрано: %s (3 байт)" % binp, out.getvalue())

    def test_build_wrong_chip(self):
        self.fake_make()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(VostokError) as cm:
                self.build(self.conf("other"))
        self.assertIn("собирает CONFIG_MCU=other, а устройству нужен chip_x", str(cm.exception))

    def test_build_failures_show_log_tail(self):
        self.fake_make(fail_on="olddefconfig")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            with self.assertRaises(VostokError) as cm:
                self.build(self.conf("chip_x"))
        self.assertEqual(str(cm.exception), "make olddefconfig (chip_x) не удался")
        self.assertIn("ошибка сборки", err.getvalue())
        self.fake_make(fail_on="-j")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            with self.assertRaises(VostokError) as cm:
                self.build(self.conf("chip_x"))
        self.assertIn("сборка chip_x не удалась, лог: %s" % (self.d / "build" / "chip_x" / "make.log"), str(cm.exception))


class HostUpdateTest(BaseTest):
    """update_host_git на настоящих временных git-репозиториях."""

    def setUp(self):
        super().setUp()
        self.origin = self.d / "origin"
        self.origin.mkdir()
        git(self.origin, "init", "-q", "-b", "main")
        (self.origin / "f.txt").write_text("1\n")
        git(self.origin, "add", ".")
        git(self.origin, "commit", "-q", "-m", "c1")
        subprocess.run(["git", "clone", "-q", str(self.origin), self.cfg.klipper_dir], env=GIT_ENV, check=True,
                       stderr=subprocess.PIPE)
        (self.d / "klipper" / "scripts").mkdir(exist_ok=True)
        (self.d / "klipper" / "scripts" / "klippy-requirements.txt").write_text("")
        self.pip_log = self.d / "pip.log"
        pip = self.d / "env" / "bin" / "pip"
        pip.parent.mkdir(parents=True)
        pip.write_text('#!/usr/bin/env bash\necho "pip $*" >> %s\n' % self.pip_log)
        pip.chmod(0o755)

    def push_commit(self, text="2\n"):
        (self.origin / "f.txt").write_text(text)
        git(self.origin, "commit", "-q", "-am", "next")
        git(self.cfg.klipper_dir, "fetch", "-q")

    def run_git_update(self):
        u = self.updater()
        out, err = capture()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            u.update_host_git()
        return out.getvalue(), err.getvalue()

    def test_fast_forward(self):
        self.push_commit()
        out, _ = self.run_git_update()
        self.assertEqual(git(self.cfg.klipper_dir, "rev-parse", "HEAD"), git(self.origin, "rev-parse", "HEAD"))
        self.assertIn("обновлено: ", out)
        self.assertIn("pip install -q -r", self.pip_log.read_text())
        self.assertIn("хост обновлён: ", out)

    def test_rewritten_upstream_reset(self):
        self.push_commit()
        git(self.cfg.klipper_dir, "merge", "-q", "--ff-only", "@{u}")
        git(self.origin, "branch", "old")   # старая история осталась на сервере в другой ветке
        git(self.origin, "reset", "-q", "--hard", "HEAD~1")
        (self.origin / "f.txt").write_text("rewritten\n")
        git(self.origin, "commit", "-q", "-am", "rewritten")
        git(self.cfg.klipper_dir, "fetch", "-q")
        out, err = self.run_git_update()
        self.assertIn("история upstream переписана, перехожу на", err)
        self.assertEqual(git(self.cfg.klipper_dir, "rev-parse", "HEAD"), git(self.origin, "rev-parse", "HEAD"))

    def test_local_commits_die(self):
        (self.d / "klipper" / "mine.txt").write_text("x")
        git(self.cfg.klipper_dir, "add", "mine.txt")
        git(self.cfg.klipper_dir, "commit", "-q", "-m", "local")
        self.push_commit()
        with self.assertRaises(VostokError) as cm:
            self.run_git_update()
        self.assertIn("есть локальные коммиты, которых нет на сервере", str(cm.exception))

    def test_pending_commits(self):
        u = self.updater()
        self.assertEqual(u.pending_commits(), 0)
        self.push_commit()
        self.assertEqual(u.pending_commits(), 1)

    def test_gcode_shell_command_restored(self):
        cfgdir = self.d / "pd" / "config"
        cfgdir.mkdir(parents=True)
        (cfgdir / "shell_command.cfg").write_text("[gcode_shell_command x]\ncommand: ls\n")
        asset = self.d / "asset.py"
        asset.write_text("# shell\n")
        self.cfg.gcode_shell_asset = str(asset)
        extras = self.d / "klipper" / "klippy" / "extras"
        extras.mkdir(parents=True)
        u = self.updater()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            u.post_update_checks()
        self.assertTrue((extras / "gcode_shell_command.py").is_file())
        self.assertIn("восстановлен gcode_shell_command.py", out.getvalue())
        # актива нет - предупреждение
        (extras / "gcode_shell_command.py").unlink()
        self.cfg.gcode_shell_asset = str(self.d / "missing.py")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            u.post_update_checks()
        self.assertIn("в конфигах есть [gcode_shell_command], но", err.getvalue())

    def test_import_test_failure(self):
        py = self.d / "env" / "bin" / "python"
        py.write_text("#!/usr/bin/env bash\nexit 1\n")
        py.chmod(0o755)
        with self.assertRaises(VostokError) as cm:
            self.updater().post_update_checks()
        self.assertEqual(str(cm.exception), "klippy --import-test не прошёл после обновления")

    def test_preflight_dirty_tree_and_no_repo(self):
        (self.d / "klipper" / "f.txt").write_text("dirty\n")
        u = self.updater(do_flash=False, git_update=True)
        err = io.StringIO()
        with mock.patch.object(update.os, "geteuid", return_value=1000), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(VostokError) as cm:
                u.preflight()
        self.assertIn("изменённые отслеживаемые файлы", str(cm.exception))
        self.assertIn("f.txt", err.getvalue())
        self.cfg.klipper_dir = str(self.d / "nogit")
        with mock.patch.object(update.os, "geteuid", return_value=1000), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(VostokError) as cm:
                u.preflight()
        self.assertEqual(str(cm.exception), "%s не git-репозиторий (KLIPPER_DIR)" % (self.d / "nogit"))

    def test_preflight_no_tty_requires_service_rights(self):
        u = self.updater(do_update=False)
        for f in ("flashtool.py",):
            p = self.d / "katapult" / "scripts" / f
            p.parent.mkdir(parents=True)
            p.write_text("")
        with mock.patch.object(update.os, "geteuid", return_value=1000), \
                mock.patch.object(update.shutil, "which", return_value="/bin/x"), \
                mock.patch.object(hardware, "run_quiet", return_value=(0, "")), \
                mock.patch.object(update.sys, "stdin") as stdin, \
                mock.patch.object(update, "can_manage_services", return_value=False):
            stdin.isatty.return_value = False
            with self.assertRaises(VostokError) as cm, contextlib.redirect_stdout(io.StringIO()):
                u.preflight()
        self.assertIn("без терминала нет прав останавливать klipper", str(cm.exception))


class VerifyTest(BaseTest):
    def verify(self, mcus):
        u = self.updater()
        u.host_version = lambda: "v1-0-gnew-dirty"
        u.discover_mcus = lambda: setattr(u, "mcus", mcus)
        out, err = capture()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            res = u.verify_versions()
        return res, out.getvalue(), err.getvalue()

    def test_verify(self):
        mk = lambda n, v: update.Mcu(n, "/p", "c", n, version=v)   # noqa: E731
        res, out, err = self.verify([mk("a", "v1-0-gnew"), mk("b", "?"), mk("c", "v1-0-gnew-dirty*")])
        self.assertTrue(res)
        self.assertIn("a: v1-0-gnew", out)
        self.assertIn("b: версию получить не удалось", out)
        self.assertIn("c: v1-0-gnew-dirty (по журналу прошивок)", out)
        res, out, err = self.verify([mk("a", "v0"), mk("b", "v0*")])
        self.assertFalse(res)
        self.assertIn("a: v0 (хост v1-0-gnew)", err)
        self.assertIn("b: v0 по журналу, хост v1-0-gnew", err)

    def test_wait_for_klipper(self):
        u = self.updater(FakeMoon(info=[{"state": ""}, {"state": "ready"}]))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(u.wait_for_klipper())
        u = self.updater(FakeMoon(info=[{"state": "error", "state_message": "boom"}]))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertFalse(u.wait_for_klipper())
        self.assertIn("состояние Klipper: error", err.getvalue())
        self.assertIn("boom", err.getvalue())
        u = self.updater(FakeMoon(info=[{"state": ""}]))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertFalse(u.wait_for_klipper())
        self.assertIn("Moonraker не ответил за 60 с", err.getvalue())


class WrapperTest(unittest.TestCase):
    def run_wrapper(self, path, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        return subprocess.run([path] + list(args), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)

    def test_help_and_symlink(self):
        script = os.path.join(INSTALLER, "update_klipper_mcu.sh")
        r = self.run_wrapper(script, "--help")
        self.assertEqual((r.returncode, r.stdout), (0, update.USAGE))
        with tempfile.TemporaryDirectory() as d:
            link = os.path.join(d, "link.sh")
            os.symlink(script, link)
            r = self.run_wrapper(link, "-V")
            self.assertEqual(r.returncode, 0)
            self.assertTrue(r.stdout.startswith("VOSTOK installer "))
            r = self.run_wrapper(link, "--bogus")
            self.assertEqual(r.returncode, 1)
            self.assertIn("ОШИБКА: неизвестная опция: --bogus", r.stderr)


if __name__ == "__main__":
    unittest.main()
