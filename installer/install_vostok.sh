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
#   5. прошивает katapult и Klipper: ALPS (F072, DFU), платы голов Fysetc H36 или BTT EBB42 (CAN),
#      Octopus Pro H723/F446 (USB или мост USB->CAN); в нужные моменты просит перевести
#      плату в DFU и что-то нажать/переключить;
#   6. скачивает vostok_configuration и вписывает найденные MCU в printer.cfg
#      (существующий конфиг VOSTOK: меняются только электроника, [mcu] и include; пустой или чужой printer.cfg считается чистой установкой);
#   7. ставит кнопку обновления в Fluidd (install_fluidd_button.sh).
#
# Запускать от обычного пользователя в терминале (sudo спросит пароль один раз).
# Подробности: README.md, ./install_vostok.sh --help

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4) )); then
    echo "Нужен bash 4.4 или новее (сейчас $BASH_VERSION)" >&2
    exit 1
fi

INSTALL_ARGS=("$@")
set --   # source не должен видеть наши аргументы

INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
PRINTER_DATA=${PRINTER_DATA:-$HOME/printer_data}
LOG_FILE=${LOG_FILE:-$PRINTER_DATA/logs/vostok_install.log}
# Функции update_klipper_mcu.sh (вывод, поиск MCU, сборка, прошивка, проверка версий).
# shellcheck source=update_klipper_mcu.sh
source "$INSTALL_DIR/update_klipper_mcu.sh"
# Общая библиотека настройки конфига (определение железа, меню конфига, генерация, модули)
# shellcheck source=lib/vostok_config.sh
source "$INSTALL_DIR/lib/vostok_config.sh"

KLIPPER_REPO_URL=${KLIPPER_REPO_URL:-https://github.com/dmbutyugin/klipper}
KLIPPER_BRANCH=${KLIPPER_BRANCH:-generic-cartesian}
KATAPULT_REPO_URL=${KATAPULT_REPO_URL:-https://github.com/Arksine/katapult}
KIAUH_REPO_URL=${KIAUH_REPO_URL:-https://github.com/dw-0/kiauh}
VOSTOK_CFG_TARBALL=${VOSTOK_CFG_TARBALL:-https://codeload.github.com/dmitry-sorkin/vostok_configuration/tar.gz/refs/heads/main}
# Конфигурация VOSTOK: если установщик запущен из клона vostok_configuration (installer/ внутри него),
# берём файлы из клона, иначе скачиваем main. VOSTOK_CFG_LOCAL=0 - всегда скачивать, =ПУТЬ - свой каталог.
VOSTOK_CFG_LOCAL=${VOSTOK_CFG_LOCAL:-auto}
KATAPULT_CONFIGS=$CONFIGS_DIR/katapult
PRINTER_CFG_DIR=$PRINTER_DATA/config
DEVICES_FILE=${DEVICES_FILE:-$INSTALL_DIR/devices.tsv}

# Ответы пользователя (можно задать опциями, иначе спросим)
OPT_MAIN=""          # h723|f446
OPT_HEADS=""           # none|v1.3|v2|ebb42
OPT_ALPS=""          # 0|1|2
OPT_ELECTRONICS=""   # имя electronics_*.cfg
OPT_CONFIG_SOURCE="" # standard|user|generate|skip
OPT_DRIVERS=""       # драйверы для сгенерированного конфига: all=2240 или x=5160,w=2240,...,e0=2209,e1=2209
DRY_RUN=0
ONLY_DETECT=0
SKIP_SOFTWARE=0
SKIP_FLASH=0
SKIP_CONFIG=0
SKIP_BUTTON=0
DO_UPGRADE=0
OPT_SKIP_BOARDS=()   # alps|alps0|alps1|main|heads: не прошивать (уже прошиты)
OPT_REFLASH=0        # не предлагать пропуск плат, уже прошитых текущей версией
BYID_DIR=${BYID_DIR:-/dev/serial/by-id}

MAIN=""              # stm32h723xx|stm32f446xx
HEADS=""               # none|v1.3|v2
ALPS_COUNT=0
MODE=""              # usb|bridge
SUDO_KEEPALIVE_PID=""

# Результаты прошивки (для devices.tsv и printer.cfg)
RES_MAIN_SERIAL=""   # режим usb: серийный номер Octopus
RES_BRIDGE_UUID=""   # режим bridge: canbus_uuid Octopus
RES_HEAD_UUID=("" "")  # платы голов T0, T1
RES_ALPS_SERIAL=("" "")

# Итоги прошивки плат: ошибка одной платы не останавливает установку
FLASH_FAILED=()      # "плата: причина"
FLASH_SKIPPED=()     # платы, пропущенные по просьбе пользователя или как уже прошитые
PREV_DEVICES=""      # содержимое devices.tsv от прошлого запуска (до перезаписи)
HEADS_SKIP=0         # платы голов уже прошиты, этапы katapult/Klipper по CAN пропускаются
BOARD_START_PHASE=full  # начальная фаза следующего flash_board: full|dfuall
OPT_MAIN_FLASH=""    # dfu|katapult: способ прошивки главной платы (иначе спросим)
BOARD_PHASE=full     # с какого шага повторять плату: full (с DFU) или klipper
BOARD_DEV=""         # usb-katapult_* устройство платы, прошиваемой сейчас

usage() {
    cat <<'EOF'
Использование: install_vostok.sh [опции]

  --main h723|f446      главная плата: Octopus Pro H723 или Octopus Pro F446 (иначе определит/спросит)
  --heads none|v1.3|v2|ebb42  платы голов по CAN: нет, Fysetc H36 v1.3/v2, BTT EBB42 (иначе спросит);
                        с платами голов Octopus прошивается мостом USB-CAN. --h36 - то же, прежнее имя
  --alps 0|1|2          сколько датчиков ALPS подключено по USB (иначе определит/спросит)
  --electronics ФАЙЛ    имя electronics_*.cfg из vostok_configuration (иначе предложит по железу)
  --config-source standard|user|generate|skip  откуда брать конфиг: корень main, user_configs, сгенерировать свой
                        (шаблон без плат и драйверов) или пропустить редактирование (только дописать
                        недостающие [mcu] в существующий printer.cfg); иначе спросит
  --drivers СПЕК        драйверы для --config-source generate: all=2130|2208|2209|2240|5160|5160plus или список по моторам
                        x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209 (e0/e1 при платах голов не нужны);
                        без опции спросит в диалоге, с -y возьмёт драйверы стокового конфига
  --only-detect         только определить подключённые MCU и показать план, ничего не менять
  --dry-run             показать все шаги и команды, ничего не менять
  --reference ФАЙЛ|none эталон пинов и параметров для сгенерированного конфига: по умолчанию ваш текущий
                        electronics-файл, при чистой установке стоковый main (H723); none - без эталона
  --modules ИМЕНА       дополнительные модули без вопроса: chamber_heater, all или none
  --skip-software       не ставить пакеты/KIAUH/Klipper/Moonraker/Fluidd (уже стоят)
  --skip-flash          не прошивать MCU
  --skip-config         не трогать конфиг принтера
  --skip-button         не ставить кнопку обновления в Fluidd
  --skip-board ПЛАТА    не прошивать плату, уже прошитую раньше: alps, alps0, alps1, main или heads
                        (можно повторять). Без этой опции установщик сам предложит пропустить платы,
                        на которых уже стоит Klipper текущей версии
  --reflash             не предлагать пропуск, прошить все платы заново
  --main-flash dfu|katapult  способ прошивки главной платы: katapult и Klipper сразу по DFU (рекомендуется,
                        по умолчанию с -y) или katapult по DFU, затем Klipper через katapult (иначе спросит)
  --upgrade             выполнить apt upgrade перед установкой
  -y, --yes             не задавать вопросов, где есть ответ по умолчанию (шаги с железом всё равно ждут Enter)
  -V, --version         показать версию установщика
  -h, --help            эта справка

Переменные окружения: PRINTER_DATA, KLIPPER_DIR, KATAPULT_DIR, KIAUH_DIR, CAN_IFACE (can0).
EOF
}

# ------------------------------------------------------------------ аргументы

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --main) [[ $# -ge 2 ]] || die "--main требует аргумент"; OPT_MAIN=$2; shift ;;
            --heads|--h36) [[ $# -ge 2 ]] || die "$1 требует аргумент"; OPT_HEADS=$2; shift ;;
            --config-source) [[ $# -ge 2 ]] || die "--config-source требует аргумент"; OPT_CONFIG_SOURCE=$2; shift ;;
            --drivers) [[ $# -ge 2 ]] || die "--drivers требует аргумент"; OPT_DRIVERS=$2; shift ;;
            --reference) [[ $# -ge 2 ]] || die "--reference требует аргумент"; OPT_REFERENCE=$2; shift ;;
            --modules) [[ $# -ge 2 ]] || die "--modules требует аргумент"; OPT_MODULES=$2; shift ;;
            --alps) [[ $# -ge 2 ]] || die "--alps требует аргумент"; OPT_ALPS=$2; shift ;;
            --electronics) [[ $# -ge 2 ]] || die "--electronics требует аргумент"; OPT_ELECTRONICS=$2; shift ;;
            --only-detect) ONLY_DETECT=1 ;;
            --dry-run) DRY_RUN=1 ;;
            --skip-software) SKIP_SOFTWARE=1 ;;
            --skip-flash) SKIP_FLASH=1 ;;
            --skip-config) SKIP_CONFIG=1 ;;
            --skip-button) SKIP_BUTTON=1 ;;
            --skip-board) [[ $# -ge 2 ]] || die "--skip-board требует аргумент"; OPT_SKIP_BOARDS+=("$2"); shift ;;
            --reflash) OPT_REFLASH=1 ;;
            --main-flash) [[ $# -ge 2 ]] || die "--main-flash требует аргумент"; OPT_MAIN_FLASH=$2; shift ;;
            --upgrade) DO_UPGRADE=1 ;;
            -y|--yes) ASSUME_YES=1 ;;
            -V|--version) echo "VOSTOK installer $VOSTOK_INSTALLER_VERSION"; exit 0 ;;
            -h|--help) usage; exit 0 ;;
            *) usage >&2; die "неизвестная опция: $1" ;;
        esac
        shift
    done
    case $OPT_MAIN in ""|h723|f446) ;; *) die "--main: h723 или f446" ;; esac
    case $OPT_HEADS in ""|none|v1.3|v2|ebb42) ;; *) die "--heads: none, v1.3, v2 или ebb42" ;; esac
    case $OPT_CONFIG_SOURCE in ""|standard|user|generate|skip) ;; *) die "--config-source: standard, user, generate или skip" ;; esac
    case $OPT_MAIN_FLASH in ""|dfu|katapult) ;; *) die "--main-flash: dfu или katapult" ;; esac
    case $OPT_ALPS in ""|0|1|2) ;; *) die "--alps: 0, 1 или 2" ;; esac
    local b
    for b in "${OPT_SKIP_BOARDS[@]}"; do
        case $b in alps|alps0|alps1|main|heads) ;; *) die "--skip-board: alps, alps0, alps1, main или heads" ;; esac
    done
}

