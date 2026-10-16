#!/usr/bin/env bash
# Обёртка: вся логика в пакете vostok (vostok/integrations.py), путь и флаги скрипта прежние.
INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
command -v python3 >/dev/null 2>&1 || { echo "ОШИБКА: нужен python3 (установите: sudo apt install python3)" >&2; exit 1; }
PYTHONPATH="$INSTALL_DIR${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 VOSTOK_PROG="$0" exec python3 -m vostok theme "$@"
