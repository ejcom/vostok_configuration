"""Общие заглушки для тестов установщика (install/flashing/host): Runner без внешних программ, песочница Env."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, List, Tuple
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = Path(os.path.dirname(HERE))
sys.path.insert(0, str(INSTALLER))

from vostok import ui  # noqa: E402
from vostok.boards import Registry  # noqa: E402
from vostok.host import Env  # noqa: E402

REG = Registry(INSTALLER / "boards")


class FakeRunner:
    """Заглушка system.Runner: пишет вызовы, отвечает по правилам, ничего не запускает.

    on(префикс или функция, rc=0, out="") - правило (первое подходящее); без правила код 0 и пустой вывод
    (default_rc=1 для запросов lsusb/ip: «нет такого»). Поведение dry-run как у Runner: печатает [dry-run] и
    возвращает 0, кроме readonly-запросов.
    """

    def __init__(self, dry_run: bool = False, default_rc: int = 0) -> None:
        self.dry_run = dry_run
        self.default_rc = default_rc
        self.rules: List[Tuple[Callable, int, object]] = []
        self.calls: List[Tuple[str, ...]] = []
        self.kwargs: List[dict] = []
        self.systemctl_calls: List[Tuple[str, str]] = []
        self.systemctl_ok = True

    def on(self, match, rc: int = 0, out="") -> "FakeRunner":
        if isinstance(match, tuple):
            pref = match
            match = lambda argv, pref=pref: tuple(argv[:len(pref)]) == pref   # noqa: E731
        self.rules.append((match, rc, out))
        return self

    def run(self, cmd, *, sudo=False, check=True, capture=False, tee=False, **kw):
        argv = [str(a) for a in cmd]
        if sudo:
            argv = ["sudo"] + argv
        if self.dry_run and not kw.get("readonly"):
            ui.info("[dry-run] " + " ".join(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")
        self.calls.append(tuple(argv))
        self.kwargs.append(kw)
        rc, out = self.default_rc, ""
        for match, r, o in self.rules:
            if match(argv):
                rc, out = r, o
                break
        if callable(out):
            out = out(argv)
        if tee and out:
            sys.stdout.write(out)
        if kw.get("stdout_file") is not None and out:
            mode = "a" if kw.get("append") else "w"
            with open(kw["stdout_file"], mode, encoding="utf-8") as f:
                f.write(out)
        if check and rc != 0:
            from vostok.system import CommandError
            raise CommandError(" ".join(argv), rc, out)
        return subprocess.CompletedProcess(argv, rc, out if (capture or tee) else "", "")

    def capture(self, cmd, **kw):
        kw.setdefault("check", False)
        return (self.run(cmd, capture=True, **kw).stdout or "").rstrip("\n")

    def systemctl(self, action, unit):
        self.systemctl_calls.append((action, unit))
        return self.systemctl_ok

    @contextlib.contextmanager
    def sudo_keepalive(self, enabled=True):
        self.keepalive_calls = getattr(self, "keepalive_calls", []) + [enabled]
        yield

    def called(self, *prefix) -> int:
        return sum(1 for c in self.calls if c[:len(prefix)] == prefix)


def quiet():
    """Подавить stdout/stderr на время вызова (возвращает (out, err))."""
    out, err = io.StringIO(), io.StringIO()
    stack = contextlib.ExitStack()
    stack.enter_context(contextlib.redirect_stdout(out))
    stack.enter_context(contextlib.redirect_stderr(err))
    return stack, out, err


class Sandbox(unittest.TestCase):
    """Временный каталог с HOME, by-id, printer_data; Env с этими путями; ui без журнала."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.byid = self.tmp / "byid"
        self.pd = self.tmp / "pd"
        for d in (self.home, self.byid, self.pd / "config", self.pd / "logs"):
            d.mkdir(parents=True)
        saved = (ui.opts.yes, ui.opts.dry_run, ui.opts.log_file)
        self.addCleanup(lambda: ui.set_options(*saved))
        ui.set_options(yes=False, dry_run=False, log_file=None)
        sleeper = mock.patch("time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        self.env = self.make_env()
        self.out = io.StringIO()
        self.err = io.StringIO()
        for cm in (contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err)):
            cm.__enter__()
            self.addCleanup(cm.__exit__, None, None, None)

    def make_env(self, **extra) -> Env:
        e = {"HOME": str(self.home), "PRINTER_DATA": str(self.pd), "BYID_DIR": str(self.byid),
             "DEVICES_FILE": str(self.tmp / "devices.tsv"), "BUILD_DIR": str(self.tmp / "build"),
             "FIRMWARE_DIR": str(self.tmp / "fw"), "KERNEL_CONFIG": str(INSTALLER / "tests" / "fixtures" / "kernel_config_can"),
             "KLIPPER_DIR": str(self.home / "klipper"), "KATAPULT_DIR": str(self.home / "katapult"),
             "KIAUH_DIR": str(self.home / "kiauh"), "KLIPPY_ENV": str(self.home / "klippy-env"),
             "MOONRAKER_DIR": str(self.home / "moonraker"), "MIN_FREE_MB": "0", "MIN_MEM_MB": "0",
             "VOSTOK_CFG_LOCAL": str(INSTALLER / "tests" / "fixtures" / "repo_root"),
             "STATE_FILE": str(self.tmp / "flashed.tsv")}
        e.update(extra)
        return Env.from_environ(e)

    def touch_byid(self, *names):
        for n in names:
            (self.byid / n).touch()

    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()