# Ожидание действия пользователя с железом. Возвращает введённую строку (обычно пустую).
pause_hw() { # сообщение [skip]: skip=1 разрешает ответ "s" (пропустить DFU); ответ пишется в $TMP_ANS
    local ans="" prompt="Нажмите Enter, когда готово: "
    : >"$TMP_ANS"
    printf '\n%s>>> %s%s\n' "$C_YELLOW" "$1" "$C_OFF"
    log_to_file "ЖДЁМ ПОЛЬЗОВАТЕЛЯ: $1"
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] ожидание Enter"; return 0; fi
    need_tty
    [[ ${2:-0} -eq 1 ]] && prompt="Enter - плата переведена в DFU; s + Enter - пропустить DFU (на плате уже katapult/Klipper): "
    read -r -p "$prompt" ans </dev/tty
    printf '%s' "$ans" >"$TMP_ANS"
}
TMP_ANS=$(mktemp)

run() { # команда...: выполняет или печатает при --dry-run
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] $*"; else log_to_file "\$ $*"; "$@"; fi
}

start_sudo() {
    command -v sudo >/dev/null || die "нет sudo"
    [[ $DRY_RUN -eq 1 || $ONLY_DETECT -eq 1 ]] && return 0
    info "Потребуется пароль sudo (запрашивается один раз)."
    sudo -v || die "нет прав sudo"
    ( while true; do sudo -n true 2>/dev/null || exit; sleep 50; done ) &
    SUDO_KEEPALIVE_PID=$!
}

cleanup() {
    local rc=$?
    [[ -n $SUDO_KEEPALIVE_PID ]] && kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
    rm -f "$TMP_ANS"
    if [[ $rc -ne 0 && ${KLIPPER_STOPPED:-0} -eq 1 ]]; then
        printf 'Klipper остановлен. После устранения проблемы запустите установку снова или: sudo systemctl start klipper\n' >&2
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------- этап 0

stage_preflight() {
    step "Проверки"
    [[ $EUID -ne 0 ]] || die "не запускайте от root; sudo спросит пароль сам"
    case $(uname -m) in aarch64|armv7l|armv6l|x86_64) ;; *) warn "необычная архитектура $(uname -m)" ;; esac
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        info "ОС: ${PRETTY_NAME:-?}"
        [[ ${ID:-} =~ ^(debian|ubuntu|armbian|raspbian|orangepi)$ || ${ID_LIKE:-} == *debian* ]] \
            || warn "ОС не похожа на Debian/Ubuntu: apt и KIAUH могут не работать"
    fi
    if command -v git >/dev/null; then
        git ls-remote -q "$KATAPULT_REPO_URL" HEAD >/dev/null 2>&1 \
            || die "нет доступа к github.com (проверьте интернет)"
    fi
    ok "проверки пройдены"
    check_bootstrap
}

# ---------------------------------------------------------------- проверки окружения

ENV_PROBLEMS=(); ENV_WARNINGS=()
KERNEL_CONFIG=${KERNEL_CONFIG:-}        # путь к конфигу ядра (иначе /proc/config.gz, /boot/config-*); нужен для тестов
USER_GROUPS=${USER_GROUPS:-}            # группы текущей сессии (иначе id -nG); для тестов
USER_GROUPS_DB=${USER_GROUPS_DB:-}      # группы пользователя в /etc/group (иначе id -nG USER); для тестов
MIN_FREE_MB=${MIN_FREE_MB:-2048}
MIN_MEM_MB=${MIN_MEM_MB:-1024}

env_item() { # ok|warn|bad текст
    case $1 in
        ok)   info "  [ок]   $2" ;;
        warn) info "  [!]    $2"; ENV_WARNINGS+=("$2") ;;
        bad)  info "  [НЕТ]  $2"; ENV_PROBLEMS+=("$2") ;;
    esac
}

