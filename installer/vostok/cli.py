"""Диспетчеризация обёрток: ``python3 -m vostok <команда> аргументы``."""
from __future__ import annotations

import sys
from typing import Callable, Dict, List, Optional

from . import VostokError, integrations, ui

# Реестр команд: имя -> main(argv) -> код выхода. Каждый агент добавляет только свою строку:
# update, install, configure, button, theme, ks-theme.
COMMANDS: Dict[str, Callable[[List[str]], int]] = {}
COMMANDS["button"] = integrations.main_button
COMMANDS["theme"] = integrations.main_theme
COMMANDS["ks-theme"] = integrations.main_ks_theme


def main(argv: Optional[List[str]] = None) -> int:
    """Выполнить команду из argv[0]; VostokError/UserAbort печатаются как ``ОШИБКА: …`` (код 1)."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in COMMANDS:
        known = ", ".join(sorted(COMMANDS)) or "нет"
        sys.stderr.write("vostok: %s команда (доступные: %s)\n"
                         % ("неизвестная" if args else "не указана", known))
        return 2
    try:
        rc = COMMANDS[args[0]](args[1:])
    except VostokError as e:
        ui.error(str(e))
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\n")
        return 130
    return 0 if rc is None else int(rc)
