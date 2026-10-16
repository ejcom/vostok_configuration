"""Тесты vostok.ui: тексты, цвета, лог-файл, вопросы (ввод подменяется)."""
import contextlib
import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from vostok import UserAbort, VostokError, ui  # noqa: E402


class TtyStream(io.StringIO):
    def isatty(self):
        return True


class UiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "logs" / "x.log"
        ui.set_options(yes=False, dry_run=False, log_file=self.log)
        self.addCleanup(ui.set_options)

    def capture(self, fn, *a, tty=False, **kw):
        out, err = (TtyStream(), TtyStream()) if tty else (io.StringIO(), io.StringIO())
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            res = fn(*a, **kw)
        return res, out.getvalue(), err.getvalue()

    def log_lines(self):
        return self.log.read_text(encoding="utf-8").splitlines()

    def test_plain_messages(self):
        _, out, err = self.capture(ui.info, "привет")
        self.assertEqual((out, err), ("привет\n", ""))
        _, out, err = self.capture(ui.ok, "готово")
        self.assertEqual((out, err), ("готово\n", ""))
        _, out, err = self.capture(ui.warn, "осторожно")
        self.assertEqual((out, err), ("", "ВНИМАНИЕ: осторожно\n"))
        _, out, err = self.capture(ui.error, "плохо")
        self.assertEqual((out, err), ("", "ОШИБКА: плохо\n"))
        _, out, err = self.capture(ui.step, "Этап")
        self.assertEqual((out, err), ("\n== Этап ==\n", ""))

    def test_colors_when_tty(self):
        _, out, _ = self.capture(ui.ok, "ok", tty=True)
        self.assertEqual(out, "\033[92mok\033[0m\n")
        _, _, err = self.capture(ui.warn, "w", tty=True)
        self.assertEqual(err, "\033[93mВНИМАНИЕ: w\033[0m\n")
        _, _, err = self.capture(ui.error, "e", tty=True)
        self.assertEqual(err, "\033[91mОШИБКА: e\033[0m\n")
        _, out, _ = self.capture(ui.info, "i", tty=True)
        self.assertEqual(out, "i\n")

    def test_log_format(self):
        self.capture(ui.info, "a")
        self.capture(ui.ok, "b")
        self.capture(ui.warn, "c")
        self.capture(ui.error, "d")
        self.capture(ui.step, "e")
        lines = self.log_lines()
        for ln in lines:
            self.assertRegex(ln, r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")
        self.assertEqual([ln[20:] for ln in lines], ["a", "OK: b", "ВНИМАНИЕ: c", "ОШИБКА: d", "== e =="])

    def test_no_log_file(self):
        ui.set_options(log_file=None)
        self.capture(ui.info, "x")
        self.assertFalse(self.log.exists())

    def test_log_unwritable_is_silent(self):
        ui.set_options(log_file=Path("/proc/nonexistent/x.log"))
        self.capture(ui.info, "x")

    def test_die(self):
        with self.assertRaises(VostokError) as cm:
            ui.die("всё плохо")
        self.assertEqual(str(cm.exception), "всё плохо")
        self.assertTrue(issubclass(UserAbort, VostokError))

    # ------------------------------------------------------------ вопросы

    def answers(self, *ans):
        it = iter(ans)
        prompts = []

        def fake(prompt):
            prompts.append(prompt)
            return next(it)
        return fake, prompts

    def test_ask_yn(self):
        fake, prompts = self.answers("y", "Y", "д", "Д", "yes", "n", "", "нет", "x")
        with mock.patch.object(ui, "_read_tty", fake), mock.patch.object(ui, "need_tty"):
            got = [ui.ask_yn("Q?") for _ in range(4)] + [ui.ask_yn("Q?"), ui.ask_yn("Q?"), ui.ask_yn("Q?"),
                                                           ui.ask_yn("Q?", "y"), ui.ask_yn("Q?")]
        self.assertEqual(got, [True, True, True, True, True, False, False, False, False])
        self.assertEqual(prompts[0], "Q? [y/N] ")
        fake, prompts = self.answers("", "")
        with mock.patch.object(ui, "_read_tty", fake), mock.patch.object(ui, "need_tty"):
            self.assertTrue(ui.ask_yn("Q?", "y"))
        self.assertEqual(prompts, ["Q? [Y/n] "])

    def test_ask_yn_assume_yes(self):
        ui.set_options(yes=True)
        with mock.patch.object(ui, "_read_tty", side_effect=AssertionError("не должен спрашивать")):
            self.assertFalse(ui.ask_yn("Q?"))
            self.assertTrue(ui.ask_yn("Q?", "y"))
            self.assertTrue(ui.confirm("Q?"))
            self.assertEqual(ui.ask_choice("Q", "b", ["a", "b"]), "b")

    def test_need_tty(self):
        with mock.patch.object(ui, "have_tty", return_value=False):
            with self.assertRaises(VostokError) as cm:
                ui.ask_yn("Q?")
            self.assertEqual(str(cm.exception), "нужен терминал: установка просит переключать платы и нажимать Enter")

    def test_need_tty_uses_open_not_access(self):
        # M4: узел /dev/tty читаем и без управляющего терминала, поэтому решает реальный open()
        with mock.patch("os.access", return_value=True), mock.patch("builtins.open", side_effect=OSError(6, "ENXIO")):
            self.assertFalse(ui.have_tty())
            with self.assertRaises(VostokError):
                ui.need_tty()
            with self.assertRaises(VostokError) as cm:
                ui.confirm("Q")
            self.assertEqual(str(cm.exception), "нет терминала для подтверждения, используйте -y")

    def test_ask_choice(self):
        fake, prompts = self.answers("2", "", "0", "9", "x", "1")
        with mock.patch.object(ui, "_read_tty", fake), mock.patch.object(ui, "need_tty"):
            res, out, err = self.capture(ui.ask_choice, "Что выбрать?", "c", ["a", "b", "c"])
            self.assertEqual(res, "b")
            self.assertEqual(out, "")
            self.assertEqual(err, "Что выбрать?\n  1) a\n  2) b\n  3) c\n")
            self.assertEqual(self.capture(ui.ask_choice, "Q", "c", ["a", "b", "c"])[0], "c")
            res, _, err = self.capture(ui.ask_choice, "Q", "c", ["a", "b", "c"])
            self.assertEqual(res, "a")
            self.assertEqual(err.count("Введите число от 1 до 3\n"), 3)
        self.assertEqual(prompts[0], "Номер [по умолчанию: c]: ")

    def test_confirm(self):
        fake, prompts = self.answers("y", "n", "")
        with mock.patch.object(ui, "_read_tty", fake), mock.patch.object(ui, "have_tty", return_value=True):
            self.assertTrue(ui.confirm("Продолжить?"))
            self.assertFalse(ui.confirm("Продолжить?"))
            self.assertFalse(ui.confirm("Продолжить?"))
        self.assertEqual(prompts[0], "Продолжить? [y/N] ")
        with mock.patch.object(ui, "have_tty", return_value=False):
            with self.assertRaises(VostokError) as cm:
                ui.confirm("Q")
            self.assertEqual(str(cm.exception), "нет терминала для подтверждения, используйте -y")
            self.assertFalse(ui.confirm("Q", need=False))

    def test_pause_hw(self):
        fake, prompts = self.answers("", "s")
        with mock.patch.object(ui, "_read_tty", fake), mock.patch.object(ui, "need_tty"):
            res, out, _ = self.capture(ui.pause_hw, "Нажмите RESET")
            self.assertEqual((res, out), ("", "\n>>> Нажмите RESET\n"))
            res, out, _ = self.capture(ui.pause_hw, "DFU", allow_skip=True, tty=True)
            self.assertEqual((res, out), ("s", "\n\033[93m>>> DFU\033[0m\n"))
        self.assertEqual(prompts[0], "Нажмите Enter, когда готово: ")
        self.assertTrue(prompts[1].startswith("Enter - плата переведена в DFU; s + Enter - пропустить DFU"))
        self.assertIn("ЖДЁМ ПОЛЬЗОВАТЕЛЯ: Нажмите RESET", [ln[20:] for ln in self.log_lines()])

    def test_pause_hw_dry_run(self):
        ui.set_options(dry_run=True, log_file=self.log)
        with mock.patch.object(ui, "_read_tty", side_effect=AssertionError("не должен ждать")):
            res, out, _ = self.capture(ui.pause_hw, "Сделайте что-то")
        self.assertEqual((res, out), ("", "\n>>> Сделайте что-то\n[dry-run] ожидание Enter\n"))

    def test_pause_hw_no_tty(self):
        with mock.patch.object(ui, "have_tty", return_value=False):
            with self.assertRaises(VostokError):
                self.capture(ui.pause_hw, "x")

    def test_read_tty_eof_aborts(self):
        # /dev/tty в тестовой среде может отсутствовать: проверяем только разбор конца ввода
        m = mock.mock_open(read_data="")
        with mock.patch("builtins.open", m):
            with self.assertRaises(UserAbort):
                self.capture(ui._read_tty, "?")
        m = mock.mock_open(read_data="ответ\n")
        with mock.patch("builtins.open", m):
            self.assertEqual(self.capture(ui._read_tty, "?")[0], "ответ")


class CliTest(unittest.TestCase):
    """cli.main: диспетчеризация и обработка VostokError/UserAbort."""

    def run_cli(self, argv, commands):
        from vostok import cli
        err = io.StringIO()
        with mock.patch.dict(cli.COMMANDS, commands, clear=True), mock.patch.object(sys, "stderr", err):
            rc = cli.main(argv)
        return rc, err.getvalue()

    def test_dispatch(self):
        seen = []
        self.assertEqual(self.run_cli(["x", "-a", "b"], {"x": lambda a: seen.append(a) or 7})[0], 7)
        self.assertEqual(seen, [["-a", "b"]])
        self.assertEqual(self.run_cli(["x"], {"x": lambda a: None})[0], 0)

    def test_errors_exit_1(self):
        def boom(a):
            raise VostokError("сломалось")

        def abort(a):
            raise UserAbort("отказ")
        self.assertEqual(self.run_cli(["x"], {"x": boom}), (1, "ОШИБКА: сломалось\n"))
        self.assertEqual(self.run_cli(["x"], {"x": abort}), (1, "ОШИБКА: отказ\n"))

    def test_unknown(self):
        rc, err = self.run_cli(["nope"], {"x": lambda a: 0})
        self.assertEqual(rc, 2)
        self.assertIn("неизвестная команда", err)
        self.assertEqual(self.run_cli([], {})[0], 2)

    def test_isolated_import(self):
        import subprocess
        install = os.path.dirname(HERE)
        pr = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r); import vostok.cli, "
                             "vostok.ui, vostok.system, vostok.boards, vostok.state, vostok.cfgfile, vostok.can_uuid"
                             % install], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(pr.returncode, 0, pr.stderr)
        # python3 -m vostok при PYTHONPATH=installer (так будут вызывать обёртки); без команды - код 2
        env = dict(os.environ, PYTHONPATH=install)
        pr = subprocess.run([sys.executable, "-m", "vostok"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(pr.returncode, 2)


if __name__ == "__main__":
    unittest.main()