# Итог блока проверок: при проблемах - остановка (в --dry-run/--only-detect только предупреждение)
env_conclude() { # что проверяли
    [[ ${#ENV_PROBLEMS[@]} -eq 0 ]] && return 0
    if [[ $DRY_RUN -eq 1 || $ONLY_DETECT -eq 1 ]]; then
        warn "$1: найдено проблем: ${#ENV_PROBLEMS[@]} (при реальной установке скрипт остановится)"
        return 0
    fi
    die "$1: найдено проблем: ${#ENV_PROBLEMS[@]}. Устраните их (подсказки выше) и запустите установку снова"
}

hw_steps_planned() { [[ $SKIP_FLASH -eq 0 && $DRY_RUN -eq 0 && $ONLY_DETECT -eq 0 ]]; }

check_dialout() {
    local sess db
    sess=${USER_GROUPS:-$(id -nG)}
    db=${USER_GROUPS_DB:-$(id -nG "$(id -un)" 2>/dev/null || true)}
    if [[ " $sess " == *" dialout "* ]]; then
        env_item ok "доступ к последовательным портам (группа dialout)"
    elif [[ " $db " == *" dialout "* ]]; then
        env_item bad "пользователь добавлен в группу dialout, но текущая сессия её не видит: выйдите и войдите заново (или выполните newgrp dialout)"
    else
        env_item bad "пользователь не в группе dialout (без неё нет доступа к /dev/serial/by-id): sudo usermod -aG dialout $(id -un), затем выйдите и войдите заново"
    fi
}

check_bootstrap() {
    step "Окружение"
    ENV_PROBLEMS=(); ENV_WARNINGS=()
    local c missing=() free_mb mem_mb pyver
    for c in sudo apt-get dpkg systemctl uname awk sed grep sort tr cut head tail mktemp xargs tar df; do
        command -v "$c" >/dev/null || missing+=("$c")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        env_item bad "нет команд: ${missing[*]} (нужна Debian-подобная система с apt и systemd)"
    else
        env_item ok "базовые утилиты, apt, dpkg, systemctl, sudo"
    fi
    if [[ -d /run/systemd/system ]]; then env_item ok "systemd запущен"; else env_item bad "systemd не запущен (службы klipper/moonraker ставятся как systemd-юниты; контейнеры и WSL без systemd не подходят)"; fi

    free_mb=$(df -Pm "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
    if [[ -n $free_mb && $free_mb -lt $MIN_FREE_MB ]]; then env_item bad "мало места в $HOME: ${free_mb} МБ, нужно не менее $MIN_FREE_MB МБ"; else env_item ok "место на диске: ${free_mb:-?} МБ"; fi
    mem_mb=$(awk '/^(MemTotal|SwapTotal):/{s+=$2} END{print int(s/1024)}' /proc/meminfo 2>/dev/null || echo 0)
    if [[ ${mem_mb:-0} -lt $MIN_MEM_MB ]]; then env_item warn "мало памяти (ОЗУ + swap): ${mem_mb} МБ, сборка и установка могут не завершиться (рекомендуется от $MIN_MEM_MB МБ)"; else env_item ok "память (ОЗУ + swap): ${mem_mb} МБ"; fi

    if command -v python3 >/dev/null; then
        pyver=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "?")
        if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then env_item ok "python3 $pyver"; else env_item bad "python3 $pyver слишком старый, нужен 3.8 или новее (KIAUH, Klipper)"; fi
    else
        env_item warn "python3 не установлен (будет установлен на этапе пакетов)"
    fi

    if hw_steps_planned; then
        if have_tty; then env_item ok "терминал для диалога"; else env_item bad "нет терминала: шаги с железом требуют ответов в диалоге (запустите в ssh/терминале или используйте --skip-flash)"; fi
        check_dialout
    fi
    if command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -qE '[:.]80[[:space:]]' \
        && [[ ! -d $HOME/fluidd ]] && ! systemctl is-active --quiet nginx 2>/dev/null; then
        env_item warn "порт 80 занят другой программой: Fluidd (nginx) может не запуститься"
    fi
    env_conclude "Окружение"
}

# Инструменты: нужные команды, python-модули. after_packages=1 - этап пакетов уже выполнен (или пропущен).
check_tools() { # need_flash(0|1) after_packages(0|1)
    local need_flash=$1 after=$2 entry cmd pkg why pkgs=() st=bad
    ENV_PROBLEMS=(); ENV_WARNINGS=()
    [[ $after -eq 0 && $SKIP_SOFTWARE -eq 0 ]] && st=warn   # пакеты ещё будут установлены
    local reqs=("python3:python3:скрипты, KIAUH" "git:git:клонирование репозиториев" "curl:curl:скачивание конфигурации" "tar:tar:распаковка архивов")
    if [[ $need_flash -eq 1 ]]; then
        reqs+=("make:make:сборка прошивок" "arm-none-eabi-gcc:gcc-arm-none-eabi:компилятор прошивок"
               "dfu-util:dfu-util:прошивка katapult по DFU" "lsusb:usbutils:обнаружение плат" "ip:iproute2:интерфейс CAN")
    fi
    step "Инструменты"
    for entry in "${reqs[@]}"; do
        IFS=: read -r cmd pkg why <<<"$entry"
        if command -v "$cmd" >/dev/null; then
            env_item ok "$cmd"
        else
            env_item "$st" "нет $cmd (пакет $pkg): $why$([[ $st == warn ]] && echo '; будет установлен на этапе пакетов')"
            pkgs+=("$pkg")
        fi
    done
    if command -v python3 >/dev/null; then
        if [[ $need_flash -eq 1 ]]; then
            if python3 -c 'import serial' 2>/dev/null; then env_item ok "python3: pyserial"; else env_item "$st" "нет python3-serial (pyserial): нужен flashtool.py"; pkgs+=(python3-serial); fi
        fi
        if [[ $SKIP_SOFTWARE -eq 0 ]]; then
            if python3 -c 'import venv, ensurepip' 2>/dev/null; then env_item ok "python3: venv"; else env_item "$st" "нет python3-venv: KIAUH не создаст окружение Klipper"; pkgs+=(python3-venv); fi
        fi
    fi
    if [[ ${#pkgs[@]} -gt 0 && $st == bad ]]; then
        info "  Установить недостающее: sudo apt install ${pkgs[*]}"
    fi
    env_conclude "Инструменты"
}

# Поддержка CAN в ядре: 0 есть, 1 нет, 2 неизвестно
kernel_can_support() {
    local cfg="" content="" opt
    if [[ -n $KERNEL_CONFIG ]]; then cfg=$KERNEL_CONFIG
    elif [[ -r /proc/config.gz ]]; then content=$(zcat /proc/config.gz 2>/dev/null || true)
    elif [[ -r /boot/config-$(uname -r) ]]; then cfg=/boot/config-$(uname -r)
    fi
    [[ -n $cfg && -r $cfg ]] && content=$(cat "$cfg")
    if [[ -n $content ]]; then
        for opt in CONFIG_CAN CONFIG_CAN_RAW CONFIG_CAN_GS_USB; do
            grep -qE "^${opt}=(y|m)$" <<<"$content" || return 1
        done
        return 0
    fi
    # конфига ядра нет: смотрим модули
    if [[ -d /sys/module/gs_usb ]] || compgen -G "/lib/modules/$(uname -r)/kernel/drivers/net/can/usb/gs_usb.ko*" >/dev/null; then return 0; fi
    return 2
}

# Требования, зависящие от выбранной схемы (после detect_hardware)
check_hw_requirements() {
    [[ $HEADS == none ]] && return 0
    ENV_PROBLEMS=(); ENV_WARNINGS=()
    step "Требования схемы с мостом USB-CAN"
    local rc=0
    kernel_can_support || rc=$?
    case $rc in
        0) env_item ok "ядро $(uname -r) поддерживает CAN и USB-CAN адаптеры (gs_usb)" ;;
        1) env_item bad "ядро $(uname -r) собрано без CAN (нужны CONFIG_CAN, CONFIG_CAN_RAW, CONFIG_CAN_GS_USB): Octopus в режиме моста USB-CAN работать не сможет. Нужно ядро с поддержкой CAN (gs_usb) либо сборка без плат голов по CAN: --heads none" ;;
        *) env_item warn "не удалось определить поддержку CAN в ядре (нет /proc/config.gz и /boot/config-*); проверьте: modinfo gs_usb" ;;
    esac
    command -v ip >/dev/null && env_item ok "ip (iproute2)" || env_item bad "нет ip (пакет iproute2): интерфейс can0 настроить нельзя"
    env_conclude "Требования схемы"
}

# ---------------------------------------------------------------- этап 1

PACKAGES=(git curl python3 python3-serial python3-venv python3-dev virtualenv make
          dfu-util gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi
          libusb-1.0-0 iproute2 usbutils)

stage_packages() {
    step "Пакеты"
    local missing=() p
    for p in "${PACKAGES[@]}"; do
        dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
    done
    if [[ $DO_UPGRADE -eq 1 ]]; then
        run sudo apt-get update
        run sudo apt-get -y upgrade
    elif [[ ${#missing[@]} -gt 0 ]]; then
        run sudo apt-get update
    fi
    if [[ ${#missing[@]} -gt 0 ]]; then
        info "Устанавливаю: ${missing[*]}"
        run sudo apt-get install -y "${missing[@]}"
    else
        info "все нужные пакеты уже установлены"
    fi
    ok "пакеты готовы"
}

# ---------------------------------------------------------------- этап 2

kiauh_set_fork_repo() {
    local cfg=$KIAUH_DIR/kiauh.cfg
    [[ $DRY_RUN -eq 1 ]] && { info "[dry-run] kiauh.cfg: единственный репозиторий Klipper = $KLIPPER_REPO_URL, $KLIPPER_BRANCH"; return; }
    [[ -f $cfg ]] || cp "$KIAUH_DIR/default.kiauh.cfg" "$cfg"
    python3 -I - "$cfg" "$KLIPPER_REPO_URL, $KLIPPER_BRANCH" <<'PYEND'
import sys, re
path, repo = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().split("\n")
out, section, skipping = [], None, False
for line in lines:
    m = re.match(r"\[(.+)\]\s*$", line)
    if m:
        section, skipping = m.group(1), False
    if section == "klipper" and line.startswith("repositories:"):
        out.append("repositories:")
        out.append("    " + repo)
        skipping = True
        continue
    if skipping:
        if line.startswith((" ", "\t")) and line.strip():
            continue
        skipping = False
    out.append(line)
open(path, "w", encoding="utf-8").write("\n".join(out))
PYEND
}

klipper_is_fork() {
    [[ -d $KLIPPER_DIR/.git ]] || return 1
    git -C "$KLIPPER_DIR" remote get-url origin 2>/dev/null | grep -qi 'dmbutyugin/klipper' \
        && [[ $(git -C "$KLIPPER_DIR" rev-parse --abbrev-ref HEAD) == "$KLIPPER_BRANCH" ]]
}

switch_klipper_to_fork() {
    warn "$KLIPPER_DIR не является форком $KLIPPER_REPO_URL ($KLIPPER_BRANCH)"
    if [[ -n $(git -C "$KLIPPER_DIR" status --porcelain --untracked-files=no) ]]; then
        die "в $KLIPPER_DIR есть локальные изменения; зафиксируйте или откатите их и запустите снова"
    fi
    ask_yn "Переключить $KLIPPER_DIR на форк (локальная ветка будет заменена)?" y || die "без форка VOSTOK работать не будет"
    run git -C "$KLIPPER_DIR" remote set-url origin "$KLIPPER_REPO_URL"
    run git -C "$KLIPPER_DIR" fetch origin "$KLIPPER_BRANCH"
    run git -C "$KLIPPER_DIR" checkout -B "$KLIPPER_BRANCH" "origin/$KLIPPER_BRANCH"
    run git -C "$KLIPPER_DIR" branch --set-upstream-to="origin/$KLIPPER_BRANCH" "$KLIPPER_BRANCH"
    run "$KLIPPY_ENV/bin/pip" install -q -r "$KLIPPER_DIR/scripts/klippy-requirements.txt"
}

kiauh_install() { # компонент аргументы...
    info "KIAUH: install $*"
    run "$KIAUH_DIR/kiauh.sh" install "$@"
}

stage_software() {
    step "KIAUH, Klipper (форк), Moonraker, Fluidd, katapult"
    if [[ ! -d $KIAUH_DIR/.git ]]; then
        run git clone "$KIAUH_REPO_URL" "$KIAUH_DIR"
    else
        info "KIAUH уже установлен"
    fi

    if [[ -d $KLIPPER_DIR/.git ]]; then
        klipper_is_fork && info "Klipper: форк уже установлен ($(host_version))" || switch_klipper_to_fork
    else
        kiauh_set_fork_repo
        kiauh_install klipper --count 1
    fi
    if [[ ! -d $MOONRAKER_DIR_DEFAULT/.git ]]; then
        kiauh_install moonraker --create-example-cfg
    else
        info "Moonraker уже установлен"
    fi
    if [[ ! -d $HOME/fluidd ]]; then
        kiauh_install fluidd --install-config
    else
        info "Fluidd уже установлен"
    fi

    # gcode_shell_command нужен макросам Input Shaping (гайд: KIAUH -> Extensions -> G-Code Shell Command, пример: N)
    local extras=$KLIPPER_DIR/klippy/extras
    if [[ ! -f $extras/gcode_shell_command.py ]]; then
        if [[ -f $GCODE_SHELL_ASSET || $DRY_RUN -eq 1 ]]; then
            run cp "$GCODE_SHELL_ASSET" "$extras/"
            info "установлено расширение gcode_shell_command"
        else
            warn "не найден $GCODE_SHELL_ASSET: поставьте расширение через KIAUH -> Extensions"
        fi
    else
        info "gcode_shell_command уже установлен"
    fi

    if [[ ! -d $KATAPULT_DIR/.git ]]; then
        run git clone "$KATAPULT_REPO_URL" "$KATAPULT_DIR"
    else
        info "katapult уже установлен"
    fi

    if [[ $DRY_RUN -eq 0 ]]; then
        "$KLIPPY_ENV/bin/python" "$KLIPPER_DIR/klippy/klippy.py" --import-test >/dev/null \
            || die "klippy --import-test не прошёл"
    fi
    ok "программное обеспечение готово"
}
MOONRAKER_DIR_DEFAULT=${MOONRAKER_DIR:-$HOME/moonraker}

print_plan() {
    info ""
    info "План установки:"
    info "  Главная плата: $(main_label), режим: $([[ $MODE == bridge ]] && echo 'мост USB-CAN (по гайду)' || echo 'USB')"
    if [[ $HEADS == none ]]; then
        info "  Платы голов: нет"
    else
        info "  Платы голов: $(head_label), 2 шт., CAN $CAN_IFACE 1 Мбит"
    fi
    info "  ALPS: $ALPS_COUNT"
    info ""
    info "Шаги с железом:"
    local i n=1
    for ((i = 0; i < ALPS_COUNT; i++)); do
        info "  $n. ALPS $(alps_side $i): katapult через DFU, затем Klipper"; n=$((n + 1))
    done
    if [[ $HEADS != none ]]; then
        info "  $n. $(head_label) (обе, по очереди): katapult через DFU по USB"; n=$((n + 1))
    fi
    info "  $n. $(main_label): katapult и Klipper по DFU (джампер BOOT0; можно выбрать katapult по DFU + Klipper через katapult), режим: $([[ $MODE == bridge ]] && echo 'USB-CAN мост' || echo USB)"; n=$((n + 1))
    if [[ $HEADS != none ]]; then
        info "  $n. $(head_label) (обе, по очереди): Klipper по CAN"; n=$((n + 1))
    fi
    info "  $n. Прошивки собираются из $CONFIGS_DIR и $KATAPULT_CONFIGS"
}

# ---------------------------------------------------------------- этап 4: CAN

stage_can() {
    [[ $HEADS == none ]] && return 0
    step "Интерфейс CAN ($CAN_IFACE)"
    if [[ $DRY_RUN -eq 0 ]]; then sudo modprobe -a can can_raw gs_usb 2>/dev/null || true; fi
    local f=/etc/network/interfaces.d/can0 body
    if dpkg -s ifupdown >/dev/null 2>&1; then
        body=$'allow-hotplug can0\niface can0 can static\n    bitrate 1000000\n    up ip link set can0 txqueuelen 128\n'
        if [[ -f $f ]] && grep -q 'bitrate 1000000' "$f"; then
            info "$f уже настроен"
        else
            info "создаю $f (по гайду)"
            if [[ $DRY_RUN -eq 1 ]]; then
                info "[dry-run] sudo tee $f <<< '$body'"
            else
                printf '%s' "$body" | sudo tee "$f" >/dev/null
            fi
        fi
    else
        info "ifupdown не установлен: настраиваю systemd-networkd"
        if [[ $DRY_RUN -eq 1 ]]; then
            info "[dry-run] /etc/systemd/network/80-can0.network + .link (BitRate=1000000, TransmitQueueLength=128)"
        else
            printf '[Match]\nName=can0\n\n[CAN]\nBitRate=1M\n' | sudo tee /etc/systemd/network/80-can0.network >/dev/null
            printf '[Match]\nOriginalName=can0\n\n[Link]\nTransmitQueueLength=128\n' | sudo tee /etc/systemd/network/80-can0.link >/dev/null
            sudo systemctl enable systemd-networkd >/dev/null 2>&1 || true
        fi
    fi
    ok "настройка CAN записана (интерфейс появится, когда будет прошит мост)"
}

# Поднять can0 вручную, если автоматически не поднялся
bring_up_can() {
    local i
    for ((i = 0; i < 40; i++)); do
        ip link show "$CAN_IFACE" >/dev/null 2>&1 && break
        sleep 0.5
    done
    ip link show "$CAN_IFACE" >/dev/null 2>&1 || return 1
    if ! can_iface_up; then
        sudo ip link set "$CAN_IFACE" down type can 2>/dev/null || true
        sudo ip link set "$CAN_IFACE" up type can bitrate 1000000 || return 1
    fi
    sudo ip link set "$CAN_IFACE" txqueuelen 128 || true
    can_iface_up
}

check_can_health() {
    local out
    out=$(ip -s -d link show "$CAN_IFACE" 2>/dev/null || true)
    info "$(printf '%s\n' "$out" | sed -n '1,3p')"
    if grep -qi 'BUS-OFF' <<<"$out"; then
        warn "CAN в состоянии BUS-OFF. Перезапуск: sudo ip link set $CAN_IFACE down type can && sudo ip link set $CAN_IFACE up type can bitrate 1000000"
        warn "Если повторяется: проверьте терминаторы (около 60 Ом между CAN_H и CAN_L при выключенном питании) и перепрошейте Klipper на платах голов"
        return 1
    fi
}

# ---------------------------------------------------------------- этап 5: прошивка

# Сборка katapult вне репозитория: build_katapult <конфиг> -> путь к katapult.bin в KATAPULT_BIN
KATAPULT_BIN=""
build_katapult() {
    local cfg=$1 key work
    key=$(basename "$cfg" .config)
    work=$BUILD_DIR/katapult-$key
    [[ -f $cfg ]] || die "нет конфига katapult: $cfg (создайте: tools/gen_configs.sh)"
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] сборка katapult ($key)"; KATAPULT_BIN=$work/out/katapult.bin; return; fi
    rm -rf "$work"; mkdir -p "$work"
    cp "$cfg" "$work/.config"
    info "сборка katapult ($key) ..."
    local mk=(make -C "$KATAPULT_DIR" "KCONFIG_CONFIG=$work/.config" "OUT=$work/out/")
    "${mk[@]}" olddefconfig >"$work/make.log" 2>&1 || { tail -n 20 "$work/make.log" >&2; die "olddefconfig katapult ($key) не удался"; }
    "${mk[@]}" -j"$(nproc)" >>"$work/make.log" 2>&1 || { tail -n 30 "$work/make.log" >&2; die "сборка katapult ($key) не удалась, лог: $work/make.log"; }
    [[ -f $work/out/katapult.bin ]] || die "сборка katapult ($key) не создала katapult.bin"
    KATAPULT_BIN=$work/out/katapult.bin
    ok "katapult собран: $KATAPULT_BIN ($(stat -c %s "$KATAPULT_BIN") байт)"
}

# Ждёт ровно одно DFU-устройство нужного семейства. Возврат 0 = готово, 1 = пользователь отказался.
wait_dfu() { # семейство подпись
    local fam=$1 label=$2 n i got
    while true; do
        for ((i = 0; i < 20; i++)); do
            n=$(dfu_count)
            [[ $n -ge 1 ]] && break
            sleep 0.5
        done
        if [[ $n -eq 0 ]]; then
            warn "устройство DFU (0483:df11) не найдено. Проверьте: USB-кабель данных, питание платы, режим DFU ($label)"
            ask_yn "Попробовать ещё раз?" y || return 1
            pause_hw "Переведите $label в DFU и нажмите Enter." 1
            continue
        fi
        if [[ $n -gt 1 ]]; then
            warn "в режиме DFU сразу $n устройства. Оставьте в DFU только $label (остальные перезагрузите/отключите)"
            ask_yn "Проверить ещё раз?" y || return 1
            continue
        fi
        got=$(dfu_family)
        if [[ $got != "$fam" ]]; then
            warn "в DFU найден чип: $(family_name "$got"), ожидался $(family_name "$fam") ($label)"
            ask_yn "Это всё равно нужная плата, продолжить?" n && return 0
            ask_yn "Попробовать ещё раз (перевести в DFU нужную плату)?" y || return 1
            continue
        fi
        ok "DFU: $(family_name "$got")"
        return 0
    done
}

# Запуск dfu-util (или make flash): вывод на экран и в лог. Успехом считается запись данных ("Download done"),
# даже если dfu-util вернул ошибку get_status после 100%: плата к этому моменту уже перезагрузилась.
dfu_run() { # команда...
    local out rc=1
    out=$(mktemp)
    log_to_file "\$ $*"
    "$@" 2>&1 | tee "$out" || true
    grep -qE 'Download done|File downloaded successfully' "$out" && rc=0
    rm -f "$out"
    return $rc
}

# Прошивка katapult по DFU. Режим make - как у пользователя для ALPS (make flash katapult),
# режим guide - команда из гайда (mass-erase, запасной вариант без него). 0 = записано, 1 = нет.
dfu_flash_katapult() { # режим(make|guide) конфиг
    local mode=$1 cfg=$2 key work
    key=$(basename "$cfg" .config); work=$BUILD_DIR/katapult-$key
    ( build_katapult "$cfg" ) || { warn "сборка katapult ($key) не удалась"; return 1; }
    KATAPULT_BIN=$work/out/katapult.bin
    [[ $DRY_RUN -eq 1 ]] && { info "[dry-run] dfu-util -> $KATAPULT_BIN"; return 0; }
    [[ -f $KATAPULT_BIN ]] || { warn "нет $KATAPULT_BIN"; return 1; }
    if [[ $mode == make ]]; then
        # make flash из katapult (sudo dfu-util -R -a 0 -s 0x08000000:leave)
        dfu_run make -C "$KATAPULT_DIR" "KCONFIG_CONFIG=$work/.config" "OUT=$work/out/" flash FLASH_DEVICE=0483:df11 && return 0
    else
        dfu_run sudo dfu-util -R -a 0 -s 0x08000000:mass-erase:force:leave -D "$KATAPULT_BIN" -d 0483:df11 && return 0
        if [[ $(dfu_count) -ge 1 ]]; then
            warn "с mass-erase не вышло, пробую без него (как рекомендует гайд)"
            dfu_run sudo dfu-util -R -a 0 -s 0x08000000:leave -D "$KATAPULT_BIN" -d 0483:df11 && return 0
        fi
    fi
    warn "katapult не записан по DFU (в выводе dfu-util нет 'Download done')"
    return 1
}

# Ждёт появления нового usb-katapult_<чип>_* (которого не было в списке «до»): результат в NEW_KATAPULT_DEV
NEW_KATAPULT_DEV=""
wait_new_katapult() { # чип секунд файл_со_списком_до
    local chip=$1 secs=$2 before=$3 i f
    NEW_KATAPULT_DEV=""
    for ((i = 0; i < secs * 2; i++)); do
        for f in "$BYID_DIR"/usb-katapult_"${chip}"_*; do
            [[ -e $f ]] || continue
            grep -qxF "$f" "$before" || { NEW_KATAPULT_DEV=$f; return 0; }
        done
        sleep 0.5
    done
    return 1
}

snapshot_katapult() { # файл
    byid_find 'usb-katapult_*' >"$1" || true
}

katapult_devices() { byid_find "usb-katapult_${1}_*"; }   # чип

# Выбор из нескольких найденных katapult-устройств (одно - берём сразу)
pick_katapult() { # подпись список_путей
    local label=$1 list=$2 n names=() p
    n=$(grep -c . <<<"$list" || true)
    if [[ $n -le 1 ]]; then printf '%s' "$list"; return; fi
    while IFS= read -r p; do names+=("$(basename "$p")"); done <<<"$list"
    p=$(ask_choice "$label: в katapult сразу несколько плат, какая нужна?" "${names[0]}" "${names[@]}")
    printf '%s/%s' "$BYID_DIR" "$p"
}

# Получить плату в режиме katapult: через DFU (прошивка katapult) или без DFU, если katapult уже на плате.
# 0 = готово (устройство в NEW_KATAPULT_DEV), 1 = не удалось (причина выведена); сама установка не прерывается.
enter_katapult() { # подпись чип семейство katapult_cfg режим подсказка_по_DFU [сообщение_после_DFU]
    local label=$1 chip=$2 fam=$3 kcfg=$4 mode=$5 hint=$6 after=${7:-} before ans found n
    NEW_KATAPULT_DEV=""
    pause_hw "$label: $hint" 1
    ans=$(cat "$TMP_ANS" 2>/dev/null || true)
    if [[ $DRY_RUN -eq 1 ]]; then
        dfu_flash_katapult "$mode" "$kcfg"
        [[ -n $after ]] && pause_hw "$after"
        NEW_KATAPULT_DEV=$BYID_DIR/usb-katapult_${chip}_DRYRUN-if00
        return 0
    fi
    before=$(mktemp)
    if [[ $ans == [sSыЫ]* ]]; then
        # katapult уже на плате (например, прошлая попытка) или он запустится двойным RESET
        found=$(katapult_devices "$chip"); n=$(grep -c . <<<"$found" || true)
        if [[ $n -ge 1 ]]; then
            NEW_KATAPULT_DEV=$(pick_katapult "$label" "$found")
            rm -f "$before"
            ok "$label уже в режиме katapult: $(basename "$NEW_KATAPULT_DEV")"
            return 0
        fi
        info "Пропускаю DFU: дважды быстро нажмите RESET на $label, чтобы войти в katapult."
        snapshot_katapult "$before"
        if ! wait_new_katapult "$chip" 25 "$before"; then
            rm -f "$before"
            warn "usb-katapult_${chip}_* не появился. Двойной RESET нужно нажимать быстро (светодиод katapult мигает медленно)."
            return 1
        fi
    else
        if ! wait_dfu "$fam" "$label"; then rm -f "$before"; return 1; fi
        # снимок после входа в DFU: katapult этой платы в by-id сейчас нет, старое имя не помешает
        snapshot_katapult "$before"
        if ! dfu_flash_katapult "$mode" "$kcfg"; then rm -f "$before"; return 1; fi
        [[ -n $after ]] && pause_hw "$after"
        if ! wait_new_katapult "$chip" 20 "$before"; then
            warn "katapult ещё не появился. После прошивки по DFU ОДИНОЧНЫЙ RESET может запустить не katapult, а прежнюю прошивку: ДВАЖДЫ быстро нажмите RESET."
            info "Устройства: $(ls "$BYID_DIR" 2>/dev/null | tr '\n' ' ')"
            if ! wait_new_katapult "$chip" 30 "$before"; then
                rm -f "$before"
                warn "usb-katapult_${chip}_* так и не появился (ls $BYID_DIR). Если плата в DFU - katapult не записан, повторите через DFU."
                return 1
            fi
        fi
    fi
    rm -f "$before"
    ok "$label в режиме katapult: $(basename "$NEW_KATAPULT_DEV")"
}

# Сборка прошивки Klipper без выхода из скрипта при ошибке: 0 = BUILT_BIN[cfg] готов
build_fw_safe() { # конфиг чип
    local cfg=$1 chip=$2
    [[ $DRY_RUN -eq 1 ]] && return 0
    ( build_firmware "$cfg" "$chip" ) || { warn "сборка прошивки Klipper ($(basename "$cfg")) не удалась"; return 1; }
    BUILT_BIN[$cfg]=$FIRMWARE_DIR/$(basename "$cfg" .config)-$(host_version).bin
    [[ -f ${BUILT_BIN[$cfg]} ]] || { warn "нет файла ${BUILT_BIN[$cfg]}"; return 1; }
}

# Klipper на плату в katapult по USB. Для обычной платы ждёт usb-Klipper_*, для моста - появления gs_usb и can0.
# Серийный номер результата в FLASHED_SERIAL. 0 = прошито, 1 = ошибка (плата остаётся в katapult).
FLASHED_SERIAL=""
FLASH_ERR=""
flash_klipper_via_katapult() { # подпись katapult_dev klipper_cfg чип bridge(0|1)
    local label=$1 dev=$2 cfg=$3 chip=$4 bridge=$5 serial bin
    serial=$(sed -n 's/^usb-katapult_.*_\([^_]*\)-if[0-9]*$/\1/p' <<<"$(basename "$dev")")
    step "Klipper -> $label"
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] сборка $(basename "$cfg"), flashtool.py -d $dev -f <bin>"; FLASHED_SERIAL=DRYRUN; return 0; fi
    build_fw_safe "$cfg" "$chip" || return 1
    bin=${BUILT_BIN[$cfg]}
    local errf; errf=$(mktemp)
    if ! python3 "$KATAPULT_DIR/scripts/flashtool.py" -d "$dev" -f "$bin" 2>&1 | tee "$errf"; then
        FLASH_ERR=$(grep -E 'FlashError' "$errf" | tail -n 1 || true)
        rm -f "$errf"
        log_to_file "flashtool: ${FLASH_ERR:-ошибка}"
        warn "причина: ${FLASH_ERR:-см. вывод выше}"
        cat >&2 <<EOF

Прошивка Klipper на $label не удалась. katapult остаётся в плате.
  - ls $BYID_DIR (должен быть usb-katapult_*), при необходимости дважды быстро нажмите RESET;
  - повтор вручную: python3 $KATAPULT_DIR/scripts/flashtool.py -d $dev -f $bin
  - если запись блока стабильно не проходит, в меню ниже выберите прошивку Klipper напрямую по DFU (katapult не затрагивается)
EOF
        return 1
    fi
    rm -f "$errf"
    FLASHED_SERIAL=$serial
    if [[ $bridge -eq 1 ]]; then
        if ! bring_up_can; then
            warn "после прошивки моста не появился рабочий интерфейс $CAN_IFACE (lsusb: Geschwister Schneider / 1d50:606f; ip link show $CAN_IFACE)"
            return 1
        fi
        ok "$label: мост USB-CAN работает, $CAN_IFACE поднят"
    else
        if ! wait_for_device "$BYID_DIR/usb-Klipper_${chip}_${serial}-if00" 20; then
            warn "после прошивки $label не появился usb-Klipper_${chip}_${serial}-if00; проверьте ls $BYID_DIR"
            return 1
        fi
        state_set "$serial" "$(host_version)"
        ok "$label прошит (serial $serial)"
    fi
}

# Klipper напрямую по DFU (запасной путь, если flashtool не может записать блок). Без katapult_cfg katapult
# в начале флеша не затрагивается; с ним katapult и Klipper пишутся за один сеанс DFU (рекомендуемый способ).
# Katapult запускает приложение со смещения CONFIG_FLASH_APPLICATION_ADDRESS.
# Серийный номер результата в FLASHED_SERIAL (для моста пустой). 0 = прошито, 1 = ошибка.
dfu_flash_klipper() { # подпись конфиг чип семейство bridge(0 USB|1 мост|2 только CAN) [katapult_cfg [режим make|guide]]
    local label=$1 cfg=$2 chip=$3 fam=$4 bridge=$5 kcfg=${6:-} kmode=${7:-guide} addr bin before f i dev="" kbin="" kkey
    FLASHED_SERIAL=""
    addr=$(sed -n 's/^CONFIG_FLASH_APPLICATION_ADDRESS=\(.*\)$/\1/p' "$cfg")
    [[ -n $addr ]] || { warn "в $(basename "$cfg") нет CONFIG_FLASH_APPLICATION_ADDRESS"; return 1; }
    if [[ -n $kcfg ]]; then
        step "katapult и Klipper по DFU за один сеанс -> $label"
        kkey=$(basename "$kcfg" .config)
        ( build_katapult "$kcfg" ) || { warn "сборка katapult ($kkey) не удалась"; return 1; }
        kbin=$BUILD_DIR/katapult-$kkey/out/katapult.bin
    else
        step "Klipper по DFU (без katapult) -> $label"
    fi
    build_fw_safe "$cfg" "$chip" || return 1
    bin=${BUILT_BIN[$cfg]:-}
    if [[ -n $kcfg ]]; then
        pause_hw "$label: переведите плату в DFU (джампер BOOT0 или кнопка BOOT, затем RESET) и нажмите Enter. В один сеанс запишутся katapult (0x08000000) и Klipper (по адресу $addr)."
    else
        pause_hw "$label: переведите плату в DFU (джампер BOOT0 или кнопка BOOT, затем RESET) и нажмите Enter. Katapult в начале флеша не затрагивается; Klipper запишется по адресу $addr."
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        [[ -n $kcfg ]] && info "[dry-run] dfu-util -a 0 -s 0x08000000$([[ $kmode == guide ]] && echo ':mass-erase:force') -D $kkey/katapult.bin"
        info "[dry-run] dfu-util -a 0 -s $addr:leave -D ${bin:-$(basename "$cfg" .config)-$(host_version).bin}"; FLASHED_SERIAL=DRYRUN; return 0
    fi
    wait_dfu "$fam" "$label" || return 1
    if [[ -n $kcfg ]]; then
        [[ -f $kbin ]] || { warn "нет $kbin"; return 1; }
        if [[ $kmode == guide ]]; then
            if ! dfu_run sudo dfu-util -a 0 -s 0x08000000:mass-erase:force -D "$kbin" -d 0483:df11; then
                [[ $(dfu_count) -ge 1 ]] || { warn "katapult не записан по DFU"; return 1; }
                warn "с mass-erase не вышло, пробую без него"
                dfu_run sudo dfu-util -a 0 -s 0x08000000 -D "$kbin" -d 0483:df11 || { warn "katapult не записан по DFU (нет 'Download done')"; return 1; }
            fi
        else
            dfu_run sudo dfu-util -a 0 -s 0x08000000 -D "$kbin" -d 0483:df11 || { warn "katapult не записан по DFU (нет 'Download done')"; return 1; }
        fi
        sleep 1
        [[ $(dfu_count) -ge 1 ]] || { warn "после записи katapult плата вышла из DFU; повторите: переведите её в DFU снова"; return 1; }
    fi
    before=$(mktemp)
    byid_find "usb-Klipper_${chip}_*" >"$before" || true
    if ! dfu_run sudo dfu-util -a 0 -s "${addr}:leave" -D "$bin" -d 0483:df11; then
        rm -f "$before"; warn "Klipper не записан по DFU (в выводе dfu-util нет 'Download done')"; return 1
    fi
    pause_hw "Снимите джампер BOOT0 (если ставили) и нажмите RESET на $label. Если плата не запустилась, нажмите RESET ещё раз."
    if [[ $bridge -eq 2 ]]; then rm -f "$before"; ok "$label прошит по DFU (дальше доступен только по CAN)"; return 0; fi
    if [[ $bridge -eq 1 ]]; then
        rm -f "$before"
        bring_up_can || { warn "после прошивки моста не появился рабочий интерфейс $CAN_IFACE"; return 1; }
        ok "$label: мост USB-CAN работает, $CAN_IFACE поднят"
        return 0
    fi
    for ((i = 0; i < 40; i++)); do
        for f in "$BYID_DIR"/usb-Klipper_"${chip}"_*; do
            [[ -e $f ]] || continue
            grep -qxF "$f" "$before" || { dev=$f; break 2; }
        done
        sleep 0.5
    done
    rm -f "$before"
    [[ -n $dev ]] || { warn "после прошивки не появился usb-Klipper_${chip}_* (ls $BYID_DIR)"; return 1; }
    FLASHED_SERIAL=$(sed -n "s/^usb-Klipper_${chip}_\(.*\)-if[0-9]*\$/\1/p" <<<"$(basename "$dev")")
    state_set "$FLASHED_SERIAL" "$(host_version)"
    ok "$label прошит по DFU (serial $FLASHED_SERIAL)"
}

# ---------------------------------------------------------------- повтор и пропуск плат

board_opt_skipped() { # имя: задан ли --skip-board для этой платы
    local b
    for b in "${OPT_SKIP_BOARDS[@]}"; do [[ $b == "$1" ]] && return 0; done
    return 1
}


# На плате с этим ключом стоит Klipper текущей версии хоста (по flashed.tsv)
version_ok() { # ключ
    local v; v=$(state_get "$1")
    [[ -n $v && $(norm_version "$v") == "$(norm_version "$(host_version)")" ]]
}

# Меню после неудачи. Печатает: retry|dfu|skip|abort. Без терминала или с -y - skip.
flash_menu() { # подпись
    local ans
    if [[ $ASSUME_YES -eq 1 ]] || ! have_tty; then echo skip; return; fi
    ans=$(ask_choice "$1: прошивка не удалась. Что делать?" "Повторить" \
        "Повторить" "Прошить katapult и Klipper сразу по DFU" "Прошить заново через DFU (katapult), Klipper через katapult" \
        "Прошить Klipper напрямую по DFU (без katapult)" "Пропустить эту плату" "Прервать установку")
    case $ans in
        "Прошить katapult и Klipper сразу"*) echo dfuall ;; "Прошить заново"*) echo dfu ;; "Прошить Klipper напрямую"*) echo dfuk ;; "Пропустить"*) echo skip ;; "Прервать"*) echo abort ;; *) echo retry ;;
    esac
}

# Прошивка одной платы с повтором. Функция fn(фаза, аргументы...) возвращает 0 при успехе и при неудаче
# записывает в BOARD_PHASE, с какого шага повторять: full (с DFU) или klipper (плата уже в katapult).
# Возврат 1 = плата пропущена пользователем; установка при этом продолжается.
flash_board() { # подпись функция [аргументы]; начальная фаза - BOARD_START_PHASE (по умолчанию full)
    local label=$1 fn=$2 phase=${BOARD_START_PHASE:-full} c; shift 2
    BOARD_START_PHASE=full
    BOARD_PHASE=$phase; BOARD_DEV=""
    while true; do
        if "$fn" "$phase" "$@"; then save_devices quiet; return 0; fi
        warn "$label: прошивка не удалась"
        c=$(flash_menu "$label")
        case $c in
            retry) phase=$BOARD_PHASE ;;
            dfu) phase=full ;;
            dfuall) phase=dfuall ;;
            dfuk) phase=dfuk ;;
            skip) FLASH_FAILED+=("$label: не прошита"); warn "$label пропущена, продолжаю с остальными платами"; return 1 ;;
            abort) die "установка прервана пользователем ($label)" ;;
        esac
    done
}

