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
#      (существующий printer.cfg не трогает, только печатает блок [mcu ...]);
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
OPT_CONFIG_SOURCE="" # standard|user
DRY_RUN=0
ONLY_DETECT=0
SKIP_SOFTWARE=0
SKIP_FLASH=0
SKIP_CONFIG=0
SKIP_BUTTON=0
DO_UPGRADE=0

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

usage() {
    cat <<'EOF'
Использование: install_vostok.sh [опции]

  --main h723|f446      главная плата: Octopus Pro H723 или Octopus Pro F446 (иначе определит/спросит)
  --heads none|v1.3|v2|ebb42  платы голов по CAN: нет, Fysetc H36 v1.3/v2, BTT EBB42 (иначе спросит);
                        с платами голов Octopus прошивается мостом USB-CAN. --h36 - то же, прежнее имя
  --alps 0|1|2          сколько датчиков ALPS подключено по USB (иначе определит/спросит)
  --electronics ФАЙЛ    имя electronics_*.cfg из vostok_configuration (иначе предложит по железу)
  --config-source standard|user  откуда брать конфиг: корень main или user_configs (иначе спросит)
  --only-detect         только определить подключённые MCU и показать план, ничего не менять
  --dry-run             показать все шаги и команды, ничего не менять
  --skip-software       не ставить пакеты/KIAUH/Klipper/Moonraker/Fluidd (уже стоят)
  --skip-flash          не прошивать MCU
  --skip-config         не трогать конфиг принтера
  --skip-button         не ставить кнопку обновления в Fluidd
  --upgrade             выполнить apt upgrade перед установкой
  -y, --yes             не задавать вопросов, где есть ответ по умолчанию (шаги с железом всё равно ждут Enter)
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
            --alps) [[ $# -ge 2 ]] || die "--alps требует аргумент"; OPT_ALPS=$2; shift ;;
            --electronics) [[ $# -ge 2 ]] || die "--electronics требует аргумент"; OPT_ELECTRONICS=$2; shift ;;
            --only-detect) ONLY_DETECT=1 ;;
            --dry-run) DRY_RUN=1 ;;
            --skip-software) SKIP_SOFTWARE=1 ;;
            --skip-flash) SKIP_FLASH=1 ;;
            --skip-config) SKIP_CONFIG=1 ;;
            --skip-button) SKIP_BUTTON=1 ;;
            --upgrade) DO_UPGRADE=1 ;;
            -y|--yes) ASSUME_YES=1 ;;
            -h|--help) usage; exit 0 ;;
            *) usage >&2; die "неизвестная опция: $1" ;;
        esac
        shift
    done
    case $OPT_MAIN in ""|h723|f446) ;; *) die "--main: h723 или f446" ;; esac
    case $OPT_HEADS in ""|none|v1.3|v2|ebb42) ;; *) die "--heads: none, v1.3, v2 или ebb42" ;; esac
    case $OPT_CONFIG_SOURCE in ""|standard|user) ;; *) die "--config-source: standard или user" ;; esac
    case $OPT_ALPS in ""|0|1|2) ;; *) die "--alps: 0, 1 или 2" ;; esac
}

# ------------------------------------------------------------------ интерактив

need_tty() { [[ -r /dev/tty ]] || die "нужен терминал: установка просит переключать платы и нажимать Enter"; }

# ask_yn "вопрос" y|n : код 0 = да. С -y возвращает значение по умолчанию.
ask_yn() {
    local def=${2:-n} ans hint="[y/N]"
    [[ $def == y ]] && hint="[Y/n]"
    if [[ $ASSUME_YES -eq 1 ]]; then [[ $def == y ]]; return; fi
    need_tty
    read -r -p "$1 $hint " ans </dev/tty
    [[ -z $ans ]] && ans=$def
    [[ $ans == [yYдД]* ]]
}

# ask_choice "вопрос" по_умолчанию вариант...: печатает выбранный вариант в ответ
ask_choice() {
    local q=$1 def=$2; shift 2
    local opts=("$@") i ans
    if [[ $ASSUME_YES -eq 1 ]]; then printf '%s' "$def"; return; fi
    need_tty
    {
        printf '%s\n' "$q"
        for i in "${!opts[@]}"; do printf '  %d) %s\n' "$((i + 1))" "${opts[$i]}"; done
    } >&2
    while true; do
        read -r -p "Номер [по умолчанию: $def]: " ans </dev/tty
        [[ -z $ans ]] && { printf '%s' "$def"; return; }
        if [[ $ans =~ ^[0-9]+$ ]] && (( ans >= 1 && ans <= ${#opts[@]} )); then
            printf '%s' "${opts[$((ans - 1))]}"; return
        fi
        echo "Введите число от 1 до ${#opts[@]}" >&2
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
        if { : </dev/tty; } 2>/dev/null; then env_item ok "терминал для диалога"; else env_item bad "нет терминала: шаги с железом требуют ответов в диалоге (запустите в ssh/терминале или используйте --skip-flash)"; fi
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

# ---------------------------------------------------------------- этап 3: обнаружение

byid_find() { # шаблон: список путей по возрастанию
    local f
    for f in /dev/serial/by-id/$1; do [[ -e $f ]] && printf '%s\n' "$f"; done
    return 0
}

dfu_count() { lsusb -d 0483:df11 2>/dev/null | wc -l; }

# Семейство чипа в DFU по адресу Option Bytes: f0|f4|h7|g|unknown
dfu_family() {
    local out
    out=$(sudo -n dfu-util -l 2>/dev/null || dfu-util -l 2>/dev/null || true)
    shopt -s nocasematch
    if   [[ $out == *0x1FFFF800* ]]; then echo f0
    elif [[ $out == *0x1FFFC000* ]]; then echo f4
    elif [[ $out == *0x5200* ]];     then echo h7
    elif [[ $out == *0x1FFF7800* ]]; then echo g
    else echo unknown; fi
    shopt -u nocasematch
}

family_name() {
    case $1 in
        f0) echo "STM32F0 (ALPS)" ;; f4) echo "STM32F4 (Octopus Pro F446)" ;;
        h7) echo "STM32H7 (Octopus Pro H723)" ;; g) echo "STM32G0/G4 (Fysetc H36 / BTT EBB42)" ;; *) echo "не определён" ;;
    esac
}

