"""Тесты vostok.host: окружение, проверки окружения, пакеты, KIAUH/форк Klipper, CAN-конфиг, ожидание Moonraker."""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fakes import INSTALLER, REG, FakeRunner, Sandbox  # noqa: E402
from vostok import VostokError, host, ui  # noqa: E402
from vostok.configurator import Hardware  # noqa: E402
from vostok.host import EnvChecks, Options, Software  # noqa: E402

FIX = INSTALLER / "tests" / "fixtures"

# прежний код правки kiauh.cfg из install_vostok.sh (heredoc), для сравнения 1:1
LEGACY_KIAUH_EDIT = r'''
import sys, re
path, repo = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().split("\n")
out, section, skipping = [], None, False
for line in lines:
    m = re.match(r"\[(.+)\]\s*$", line)
    if m:
        section, skipping = m.group(1), False
    if section == "klipper" and line.startswith("repositories:"):
        out.append("repositories:")
        out.append("    " + repo)
        skipping = True
        continue
    if skipping:
        if line.startswith((" ", "\t")) and line.strip():
            continue
        skipping = False
    out.append(line)
open(path, "w", encoding="utf-8").write("\n".join(out))
'''

KIAUH_SAMPLES = [
    "[klipper]\nrepositories:\n    https://github.com/Klipper3d/klipper, master\n    https://x/y, z\nother: 1\n\n[moonraker]\nrepositories:\n    a, b\n",
    "[klipper]\nrepositories:\n\tone, two\n[fluidd]\nx: y\n",
    "[general]\na=1\n[klipper]\nfoo: bar\nrepositories:\n    old, old\n",
    "no sections at all\n",
    "[klipper]\nrepositories:\n",
]


class TestEnv(Sandbox):
    def test_defaults_and_overrides(self):
        e = host.Env.from_environ({"HOME": "/home/u"})
        self.assertEqual(e.cfg.klipper_dir, "/home/u/klipper")
        self.assertEqual(e.moonraker_dir, "/home/u/moonraker")
        self.assertEqual(e.klipper_repo_url, "https://github.com/dmbutyugin/klipper")
        self.assertEqual(e.klipper_branch, "generic-cartesian")
        self.assertEqual(e.katapult_repo_url, "https://github.com/Arksine/katapult")
        self.assertEqual(e.kiauh_repo_url, "https://github.com/dw-0/kiauh")
        self.assertEqual((e.min_free_mb, e.min_mem_mb), (2048, 1024))
        self.assertEqual(str(e.log_file), "/home/u/printer_data/logs/vostok_install.log")
        self.assertEqual(str(e.devices_file), str(INSTALLER / "devices.tsv"))
        e = host.Env.from_environ({"HOME": "/h", "PRINTER_DATA": "/p", "LOG_FILE": "/l.log", "DEVICES_FILE": "/d.tsv",
                                   "MOONRAKER_DIR": "/m", "KLIPPER_BRANCH": "b", "MIN_FREE_MB": "5", "KERNEL_CONFIG": "/k",
                                   "BYID_DIR": "/b", "CAN_IFACE": "can1"})
        self.assertEqual((str(e.log_file), str(e.devices_file), e.moonraker_dir, e.klipper_branch, e.min_free_mb,
                          e.kernel_config, e.byid_dir, e.can_iface),
                         ("/l.log", "/d.tsv", "/m", "b", 5, "/k", "/b", "can1"))
        self.assertEqual(e.cfg.log_file, "/l.log")

    def test_results_prev_keys(self):
        r = host.Results()
        r.prev_devices = [host.Device("a", "x.config", "usb"), host.Device("b", "y.config", "usb"),
                          host.Device("c", "x.config", "usb")]
        self.assertEqual(r.prev_keys("x.config"), ["a", "c"])
        self.assertEqual(r.prev_keys(""), [])

    def test_options_board_skipped(self):
        o = Options(skip_boards=["alps1"])
        self.assertTrue(o.board_skipped("alps1"))
        self.assertFalse(o.board_skipped("alps"))

    def test_read_os_release(self):
        p = self.tmp / "os-release"
        p.write_text('PRETTY_NAME="Debian GNU/Linux 11 (bullseye)"\nID=debian\nID_LIKE=\'x y\'\n# c\nBAD LINE\n')
        self.assertEqual(host.read_os_release(str(p)), {"PRETTY_NAME": "Debian GNU/Linux 11 (bullseye)", "ID": "debian",
                                                        "ID_LIKE": "x y"})
        self.assertEqual(host.read_os_release(str(self.tmp / "none")), {})


