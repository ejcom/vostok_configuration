"""Запуск внешних команд: единственное место с subprocess. Dry-run реализован один раз."""
from __future__ import annotations

import subprocess
from contextlib import contextmanager
from typing import Iterator, Mapping, Optional, Sequence, Union

from . import VostokError

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

    dry_run=None - брать значение из ui.options.dry_run в момент вызова.
    """

    def __init__(self, dry_run: Optional[bool] = None) -> None:
        raise NotImplementedError

    def run(self, cmd: Cmd, *, sudo: bool = False, check: bool = True, capture: bool = False,
            tee: bool = False, env: Optional[Mapping[str, str]] = None, cwd: Optional[str] = None,
            timeout: Optional[float] = None) -> "subprocess.CompletedProcess[str]":
        """Выполнить команду. Dry-run: печатает ``[dry-run] <команда>`` и возвращает код 0 (stdout пустой);
        иначе пишет в журнал ``$ <команда>``. sudo - добавить ``sudo`` в начало. capture - собрать stdout/stderr
        в результат (text). tee - выводить на экран и дописывать вывод в журнал. check - при коде != 0
        CommandError. env дополняет окружение процесса."""
        raise NotImplementedError

    def sudo(self, cmd: Cmd, **kw) -> "subprocess.CompletedProcess[str]":
        """run(cmd, sudo=True, ...)."""
        raise NotImplementedError

    def capture(self, cmd: Cmd, **kw) -> str:
        """stdout команды без завершающего перевода строки; код возврата не проверяется (check=False по умолчанию)."""
        raise NotImplementedError

    def systemctl(self, action: str, unit: str) -> bool:
        """``systemctl --no-ask-password <action> <unit>`` (polkit), при неудаче sudo (``sudo -n`` без терминала).
        True - успех. Как sctl из update_klipper_mcu.sh; в dry-run только печатает."""
        raise NotImplementedError

    @contextmanager
    def sudo_keepalive(self, enabled: bool = True) -> Iterator[None]:
        """Один раз запросить пароль sudo (``sudo -v``) и поддерживать его фоновым потоком (каждые 50 с).
        В dry-run или enabled=False ничего не делает. Нет sudo/прав - VostokError."""
        raise NotImplementedError
        yield  # pragma: no cover


def can_manage_services(allow_sudo: bool = True) -> bool:
    """Можно ли управлять службами без терминала: pkcheck org.freedesktop.systemd1.manage-units,
    а при allow_sudo - ещё и ``sudo -n true`` (update_klipper_mcu.sh; кнопка Fluidd использует allow_sudo=False)."""
    raise NotImplementedError
