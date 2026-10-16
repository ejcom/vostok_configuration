"""Диспетчеризация обёрток: ``python3 -m vostok <команда> аргументы``."""
from __future__ import annotations

import os
import sys
from typing import Callable, Dict, List, Optional

from . import VostokError, configurator, install, integrations, ui, update

# Реестр команд: имя -> main(argv) -> код выхода. Каждый агент добавляет только свою строку:
# update, install, configure, button, theme, ks-theme.
COMMANDS: Dict[str, Callable[[List[str]], int]] = {}
COMMANDS["button"] = integrations.main_button
COMMANDS["theme"] = integrations.main_theme
COMMANDS["ks-theme"] = integrations.main_ks_theme
COMMANDS["update"] = update.main
COMMANDS["configure"] = configurator.main
COMMANDS["install"] = install.main


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
    except BrokenPipeError:    # вывод в закрытый конвейер (| head): тихо, как SIGPIPE в bash
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        return 141
    except Exception as e:     # непредвиденная ошибка (диск полон, права): сообщение вместо traceback, подробности в журнал
        import traceback
        ui.error("%s: %s" % (type(e).__name__, e))
        ui.log(traceback.format_exc().rstrip("\n"))
        return 1
    return 0 if rc is None else int(rc)