# ---------------------------------------------------------------- ALPS

alps_candidates() { # serial присутствующих ALPS с Klipper: сначала в порядке прошлого devices.tsv, без занятых
    local s seen=" ${RES_ALPS_SERIAL[*]} "
    for s in $(prev_keys stm32f072xb.config) \
             $(byid_find 'usb-Klipper_stm32f072xb_*' | sed -n 's/.*stm32f072xb_\(.*\)-if00$/\1/p'); do
        [[ -e $BYID_DIR/usb-Klipper_stm32f072xb_${s}-if00 ]] || continue
        [[ $seen == *" $s "* ]] && continue
        seen+="$s "
        printf '%s\n' "$s"
    done
}

# 0 = ALPS i пропущен (уже прошит), 1 = нужно прошивать
alps_try_skip() { # индекс
    local i=$1 s forced=0
    board_opt_skipped alps || board_opt_skipped "alps$i" && forced=1
    [[ $forced -eq 0 && $OPT_REFLASH -eq 1 ]] && return 1
    s=$(alps_candidates | head -n 1)
    if [[ -z $s ]]; then
        [[ $forced -eq 1 ]] || return 1
        warn "--skip-board: ALPS $(alps_side "$i") не найден, serial неизвестен (впишите [mcu alps...] вручную)"
        FLASH_SKIPPED+=("ALPS $(alps_side "$i"): пропущен по --skip-board, serial неизвестен")
        return 0
    fi
    if [[ $forced -eq 0 ]]; then
        version_ok "$s" || return 1
        ask_yn "ALPS $(alps_side "$i"): найден $s, Klipper $(host_version) уже установлен. Пропустить прошивку?" y || return 1
    fi
    RES_ALPS_SERIAL[$i]=$s
    FLASH_SKIPPED+=("ALPS $(alps_side "$i"): уже прошит ($s)")
    ok "ALPS $(alps_side "$i"): пропускаю, serial $s"
    save_devices quiet
}

