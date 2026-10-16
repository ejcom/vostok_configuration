#!/usr/bin/env bash
# Настройка конфига VOSTOK отдельно от установки: выбор или генерация electronics_*.cfg, драйверы моторов,
# недостающие секции [mcu ...] в printer.cfg и дополнительные модули (например, chamber_heater.cfg).
# Прошивку плат и установку софта не трогает. Запускать можно в любой момент после установки.
#
# Основа - ваш текущий конфиг: если в printer.cfg уже подключён electronics_*.cfg, пины и параметры
# моторов и драйверов берутся из него. Стоковый main берётся только при чистой установке.
# Прежние файлы перед заменой сохраняются как *.bak-<дата>.
#
# Вся логика в Python-пакете vostok (configurator.py, electronics.py); здесь только обёртка,
# чтобы путь ./configure_vostok.sh и его опции остались прежними. Опции: ./configure_vostok.sh --help
# Подробности: CONFIGURATOR.md

set -euo pipefail

INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
command -v python3 >/dev/null || { echo "ОШИБКА: нужен python3" >&2; exit 1; }
PYTHONPATH="$INSTALL_DIR" exec python3 -m vostok configure "$@"