class TestKiauhCfg(unittest.TestCase):
    def test_same_as_legacy_heredoc(self):
        import tempfile
        for sample in KIAUH_SAMPLES:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "kiauh.cfg"
                p.write_text(sample, encoding="utf-8")
                subprocess.run([sys.executable, "-I", "-c", LEGACY_KIAUH_EDIT, str(p), "https://r/k, br"], check=True)
                self.assertEqual(host.kiauh_cfg_with_repo(sample, "https://r/k, br"), p.read_text(encoding="utf-8"), sample)


class TestChecks(Sandbox):
    def checks(self, dry=False, only=False, skip_flash=False, skip_sw=False, **envkw):
        self.opts = Options(dry_run=dry, only_detect=only, skip_flash=skip_flash, skip_software=skip_sw)
        self.runner = FakeRunner(dry_run=dry, default_rc=1)
        self.runner.on(("df",), 0, "Filesystem 1048576-blocks Used Available Capacity Mounted on\n/dev/x 100000 1000 99000 2% /\n")
        self.runner.on(("uname", "-r"), 0, "5.15.0-test\n")
        self.runner.on(("id", "-nG"), 0, "klipper dialout\n")
        self.runner.on(("id", "-un"), 0, "klipper\n")
        return EnvChecks(self.make_env(**envkw), self.opts, self.runner)

    def test_item_and_conclude(self):
        c = self.checks()
        c.item("ok", "a")
        c.item("warn", "b")
        c.item("bad", "c")
        self.assertEqual(self.out.getvalue(), "  [ок]   a\n  [!]    b\n  [НЕТ]  c\n")
        self.assertEqual((c.warnings, c.problems), (["b"], ["c"]))
        with self.assertRaises(VostokError) as cm:
            c.conclude("Окружение")
        self.assertIn("Окружение: найдено проблем: 1. Устраните их", str(cm.exception))
        for kw in ({"dry": True}, {"only": True}):             # в dry-run/--only-detect - только предупреждение
            c = self.checks(**kw)
            c.item("bad", "c")
            c.conclude("Окружение")
        self.assertIn("при реальной установке скрипт остановится", self.err.getvalue())

    def test_bootstrap_ok_and_low_resources(self):
        c = self.checks(dry=True, MIN_FREE_MB="200000", MIN_MEM_MB="99999999")
        c.check_bootstrap()
        t = self.text()
        self.assertIn("[НЕТ]  мало места в %s: 99000 МБ, нужно не менее 200000 МБ" % self.home, t)
        self.assertIn("[!]    мало памяти (ОЗУ + swap):", t)
        self.assertRegex(t, r"\[ок\]   python3 \d+\.\d+")
        c = self.checks(dry=True)
        c.problems = ["x"]
        c.check_bootstrap()
        self.assertEqual(c.problems, [])                       # блок сбрасывает прошлые проблемы
        self.assertIn("[ок]   место на диске: 99000 МБ", self.out.getvalue())

    def test_bootstrap_hardware_steps_need_tty_and_dialout(self):
        c = self.checks(USER_GROUPS="klipper dialout", USER_GROUPS_DB="klipper dialout")
        with mock.patch.object(ui, "have_tty", return_value=True):
            with self.assertRaises(VostokError) if False else mock.patch.object(c, "conclude"):
                c.check_bootstrap()
        t = self.out.getvalue()
        self.assertIn("[ок]   терминал для диалога", t)
        self.assertIn("[ок]   доступ к последовательным портам (группа dialout)", t)
        for env, want in (({"USER_GROUPS": "klipper", "USER_GROUPS_DB": "klipper dialout"}, "текущая сессия её не видит"),
                          ({"USER_GROUPS": "klipper", "USER_GROUPS_DB": "klipper"}, "пользователь не в группе dialout")):
            c = self.checks(**env)
            c.check_dialout()
            self.assertIn(want, c.problems[0])
        c = self.checks()
        with mock.patch.object(ui, "have_tty", return_value=False), mock.patch.object(c, "conclude"):
            c.check_bootstrap()
        self.assertIn("нет терминала: шаги с железом требуют ответов в диалоге", c.problems[0])
        # прошивка не планируется (--skip-flash / --dry-run): терминал и dialout не проверяются
        c = self.checks(skip_flash=True)
        with mock.patch.object(c, "conclude"):
            c.check_bootstrap()
        self.assertFalse(any("терминал" in p or "dialout" in p for p in c.problems + c.warnings))

    def test_tools_states(self):
        c = self.checks()
        with mock.patch.object(host.shutil, "which", side_effect=lambda x: None if x in ("dfu-util", "make") else "/bin/" + x):
            c.check_tools(True, False)         # пакеты ещё будут установлены: предупреждения
        self.assertEqual(len(c.problems), 0)
        self.assertEqual(len(c.warnings), 2 + 2)                  # dfu-util, make + pyserial и venv (python3 -c: rc 1)
        self.assertIn("нет make (пакет make): сборка прошивок; будет установлен на этапе пакетов", self.out.getvalue())
        c = self.checks()
        with mock.patch.object(host.shutil, "which", side_effect=lambda x: None if x == "git" else "/bin/" + x):
            with self.assertRaises(VostokError):
                c.check_tools(False, True)                         # после пакетов - проблема
        self.assertIn("Установить недостающее: sudo apt install git", self.out.getvalue())
        c = self.checks(skip_flash=True)
        self.runner.rules.insert(0, (lambda a: a[0] == "python3", 0, ""))
        with mock.patch.object(host.shutil, "which", return_value="/bin/x"):
            c.check_tools(False, True)
        self.assertNotIn("pyserial", self.out.getvalue().split("Инструменты")[-1].split("python3: venv")[0])   # без прошивки pyserial не нужен

    def test_hw_requirements(self):
        c = self.checks()
        hw = Hardware(REG, main_board="octopus-pro-h723", heads="none", mode="usb")
        c.check_hw_requirements(hw)
        self.assertEqual(self.out.getvalue(), "")                  # без плат голов - тихо
        hw.heads, hw.mode = "v2", "bridge"
        with mock.patch.object(host.shutil, "which", return_value="/bin/ip"):
            c.check_hw_requirements(hw)
        self.assertIn("ядро 5.15.0-test поддерживает CAN и USB-CAN адаптеры (gs_usb)", self.out.getvalue())
        c = self.checks(KERNEL_CONFIG=str(FIX / "kernel_config_nocan"))
        with mock.patch.object(host.shutil, "which", return_value=None):
            with self.assertRaises(VostokError):
                c.check_hw_requirements(hw)
        t = self.out.getvalue()
        self.assertIn("собрано без CAN (нужны CONFIG_CAN, CONFIG_CAN_RAW, CONFIG_CAN_GS_USB): Octopus в режиме моста USB-CAN", t)
        self.assertIn("[НЕТ]  нет ip (пакет iproute2)", t)
        c = self.checks(KERNEL_CONFIG=str(self.tmp / "empty"))
        (self.tmp / "empty").write_text("")
        with mock.patch.object(host.hardware, "kernel_can_support", return_value=2), \
                mock.patch.object(host.shutil, "which", return_value="/bin/ip"):
            c.check_hw_requirements(hw)
        self.assertIn("не удалось определить поддержку CAN в ядре", self.out.getvalue())