try_alps() { # фаза индекс
    local phase=$1 i=$2 label fcfg=$CONFIGS_DIR/stm32f072xb.config
    label="ALPS $(alps_side "$i")"
    if [[ $phase == dfuk || $phase == dfuall ]]; then
        BOARD_PHASE=$phase
        if [[ $phase == dfuall ]]; then
            dfu_flash_klipper "$label" "$fcfg" stm32f072xb f0 0 "$KATAPULT_CONFIGS/stm32f072xb.config" make || return 1
        else
            dfu_flash_klipper "$label" "$fcfg" stm32f072xb f0 0 || return 1
        fi
        RES_ALPS_SERIAL[$i]=$FLASHED_SERIAL
        return 0
    fi
    [[ $phase == klipper && ! -e $BOARD_DEV ]] && phase=full
    if [[ $phase == full ]]; then
        BOARD_PHASE=full
        enter_katapult "$label" stm32f072xb f0 "$KATAPULT_CONFIGS/stm32f072xb.config" make \
            "переведите этот ALPS в режим DFU (BOOT + RESET, затем отпустить BOOT)" || return 1
        BOARD_DEV=$NEW_KATAPULT_DEV
    fi
    BOARD_PHASE=klipper
    flash_klipper_via_katapult "$label" "$BOARD_DEV" "$fcfg" stm32f072xb 0 || return 1
    RES_ALPS_SERIAL[$i]=$FLASHED_SERIAL
}

