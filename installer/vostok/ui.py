"""Вывод, лог-файл и вопросы пользователю (бывшие info/ok/warn/die/step/ask_yn/ask_choice/pause_hw из bash).

Тексты, цвета и формат лога как в bash: ``ВНИМАНИЕ:``/``ОШИБКА:``, ``== шаг ==``, ``>>> `` для pause_hw,
ответы y/Y/д/Д считаются «да», строка лога ``YYYY-mm-dd HH:MM:SS сообщение``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from . import UserAbort, VostokError  # noqa: F401  (UserAbort - часть публичного контракта ui)


class Options:
    """Глобальные настройки вывода: -y/--yes, --dry-run, файл журнала."""
    yes: bool = False
    dry_run: bool = False
    log_file: Optional[Path] = None


options = Options()


def set_options(yes: bool = False, dry_run: bool = False, log_file: Optional[Path] = None) -> None:
    """Задать --yes (вопросы получают ответ по умолчанию), --dry-run и файл журнала (None - без журнала)."""
    raise NotImplementedError


def log(msg: str) -> None:
    """Дописать строку ``YYYY-mm-dd HH:MM:SS msg`` в журнал (каталог создаётся; ошибки записи молча игнорируются)."""
    raise NotImplementedError


def info(msg: str) -> None:
    """Обычное сообщение в stdout (в журнал как есть)."""
    raise NotImplementedError


def ok(msg: str) -> None:
    """Зелёное сообщение об успехе в stdout (в журнал с префиксом ``OK: ``)."""
    raise NotImplementedError


def warn(msg: str) -> None:
    """Жёлтое ``ВНИМАНИЕ: …`` в stderr."""
    raise NotImplementedError


def error(msg: str) -> None:
    """Красное ``ОШИБКА: …`` в stderr (выход не делает; исключение превращает в сообщение cli.main)."""
    raise NotImplementedError


def step(msg: str) -> None:
    """Заголовок этапа: пустая строка и ``== msg ==``."""
    raise NotImplementedError


def die(msg: str) -> None:
    """Бросить VostokError(msg) (аналог bash ``die``; печатает и логирует cli.main)."""
    raise NotImplementedError


def have_tty() -> bool:
    """Можно ли открыть /dev/tty на чтение."""
    raise NotImplementedError


def need_tty() -> None:
    """Требует читаемый /dev/tty, иначе VostokError «нужен терминал: …»."""
    raise NotImplementedError


def ask_yn(q: str, default: str = "n") -> bool:
    """Вопрос да/нет (``[y/N]``/``[Y/n]``). С --yes возвращает ``default == "y"`` без вопроса."""
    raise NotImplementedError


def ask_choice(q: str, default: str, options: Sequence[str]) -> str:
    """Меню с номерами (в stderr); Enter - ``default``; с --yes сразу ``default``. Возвращает выбранный вариант."""
    raise NotImplementedError


def confirm(q: str, need: bool = True) -> bool:
    """Подтверждение ``[y/N]`` (confirm из update_klipper_mcu.sh и install_*). С --yes - да.
    Нет терминала: need=True - VostokError «нет терминала для подтверждения, используйте -y», иначе False."""
    raise NotImplementedError


def pause_hw(msg: str, allow_skip: bool = False) -> str:
    """Ожидание действия пользователя с железом: печатает ``>>> msg``, ждёт Enter, возвращает введённую строку.
    allow_skip - в подсказке предлагается ``s`` (пропустить DFU). В dry-run только печатает и возвращает ""."""
    raise NotImplementedError