class TestPackagesAndSoftware(Sandbox):
    def setUp(self):
        super().setUp()
        self.runner = FakeRunner(default_rc=0)

    def test_packages_install_missing_only(self):
        self.runner.on(("dpkg", "-s", "dfu-util"), 1)
        self.runner.on(("dpkg", "-s", "make"), 1)
        host.stage_packages(self.env, Options(), self.runner)
        self.assertEqual(self.runner.calls[-2:], [("sudo", "apt-get", "update"), ("sudo", "apt-get", "install", "-y", "make", "dfu-util")])
        self.assertIn("Устанавливаю: make dfu-util", self.out.getvalue())
        self.assertIn("пакеты готовы", self.out.getvalue())

    def test_packages_nothing_missing_and_upgrade(self):
        host.stage_packages(self.env, Options(), self.runner)
        self.assertEqual(self.runner.called("sudo"), 0)
        self.assertIn("все нужные пакеты уже установлены", self.out.getvalue())
        host.stage_packages(self.env, Options(upgrade=True), self.runner)
        self.assertEqual([c for c in self.runner.calls if c[0] == "sudo"],
                         [("sudo", "apt-get", "update"), ("sudo", "apt-get", "-y", "upgrade")])

    def test_packages_dry_run_prints(self):
        r = FakeRunner(dry_run=True, default_rc=1)             # dpkg -s: ничего не стоит
        host.stage_packages(self.env, Options(upgrade=True), r)
        t = self.out.getvalue()
        self.assertIn("[dry-run] sudo apt-get update", t)
        self.assertIn("[dry-run] sudo apt-get -y upgrade", t)
        self.assertIn("[dry-run] sudo apt-get install -y git curl python3", t)

    def sw(self, runner=None):
        return Software(self.env, Options(), runner or self.runner)

    def test_klipper_is_fork(self):
        sw = self.sw()
        self.assertFalse(sw.klipper_is_fork())                 # нет каталога
        (Path(self.env.klipper_dir) / ".git").mkdir(parents=True)
        self.runner.on(("git", "-C", self.env.klipper_dir, "remote", "get-url", "origin"), 0, "https://github.com/DMButyugin/klipper.git\n")
        self.runner.on(("git", "-C", self.env.klipper_dir, "rev-parse", "--abbrev-ref", "HEAD"), 0, "generic-cartesian\n")
        self.assertTrue(sw.klipper_is_fork())
        self.runner.rules.insert(0, (lambda a: "get-url" in a, 0, "https://github.com/Klipper3d/klipper\n"))
        self.assertFalse(sw.klipper_is_fork())

    def test_switch_klipper_to_fork(self):
        sw = self.sw()
        kd = self.env.klipper_dir
        self.runner.on(("git", "-C", kd, "status"), 0, " M klippy/x.py\n")
        with self.assertRaises(VostokError) as cm:
            sw.switch_klipper_to_fork()
        self.assertIn("есть локальные изменения", str(cm.exception))
        self.runner.rules.clear()
        with mock.patch.object(ui, "ask_yn", return_value=False):
            with self.assertRaises(VostokError) as cm:
                sw.switch_klipper_to_fork()
        self.assertEqual(str(cm.exception), "без форка VOSTOK работать не будет")
        with mock.patch.object(ui, "ask_yn", return_value=True):
            sw.switch_klipper_to_fork()
        self.assertEqual(self.runner.calls[-5:], [
            ("git", "-C", kd, "remote", "set-url", "origin", "https://github.com/dmbutyugin/klipper"),
            ("git", "-C", kd, "fetch", "origin", "generic-cartesian"),
            ("git", "-C", kd, "checkout", "-B", "generic-cartesian", "origin/generic-cartesian"),
            ("git", "-C", kd, "branch", "--set-upstream-to=origin/generic-cartesian", "generic-cartesian"),
            (self.env.klippy_env + "/bin/pip", "install", "-q", "-r", kd + "/scripts/klippy-requirements.txt")])

    def test_kiauh_set_fork_repo_writes_file(self):
        kd = Path(self.env.kiauh_dir)
        kd.mkdir()
        (kd / "default.kiauh.cfg").write_text("[klipper]\nrepositories:\n    old, master\n\n[x]\ny: 1\n")
        self.sw().kiauh_set_fork_repo()
        self.assertEqual((kd / "kiauh.cfg").read_text(),
                         "[klipper]\nrepositories:\n    https://github.com/dmbutyugin/klipper, generic-cartesian\n\n[x]\ny: 1\n")
        # kiauh.cfg уже есть - используется он, а не default
        (kd / "kiauh.cfg").write_text("[klipper]\nrepositories:\n    mine, b\n")
        self.sw().kiauh_set_fork_repo()
        self.assertIn("dmbutyugin/klipper, generic-cartesian", (kd / "kiauh.cfg").read_text())

    def test_stage_software_fresh_install(self):
        self.runner.rules.append((lambda a: a[0].endswith("klippy.py"), 0, ""))
        kd = Path(self.env.kiauh_dir)
        kd.mkdir()
        (kd / "default.kiauh.cfg").write_text("[klipper]\nrepositories:\n    a, b\n")
        asset = Path(self.env.cfg.gcode_shell_asset)
        asset.parent.mkdir(parents=True)
        asset.write_text("x")
        self.sw().stage_software()
        calls = self.runner.calls
        k = self.env.kiauh_dir + "/kiauh.sh"
        self.assertIn(("git", "clone", self.env.kiauh_repo_url, self.env.kiauh_dir), calls)
        self.assertIn((k, "install", "klipper", "--count", "1"), calls)
        self.assertIn((k, "install", "moonraker", "--create-example-cfg"), calls)
        self.assertIn((k, "install", "fluidd", "--install-config"), calls)
        self.assertIn(("cp", str(asset), self.env.klipper_dir + "/klippy/extras/"), calls)
        self.assertIn(("git", "clone", self.env.katapult_repo_url, self.env.katapult_dir), calls)
        self.assertTrue(any(c[-1] == "--import-test" for c in calls))
        self.assertIn("программное обеспечение готово", self.out.getvalue())

    def test_stage_software_everything_installed_and_import_failure(self):
        for d in (self.env.kiauh_dir, self.env.klipper_dir, self.env.moonraker_dir, self.env.katapult_dir):
            (Path(d) / ".git").mkdir(parents=True)
        (self.home / "fluidd").mkdir()
        extras = Path(self.env.klipper_dir) / "klippy" / "extras"
        extras.mkdir(parents=True)
        (extras / "gcode_shell_command.py").write_text("")
        self.runner.on(("git", "-C", self.env.klipper_dir, "remote"), 0, "https://github.com/dmbutyugin/klipper\n")
        self.runner.on(("git", "-C", self.env.klipper_dir, "rev-parse"), 0, "generic-cartesian\n")
        self.runner.on(("git", "-C", self.env.klipper_dir, "describe"), 0, "v1-2-gabc\n")
        self.runner.on((self.env.klippy_env + "/bin/python",), 1)
        with self.assertRaises(VostokError) as cm:
            self.sw().stage_software()
        self.assertEqual(str(cm.exception), "klippy --import-test не прошёл")
        t = self.out.getvalue()
        for s in ("KIAUH уже установлен", "Klipper: форк уже установлен (v1-2-gabc)", "Moonraker уже установлен",
                  "Fluidd уже установлен", "gcode_shell_command уже установлен", "katapult уже установлен"):
            self.assertIn(s, t)
        self.assertEqual(self.runner.called("git", "clone"), 0)

    def test_missing_gcode_shell_asset_warns(self):
        (Path(self.env.klipper_dir) / ".git").mkdir(parents=True)
        self.runner.on(("git", "-C", self.env.klipper_dir, "remote"), 0, "dmbutyugin/klipper\n")
        self.runner.on(("git", "-C", self.env.klipper_dir, "rev-parse"), 0, "generic-cartesian\n")
        self.runner.on(("git", "-C", self.env.klipper_dir, "describe"), 0, "v1\n")
        for d in (self.env.kiauh_dir, self.env.moonraker_dir, self.env.katapult_dir):
            (Path(d) / ".git").mkdir(parents=True)
        (self.home / "fluidd").mkdir()
        self.sw().stage_software()
        self.assertIn("не найден %s: поставьте расширение через KIAUH -> Extensions" % self.env.cfg.gcode_shell_asset,
                      self.err.getvalue())