stage_flash_alps() {
    local i
    for ((i = 0; i < ALPS_COUNT; i++)); do
        step "ALPS $(alps_side "$i")"
        alps_try_skip "$i" && continue
        cat <<EOF
Датчик ALPS подключите USB-кабелем к хосту (другие ALPS можно не отключать).
Режим DFU: зажмите BOOT, нажмите и отпустите RESET, отпустите BOOT.
EOF
        flash_board "ALPS $(alps_side "$i")" try_alps "$i" || true
    done
}

# ---------------------------------------------------------------- платы голов

# UUID с «Application: Klipper»/«Katapult» в CAN
can_uuids() { # Klipper|Katapult
    local app=$1 out
    if [[ $app == Katapult ]]; then
        out=$(python3 "$KATAPULT_DIR/scripts/flashtool.py" -i "$CAN_IFACE" -q 2>&1 || true)
        sed -n 's/.*Detected UUID: \([0-9a-fA-F]\{12\}\),.*Application: Katapult.*/\1/p' <<<"$out"
    else
        out=$("$KLIPPY_ENV/bin/python" "$KLIPPER_DIR/scripts/canbus_query.py" "$CAN_IFACE" 2>&1 || true)
        sed -n 's/.*canbus_uuid=\([0-9a-fA-F]\{12\}\),.*Application: Klipper.*/\1/p' <<<"$out"
    fi
}

# 0 = платы голов уже прошиты (оба этапа пропускаются), 1 = прошивать
heads_try_skip() {
    [[ $HEADS == none ]] && return 1
    local forced=0 u0 u1 uuids
    board_opt_skipped heads && forced=1
    [[ $forced -eq 0 && $OPT_REFLASH -eq 1 ]] && return 1
    { read -r u0; read -r u1; } < <(prev_keys "$(head_cfg_name)") || true
    if [[ $forced -eq 0 ]]; then
        [[ -n ${u0:-} && -n ${u1:-} ]] || return 1
        can_iface_up || return 1
        uuids=$(can_uuids Klipper)
        grep -qix "$u0" <<<"$uuids" && grep -qix "$u1" <<<"$uuids" || return 1
        version_ok "$u0" && version_ok "$u1" || return 1
        ask_yn "$(head_label): обе платы на шине, Klipper $(host_version) уже установлен. Пропустить прошивку плат голов?" y || return 1
    elif [[ -z ${u0:-} || -z ${u1:-} ]]; then
        warn "--skip-board heads: UUID плат голов неизвестны (нет devices.tsv), впишите canbus_uuid в printer.cfg вручную"
    fi
    RES_HEAD_UUID=("${u0:-}" "${u1:-}")
    HEADS_SKIP=1
    FLASH_SKIPPED+=("$(head_label): уже прошиты")
    ok "платы голов: пропускаю (${u0:-?}, ${u1:-?})"
    save_devices quiet
}

HEAD_DFU_DONE=(0 0)  # на плате головы Klipper уже записан по DFU вместе с katapult

# katapult и Klipper платы головы за один сеанс DFU (USB), затем плата работает только по CAN
head_dfu_all() { # индекс
    local i=$1
    dfu_flash_klipper "$(head_label) $(head_side "$i")" "$CONFIGS_DIR/$(head_cfg_name)" "$(head_chip)" g 2 \
        "$KATAPULT_CONFIGS/$(head_cfg_name)" guide || return 1
    HEAD_DFU_DONE[$i]=1
}

