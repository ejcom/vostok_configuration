"""Тесты vostok.integrations: кнопка Fluidd, тема Fluidd, тема KlipperScreen.

Файлы - во временном каталоге, sudo/systemctl/apt - через заглушку Runner, Moonraker - через заглушку http.
Реальный ~/printer_data и реальные службы не трогаются.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from vostok import INSTALL_DIR, VostokError, integrations as ig, ui  # noqa: E402


class FakeRunner:
    """Заглушка system.Runner: записывает вызовы, ничего не выполняет."""

    def __init__(self, dry_run=False, returncodes=None, outputs=None):
        self.dry_run = dry_run
        self.calls = []
        self.returncodes = returncodes or {}
        self.outputs = outputs or {}
        self.systemctl_ok = True

    def _cp(self, argv):
        text = " ".join(argv)
        rc = 0
        for key, val in self.returncodes.items():
            if key in text:
                rc = val
        return subprocess.CompletedProcess(argv, rc, self.outputs.get(text, ""), "")

    def run(self, cmd, *, sudo=False, check=True, capture=False, **kw):
        argv = list(cmd)
        if sudo:
            argv = ["sudo"] + argv
        self.calls.append(argv)
        cp = self._cp(argv)
        if check and cp.returncode != 0:
            raise VostokError("fail: " + " ".join(argv))
        return cp

    def sudo(self, cmd, **kw):
        return self.run(cmd, sudo=True, **kw)

    def capture(self, cmd, **kw):
        self.calls.append(list(cmd))
        return self.outputs.get(" ".join(cmd), "")

    def systemctl(self, action, unit):
        self.calls.append(["systemctl", action, unit])
        return self.systemctl_ok

    def texts(self):
        return [" ".join(c) for c in self.calls]


class FakeMoonraker:
    """Заглушка http_request: база данных Moonraker в памяти."""

    def __init__(self, theme=None, alive=True):
        self.theme = theme
        self.alive = alive
        self.log = []

    def __call__(self, method, url, data=None, timeout=5):
        self.log.append((method, url))
        if not self.alive:
            return None
        if url.endswith("/server/info"):
            return b"{}"
        if method == "GET":
            if self.theme is None:
                return None
            return json.dumps({"result": {"value": self.theme}}).encode()
        if method == "POST":
            self.theme = json.loads(data.decode())["value"]
            return b"{}"
        if method == "DELETE":
            self.theme = None
            return b"{}"
        return None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        ui.set_options(yes=True)
        self.addCleanup(ui.set_options)
        p = mock.patch("os.geteuid", return_value=1000)
        p.start()
        self.addCleanup(p.stop)

    def call(self, fn, *a, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = fn(*a, **kw)
        return rc, out.getvalue(), err.getvalue()

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def baks(self, pattern):
        return sorted(self.dir.glob(pattern + ".bak-*"))


class ParseTest(Base):
    def test_help_version_errors(self):
        rc, out, _ = self.call(ig.main_theme, ["-h"])
        self.assertEqual((rc, out), (0, ig.USAGE_THEME))
        rc, out, _ = self.call(ig.main_button, ["--version"])
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("VOSTOK installer "))
        with self.assertRaises(VostokError) as e:
            self.call(ig.main_ks_theme, ["--ks-dir"])
        self.assertEqual(str(e.exception), "--ks-dir требует аргумент")
        with self.assertRaises(VostokError) as e:
            self.call(ig.main_theme, ["-y", "--zzz"])
        self.assertEqual(str(e.exception), "неизвестная опция: --zzz")

    def test_help_before_bad_option(self):
        rc, out, _ = self.call(ig.main_button, ["-h", "--zzz"])
        self.assertEqual((rc, out), (0, ig.USAGE_BUTTON))


class FluiddThemeTest(Base):
    def setUp(self):
        super().setUp()
        self.pd = self.dir / "pd"
        (self.pd / "config").mkdir(parents=True)
        self.fd = self.dir / "fluidd"
        self.fd.mkdir()
        self.cfg = self.write("fluidd/config.json", '{"x": 1, "themePresets": [{"name": "other"}]}')
        self.moon = FakeMoonraker()

    def theme(self, **kw):
        o = ig.FluiddThemeOptions(printer_data=str(self.pd), fluidd_dir=str(self.fd),
                                  moonraker_url="http://m", yes=True, **kw)
        return ig.FluiddTheme(o, http=self.moon, prog="./install_fluidd_theme.sh")

    def presets(self):
        return json.loads(self.cfg.read_text(encoding="utf-8"))["themePresets"]

    def test_install_and_repeat(self):
        rc, out, _ = self.call(self.theme().run)
        self.assertEqual(rc, 0)
        tdir = self.pd / "config" / ".fluidd-theme"
        self.assertTrue((tdir / "logo_vostok.svg").is_file())
        self.assertIn("VOSTOK-THEME", (tdir / "custom.css").read_text(encoding="utf-8").split("\n")[0])
        self.assertEqual([p["name"] for p in self.presets()], ["other", "K3D VOSTOK"])
        self.assertEqual(self.presets()[1]["logo"]["src"], "server/files/config/.fluidd-theme/logo_vostok.svg")
        self.assertEqual(len(self.baks("fluidd/config.json")), 1)
        self.assertEqual(self.moon.theme["color"], "#009B98")
        self.assertTrue(self.moon.theme["backgroundLogo"])
        self.assertIn("тема включена", out)
        self.assertIn("Удалить: ./install_fluidd_theme.sh --uninstall", out)
        # повтор: пресет не меняется, новой копии нет
        rc, out, _ = self.call(self.theme().run)
        self.assertIn("без изменений", out)
        self.assertEqual(len(self.baks("fluidd/config.json")), 1)

    def test_logo_copy(self):
        self.call(self.theme(logo_copy=True, activate=False).run)
        self.assertTrue((self.fd / "logo_vostok.svg").is_file())
        self.assertEqual(self.presets()[1]["logo"]["src"], "logo_vostok.svg")
        self.assertIsNone(self.moon.theme)
        self.call(self.theme(uninstall=True, activate=False).run)
        self.assertFalse((self.fd / "logo_vostok.svg").exists())

    def test_foreign_css_not_overwritten_without_force(self):
        css = self.write("pd/config/.fluidd-theme/custom.css", "/* чужой */\nbody{}\n")
        rc, out, err = self.call(self.theme(activate=False).run)
        self.assertEqual(css.read_text(encoding="utf-8"), "/* чужой */\nbody{}\n")
        self.assertIn("создан не нами", err)
        self.assertEqual(self.baks("pd/config/.fluidd-theme/custom.css"), [])

    def test_foreign_css_force_makes_backup(self):
        css = self.write("pd/config/.fluidd-theme/custom.css", "/* чужой */\nbody{}\n")
        self.call(self.theme(activate=False, force=True).run)
        self.assertIn("VOSTOK-THEME", css.read_text(encoding="utf-8"))
        baks = self.baks("pd/config/.fluidd-theme/custom.css")
        self.assertEqual(len(baks), 1)
        self.assertEqual(baks[0].read_text(encoding="utf-8"), "/* чужой */\nbody{}\n")

    def test_foreign_theme_with_yes_is_replaced_like_bash(self):
        # 1:1 с bash: confirm() при -y отвечает «да», тема заменяется (в KlipperScreen иначе)
        self.moon.theme = {"logo": {"src": "x/other.svg"}}
        self.call(self.theme().run)
        self.assertEqual(self.moon.theme["logo"]["src"], "server/files/config/.fluidd-theme/logo_vostok.svg")

    def test_foreign_theme_declined_without_tty(self):
        self.moon.theme = {"logo": {"src": "x/other.svg"}}
        ui.set_options(yes=False)
        o = ig.FluiddThemeOptions(printer_data=str(self.pd), fluidd_dir=str(self.fd), moonraker_url="http://m")
        with mock.patch("os.access", return_value=False):
            rc, out, err = self.call(ig.FluiddTheme(o, http=self.moon).run)
        self.assertEqual(rc, 0)
        self.assertIn("тему не меняю", err)
        self.assertEqual(self.moon.theme["logo"]["src"], "x/other.svg")
        self.assertNotIn(("POST", "http://m/server/database/item"), self.moon.log)

    def test_dry_run_writes_nothing(self):
        self.moon.theme = {"logo": {"src": "x/other.svg"}}
        rc, out, _ = self.call(self.theme(dry_run=True).run)
        self.assertFalse((self.pd / "config" / ".fluidd-theme").exists())
        self.assertEqual(self.presets(), [{"name": "other"}])
        self.assertIn("[dry-run] POST http://m/server/database/item ", out)
        self.assertEqual([m for m, _u in self.moon.log if m != "GET"], [])

    def test_uninstall(self):
        self.call(self.theme().run)
        rc, out, _ = self.call(self.theme(uninstall=True).run)
        self.assertEqual(rc, 0)
        self.assertEqual(self.presets(), [{"name": "other"}])
        self.assertFalse((self.pd / "config" / ".fluidd-theme").exists())
        self.assertIsNone(self.moon.theme)
        self.assertIn("активная тема сброшена на стандартную", out)

    def test_uninstall_keeps_foreign_css_and_theme(self):
        css = self.write("pd/config/.fluidd-theme/custom.css", "/* чужой */\n")
        self.moon.theme = {"logo": {"src": "x/other.svg"}}
        self.call(self.theme(uninstall=True).run)
        self.assertTrue(css.is_file())
        self.assertEqual(self.moon.theme["logo"]["src"], "x/other.svg")

    def test_checks(self):
        self.cfg.write_text("{bad", encoding="utf-8")
        with self.assertRaises(VostokError) as e:
            self.call(self.theme(activate=False).run)
        self.assertIn("не разобрать как JSON", str(e.exception))
        self.cfg.write_text("{}", encoding="utf-8")
        self.moon.alive = False
        with self.assertRaises(VostokError) as e:
            self.call(self.theme().run)
        self.assertIn("Moonraker недоступен (http://m), либо запустите с --no-activate", str(e.exception))
        self.cfg.unlink()
        with self.assertRaises(VostokError) as e:
            self.call(self.theme(activate=False).run)
        self.assertIn("Fluidd не установлен?", str(e.exception))

    def test_db_write_failure(self):
        class Flaky(FakeMoonraker):
            def __call__(s, method, url, data=None, timeout=5):
                return None if method == "POST" else FakeMoonraker.__call__(s, method, url, data, timeout)
        self.moon = Flaky()
        with self.assertRaises(VostokError) as e:
            self.call(self.theme().run)
        self.assertEqual(str(e.exception), "не удалось записать тему в базу Moonraker")

    def test_root_refused(self):
        with mock.patch("os.geteuid", return_value=0):
            with self.assertRaises(VostokError):
                self.call(self.theme().run)


class KsConfTest(Base):
    SAVED = ("\n#~# --- Do not edit below this line. This section is auto generated --- #~#\n"
             "#~#\n#~# [main]\n#~# theme = %s\n")

    def edit(self, text, mode="set"):
        p = self.write("KlipperScreen.conf", text)
        res = ig.edit_ks_conf(p, mode, "vostok", "material-dark")
        return res, p.read_text(encoding="utf-8")

    def test_set_variants(self):
        res, text = self.edit("[main]\ntheme = base\n")
        self.assertEqual((res, text), (("base", "обновлён"), "[main]\ntheme = vostok\n"))
        # двоеточие: bash-код не видит значение, возвращает базовую тему и заменяет строку
        res, text = self.edit("[main]\ntheme: material-dark\n")
        self.assertEqual((res, text), (("material-dark", "обновлён"), "[main]\ntheme = vostok\n"))
        res, text = self.edit("[other]\na = 1\n")
        self.assertEqual(text, "[main]\ntheme = vostok\n\n[other]\na = 1\n")
        res, text = self.edit("[main]\nlanguage = ru")
        self.assertEqual(text, "[main]\ntheme = vostok\nlanguage = ru\n")
        res, text = self.edit("[main]\nlanguage = ru\n" + self.SAVED % "base")
        self.assertEqual(res, ("base", "обновлён"))
        self.assertIn("#~# theme = vostok", text)
        self.assertTrue(text.startswith("[main]\nlanguage = ru\n"))

    def test_same_and_reset(self):
        res, _ = self.edit("[main]\ntheme = vostok\n")
        self.assertEqual(res, ("vostok", "без изменений"))
        res, text = self.edit("[main]\ntheme = vostok\n", "reset")
        self.assertEqual((res[1], text), ("обновлён", "[main]\ntheme = material-dark\n"))
        res, text = self.edit("[main]\ntheme = other\n", "reset")
        self.assertEqual((res, text), (("other", "без изменений"), "[main]\ntheme = other\n"))

    def test_backup_and_new_file(self):
        self.edit("[main]\ntheme = base\n")
        self.assertEqual(len(self.baks("KlipperScreen.conf")), 1)
        p = self.dir / "new" / "KlipperScreen.conf"
        p.parent.mkdir()
        res = ig.edit_ks_conf(p, "set", "vostok", "material-dark")
        self.assertEqual(res, ("material-dark", "обновлён"))
        self.assertEqual(p.read_text(encoding="utf-8"), "[main]\ntheme = vostok\n\n")
        self.assertEqual(list(p.parent.glob("*.bak-*")), [])

    def test_current_theme(self):
        p = self.write("c.conf", "[main]\ntheme: abc\n" + self.SAVED % "xyz")
        self.assertEqual(ig.current_ks_theme(p), "xyz")
        p = self.write("c.conf", "[other]\ntheme = no\n[main]\ntheme: abc\n")
        self.assertEqual(ig.current_ks_theme(p), "abc")
        self.assertEqual(ig.current_ks_theme(self.dir / "none.conf"), "")


class KsThemeTest(Base):
    def setUp(self):
        super().setUp()
        self.pd = self.dir / "pd"
        (self.pd / "config").mkdir(parents=True)
        self.write("ks/styles/material-dark/images/a.svg", "<svg/>")
        self.fonts = self.dir / "fonts"
        self.runner = FakeRunner()

    def theme(self, **kw):
        o = ig.KsThemeOptions(printer_data=str(self.pd), ks_dir=str(self.dir / "ks"), font_dir=str(self.fonts),
                              yes=True, **kw)
        return ig.KlipperScreenTheme(o, runner=self.runner, prog="/x/install_klipperscreen_theme.sh")

    def conf(self):
        return (self.pd / "config" / "KlipperScreen.conf")

    def test_install_uninstall(self):
        self.write("pd/config/KlipperScreen.conf", "[main]\ntheme = material-dark\n")
        with mock.patch("shutil.which", return_value="/usr/bin/fc-cache"):
            rc, out, _ = self.call(self.theme().run)
            dst = self.dir / "ks" / "styles" / "vostok"
            self.assertTrue((dst / "style.css").is_file())
            self.assertTrue((dst / "images" / "a.svg").is_file())
            self.assertTrue((dst / "images" / "klipper.svg").is_file())
            self.assertFalse(Path(str(dst) + ".new").exists())
            self.assertIn("theme = vostok", self.conf().read_text(encoding="utf-8"))
            self.assertIn("(была тема: material-dark)", out)
            self.assertTrue((self.fonts / "Tektur-OFL.txt").is_file())
            self.assertEqual(self.runner.texts(), ["fc-cache -f %s" % self.fonts])
            # повтор безопасен
            self.call(self.theme().run)
            rc, out, _ = self.call(self.theme(uninstall=True).run)
        self.assertEqual(rc, 0)
        self.assertFalse(dst.exists())
        self.assertIn("theme = material-dark", self.conf().read_text(encoding="utf-8"))
        # как в bash: Tektur-OFL.txt при удалении остаётся
        self.assertEqual([p.name for p in self.fonts.iterdir()], ["Tektur-OFL.txt"])

    def test_foreign_theme_with_yes_not_changed(self):
        self.write("pd/config/KlipperScreen.conf", "[main]\ntheme = other\n")
        with mock.patch("shutil.which", return_value=None):
            rc, out, err = self.call(self.theme().run)
        self.assertEqual(rc, 0)
        self.assertIn('тему не меняю; выберите "vostok"', err)
        self.assertIn("theme = other", self.conf().read_text(encoding="utf-8"))
        self.assertTrue((self.dir / "ks" / "styles" / "vostok").is_dir())

    def test_foreign_theme_force(self):
        self.write("pd/config/KlipperScreen.conf", "[main]\ntheme = other\n")
        with mock.patch("shutil.which", return_value=None):
            self.call(self.theme(force=True).run)
        self.assertIn("theme = vostok", self.conf().read_text(encoding="utf-8"))
        self.assertEqual(len(self.baks("pd/config/KlipperScreen.conf")), 1)

    def test_foreign_dir(self):
        self.write("ks/styles/vostok/style.css", "чужой\n")
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(VostokError) as e:
                self.call(self.theme().run)
            self.assertIn("создан не нами (используйте --force", str(e.exception))
            rc, out, err = self.call(self.theme(uninstall=True).run)
            self.assertIn("создан не нами, не удаляю", err)
            self.assertTrue((self.dir / "ks" / "styles" / "vostok" / "style.css").is_file())
            self.call(self.theme(force=True, activate=False).run)
        self.assertIn("VOSTOK-THEME", (self.dir / "ks" / "styles" / "vostok" / "style.css").read_text().split("\n")[0])

    def test_dry_run(self):
        self.write("pd/config/KlipperScreen.conf", "[main]\ntheme = material-dark\n")
        with mock.patch("shutil.which", return_value="/usr/bin/fc-cache"):
            rc, out, _ = self.call(self.theme(dry_run=True).run)
        self.assertFalse((self.dir / "ks" / "styles" / "vostok").exists())
        self.assertFalse(self.fonts.exists())
        self.assertEqual(self.runner.calls, [])
        self.assertIn("[dry-run] theme = vostok в", out)
        self.assertIn("Удалить: /x/install_klipperscreen_theme.sh --uninstall", out)

    def test_missing_base_theme(self):
        o = ig.KsThemeOptions(printer_data=str(self.pd), ks_dir=str(self.dir / "nope"), font_dir=str(self.fonts))
        with self.assertRaises(VostokError) as e:
            self.call(ig.KlipperScreenTheme(o, runner=self.runner).run)
        self.assertIn("KlipperScreen не установлен? (--ks-dir)", str(e.exception))


class ButtonTest(Base):
    def setUp(self):
        super().setUp()
        self.pd = self.dir / "pd"
        (self.pd / "config").mkdir(parents=True)
        (self.dir / "klipper" / ".git").mkdir(parents=True)
        self.write("katapult/scripts/flashtool.py", "")
        self.units = self.dir / "systemd"
        self.units.mkdir()
        self.runner = FakeRunner()
        self.query = FakeRunner(outputs={
            "systemctl list-unit-files moonraker*.service --no-legend": "moonraker.service enabled\n"})
        self.moon = FakeMoonraker()
        self.managed = True

    def button(self, **kw):
        o = ig.ButtonOptions(printer_data=str(self.pd), klipper_dir=str(self.dir / "klipper"),
                             katapult_dir=str(self.dir / "katapult"), moonraker_url="http://m", yes=True, **kw)
        return ig.FluiddButton(o, runner=self.runner, query_runner=self.query, unit_dir=str(self.units),
                               sudoers_dir=str(self.dir / "sudoers.d"), http=self.moon,
                               can_manage=lambda allow_sudo: self.managed)

    @contextlib.contextmanager
    def env(self, have=("systemctl", "arm-none-eabi-gcc", "make"), serial=True):
        with mock.patch("shutil.which", side_effect=lambda n: "/usr/bin/" + n if n in have else None), \
                mock.patch.object(ig.FluiddButton, "_have_serial", staticmethod(lambda: serial)):
            yield

    def test_render_unit(self):
        b = self.button(flash_args="--no-update --force-flash")
        text = b.render_unit()
        self.assertIn("ExecStart=%s/update_klipper_mcu.sh -y --no-update --force-flash\n" % INSTALL_DIR, text)
        self.assertIn("Environment=PRINTER_DATA=%s\n" % self.pd, text)
        self.assertTrue(text.endswith("TimeoutStartSec=30min\n"))
        self.assertNotIn("@", text)
        self.assertIn("ExecStart=%s/update_klipper_mcu.sh -y \n" % INSTALL_DIR, self.button().render_unit())

    def test_install_polkit(self):
        with self.env():
            rc, out, err = self.call(self.button(with_macro=True).run)
        self.assertEqual(rc, 0)
        self.assertEqual(self.query.texts()[0], "%s/update_klipper_mcu.sh --list" % INSTALL_DIR)
        t = self.runner.texts()
        self.assertEqual(t[0].split()[:3], ["sudo", "install", "-m"])
        self.assertTrue(t[0].endswith(str(self.units / "mcu-update.service")))
        self.assertIn("sudo systemctl daemon-reload", t)
        self.assertNotIn("visudo", " ".join(t))
        self.assertEqual((self.pd / "moonraker.asvc").read_text(encoding="utf-8"), "mcu-update\n")
        # drop-in для moonraker.service и перезапуск Moonraker
        self.assertTrue(any("install -d -m 0755 %s/moonraker.service.d" % self.units in x for x in t))
        self.assertTrue(any(x.endswith("%s/moonraker.service.d/mcu-update.conf" % self.units) for x in t))
        self.assertEqual(t[-1], "systemctl restart moonraker")
        macro = (self.pd / "config" / "mcu_update.cfg").read_text(encoding="utf-8")
        self.assertIn("command: systemctl --no-ask-password start --no-block mcu-update", macro)
        self.assertIn("[gcode_macro MCU_UPDATE]", macro)
        self.assertIn("нет gcode_shell_command.py", err)

    def test_existing_asvc_and_dropin_not_duplicated(self):
        (self.pd / "moonraker.asvc").write_text("klipper\nmoonraker", encoding="utf-8")
        d = self.units / "moonraker.service.d"
        d.mkdir()
        (d / "mcu-update.conf").write_text("[Unit]\nAfter=mcu-update.service\n", encoding="utf-8")
        with self.env():
            self.call(self.button().run)
        self.assertEqual((self.pd / "moonraker.asvc").read_text(encoding="utf-8"), "klipper\nmoonraker\nmcu-update\n")
        t = self.runner.texts()
        self.assertFalse(any("mcu-update.conf" in x for x in t))
        # asvc изменён - Moonraker перезапускается
        self.assertEqual(t[-1], "systemctl restart moonraker")
        self.runner.calls.clear()
        with self.env():
            rc, out, _ = self.call(self.button().run)
        self.assertIn("mcu-update уже есть в", out)
        self.assertNotIn("systemctl restart moonraker", self.runner.texts())

    def test_install_sudoers_when_no_polkit(self):
        self.managed = False
        with self.env():
            rc, out, err = self.call(self.button().run)
        t = self.runner.texts()
        self.assertTrue(any(x.startswith("sudo visudo -cf ") for x in t))
        inst = [x for x in t if x.startswith("sudo install -m 0440 -o root -g root ")]
        self.assertEqual(len(inst), 1)
        self.assertTrue(inst[0].endswith(str(self.dir / "sudoers.d" / "mcu-update")))
        self.assertIn("polkit не разрешает управлять сервисами", err)

    def test_visudo_failure(self):
        self.managed = False
        self.runner.returncodes = {"visudo": 1}
        with self.env():
            with self.assertRaises(VostokError) as e:
                self.call(self.button().run)
        self.assertEqual(str(e.exception), "sudoers-правило не прошло visudo")
        self.assertFalse(any("install -m 0440" in x for x in self.runner.texts()))

    def test_dry_run_changes_nothing(self):
        self.managed = False
        self.runner.dry_run = True
        with self.env():
            rc, out, _ = self.call(self.button(dry_run=True, with_macro=True).run)
        self.assertEqual(self.runner.calls, [])
        self.assertFalse((self.pd / "moonraker.asvc").exists())
        self.assertFalse((self.pd / "config" / "mcu_update.cfg").exists())
        self.assertIn("[dry-run] %s/mcu-update.service:" % self.units, out)
        self.assertIn("[dry-run] добавить mcu-update в", out)
        self.assertIn("[dry-run] %s/moonraker.service.d/mcu-update.conf: After=mcu-update.service" % self.units, out)

    def test_missing_packages(self):
        with self.env(have=("systemctl",), serial=False):
            rc, out, err = self.call(self.button().run)
        self.assertIn("не хватает пакетов: gcc-arm-none-eabi make python3-serial", err)
        self.assertIn(["sudo", "apt", "install", "-y", "gcc-arm-none-eabi", "make", "python3-serial"],
                      self.runner.calls)
        self.runner.calls.clear()
        with self.env(have=("systemctl",)):
            self.call(self.button(dry_run=True).run)
        self.assertNotIn("apt", " ".join(" ".join(c) for c in self.runner.calls))

    def test_checks_errors(self):
        with self.env():
            self.moon.alive = False
            with self.assertRaises(VostokError) as e:
                self.call(self.button().run)
            self.assertEqual(str(e.exception), "Moonraker недоступен (http://m)")
            self.moon.alive = True
            (self.dir / "katapult" / "scripts" / "flashtool.py").unlink()
            with self.assertRaises(VostokError) as e:
                self.call(self.button().run)
            self.assertIn("(KATAPULT_DIR)", str(e.exception))
        with self.env(have=("make",)):
            self.write("katapult/scripts/flashtool.py", "")
            with self.assertRaises(VostokError) as e:
                self.call(self.button().run)
            self.assertEqual(str(e.exception), "нет systemctl")

    def test_list_failure_warns(self):
        self.query.returncodes = {"--list": 1}
        with self.env():
            rc, out, err = self.call(self.button().run)
        self.assertEqual(rc, 0)
        self.assertIn("--list завершился с ошибкой, посмотрите вывод выше", err)

    def test_uninstall(self):
        (self.units / "mcu-update.service").write_text("x", encoding="utf-8")
        d = self.units / "moonraker.service.d"
        d.mkdir()
        (d / "mcu-update.conf").write_text("x", encoding="utf-8")
        (self.pd / "moonraker.asvc").write_text("klipper\nmcu-update\nmoonraker", encoding="utf-8")
        self.write("pd/config/mcu_update.cfg", "x")
        rc, out, err = self.call(self.button(uninstall=True).run)
        self.assertEqual(rc, 0)
        t = self.runner.texts()
        self.assertEqual(t[:3], ["sudo systemctl stop mcu-update",
                                 "sudo rm -f %s/mcu-update.service" % self.units, "sudo systemctl daemon-reload"])
        self.assertIn("sudo rmdir --ignore-fail-on-non-empty %s" % d, t)
        self.assertEqual(t[-1], "systemctl restart moonraker")
        self.assertEqual((self.pd / "moonraker.asvc").read_text(encoding="utf-8"), "klipper\nmoonraker\n")
        self.assertIn("mcu_update.cfg не удалён", err)

    def test_uninstall_stop_failure_ignored(self):
        (self.units / "mcu-update.service").write_text("x", encoding="utf-8")
        self.runner.returncodes = {"stop mcu-update": 5}
        rc, out, _ = self.call(self.button(uninstall=True).run)
        self.assertEqual(rc, 0)

    def test_uninstall_dry_run(self):
        self.runner.dry_run = True
        (self.pd / "moonraker.asvc").write_text("mcu-update\n", encoding="utf-8")
        rc, out, _ = self.call(self.button(uninstall=True, dry_run=True).run)
        self.assertEqual((self.pd / "moonraker.asvc").read_text(encoding="utf-8"), "mcu-update\n")
        self.assertIn("[dry-run] удалить строку mcu-update из", out)
        self.assertEqual(self.runner.calls, [])


if __name__ == "__main__":
    unittest.main()
