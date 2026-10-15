"""Запуск внешних команд: единственное место с subprocess. Dry-run реализован один раз."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from contextlib import contextmanager
from typing import Iterator, List, Mapping, Optional, Sequence, Union

from . import VostokError, ui

Cmd = Union[str, Sequence[str]]


class CommandError(VostokError):
    """Команда завершилась с ненулевым кодом (check=True)."""

    def __init__(self, cmd: str, returncode: int, stdout: str = "") -> None:
        super().__init__("команда завершилась с кодом %d: %s" % (returncode, cmd))
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout


class Runner:
    """Запуск команд с учётом --dry-run и журнала.

    dry_run=None - брать значение из ui.opts.dry_run в момент вызова.
    """

    def __init__(self, dry_run: Optional[bool] = None) -> None:
        self._dry_run = dry_run

    @property
    def dry_run(self) -> bool:
        return ui.opts.dry_run if self._dry_run is None else self._dry_run

    def run(self, cmd: Cmd, *, sudo: bool = False, check: bool = True, capture: bool = False,
            tee: bool = False, env: Optional[Mapping[str, str]] = None, cwd: Optional[str] = None,
            timeout: Optional[float] = None) -> "subprocess.CompletedProcess[str]":
        """Выполнить команду. Dry-run: печатает ``[dry-run] <команда>`` и возвращает код 0 (stdout пустой);
        иначе пишет в журнал ``$ <команда>``. sudo - добавить ``sudo`` в начало. capture - собрать stdout
        в результат (text; stderr остаётся на экране, как у ``$(...)``). tee - выводить на экран (stdout+stderr)
        и дописывать вывод в журнал; вместе с capture вывод попадает и в результат. check - при коде != 0
        CommandError. env дополняет окружение процесса."""
        argv: List[str] = shlex.split(cmd) if isinstance(cmd, str) else [str(a) for a in cmd]
        if sudo:
            argv = ["sudo"] + argv
        text = " ".join(argv)
        if self.dry_run:
            ui.info("[dry-run] " + text)
            return subprocess.CompletedProcess(argv, 0, "", "")
        ui.log("$ " + text)
        penv = None
        if env is not None:
            penv = dict(os.environ)
            penv.update(env)
        try:
            if tee:
                cp = self._run_tee(argv, penv, cwd, timeout)
            else:
                cp = subprocess.run(argv, env=penv, cwd=cwd, timeout=timeout, universal_newlines=True,
                                    stdout=subprocess.PIPE if capture else None)
        except FileNotFoundError:
            cp = subprocess.CompletedProcess(argv, 127, "", "")
        if check and cp.returncode != 0:
            raise CommandError(text, cp.returncode, cp.stdout or "")
        return cp

    @staticmethod
    def _run_tee(argv, penv, cwd, timeout) -> "subprocess.CompletedProcess[str]":
        proc = subprocess.Popen(argv, env=penv, cwd=cwd, universal_newlines=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        timer = None
        if timeout:
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
        lines: List[str] = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                lines.append(line)
                sys.stdout.write(line)
                sys.stdout.flush()
                ui.log(line.rstrip("\n"))
            rc = proc.wait()
        finally:
            if proc.stdout:
                proc.stdout.close()
            if timer:
                timer.cancel()
        return subprocess.CompletedProcess(argv, rc, "".join(lines), "")

    def sudo(self, cmd: Cmd, **kw) -> "subprocess.CompletedProcess[str]":
        """run(cmd, sudo=True, ...)."""
        return self.run(cmd, sudo=True, **kw)

    def capture(self, cmd: Cmd, **kw) -> str:
        """stdout команды без завершающего перевода строки; код возврата не проверяется (check=False по умолчанию).
        В dry-run команда не выполняется (пустая строка)."""
        kw.setdefault("check", False)
        cp = self.run(cmd, capture=True, **kw)
        return (cp.stdout or "").rstrip("\n")

    def systemctl(self, action: str, unit: str) -> bool:
        """``systemctl --no-ask-password <action> <unit>`` (polkit), при неудаче sudo (``sudo -n`` без терминала).
        True - успех. Как sctl из update_klipper_mcu.sh; в dry-run только печатает."""
        if self.dry_run:
            ui.info("[dry-run] systemctl %s %s" % (action, unit))
            return True
        try:
            cp = subprocess.run(["systemctl", "--no-ask-password", action, unit],
                                stderr=subprocess.DEVNULL)
            if cp.returncode == 0:
                return True
        except FileNotFoundError:
            pass
        sudo = ["sudo"] if sys.stdin.isatty() else ["sudo", "-n"]
        return self.run(sudo + ["systemctl", action, unit], check=False).returncode == 0

    @contextmanager
    def sudo_keepalive(self, enabled: bool = True) -> Iterator[None]:
        """Один раз запросить пароль sudo (``sudo -v``) и поддерживать его фоновым потоком (каждые 50 с).
        В dry-run или enabled=False ничего не делает. Нет sudo/прав - VostokError."""
        if not enabled or self.dry_run:
            yield
            return
        if not any(os.access(os.path.join(d, "sudo"), os.X_OK) for d in os.environ.get("PATH", "").split(":")):
            raise VostokError("нет sudo")
        ui.info("Потребуется пароль sudo (запрашивается один раз).")
        if subprocess.run(["sudo", "-v"]).returncode != 0:
            raise VostokError("нет прав sudo")
        stop = threading.Event()

        def loop() -> None:
            while not stop.wait(50):
                if subprocess.run(["sudo", "-n", "true"], stderr=subprocess.DEVNULL).returncode != 0:
                    return

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()


def can_manage_services(allow_sudo: bool = True) -> bool:
    """Можно ли управлять службами без терминала: pkcheck org.freedesktop.systemd1.manage-units,
    а при allow_sudo - ещё и ``sudo -n true`` (update_klipper_mcu.sh; кнопка Fluidd использует allow_sudo=False)."""
    def ok(argv) -> bool:
        try:
            return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        except OSError:
            return False

    if ok(["pkcheck", "--action-id", "org.freedesktop.systemd1.manage-units", "--process", str(os.getpid())]):
        return True
    return allow_sudo and ok(["sudo", "-n", "true"])