show_usb_state() {
    local f n
    info "Устройства в /dev/serial/by-id:"
    n=0
    for f in /dev/serial/by-id/*; do
        [[ -e $f ]] || continue
        info "  $(basename "$f")"; n=$((n + 1))
    done
    [[ $n -eq 0 ]] && info "  (пусто)"
    info "Устройств в режиме DFU (0483:df11): $(dfu_count)"
    if lsusb -d 1d50:606f >/dev/null 2>&1; then
        info "Найден мост USB-CAN Klipper (1d50:606f); интерфейс $CAN_IFACE: $(ip -br link show "$CAN_IFACE" 2>/dev/null | awk '{print $2}' || true)"
    fi
}

detect_hardware() {
    step "Определение подключённых MCU"
    show_usb_state

    # Главная плата
    local guess="" alps_guess heads_guess ans
    if   [[ -n $(byid_find 'usb-*stm32h723xx_*') ]]; then guess=h723
    elif [[ -n $(byid_find 'usb-*stm32f446xx_*') ]]; then guess=f446
    elif [[ $(dfu_count) -eq 1 ]]; then
        case $(dfu_family) in h7) guess=h723 ;; f4) guess=f446 ;; esac
    fi
    local main_ans=$OPT_MAIN
    if [[ -z $main_ans ]]; then
        if [[ $ONLY_DETECT -eq 1 && -n $guess ]]; then
            main_ans=$guess
        else
            ans=$(ask_choice "Главная плата:" "${guess:-h723}" "h723" "f446")
            main_ans=$ans
        fi
    fi
    # Подписи вариантов
    [[ -n $main_ans ]] || { warn "главная плата не определена, принимаю h723 (укажите --main f446, если у вас F446)"; main_ans=h723; }
    case $main_ans in f446) MAIN=stm32f446xx ;; *) MAIN=stm32h723xx ;; esac

    # Платы голов
    heads_guess=none
    if lsusb -d 1d50:606f >/dev/null 2>&1 || ip link show "$CAN_IFACE" >/dev/null 2>&1; then heads_guess=v2; fi
    HEADS=$OPT_HEADS
    if [[ -z $HEADS ]]; then
        if [[ $ONLY_DETECT -eq 1 ]]; then
            HEADS=$heads_guess
        else
            local def_lbl="нет"
            [[ $heads_guess != none ]] && def_lbl="Fysetc H36 v2"
            ans=$(ask_choice "Платы голов по CAN (при их наличии Octopus станет мостом USB-CAN):" "$def_lbl" \
                "нет" "Fysetc H36 v1.3" "Fysetc H36 v2" "BTT EBB42")
            case $ans in
                "Fysetc H36 v1.3") HEADS=v1.3 ;; "Fysetc H36 v2") HEADS=v2 ;; "BTT EBB42") HEADS=ebb42 ;; *) HEADS=none ;;
            esac
        fi
    fi
    set_head_names

    # ALPS
    alps_guess=$(byid_find 'usb-*stm32f072xb_*' | wc -l)
    [[ $alps_guess -gt 2 ]] && alps_guess=2
    if [[ -n $OPT_ALPS ]]; then
        ALPS_COUNT=$OPT_ALPS
    elif [[ $ONLY_DETECT -eq 1 ]]; then
        ALPS_COUNT=$alps_guess
    else
        ALPS_COUNT=$(ask_choice "Сколько датчиков ALPS подключено по USB (0 - нет)?" "$alps_guess" 0 1 2)
    fi

    if [[ $HEADS == none ]]; then MODE=usb; else MODE=bridge; fi
    print_plan
}

main_label() { [[ $MAIN == stm32h723xx ]] && echo "Octopus Pro v1.1 H723" || echo "Octopus Pro F446"; }
alps_side() { [[ $1 -eq 0 ]] && echo "левый (T0)" || echo "правый (T1)"; }
HEAD_MCU=(T0CB T1CB)   # имена секций [mcu ...] плат голов (уточняются по electronics-файлу)
set_head_names() { if [[ $HEADS == ebb42 ]]; then HEAD_MCU=(T0_EBB T1_EBB); else HEAD_MCU=(T0CB T1CB); fi; }
head_side() { [[ $1 -eq 0 ]] && echo "левая (${HEAD_MCU[0]})" || echo "правая (${HEAD_MCU[1]})"; }
head_label() {
    case $HEADS in
        v1.3) echo "Fysetc H36 v1.3" ;; v2) echo "Fysetc H36 v2" ;; ebb42) echo "BTT EBB42" ;; *) echo "платы голов" ;;
    esac
}
head_chip() { [[ $HEADS == v2 ]] && echo stm32g431xx || echo stm32g0b1xx; }
head_cfg_name() { # имя файла конфига сборки (общее для Klipper и katapult)
    case $HEADS in v1.3) echo stm32g0b1xx-can.config ;; v2) echo stm32g431xx-can.config ;; ebb42) echo stm32g0b1xx-ebb42-can.config ;; esac
}
head_dfu_hint() {
    if [[ $HEADS == ebb42 ]]; then echo "зажмите BOOT, нажмите RESET, отпустите BOOT (на старых ревизиях - перемычка BOOT0 + RESET)"
    else echo "зажмите BOOT0, нажмите RST, отпустите BOOT0"; fi
}

klipper_cfg_for_main() {
    if [[ $MODE == bridge ]]; then echo "$CONFIGS_DIR/${MAIN}-canbridge.config"; else echo "$CONFIGS_DIR/${MAIN}.config"; fi
}
katapult_cfg_for_main() { echo "$KATAPULT_CONFIGS/${MAIN}.config"; }

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
    info "  $n. $(main_label): katapult через DFU (джампер BOOT0), затем Klipper ($([[ $MODE == bridge ]] && echo 'USB-CAN мост' || echo USB))"; n=$((n + 1))
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

# Прошивка katapult по DFU. Режим make - как у пользователя для ALPS (make flash katapult),
# режим guide - команда из гайда (mass-erase, запасной вариант без него).
dfu_flash_katapult() { # режим(make|guide) конфиг
    local mode=$1 cfg=$2 key work
    build_katapult "$cfg"
    [[ $DRY_RUN -eq 1 ]] && { info "[dry-run] dfu-util -> $KATAPULT_BIN"; return 0; }
    if [[ $mode == make ]]; then
        key=$(basename "$cfg" .config); work=$BUILD_DIR/katapult-$key
        # make flash из katapult (sudo dfu-util -R -a 0 -s 0x08000000:leave), ошибку get_status в конце игнорируем
        make -C "$KATAPULT_DIR" "KCONFIG_CONFIG=$work/.config" "OUT=$work/out/" flash FLASH_DEVICE=0483:df11 \
            || warn "make flash вернул ошибку (get_status после 100% - нормально); проверяю результат"
    else
        sudo dfu-util -R -a 0 -s 0x08000000:mass-erase:force:leave -D "$KATAPULT_BIN" -d 0483:df11 \
            || { warn "с mass-erase не вышло, пробую без него (как рекомендует гайд)";
                 sudo dfu-util -R -a 0 -s 0x08000000:leave -D "$KATAPULT_BIN" -d 0483:df11 \
                    || warn "dfu-util вернул ошибку (get_status после 100% - нормально); проверяю результат"; }
    fi
}

# Ждёт появления нового usb-katapult_<чип>_* (которого не было в списке «до»): результат в NEW_KATAPULT_DEV
NEW_KATAPULT_DEV=""
wait_new_katapult() { # чип секунд файл_со_списком_до
    local chip=$1 secs=$2 before=$3 i f
    NEW_KATAPULT_DEV=""
    for ((i = 0; i < secs * 2; i++)); do
        for f in /dev/serial/by-id/usb-katapult_"${chip}"_*; do
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

# Получить плату в режиме katapult: через DFU (прошивка katapult) или двойным RESET, если katapult/Klipper уже есть.
# Результат в NEW_KATAPULT_DEV.
enter_katapult() { # подпись чип семейство katapult_cfg режим(make|guide) подсказка_по_DFU
    local label=$1 chip=$2 fam=$3 kcfg=$4 mode=$5 hint=$6 before ans
    before=$(mktemp); snapshot_katapult "$before"
    while true; do
        pause_hw "$label: $hint" 1
        ans=$(cat "$TMP_ANS" 2>/dev/null || true)
        if [[ $DRY_RUN -eq 1 ]]; then dfu_flash_katapult "$mode" "$kcfg"; NEW_KATAPULT_DEV=/dev/serial/by-id/usb-katapult_${chip}_DRYRUN-if00; rm -f "$before"; return 0; fi
        if [[ $ans == [sSыЫ]* ]]; then
            info "Пропускаю DFU: дважды быстро нажмите RESET на $label, чтобы войти в katapult."
            if wait_new_katapult "$chip" 25 "$before"; then break; fi
            warn "usb-katapult_${chip}_* не появился. Двойной RESET нужно нажимать быстро (светодиод katapult мигает медленно)."
            ask_yn "Повторить?" y || { rm -f "$before"; die "не удалось войти в katapult: $label"; }
            continue
        fi
        if ! wait_dfu "$fam" "$label"; then rm -f "$before"; die "прошивка $label прервана"; fi
        dfu_flash_katapult "$mode" "$kcfg"
        if wait_new_katapult "$chip" 20 "$before"; then break; fi
        warn "после прошивки katapult не появился usb-katapult_${chip}_*."
        warn "Если появился usb-Klipper_*, дважды быстро нажмите RESET; если ничего нет - прошейте katapult заново."
        if wait_new_katapult "$chip" 15 "$before"; then break; fi
        ask_yn "Повторить прошивку katapult для $label?" y || { rm -f "$before"; die "katapult не запустился: $label"; }
    done
    rm -f "$before"
    ok "$label в режиме katapult: $(basename "$NEW_KATAPULT_DEV")"
}

# Klipper на плату в katapult по USB. Для обычной платы ждёт usb-Klipper_*, для моста - появления gs_usb и can0.
# Серийный номер результата в FLASHED_SERIAL.
FLASHED_SERIAL=""
flash_klipper_via_katapult() { # подпись katapult_dev klipper_cfg чип bridge(0|1)
    local label=$1 dev=$2 cfg=$3 chip=$4 bridge=$5 serial bin
    serial=$(sed -n 's/^usb-katapult_.*_\([^_]*\)-if[0-9]*$/\1/p' <<<"$(basename "$dev")")
    step "Klipper -> $label"
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] сборка $(basename "$cfg"), flashtool.py -d $dev -f <bin>"; FLASHED_SERIAL=DRYRUN; return 0; fi
    build_firmware "$cfg" "$chip"
    bin=${BUILT_BIN[$cfg]}
    if ! python3 "$KATAPULT_DIR/scripts/flashtool.py" -d "$dev" -f "$bin"; then
        cat >&2 <<EOF

Прошивка Klipper на $label не удалась. katapult остаётся в плате.
  - ls /dev/serial/by-id/ (должен быть usb-katapult_*), при необходимости дважды нажмите RESET;
  - повтор: python3 $KATAPULT_DIR/scripts/flashtool.py -d $dev -f $bin
EOF
        die "прошивка Klipper на $label не удалась"
    fi
    FLASHED_SERIAL=$serial
    if [[ $bridge -eq 1 ]]; then
        bring_up_can || die "после прошивки моста не появился рабочий интерфейс $CAN_IFACE (lsusb: Geschwister Schneider / 1d50:606f; ip link show $CAN_IFACE)"
        ok "$label: мост USB-CAN работает, $CAN_IFACE поднят"
    else
        wait_for_device "/dev/serial/by-id/usb-Klipper_${chip}_${serial}-if00" 20 \
            || die "после прошивки $label не появился usb-Klipper_${chip}_${serial}-if00; проверьте ls /dev/serial/by-id/"
        state_set "$serial" "$(host_version)"
        ok "$label прошит (serial $serial)"
    fi
}

stage_flash_alps() {
    local i fcfg=$CONFIGS_DIR/stm32f072xb.config
    for ((i = 0; i < ALPS_COUNT; i++)); do
        step "ALPS $(alps_side $i)"
        cat <<EOF
Датчик ALPS подключите USB-кабелем к хосту (другие ALPS можно не отключать).
Режим DFU: зажмите BOOT, нажмите и отпустите RESET, отпустите BOOT.
EOF
        enter_katapult "ALPS $(alps_side $i)" stm32f072xb f0 "$KATAPULT_CONFIGS/stm32f072xb.config" make \
            "переведите этот ALPS в режим DFU (BOOT + RESET, затем отпустить BOOT)"
        flash_klipper_via_katapult "ALPS $(alps_side $i)" "$NEW_KATAPULT_DEV" "$fcfg" stm32f072xb 0
        RES_ALPS_SERIAL[$i]=$FLASHED_SERIAL
    done
}

stage_flash_heads_katapult() {
    [[ $HEADS == none ]] && return 0
    local i kcfg
    kcfg=$KATAPULT_CONFIGS/$(head_cfg_name)
    for ((i = 0; i < 2; i++)); do
        step "$(head_label): katapult, плата $(head_side $i)"
        cat <<EOF
Эти шаги выполняются по одной плате:
  - подключите к хосту USB-кабелем ТОЛЬКО $(head_label) $(head_side $i) (другую плату головы от USB отключите);
  - режим DFU: $(head_dfu_hint).
katapult на этих платах работает только по CAN, поэтому после прошивки отключите USB.
EOF
        pause_hw "$(head_label) $(head_side $i): подключите USB, переведите в DFU и нажмите Enter. DFU: $(head_dfu_hint)." 1
        if [[ $(cat "$TMP_ANS" 2>/dev/null || true) == [sSыЫ]* && $DRY_RUN -eq 0 ]]; then
            info "DFU для этой платы головы пропущен (katapult уже на плате)"
            continue
        fi
        if [[ $DRY_RUN -eq 1 ]]; then dfu_flash_katapult guide "$kcfg"; continue; fi
        wait_dfu g "$(head_label) $(head_side $i)" || die "прошивка платы головы прервана"
        dfu_flash_katapult guide "$kcfg"
        pause_hw "Отключите USB от $(head_label) $(head_side $i). Дальше она будет подключена только по CAN."
        ok "katapult записан на $(head_label) $(head_side $i)"
    done
}

stage_flash_main() {
    step "$(main_label)"
    local hint kcfg fcfg bridge=0
    kcfg=$(katapult_cfg_for_main); fcfg=$(klipper_cfg_for_main)
    [[ $MODE == bridge ]] && bridge=1
    cat <<EOF
Подключите $(main_label) USB-кабелем к хосту (питание 24 В не нужно, достаточно USB).
Режим DFU: установите джампер на BOOT0, нажмите RESET (кнопка на плате).
Другие платы в режиме DFU быть не должны.
EOF
    hint="поставьте джампер BOOT0, нажмите RESET и нажмите Enter (после прошивки katapult джампер нужно будет снять)"
    local before; before=$(mktemp); snapshot_katapult "$before"
    pause_hw "$(main_label): $hint"
    local ans; ans=$(cat "$TMP_ANS" 2>/dev/null || true)
    if [[ $DRY_RUN -eq 1 ]]; then
        dfu_flash_katapult guide "$kcfg"; NEW_KATAPULT_DEV=/dev/serial/by-id/usb-katapult_${MAIN}_DRYRUN-if00
    elif [[ $ans == [sSыЫ]* ]]; then
        info "Пропускаю DFU: дважды быстро нажмите RESET на $(main_label)."
        wait_new_katapult "$MAIN" 25 "$before" || die "usb-katapult_${MAIN}_* не появился после двойного RESET"
    else
        local fam=h7; [[ $MAIN == stm32f446xx ]] && fam=f4
        wait_dfu "$fam" "$(main_label)" || die "прошивка $(main_label) прервана"
        dfu_flash_katapult guide "$kcfg"
        pause_hw "Снимите джампер BOOT0 с $(main_label) и нажмите RESET."
        if ! wait_new_katapult "$MAIN" 20 "$before"; then
            warn "usb-katapult_${MAIN}_* не появился. Если вместо него usb-Klipper_* - дважды быстро нажмите RESET."
            wait_new_katapult "$MAIN" 20 "$before" || die "katapult на $(main_label) не запустился (ls /dev/serial/by-id/); прошейте его заново"
        fi
    fi
    rm -f "$before"
    ok "$(main_label) в режиме katapult: $(basename "$NEW_KATAPULT_DEV")"
    flash_klipper_via_katapult "$(main_label)" "$NEW_KATAPULT_DEV" "$fcfg" "$MAIN" "$bridge"
    if [[ $MODE == usb ]]; then RES_MAIN_SERIAL=$FLASHED_SERIAL; fi
}

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

stage_flash_heads_klipper() {
    [[ $HEADS == none ]] && return 0
    local i fcfg chip uuids n
    chip=$(head_chip)
    fcfg=$CONFIGS_DIR/$(head_cfg_name)
    step "UUID моста ($(main_label))"
    info "Для этого этапа подайте питание 24 В на Octopus и платы голов и подключите CAN-кабели по схеме из гайда."
    if [[ $DRY_RUN -eq 1 ]]; then
        info "[dry-run] canbus_query.py $CAN_IFACE -> UUID Octopus"
        RES_BRIDGE_UUID=000000000000
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
            die "не удалось определить UUID Octopus"
        fi
        RES_BRIDGE_UUID=$uuids
        ok "UUID Octopus (мост): $RES_BRIDGE_UUID"
    fi

    for ((i = 0; i < 2; i++)); do
        step "$(head_label) $(head_side $i): Klipper по CAN"
        local uuid="" bin
        if [[ $DRY_RUN -eq 1 ]]; then
            info "[dry-run] flashtool.py -i $CAN_IFACE -q -> UUID, затем -u UUID -f klipper.bin"
            RES_HEAD_UUID[$i]=00000000000$i
            continue
        fi
        pause_hw "Подключите CAN-кабелем ТОЛЬКО $(head_label) $(head_side $i) (вторую плату головы отключите) вместе с питанием платы и нажмите Enter."
        uuids=$(can_uuids Katapult)
        n=$(grep -c . <<<"$uuids" || true)
        if [[ $n -eq 0 ]]; then
            warn "плата katapult по CAN не найдена. Проверьте CAN_H/CAN_L, терминаторы 120 Ом (около 60 Ом на шине), питание плат голов."
            warn "Если на плате уже Klipper, дважды быстро нажмите RESET (красный светодиод мигает) - она станет Katapult."
            ask_yn "Проверить ещё раз?" y || die "$(head_label) $(head_side $i) не найдена"
            pause_hw "Нажмите Enter для повторного опроса шины."
            uuids=$(can_uuids Katapult); n=$(grep -c . <<<"$uuids" || true)
        fi
        [[ $n -eq 1 ]] || die "ожидалась одна плата в katapult на CAN, найдено: $n (оставьте подключённой только $(head_label) $(head_side $i))"
        uuid=$uuids
        build_firmware "$fcfg" "$chip"
        bin=${BUILT_BIN[$fcfg]}
        python3 "$KATAPULT_DIR/scripts/flashtool.py" -i "$CAN_IFACE" -u "$uuid" -f "$bin" \
            || die "прошивка $(head_label) $(head_side $i) ($uuid) не удалась: повтор python3 $KATAPULT_DIR/scripts/flashtool.py -i $CAN_IFACE -u $uuid -f $bin"
        sleep 2
        if can_uuids Klipper | grep -qix "$uuid"; then
            ok "$(head_label) $(head_side $i): $uuid, Application: Klipper"
        else
            warn "после прошивки $uuid не отвечает как Klipper (canbus_query.py $CAN_IFACE); продолжаю"
        fi
        state_set "$uuid" "$(host_version)"
        RES_HEAD_UUID[$i]=$uuid
    done
    if [[ $DRY_RUN -eq 0 ]]; then
        pause_hw "Подключите CAN-кабелем обе платы голов вместе и нажмите Enter для проверки шины."
        uuids=$(can_uuids Klipper); n=$(grep -c . <<<"$uuids" || true)
        info "На шине устройств с Klipper: $n (ожидается 3: Octopus и две платы голов)"
        check_can_health || true
    fi
}

stage_flash() {
    if [[ $DRY_RUN -eq 0 ]]; then
        step "Остановка Klipper на время прошивки"
        local u; u=$(klipper_units)
        if [[ -n $u ]]; then services stop; KLIPPER_STOPPED=1; fi
    fi
    stage_flash_alps
    stage_flash_heads_katapult
    stage_flash_main
    stage_flash_heads_klipper
    save_devices
}

# devices.tsv: ключ(serial|uuid) -> конфиг сборки и роль (его читает update_klipper_mcu.sh / кнопка)
save_devices() {
    step "Карта устройств ($DEVICES_FILE)"
    local lines="" i
    if [[ $MODE == bridge ]]; then
        lines+="${RES_BRIDGE_UUID}"$'\t'"${MAIN}-canbridge.config"$'\t'"bridge"$'\n'
        for i in 0 1; do lines+="${RES_HEAD_UUID[$i]}"$'\t'"$(head_cfg_name)"$'\t'"can"$'\n'; done
    else
        lines+="${RES_MAIN_SERIAL}"$'\t'"${MAIN}.config"$'\t'"usb"$'\n'
    fi
    for ((i = 0; i < ALPS_COUNT; i++)); do lines+="${RES_ALPS_SERIAL[$i]}"$'\t'"stm32f072xb.config"$'\t'"usb"$'\n'; done
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] записал бы:"; printf '%s' "$lines"; return; fi
    printf '%s' "$lines" >"$DEVICES_FILE"
    cat "$DEVICES_FILE"
}

# ---------------------------------------------------------------- этап 6: конфигурация

# Выбор electronics_*.cfg: сначала источник (корень main или user_configs), затем файл.
# Результат: EL_SRC (standard|user) и EL_NAME. Аргумент - корень распакованного архива.
EL_SRC=""; EL_NAME=""
SRC_LBL_STD="Стандартный (корень main)"
SRC_LBL_USR="Пользовательский (user_configs)"

el_matches() { # имя: подходит ли файл под выбранные главную плату и платы голов
    local f=$1 chip_pat head_pat=""
    [[ $MAIN == stm32h723xx ]] && chip_pat="_h723_" || chip_pat="_f446_"
    [[ $f == *$chip_pat* ]] || return 1
    case $HEADS in v1.3) head_pat="H36v1.3" ;; v2) head_pat="H36v2" ;; ebb42) head_pat="ebb42" ;; esac
    [[ -z $head_pat || $f == *$head_pat* ]]
}

pick_electronics() { # корень_архива
    local root=$1 f d std=() usr=() def_src="" def_file="" labels=() names=() ans k src_ans
    for f in "$root"/electronics_*.cfg; do [[ -f $f ]] && std+=("$(basename "$f")"); done
    for f in "$root"/user_configs/electronics_*.cfg; do [[ -f $f ]] && usr+=("$(basename "$f")"); done
    [[ ${#std[@]} -gt 0 || ${#usr[@]} -gt 0 ]] || die "в архиве нет electronics_*.cfg"

    # Явно заданный файл: ищем в обоих каталогах
    if [[ -n $OPT_ELECTRONICS ]]; then
        for f in "${std[@]}"; do [[ $f == "$OPT_ELECTRONICS" ]] && { EL_SRC=standard; EL_NAME=$f; return; }; done
        for f in "${usr[@]}"; do [[ $f == "$OPT_ELECTRONICS" ]] && { EL_SRC=user; EL_NAME=$f; return; }; done
        die "файл $OPT_ELECTRONICS не найден ни в корне main, ни в user_configs"
    fi

    # Источник
    def_src=user
    for f in "${std[@]}"; do el_matches "$f" && def_src=standard; done
    [[ ${#std[@]} -eq 0 ]] && def_src=user
    [[ ${#usr[@]} -eq 0 ]] && def_src=standard
    if [[ -n $OPT_CONFIG_SOURCE ]]; then
        EL_SRC=$OPT_CONFIG_SOURCE
    elif [[ ${#std[@]} -eq 0 ]]; then EL_SRC=user
    elif [[ ${#usr[@]} -eq 0 ]]; then EL_SRC=standard
    else
        info ""
        info "Конфиг электроники можно взять из репозитория vostok_configuration:"
        info "  - стандартный: корень main, поддерживается автором (${std[*]});"
        info "  - пользовательский: каталог user_configs, конфиги пользователей (${#usr[@]} шт.), могут не совпадать с документацией."
        src_ans=$(ask_choice "Откуда взять конфиг?" "$([[ $def_src == standard ]] && echo "$SRC_LBL_STD" || echo "$SRC_LBL_USR")" "$SRC_LBL_STD" "$SRC_LBL_USR")
        [[ $src_ans == "$SRC_LBL_USR" ]] && EL_SRC=user || EL_SRC=standard
    fi
    if [[ $EL_SRC == standard && ${#std[@]} -eq 0 ]]; then die "в корне main нет electronics_*.cfg; используйте --config-source user"; fi
    if [[ $EL_SRC == user && ${#usr[@]} -eq 0 ]]; then die "в user_configs нет electronics_*.cfg"; fi

    # Файл
    local list=()
    if [[ $EL_SRC == standard ]]; then list=("${std[@]}"); else
        list=("${usr[@]}")
        warn "user_configs: конфиги ведут пользователи. Перед использованием сверьте схему подключения в начале файла с вашей проводкой: неверная схема может вывести электронику из строя."
    fi
    for f in "${list[@]}"; do
        if el_matches "$f"; then labels+=("$f"); else labels+=("$f (другая плата)"); fi
        names+=("$f")
        [[ -z $def_file ]] && el_matches "$f" && def_file=${labels[-1]}
    done
    [[ -n $def_file ]] || def_file=${labels[0]}
    ans=$(ask_choice "Файл электроники (распиновка плат):" "$def_file" "${labels[@]}")
    for k in "${!labels[@]}"; do
        [[ ${labels[$k]} == "$ans" ]] && EL_NAME=${names[$k]}
    done
    [[ -n $EL_NAME ]] || die "файл электроники не выбран"
}

# Имена секций [mcu ...] плат голов берём из electronics-файла (он ссылается на них как T0CB:PA1, T0_EBB:PB3 ...)
sync_head_names() { # путь к electronics-файлу
    local file=$1 names n0 n1
    [[ $HEADS == none ]] && return 0
    names=$(grep -v '^[[:space:]]*#' "$file" | grep -oE '\bT[01][A-Za-z0-9_]+:' | tr -d ':' | sort -u || true)
    n0=$(grep -E '^T0' <<<"$names" | head -n 1 || true)
    n1=$(grep -E '^T1' <<<"$names" | head -n 1 || true)
    if [[ -n $n0 && -n $n1 && ( $n0 != "${HEAD_MCU[0]}" || $n1 != "${HEAD_MCU[1]}" ) ]]; then
        warn "в $(basename "$file") платы голов называются $n0 и $n1 (по умолчанию: ${HEAD_MCU[0]} и ${HEAD_MCU[1]}); использую имена из файла"
        HEAD_MCU=("$n0" "$n1")
    fi
}

mcu_blocks() {
    local i
    if [[ $MODE == bridge ]]; then
        printf '[mcu]\ncanbus_uuid: %s\n\n' "$RES_BRIDGE_UUID"
        printf '[mcu %s]\ncanbus_uuid: %s\n\n' "${HEAD_MCU[0]}" "${RES_HEAD_UUID[0]}"
        printf '[mcu %s]\ncanbus_uuid: %s\n\n' "${HEAD_MCU[1]}" "${RES_HEAD_UUID[1]}"
    else
        printf '[mcu]\nserial: /dev/serial/by-id/usb-Klipper_%s_%s-if00\n\n' "$MAIN" "$RES_MAIN_SERIAL"
    fi
    for ((i = 0; i < ALPS_COUNT; i++)); do
        printf '[mcu alps%s]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_%s-if00\n\n' "$([[ $i -eq 1 ]] && echo _t1)" "${RES_ALPS_SERIAL[$i]}"
    done
}

# Каталог с printer.cfg/printer_base.cfg/electronics_*.cfg: печатает путь или ничего (тогда нужно скачать)
local_cfg_root() {
    local root
    case $VOSTOK_CFG_LOCAL in
        0|no|off) return 0 ;;
        auto) root=$(dirname "$INSTALL_DIR") ;;
        *) root=$VOSTOK_CFG_LOCAL ;;
    esac
    [[ -f $root/printer.cfg && -f $root/printer_base.cfg ]] && printf '%s' "$root"
    return 0
}

stage_config() {
    step "Конфигурация принтера"
    local blocks local_root; blocks=$(mcu_blocks); local_root=$(local_cfg_root)
    if [[ -f $PRINTER_CFG_DIR/printer.cfg ]]; then
        warn "$PRINTER_CFG_DIR/printer.cfg уже существует, не трогаю"
        info "Впишите в него (замените секции [mcu ...]):"
        printf '\n%s\n' "$blocks"
        return 0
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        info "[dry-run] взял бы конфигурацию из ${local_root:-$VOSTOK_CFG_TARBALL}, скопировал printer.cfg, printer_base.cfg, chamber_heater.cfg, electronics_*.cfg, postprocessing/ в $PRINTER_CFG_DIR"
        printf '%s\n' "$blocks"
        return 0
    fi
    local tmp tarball el src_dir cfg_root
    tmp=$(mktemp -d)
    if [[ -n $local_root ]]; then
        cfg_root=$local_root
        info "Конфигурация берётся из локального клона: $cfg_root"
    else
        tarball=$tmp/vostok_configuration.tar.gz
        cfg_root=$tmp/src
        mkdir -p "$cfg_root"
        curl -fsSL -o "$tarball" "$VOSTOK_CFG_TARBALL" || die "не удалось скачать $VOSTOK_CFG_TARBALL"
        tar -xzf "$tarball" -C "$cfg_root" --strip-components=1 || die "не удалось распаковать конфигурацию"
        [[ -f $cfg_root/printer.cfg && -f $cfg_root/printer_base.cfg ]] || die "в архиве нет printer.cfg/printer_base.cfg"
    fi
    pick_electronics "$cfg_root"
    el=$EL_NAME
    if [[ $EL_SRC == user ]]; then src_dir=$cfg_root/user_configs; else src_dir=$cfg_root; fi
    sync_head_names "$src_dir/$el"
    blocks=$(mcu_blocks)
    mkdir -p "$PRINTER_CFG_DIR"
    cp "$cfg_root/printer_base.cfg" "$cfg_root/printer.cfg" "$PRINTER_CFG_DIR/"
    [[ -f $cfg_root/chamber_heater.cfg ]] && cp "$cfg_root/chamber_heater.cfg" "$PRINTER_CFG_DIR/"
    cp "$src_dir/$el" "$PRINTER_CFG_DIR/"
    [[ -d $cfg_root/postprocessing ]] && cp -r "$cfg_root/postprocessing" "$PRINTER_CFG_DIR/"
    printf '%s' "$blocks" >"$tmp/mcu_blocks.txt"
    python3 -I - "$PRINTER_CFG_DIR/printer.cfg" "$el" "$tmp/mcu_blocks.txt" <<'PYEND'
import sys, re
path, electronics, blocks_path = sys.argv[1:4]
text = open(path, encoding="utf-8").read().split("\n")
blocks = open(blocks_path, encoding="utf-8").read().rstrip("\n").split("\n")
out, i, inserted = [], 0, False
while i < len(text):
    line = text[i]
    if re.match(r"\s*\[mcu(\s+[^\]]+)?\]", line):
        # убрать секцию [mcu ...] целиком (до следующего заголовка), вставить свои блоки на место первой
        if not inserted:
            out.extend(blocks + [""])
            inserted = True
        i += 1
        while i < len(text) and not re.match(r"\s*\[", text[i]):
            i += 1
        continue
    if re.match(r"\s*\[include\s+electronics_.*\.cfg\]", line):
        tail = line.split("]", 1)[1]
        line = "[include %s]%s" % (electronics, tail)
    out.append(line)
    i += 1
if not inserted:
    out = blocks + [""] + out
open(path, "w", encoding="utf-8").write("\n".join(out))
PYEND
    rm -rf "$tmp"
    ok "конфигурация записана в $PRINTER_CFG_DIR (electronics: $el, источник: $([[ $EL_SRC == user ]] && echo user_configs || echo "корень main"))"
    if [[ $HEADS == none ]]; then
        warn "в $el могут быть включены платы голов по CAN. Без них адаптируйте этот файл под вашу проводку (гайд, раздел «Конфигурация», п. 3)"
    fi
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
  1. Адаптировать electronics_*.cfg под вашу электронику (драйверы, термисторы, пины) и проверить printer.cfg: все параметры описаны комментариями.
  2. Проверить термисторы голов: возьмите термистор пальцами, температура должна расти у нужной головы (иначе поменяйте ${HEAD_MCU[0]} и ${HEAD_MCU[1]} местами).
  3. ALPS: добавьте [static_pwm_clock]/[load_cell_probe] (см. документацию ALPS) и выполните LOAD_CELL_CALIBRATE.
  4. Fluidd: ⏻ (вверху справа) -> mcu-update -> Start обновляет Klipper и прошивки всех MCU.
  5. Если у вашей платы другой кварц или смещение загрузчика, настройте configs/*.config через make menuconfig KCONFIG_CONFIG=...
EOF
    if [[ $FINISH_RC -eq 0 ]]; then ok "установка завершена"; else warn "установка завершена с замечаниями (лог: $LOG_FILE)"; fi
}

# ---------------------------------------------------------------- main

install_main() {
    parse_args "${INSTALL_ARGS[@]}"
    log_to_file "=== install_vostok.sh: ${INSTALL_ARGS[*]:-} ==="
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