try_head_katapult() { # фаза индекс
    local i=$2 kcfg ans
    kcfg=$KATAPULT_CONFIGS/$(head_cfg_name)
    if [[ $1 == dfuall ]]; then
        BOARD_PHASE=dfuall
        head_dfu_all "$i" || return 1
        pause_hw "Отключите USB от $(head_label) $(head_side "$i"). Дальше она будет подключена только по CAN."
        return 0
    fi
    pause_hw "$(head_label) $(head_side "$i"): подключите USB, переведите в DFU и нажмите Enter. DFU: $(head_dfu_hint)." 1
    ans=$(cat "$TMP_ANS" 2>/dev/null || true)
    if [[ $ans == [sSыЫ]* && $DRY_RUN -eq 0 ]]; then
        info "DFU для этой платы головы пропущен (katapult уже на плате)"
        return 0
    fi
    if [[ $DRY_RUN -eq 1 ]]; then dfu_flash_katapult guide "$kcfg"; return 0; fi
    wait_dfu g "$(head_label) $(head_side "$i")" || return 1
    dfu_flash_katapult guide "$kcfg" || return 1
    pause_hw "Отключите USB от $(head_label) $(head_side "$i"). Дальше она будет подключена только по CAN."
}

stage_flash_heads_katapult() {
    [[ $HEADS == none ]] && return 0
    heads_try_skip && return 0
    local i
    for ((i = 0; i < 2; i++)); do
        step "$(head_label): katapult, плата $(head_side "$i")"
        cat <<EOF
Эти шаги выполняются по одной плате:
  - подключите к хосту USB-кабелем ТОЛЬКО $(head_label) $(head_side "$i") (другую плату головы от USB отключите);
  - режим DFU: $(head_dfu_hint).
katapult на этих платах работает только по CAN, поэтому после прошивки отключите USB.
EOF
        if flash_board "$(head_label) $(head_side "$i") (katapult)" try_head_katapult "$i"; then
            ok "katapult записан на $(head_label) $(head_side "$i")"
        fi
    done
}

try_head_klipper() { # фаза индекс
    local i=$2 uuids n uuid fcfg bin
    fcfg=$CONFIGS_DIR/$(head_cfg_name)
    if [[ $1 == dfuall ]]; then
        BOARD_PHASE=dfuall
        pause_hw "Подключите USB-кабелем ТОЛЬКО $(head_label) $(head_side "$i") (CAN пока отключите): плату нужно перевести в DFU ($(head_dfu_hint))."
        head_dfu_all "$i" || return 1
    fi
    if [[ ${HEAD_DFU_DONE[$i]} -eq 1 ]]; then
        pause_hw "Отключите USB, подключите CAN-кабелем ТОЛЬКО $(head_label) $(head_side "$i") (вторую плату головы отключите), подайте питание и нажмите Enter."
        if [[ $DRY_RUN -eq 1 ]]; then RES_HEAD_UUID[$i]=00000000000$i; return 0; fi
        uuids=$(can_uuids Klipper | grep -vix "${RES_BRIDGE_UUID:-x}" || true); n=$(grep -c . <<<"$uuids" || true)
        if [[ $n -ne 1 ]]; then
            warn "ожидалась одна новая плата с Klipper на CAN (кроме моста), найдено: $n. Проверьте CAN_H/CAN_L, терминаторы, питание; оставьте подключённой только эту плату."
            return 1
        fi
        RES_HEAD_UUID[$i]=$uuids
        state_set "$uuids" "$(host_version)"
        ok "$(head_label) $(head_side "$i"): $uuids, Application: Klipper"
        return 0
    fi
    pause_hw "Подключите CAN-кабелем ТОЛЬКО $(head_label) $(head_side "$i") (вторую плату головы отключите) вместе с питанием платы и нажмите Enter."
    uuids=$(can_uuids Katapult); n=$(grep -c . <<<"$uuids" || true)
    if [[ $n -eq 0 ]]; then
        warn "плата katapult по CAN не найдена. Проверьте CAN_H/CAN_L, терминаторы 120 Ом (около 60 Ом на шине), питание плат голов."
        warn "Если на плате уже Klipper, дважды быстро нажмите RESET (красный светодиод мигает) - она станет Katapult."
        return 1
    fi
    if [[ $n -ne 1 ]]; then
        warn "ожидалась одна плата в katapult на CAN, найдено: $n (оставьте подключённой только $(head_label) $(head_side "$i"))"
        return 1
    fi
    uuid=$uuids
    build_fw_safe "$fcfg" "$(head_chip)" || return 1
    bin=${BUILT_BIN[$fcfg]:-}
    if [[ $DRY_RUN -eq 0 ]] && ! python3 "$KATAPULT_DIR/scripts/flashtool.py" -i "$CAN_IFACE" -u "$uuid" -f "$bin"; then
        warn "прошивка $(head_label) $(head_side "$i") ($uuid) не удалась: повтор python3 $KATAPULT_DIR/scripts/flashtool.py -i $CAN_IFACE -u $uuid -f $bin"
        return 1
    fi
    sleep 2
    if can_uuids Klipper | grep -qix "$uuid"; then
        ok "$(head_label) $(head_side "$i"): $uuid, Application: Klipper"
    else
        warn "после прошивки $uuid не отвечает как Klipper (canbus_query.py $CAN_IFACE); продолжаю"
    fi
    state_set "$uuid" "$(host_version)"
    RES_HEAD_UUID[$i]=$uuid
}

stage_flash_heads_klipper() {
    [[ $HEADS == none || $HEADS_SKIP -eq 1 ]] && return 0
    local i uuids n
    if [[ $DRY_RUN -eq 0 ]] && ! ip link show "$CAN_IFACE" >/dev/null 2>&1; then
        warn "интерфейса $CAN_IFACE нет (мост USB-CAN не работает): платы голов по CAN не прошиваю"
        FLASH_FAILED+=("$(head_label): не прошиты по CAN (нет $CAN_IFACE; прошейте Octopus и запустите установку снова)")
        return 0
    fi
    step "UUID моста ($(main_label))"
    info "Для этого этапа подайте питание 24 В на Octopus и платы голов и подключите CAN-кабели по схеме из гайда."
    if [[ $DRY_RUN -eq 1 ]]; then
        info "[dry-run] canbus_query.py $CAN_IFACE -> UUID Octopus"
        RES_BRIDGE_UUID=000000000000
    elif [[ -n $RES_BRIDGE_UUID ]]; then
        info "UUID Octopus (мост) известен: $RES_BRIDGE_UUID"
    else
        check_can_health || true
        uuids=$(can_uuids Klipper)
        n=$(grep -c . <<<"$uuids" || true)
        if [[ $n -gt 1 ]]; then
            pause_hw "На шине несколько устройств с Klipper. Отключите CAN-кабель от обеих плат голов (должен остаться только Octopus) и нажмите Enter."
            uuids=$(can_uuids Klipper)
            n=$(grep -c . <<<"$uuids" || true)
        fi
        if [[ $n -ne 1 ]]; then
            warn "ожидался один UUID на шине, найдено: $n"
            info "Проверьте: ip -s -d link show $CAN_IFACE; $KLIPPY_ENV/bin/python $KLIPPER_DIR/scripts/canbus_query.py $CAN_IFACE"
            FLASH_FAILED+=("Octopus: UUID моста не определён (впишите canbus_uuid в [mcu] вручную)")
        else
            RES_BRIDGE_UUID=$uuids
            state_set "$RES_BRIDGE_UUID" "$(host_version)"
            ok "UUID Octopus (мост): $RES_BRIDGE_UUID"
            save_devices quiet
        fi
    fi

    for ((i = 0; i < 2; i++)); do
        step "$(head_label) $(head_side "$i"): Klipper по CAN"
        if [[ $DRY_RUN -eq 1 ]]; then
            info "[dry-run] flashtool.py -i $CAN_IFACE -q -> UUID, затем -u UUID -f klipper.bin"
            RES_HEAD_UUID[$i]=00000000000$i
            continue
        fi
        flash_board "$(head_label) $(head_side "$i") (Klipper)" try_head_klipper "$i" || true
    done
    if [[ $DRY_RUN -eq 0 ]]; then
        pause_hw "Подключите CAN-кабелем обе платы голов вместе и нажмите Enter для проверки шины."
        uuids=$(can_uuids Klipper); n=$(grep -c . <<<"$uuids" || true)
        info "На шине устройств с Klipper: $n (ожидается 3: Octopus и две платы голов)"
        check_can_health || true
    fi
}

# ---------------------------------------------------------------- главная плата

# 0 = Octopus пропущен (уже прошит), 1 = прошивать
main_try_skip() {
    local forced=0 s u
    board_opt_skipped main && forced=1
    [[ $forced -eq 0 && $OPT_REFLASH -eq 1 ]] && return 1
    if [[ $MODE == usb ]]; then
        s=$(byid_find "usb-Klipper_${MAIN}_*" | sed -n "s/.*${MAIN}_\\(.*\\)-if00\$/\\1/p" | head -n 1)
        if [[ -z $s ]]; then
            [[ $forced -eq 1 ]] || return 1
            warn "--skip-board main: usb-Klipper_${MAIN}_* не найден, serial неизвестен (впишите [mcu] вручную)"
        elif [[ $forced -eq 0 ]]; then
            version_ok "$s" || return 1
            ask_yn "$(main_label): найден $s, Klipper $(host_version) уже установлен. Пропустить прошивку?" y || return 1
        fi
        RES_MAIN_SERIAL=$s
    else
        u=$(prev_keys "${MAIN}-canbridge.config" | head -n 1)
        if [[ $forced -eq 0 ]]; then
            [[ -n $u ]] || return 1
            can_iface_up || return 1
            can_uuids Klipper | grep -qix "$u" || return 1
            version_ok "$u" || return 1
            ask_yn "$(main_label): мост на шине ($u), Klipper $(host_version) уже установлен. Пропустить прошивку?" y || return 1
        elif [[ -z $u ]]; then
            warn "--skip-board main: UUID моста неизвестен (нет devices.tsv), впишите canbus_uuid в [mcu] вручную"
        fi
        RES_BRIDGE_UUID=${u:-}
    fi
    FLASH_SKIPPED+=("$(main_label): уже прошит")
    ok "$(main_label): пропускаю"
    save_devices quiet
}

