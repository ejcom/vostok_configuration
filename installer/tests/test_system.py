"""Тесты vostok.system.Runner: dry-run, журнал, capture/tee, systemctl и sudo через заглушки в PATH."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from vostok import VostokError, system, ui  # noqa: E402


class SystemTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "run.log"
        ui.set_options(log_file=self.log)
        self.addCleanup(ui.set_options)
        self.bin = self.dir / "bin"
        self.bin.mkdir()

    def stub(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        p.chmod(0o755)

    @contextlib.contextmanager
    def path(self):
        with mock.patch.dict(os.environ, {"PATH": "%s:%s" % (self.bin, os.environ["PATH"])}):
            yield

    def out(self, fn, *a, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = fn(*a, **kw)
        return res, buf.getvalue()

    def log_lines(self):
        return [ln[20:] for ln in self.log.read_text(encoding="utf-8").splitlines()]

    def test_dry_run_prints_and_does_not_run(self):
        marker = self.dir / "marker"
        r = system.Runner(dry_run=True)
        cp, out = self.out(r.run, ["touch", str(marker)])
        self.assertEqual((cp.returncode, cp.stdout), (0, ""))
        self.assertEqual(out, "[dry-run] touch %s\n" % marker)
        self.assertFalse(marker.exists())
        cp, out = self.out(r.sudo, ["systemctl", "restart", "klipper"])
        self.assertEqual(out, "[dry-run] sudo systemctl restart klipper\n")
        self.assertEqual(self.out(r.capture, ["echo", "x"])[0], "")
        self.assertNotIn("$ touch", "\n".join(self.log_lines()))  # в dry-run строка журнала - обычный info

    def test_dry_run_from_ui_options(self):
        r = system.Runner()
        ui.set_options(dry_run=True, log_file=self.log)
        self.assertEqual(self.out(r.run, ["echo", "a b"])[1], "[dry-run] echo a b\n")
        ui.set_options(dry_run=False, log_file=self.log)
        self.assertEqual(r.run(["true"]).returncode, 0)

    def test_run_logs_command(self):
        r = system.Runner(dry_run=False)
        r.run(["true"])
        r.run("echo hi", capture=True)
        self.assertEqual(self.log_lines(), ["$ true", "$ echo hi"])

    def test_capture(self):
        r = system.Runner(dry_run=False)
        self.assertEqual(r.capture(["printf", "a\nb\n\n"]), "a\nb")
        cp = r.run(["echo", "x"], capture=True)
        self.assertEqual(cp.stdout, "x\n")

    def test_check_raises(self):
        r = system.Runner(dry_run=False)
        with self.assertRaises(system.CommandError) as cm:
            r.run(["sh", "-c", "echo out; exit 3"], capture=True)
        self.assertEqual(cm.exception.returncode, 3)
        self.assertEqual(cm.exception.stdout, "out\n")
        self.assertIn("кодом 3", str(cm.exception))
        self.assertIsInstance(cm.exception, VostokError)
        self.assertEqual(r.run(["false"], check=False).returncode, 1)

    def test_missing_command(self):
        r = system.Runner(dry_run=False)
        self.assertEqual(r.run(["definitely-not-a-command-xyz"], check=False).returncode, 127)
        with self.assertRaises(system.CommandError):
            r.run(["definitely-not-a-command-xyz"])

    def test_env_and_cwd(self):
        r = system.Runner(dry_run=False)
        self.assertEqual(r.capture(["sh", "-c", "echo $VOSTOK_T"], env={"VOSTOK_T": "42"}), "42")
        self.assertEqual(r.capture(["pwd"], cwd=str(self.dir)), os.path.realpath(str(self.dir)))
        self.assertNotIn("VOSTOK_T", os.environ)

    def test_tee(self):
        r = system.Runner(dry_run=False)
        cp, out = self.out(r.run, ["sh", "-c", "echo одна; echo две >&2"], tee=True, capture=True)
        self.assertEqual(out, "одна\nдве\n")
        self.assertEqual(cp.stdout, "одна\nдве\n")
        self.assertEqual(self.log_lines(), ["$ sh -c echo одна; echo две >&2", "одна", "две"])
        with self.assertRaises(system.CommandError):
            self.out(r.run, ["sh", "-c", "echo x; exit 2"], tee=True)

    def test_sudo_prefix(self):
        self.stub("sudo", 'echo "sudo $*" >> "%s"' % (self.dir / "calls"))
        r = system.Runner(dry_run=False)
        with self.path():
            r.sudo(["apt-get", "update"])
        self.assertEqual((self.dir / "calls").read_text(encoding="utf-8"), "sudo apt-get update\n")

    def test_systemctl(self):
        calls = self.dir / "calls"
        self.stub("systemctl", 'echo "systemctl $*" >> "%s"; [ -n "$SYSTEMCTL_OK" ]' % calls)
        self.stub("sudo", 'echo "sudo $*" >> "%s"; [ "$1" = "-n" ] && shift; shift; exit 0' % calls)
        r = system.Runner(dry_run=False)
        with self.path():
            with mock.patch.dict(os.environ, {"SYSTEMCTL_OK": "1"}):
                self.assertTrue(r.systemctl("stop", "klipper.service"))
            lines = calls.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, ["systemctl --no-ask-password stop klipper.service"])
            calls.unlink()
            with mock.patch.dict(os.environ, {"SYSTEMCTL_OK": ""}):
                with mock.patch.object(sys.stdin, "isatty", return_value=False, create=True):
                    self.assertTrue(r.systemctl("start", "klipper.service"))
            lines = calls.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "systemctl --no-ask-password start klipper.service")
            self.assertEqual(lines[1], "sudo -n systemctl start klipper.service")

    def test_systemctl_dry_run(self):
        r = system.Runner(dry_run=True)
        res, out = self.out(r.systemctl, "stop", "klipper")
        self.assertTrue(res)
        self.assertEqual(out, "[dry-run] systemctl stop klipper\n")

    def test_can_manage_services(self):
        self.stub("pkcheck", "exit 1")
        self.stub("sudo", "exit 1")
        with self.path():
            self.assertFalse(system.can_manage_services())
            self.stub("sudo", "exit 0")
            self.assertTrue(system.can_manage_services())
            self.assertFalse(system.can_manage_services(allow_sudo=False))
            self.stub("pkcheck", "exit 0")
            self.assertTrue(system.can_manage_services(allow_sudo=False))

    def test_sudo_keepalive(self):
        calls = self.dir / "calls"
        self.stub("sudo", 'echo "sudo $*" >> "%s"' % calls)
        r = system.Runner(dry_run=False)
        with self.path():
            with contextlib.redirect_stdout(io.StringIO()) as out:
                with r.sudo_keepalive():
                    pass
            self.assertIn("Потребуется пароль sudo", out.getvalue())
            self.assertEqual(calls.read_text(encoding="utf-8"), "sudo -v\n")
            calls.unlink()
            with r.sudo_keepalive(enabled=False):
                pass
            self.assertFalse(calls.exists())
            self.stub("sudo", "exit 1")
            with self.assertRaises(VostokError) as cm:
                with contextlib.redirect_stdout(io.StringIO()):
                    with r.sudo_keepalive():
                        pass
            self.assertEqual(str(cm.exception), "нет прав sudo")

    def test_sudo_keepalive_dry_run_and_missing(self):
        with system.Runner(dry_run=True).sudo_keepalive():
            pass
        with mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            with self.assertRaises(VostokError) as cm:
                with system.Runner(dry_run=False).sudo_keepalive():
                    pass
            self.assertEqual(str(cm.exception), "нет sudo")


if __name__ == "__main__":
    unittest.main()
