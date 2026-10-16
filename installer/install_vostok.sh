#!/usr/bin/env bash
# Первоначальная установка K3D VOSTOK на чистую систему (Debian/Armbian/Orange Pi/BTT Pi).
# Основа: гайд https://k3d.tech/vostok/manual/electronics/firmware/
#
# Что делает (каждый этап можно повторять, готовое пропускается):
#   1. пакеты (apt);
#   2. KIAUH, форк Klipper dmbutyugin/klipper (generic-cartesian), Moonraker, Fluidd,
#      расширение gcode_shell_command, katapult;
#   3. определяет подключённые MCU, спрашивает про отсутствующее (платы голов, ALPS) и показывает план;
#   4. при наличии плат голов настраивает CAN-интерфейс can0 (1 Мбит, txqueuelen 128);
#   5. прошивает katapult и Klipper: ALPS (F072, DFU), платы голов Fysetc H36 или BTT EBB42,
#      главная плата из реестра boards/ (Octopus Pro H723/F446, Manta M8P, Spider, FLY-C8 ...; USB или мост USB->CAN); в нужные моменты просит перевести
#      плату в DFU и что-то нажать/переключить. Платы голов - на выбор:
#        dfu (по умолчанию) - "на столе": katapult и Klipper сразу по DFU через USB, без 24 В и CAN;
#          canbus_uuid вычисляется по UID чипа, после установки в принтер его проверяют (--check-can);
#        can - в собранном принтере: katapult по DFU, Klipper по CAN (нужны 24 В и CAN-кабели);
#   6. скачивает vostok_configuration и вписывает найденные MCU в printer.cfg
#      (существующий конфиг VOSTOK: меняются только электроника, [mcu] и include; пустой или чужой printer.cfg считается чистой установкой);
#   7. ставит кнопку обновления в Fluidd (install_fluidd_button.sh);
#   8. ставит тему K3D VOSTOK в Fluidd (install_fluidd_theme.sh) и, если есть KlipperScreen,
#      в него (install_klipperscreen_theme.sh).
#
# Запускать от обычного пользователя в терминале (sudo спросит пароль один раз).
# Подробности: README.md, ./install_vostok.sh --help
#
# Тонкий загрузчик: вся логика в Python-пакете vostok (vostok/install.py). Здесь только установка python3,
# если его ещё нет (чистая система), и запуск.

set -euo pipefail

INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")

# Без python3 ничего не сделать. Ставим его (и python3-venv для KIAUH) один раз, но не в режимах, которые
# обещают ничего не менять (--dry-run, --only-detect, справка).
if ! command -v python3 >/dev/null 2>&1; then
    readonly_mode=0
    for a in "$@"; do
        case $a in --dry-run|--only-detect|--list-boards|-h|--help|-V|--version) readonly_mode=1 ;; esac
    done
    if [[ $readonly_mode -eq 1 ]]; then
        echo "ОШИБКА: нужен python3 (в режимах --dry-run/--only-detect/справка он не устанавливается; установите: sudo apt install python3 python3-venv)" >&2
        exit 1
    fi
    command -v apt-get >/dev/null 2>&1 || { echo "ОШИБКА: нужен python3, а apt-get не найден (установите python3 вручную)" >&2; exit 1; }
    echo "python3 не установлен: ставлю python3 и python3-venv (потребуется пароль sudo)."
    if [[ $EUID -eq 0 ]]; then
        apt-get update && apt-get install -y python3 python3-venv
    else
        command -v sudo >/dev/null 2>&1 || { echo "ОШИБКА: нет sudo" >&2; exit 1; }
        sudo apt-get update && sudo apt-get install -y python3 python3-venv
    fi
    command -v python3 >/dev/null 2>&1 || { echo "ОШИБКА: не удалось установить python3" >&2; exit 1; }
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    echo "ОШИБКА: python3 слишком старый, нужен 3.8 или новее (KIAUH, Klipper): $(python3 -V 2>&1)" >&2
    exit 1
fi

PYTHONPATH="$INSTALL_DIR" PYTHONDONTWRITEBYTECODE=1 exec python3 -m vostok install "$@"
