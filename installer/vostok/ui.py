"""Вывод, лог-файл и вопросы пользователю (бывшие info/ok/warn/die/step/ask_yn/ask_choice/pause_hw из bash).

Тексты, цвета и формат лога как в bash: ``ВНИМАНИЕ:``/``ОШИБКА:``, ``== шаг ==``, ``>>> `` для pause_hw,
ответы y/Y/д/Д считаются «да», строка лога ``YYYY-mm-dd HH:MM:SS сообщение``.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from . import UserAbort, VostokError  # noqa: F401  (UserAbort - часть публичного контракта ui)
from .boards import Registry, pinout_url, pinouts_dir


class Options:
    """Глобальные настройки вывода: -y/--yes, --dry-run, файл журнала."""
    yes: bool = False
    dry_run: bool = False
    log_file: Optional[Path] = None


opts = Options()


def set_options(yes: bool = False, dry_run: bool = False, log_file: Optional[Path] = None) -> None:
    """Задать --yes (вопросы получают ответ по умолчанию), --dry-run и файл журнала (None - без журнала)."""
    opts.yes = bool(yes)
    opts.dry_run = bool(dry_run)
    opts.log_file = Path(log_file) if log_file else None


def _colors():
    # как в bash: цвета включаются, если stdout - терминал (и для stderr тоже)
    if sys.stdout.isatty():
        return "\033[91m", "\033[92m", "\033[93m", "\033[0m"
    return "", "", "", ""


def log(msg: str) -> None:
    """Дописать строку ``YYYY-mm-dd HH:MM:SS msg`` в журнал (каталог создаётся; ошибки записи молча игнорируются)."""
    if opts.log_file is None:
        return
    try:
        opts.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(opts.log_file, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def _out(text: str, stream) -> None:
    stream.write(text + "\n")
    stream.flush()


def info(msg: str) -> None:
    """Обычное сообщение в stdout (в журнал как есть)."""
    _out(msg, sys.stdout)
    log(msg)


def ok(msg: str) -> None:
    """Зелёное сообщение об успехе в stdout (в журнал с префиксом ``OK: ``)."""
    _, green, _, off = _colors()
    _out("%s%s%s" % (green, msg, off), sys.stdout)
    log("OK: " + msg)


def warn(msg: str) -> None:
    """Жёлтое ``ВНИМАНИЕ: …`` в stderr."""
    _, _, yellow, off = _colors()
    _out("%sВНИМАНИЕ: %s%s" % (yellow, msg, off), sys.stderr)
    log("ВНИМАНИЕ: " + msg)


def error(msg: str) -> None:
    """Красное ``ОШИБКА: …`` в stderr (выход не делает; исключение превращает в сообщение cli.main)."""
    red, _, _, off = _colors()
    _out("%sОШИБКА: %s%s" % (red, msg, off), sys.stderr)
    log("ОШИБКА: " + msg)


def step(msg: str) -> None:
    """Заголовок этапа: пустая строка и ``== msg ==``."""
    _out("\n== %s ==" % msg, sys.stdout)
    log("== %s ==" % msg)


def die(msg: str) -> None:
    """Бросить VostokError(msg) (аналог bash ``die``; печатает и логирует cli.main)."""
    raise VostokError(msg)


def have_tty() -> bool:
    """Можно ли открыть /dev/tty на чтение."""
    try:
        with open("/dev/tty"):
            return True
    except OSError:
        return False


def need_tty() -> None:
    """Требует читаемый /dev/tty, иначе VostokError «нужен терминал: …»."""
    if not have_tty():
        raise VostokError("нужен терминал: установка просит переключать платы и нажимать Enter")


def _read_tty(prompt: str) -> str:
    """Прочитать строку с /dev/tty (подсказка в stderr). Заменяется в тестах."""
    sys.stderr.write(prompt)
    sys.stderr.flush()
    try:
        with open("/dev/tty", encoding="utf-8", errors="replace") as tty:
            line = tty.readline()
    except OSError:
        raise VostokError("нужен терминал: установка просит переключать платы и нажимать Enter")
    if line == "":
        raise UserAbort("ввод прерван (конец ввода)")
    return line.rstrip("\n")


def _is_yes(ans: str) -> bool:
    return ans[:1] in ("y", "Y", "д", "Д")


def ask_yn(q: str, default: str = "n") -> bool:
    """Вопрос да/нет (``[y/N]``/``[Y/n]``). С --yes возвращает ``default == "y"`` без вопроса."""
    if opts.yes:
        return default == "y"
    need_tty()
    hint = "[Y/n]" if default == "y" else "[y/N]"
    ans = _read_tty("%s %s " % (q, hint))
    if not ans:
        ans = default
    return _is_yes(ans)


def ask_choice(q: str, default: str, options: Sequence[str]) -> str:  # noqa: F811 - имя как в контракте
    """Меню с номерами (в stderr); Enter - ``default``; с --yes сразу ``default``. Возвращает выбранный вариант."""
    if opts.yes:
        return default
    need_tty()
    sys.stderr.write(q + "\n")
    for i, o in enumerate(options, 1):
        sys.stderr.write("  %d) %s\n" % (i, o))
    sys.stderr.flush()
    while True:
        ans = _read_tty("Номер [по умолчанию: %s]: " % default)
        if not ans:
            return default
        if ans.isdigit() and ans.isascii() and 1 <= int(ans) <= len(options):
            return options[int(ans) - 1]
        sys.stderr.write("Введите число от 1 до %d\n" % len(options))
        sys.stderr.flush()


def confirm(q: str, need: bool = True) -> bool:
    """Подтверждение ``[y/N]`` (confirm из update_klipper_mcu.sh и install_*). С --yes - да.
    Нет терминала: need=True - VostokError «нет терминала для подтверждения, используйте -y», иначе False."""
    if opts.yes:
        return True
    if not have_tty():
        if need:
            raise VostokError("нет терминала для подтверждения, используйте -y")
        return False
    return _is_yes(_read_tty("%s [y/N] " % q))


def pause_hw(msg: str, allow_skip: bool = False) -> str:
    """Ожидание действия пользователя с железом: печатает ``>>> msg``, ждёт Enter, возвращает введённую строку.
    allow_skip - в подсказке предлагается ``s`` (пропустить DFU). В dry-run только печатает и возвращает ""."""
    _, _, yellow, off = _colors()
    _out("\n%s>>> %s%s" % (yellow, msg, off), sys.stdout)
    log("ЖДЁМ ПОЛЬЗОВАТЕЛЯ: " + msg)
    if opts.dry_run:
        info("[dry-run] ожидание Enter")
        return ""
    need_tty()
    prompt = "Нажмите Enter, когда готово: "
    if allow_skip:
        prompt = ("Enter - плата переведена в DFU; s + Enter - пропустить DFU "
                  "(на плате уже katapult/Klipper): ")
    return _read_tty(prompt)


def pinout_lines(reg: Registry, board_id: str, indent: str = "  ") -> List[str]:
    """Строки про распиновку платы: локальный путь и веб-ссылка на каждую картинку (поле PINOUT).
    Нет картинок (PINOUT пуст или файлов нет) - вместо них пояснение и DOC платы; нет и DOC - пустой список."""
    board = reg.get(board_id)
    root = pinouts_dir()
    found = [rel for rel in board.pinout_list if (root / rel).is_file()]
    lines: List[str] = []
    for rel in found:
        name = "Схема" if os.path.basename(rel).startswith("schematic") else "Распиновка"
        title = board.label
        if len(found) > 1:      # несколько листов: ревизия из имени каталога (v2_3 -> v2.3)
            rev = os.path.basename(os.path.dirname(rel))
            title += " " + (rev.replace("_", ".") if re.match(r"^v\d+(_\d+)*$", rev) else rev)
        lines.append("%s%s %s: %s" % (indent, name, title, root / rel))
        lines.append("%s  онлайн: %s" % (indent, pinout_url(rel)))
    if not lines and board.doc:
        if board.role == "alps":
            lines.append("%s%s: официального листа распиновки нет; подключение - в гайде: %s" % (indent, board.label, board.doc))
        else:
            lines.append("%s%s: картинки распиновки в каталоге нет, документация: %s" % (indent, board.label, board.doc))
    return lines


def pinout_hint(reg: Registry, board_id: str, indent: str = "  ",
                out: Optional[Callable[[str], None]] = None) -> None:
    """Вывести распиновку платы (pinout_lines) через out (по умолчанию info)."""
    for ln in pinout_lines(reg, board_id, indent):
        (out or info)(ln)