try_main() { # фаза
    local phase=$1 kcfg fcfg bridge=0 fam=h7
    kcfg=$(katapult_cfg_for_main); fcfg=$(klipper_cfg_for_main)
    [[ $MODE == bridge ]] && bridge=1
    [[ $MAIN == stm32f446xx ]] && fam=f4
    if [[ $phase == dfuk || $phase == dfuall ]]; then
        BOARD_PHASE=$phase
        if [[ $phase == dfuall ]]; then
            dfu_flash_klipper "$(main_label)" "$fcfg" "$MAIN" "$fam" "$bridge" "$kcfg" guide || return 1
        else
            dfu_flash_klipper "$(main_label)" "$fcfg" "$MAIN" "$fam" "$bridge" || return 1
        fi
        if [[ $MODE == usb ]]; then RES_MAIN_SERIAL=$FLASHED_SERIAL; fi
        return 0
    fi
    [[ $phase == klipper && ! -e $BOARD_DEV ]] && phase=full
    if [[ $phase == full ]]; then
        BOARD_PHASE=full
        enter_katapult "$(main_label)" "$MAIN" "$fam" "$kcfg" guide \
            "поставьте джампер BOOT0 и нажмите RESET (после прошивки katapult джампер нужно будет снять)" \
            "Снимите джампер BOOT0 с $(main_label) и ДВАЖДЫ быстро нажмите RESET (одиночный RESET после прошивки по DFU может не запустить katapult)." \
            || return 1
        BOARD_DEV=$NEW_KATAPULT_DEV
    fi
    BOARD_PHASE=klipper
    flash_klipper_via_katapult "$(main_label)" "$BOARD_DEV" "$fcfg" "$MAIN" "$bridge" || return 1
    if [[ $MODE == usb ]]; then RES_MAIN_SERIAL=$FLASHED_SERIAL; fi
}

stage_flash_main() {
    step "$(main_label)"
    main_try_skip && return 0
    local m_dfu="katapult и Klipper сразу по DFU (рекомендуется)" m_kat="katapult по DFU, затем Klipper через katapult" way
    case $OPT_MAIN_FLASH in
        dfu) way=$m_dfu ;;
        katapult) way=$m_kat ;;
        *) way=$(ask_choice "Как прошить $(main_label)?" "$m_dfu" "$m_dfu" "$m_kat") ;;
    esac
    cat <<EOF
Подключите $(main_label) USB-кабелем к хосту (питание 24 В не нужно, достаточно USB).
Режим DFU: установите джампер на BOOT0, нажмите RESET (кнопка на плате).
Другие платы в режиме DFU быть не должны.
EOF
    if [[ $way == "$m_dfu" ]]; then
        BOARD_START_PHASE=dfuall
        info "Способ: katapult и Klipper за один сеанс DFU."
    else
        info "Способ: katapult по DFU, затем Klipper через katapult. Если katapult уже на плате (прошлая попытка), на запросе DFU ответьте s."
    fi
    flash_board "$(main_label)" try_main || true
}

stage_flash() {
    [[ -f $DEVICES_FILE ]] && PREV_DEVICES=$(cat "$DEVICES_FILE")
    if [[ $DRY_RUN -eq 0 ]]; then
        step "Остановка Klipper на время прошивки"
        local u; u=$(klipper_units)
        if [[ -n $u ]]; then services stop; KLIPPER_STOPPED=1; fi
    fi
    stage_flash_alps
    stage_flash_heads_katapult
    stage_flash_main
    stage_flash_heads_klipper
    step "Карта устройств ($DEVICES_FILE)"
    save_devices
    [[ ${#FLASH_FAILED[@]} -gt 0 ]] && FINISH_RC=1
    return 0
}

# devices.tsv: ключ(serial|uuid) -> конфиг сборки и роль (его читает update_klipper_mcu.sh / кнопка).
# quiet - промежуточное сохранение после каждой платы: к известным платам добавляются строки прошлого запуска.
save_devices() { # [quiet]
    local quiet=${1:-} lines="" i k keys=" "
    add_dev() { [[ -n $1 ]] || return 0; lines+="$1"$'\t'"$2"$'\t'"$3"$'\n'; keys+="$1 "; }
    if [[ $MODE == bridge ]]; then
        add_dev "$RES_BRIDGE_UUID" "${MAIN}-canbridge.config" bridge
        for i in 0 1; do add_dev "${RES_HEAD_UUID[$i]}" "$(head_cfg_name)" can; done
    else
        add_dev "$RES_MAIN_SERIAL" "${MAIN}.config" usb
    fi
    for ((i = 0; i < ALPS_COUNT; i++)); do add_dev "${RES_ALPS_SERIAL[$i]}" stm32f072xb.config usb; done
    if [[ $quiet == quiet && -n $PREV_DEVICES ]]; then
        local cfg role
        while IFS=$'\t' read -r k cfg role; do
            [[ -n $k && $keys != *" $k "* ]] && lines+="$k"$'\t'"$cfg"$'\t'"$role"$'\n'
        done <<<"$PREV_DEVICES"
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        [[ $quiet == quiet ]] || { info "[dry-run] записал бы:"; printf '%s' "$lines"; }
        return 0
    fi
    printf '%s' "$lines" >"$DEVICES_FILE"
    [[ $quiet == quiet ]] || cat "$DEVICES_FILE"
}

# ---------------------------------------------------------------- этап 7: запуск, кнопка, итоги

# Ждёт Moonraker (после запуска служб он отвечает не сразу)
wait_moonraker() {
    local i
    for ((i = 0; i < 60; i++)); do
        if mr_get /server/info >/dev/null 2>&1; then MOONRAKER_OK=1; return 0; fi
        sleep 1
    done
    MOONRAKER_OK=0
    return 1
}

FINISH_RC=0

stage_start_klipper() {
    step "Запуск Klipper"
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] systemctl start klipper; проверка ready и версий MCU"; return 0; fi
    if [[ $KLIPPER_STOPPED -eq 1 ]]; then services start; KLIPPER_STOPPED=0; else sctl restart klipper || true; fi
    if ! wait_moonraker; then warn "Moonraker не отвечает: systemctl status moonraker"; FINISH_RC=1; return 0; fi
    wait_for_klipper || FINISH_RC=1
    verify_versions || FINISH_RC=1
}

stage_button() {
    step "Кнопка обновления в Fluidd"
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] $INSTALL_DIR/install_fluidd_button.sh -y"; return 0; fi
    "$INSTALL_DIR/install_fluidd_button.sh" -y \
        || { warn "кнопку установить не удалось; позже: $INSTALL_DIR/install_fluidd_button.sh"; FINISH_RC=1; }
}

print_summary() {
    cat <<EOF

Что осталось сделать вручную:
  1. $([[ $GEN_USED -eq 1 ]] && echo "Вписать пины в сгенерированный $EL_NAME (поиск: ЗАПОЛНИТЕ), сверить блоки с пометкой СВЕРЬТЕ, проверить параметры моторов и драйверов, затем перезапустить Klipper." || echo "Адаптировать electronics_*.cfg под вашу электронику (драйверы, термисторы, пины) и проверить printer.cfg: все параметры описаны комментариями.")
  2. Проверить термисторы голов: возьмите термистор пальцами, температура должна расти у нужной головы (иначе поменяйте ${HEAD_MCU[0]} и ${HEAD_MCU[1]} местами).
  3. ALPS: добавьте [static_pwm_clock]/[load_cell_probe] (см. документацию ALPS) и выполните LOAD_CELL_CALIBRATE.
  4. Fluidd: ⏻ (вверху справа) -> mcu-update -> Start обновляет Klipper и прошивки всех MCU.
  5. Конфиг можно перенастроить отдельно, без переустановки (драйверы, другая проводка, модули вроде chamber_heater.cfg): $INSTALL_DIR/configure_vostok.sh
  6. Если у вашей платы другой кварц или смещение загрузчика, настройте configs/*.config через make menuconfig KCONFIG_CONFIG=...
EOF
    if [[ ${#FLASH_FAILED[@]} -gt 0 ]]; then
        warn "Не прошиты платы:"
        printf '  - %s\n' "${FLASH_FAILED[@]}" >&2
        info "В printer.cfg у них стоит $TODO_MARK вместо serial/canbus_uuid. Чтобы повторить, запустите установку снова:"
        info "  уже прошитые платы установщик предложит пропустить (или укажите --skip-board alps|main|heads)."
    fi
    if [[ ${#FLASH_SKIPPED[@]} -gt 0 ]]; then
        info "Пропущено как уже прошитое:"
        printf '  - %s\n' "${FLASH_SKIPPED[@]}"
    fi
    if [[ $FINISH_RC -eq 0 ]]; then ok "установка завершена"; else warn "установка завершена с замечаниями (лог: $LOG_FILE)"; fi
}

# ---------------------------------------------------------------- main

install_main() {
    parse_args "${INSTALL_ARGS[@]}"
    log_to_file "=== install_vostok.sh $VOSTOK_INSTALLER_VERSION: ${INSTALL_ARGS[*]:-} ==="
    stage_preflight
    start_sudo

    local need_flash=1; [[ $SKIP_FLASH -eq 1 ]] && need_flash=0
    if [[ $SKIP_SOFTWARE -eq 0 && $ONLY_DETECT -eq 0 ]]; then
        stage_packages
        stage_software
        check_tools "$need_flash" 1
    else
        check_tools "$need_flash" 0
    fi

    detect_hardware
    print_plan
    [[ $SKIP_FLASH -eq 0 ]] && check_hw_requirements
    [[ $ONLY_DETECT -eq 1 ]] && exit 0
    if [[ $DRY_RUN -eq 0 ]]; then
        ask_yn "Продолжить с этим планом?" y || { info "отменено"; exit 0; }
    fi

    if [[ $SKIP_FLASH -eq 0 ]]; then
        stage_can
        stage_flash
        [[ $SKIP_CONFIG -eq 0 ]] && stage_config
    else
        info "Прошивка пропущена (--skip-flash): serial/UUID для printer.cfg неизвестны, впишите [mcu ...] вручную"
    fi
    stage_start_klipper
    [[ $SKIP_BUTTON -eq 0 ]] && stage_button
    print_summary
    exit $FINISH_RC
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    install_main
fi