class TestCanConfig(Sandbox):
    def hw(self, heads="v2"):
        return Hardware(REG, main_board="octopus-pro-h723", heads=heads, mode="bridge")

    def test_none_heads_does_nothing(self):
        r = FakeRunner()
        host.stage_can(self.env, Options(), self.hw("none"), r)
        self.assertEqual((r.calls, self.out.getvalue()), ([], ""))

    def test_ifupdown_dry_run_and_real(self):
        f = self.tmp / "can0"
        r = FakeRunner(dry_run=True)
        ui.set_options(dry_run=True)
        with mock.patch.object(host, "CAN_IFACE_FILE", str(f)):
            host.stage_can(self.env, Options(dry_run=True), self.hw(), r)
        t = self.out.getvalue()
        self.assertIn("создаю %s (по гайду)" % f, t)
        self.assertIn("[dry-run] sudo tee %s <<< 'allow-hotplug can0\niface can0 can static\n" % f, t)
        self.assertNotIn("modprobe", t)                               # в dry-run modprobe молчит (как в bash)
        ui.set_options(dry_run=False)
        r = FakeRunner()

        def install(argv):
            Path(argv[-1]).write_text(Path(argv[-2]).read_text())
            return ""
        r.on(("sudo", "install"), 0, install)
        with mock.patch.object(host, "CAN_IFACE_FILE", str(f)):
            host.stage_can(self.env, Options(), self.hw(), r)
        self.assertEqual(f.read_text(), host.CAN_IFACE_BODY)
        self.assertIn(("sudo", "modprobe", "-a", "can", "can_raw", "gs_usb"), r.calls)
        # уже настроен - не пересоздаётся
        r2 = FakeRunner()
        with mock.patch.object(host, "CAN_IFACE_FILE", str(f)):
            host.stage_can(self.env, Options(), self.hw(), r2)
        self.assertEqual(r2.called("sudo", "install"), 0)
        self.assertIn("уже настроен", self.out.getvalue())

    def test_networkd_when_no_ifupdown(self):
        r = FakeRunner(dry_run=True, default_rc=1)                    # dpkg -s ifupdown: нет
        host.stage_can(self.env, Options(dry_run=True), self.hw(), r)
        self.assertIn("ifupdown не установлен: настраиваю systemd-networkd", self.out.getvalue())
        self.assertIn("[dry-run] /etc/systemd/network/80-can0.network + .link", self.out.getvalue())
        written = {}
        r = FakeRunner(default_rc=1)
        r.on(("sudo", "install"), 0, lambda a: written.__setitem__(a[-1], Path(a[-2]).read_text()) or "")
        host.stage_can(self.env, Options(), self.hw(), r)
        self.assertEqual(written[host.NETWORKD_NETWORK], "[Match]\nName=can0\n\n[CAN]\nBitRate=1M\n")
        self.assertEqual(written[host.NETWORKD_LINK], "[Match]\nOriginalName=can0\n\n[Link]\nTransmitQueueLength=128\n")
        self.assertIn(("sudo", "systemctl", "enable", "systemd-networkd"), r.calls)


class TestMoonrakerWait(unittest.TestCase):
    def test_wait(self):
        moon = mock.Mock()
        moon.fetch.side_effect = [None, None, "{}"]
        up = mock.Mock(moon=moon)
        with mock.patch.object(host.time, "sleep"):
            self.assertTrue(host.wait_moonraker(up))
        self.assertTrue(moon.ok)
        moon.fetch.side_effect = None
        moon.fetch.return_value = None
        with mock.patch.object(host.time, "sleep"):
            self.assertFalse(host.wait_moonraker(up, tries=3))
        self.assertFalse(moon.ok)


if __name__ == "__main__":
    unittest.main()
