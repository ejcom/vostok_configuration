"""Диспетчеризация обёрток: ``python3 -m vostok <команда> аргументы``."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

# Реестр команд: имя -> main(argv) -> код выхода. Каждый агент добавляет только свою строку:
# update, install, configure, button, theme, ks-theme.
COMMANDS: Dict[str, Callable[[List[str]], int]] = {}


def main(argv: Optional[List[str]] = None) -> int:
    """Выполнить команду из argv[0]; VostokError/UserAbort печатаются как ``ОШИБКА: …`` (код 1)."""
    raise NotImplementedError
