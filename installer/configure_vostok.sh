#!/usr/bin/env bash
# Настройка конфига VOSTOK отдельно от установки: выбор или генерация electronics_*.cfg, драйверы моторов,
# недостающие секции [mcu ...] в printer.cfg и дополнительные модули (например, chamber_heater.cfg).
# Прошивку плат и установку софта не трогает. Запускать можно в любой момент после установки.
#
# Основа - ваш текущий конфиг: если в printer.cfg уже подключён electronics_*.cfg, пины и параметры
# моторов и драйверов берутся из него. Стоковый main берётся только при чистой установке.
# Прежние файлы перед заменой сохраняются как *.bak-<дата>.
#
# Подробности: README.md, ./configure_vostok.sh --help

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4) )); then
    echo "Нужен bash 4.4 или новее (сейчас $BASH_VERSION)" >&2
    exit 1
fi

CONFIGURE_ARGS=("$@")
set --   # source не должен видеть наши аргументы

INSTALL_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
PRINTER_DATA=${PRINTER_DATA:-$HOME/printer_data}
LOG_FILE=${LOG_FILE:-$PRINTER_DATA/logs/vostok_configure.log}
# shellcheck source=update_klipper_mcu.sh
source "$INSTALL_DIR/update_klipper_mcu.sh"
# shellcheck source=lib/vostok_config.sh
source "$INSTALL_DIR/lib/vostok_config.sh"

VOSTOK_CFG_TARBALL=${VOSTOK_CFG_TARBALL:-https://codeload.github.com/dmitry-sorkin/vostok_configuration/tar.gz/refs/heads/main}
VOSTOK_CFG_LOCAL=${VOSTOK_CFG_LOCAL:-auto}
PRINTER_CFG_DIR=$PRINTER_DATA/config
DEVICES_FILE=${DEVICES_FILE:-$INSTALL_DIR/devices.tsv}
HEAD_MCU=(T0CB T1CB)

usage() {
    cat <<'EOF'
Использование: configure_vostok.sh [опции]

Настройка конфига принтера без установки и прошивки.

  --main h723|f446      главная плата (иначе определит по printer.cfg/железу или спросит)
  --heads none|v1.3|v2|ebb42  платы голов по CAN (иначе определит по printer.cfg или спросит)
  --alps 0|1|2          число датчиков ALPS (иначе определит или спросит)
  --config-source standard|user|generate|skip  источник конфига электроники: корень main, user_configs,
                        сгенерировать свой (шаблон без плат и драйверов) или пропустить редактирование
                        (только дописать недостающие [mcu] в существующий printer.cfg); иначе спросит
  --electronics ФАЙЛ    имя electronics_*.cfg из vostok_configuration (для standard/user)
  --drivers СПЕК        драйверы для generate: all=2130|2208|2209|2240|5160|5160plus или список по моторам
                        x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209 (иначе спросит; с -y как в стоке)
  --reference ФАЙЛ|none эталон для пинов и параметров. По умолчанию ваш текущий electronics-файл
                        (активный include в printer.cfg), при чистой установке стоковый main (H723).
                        none - не использовать эталон
  --modules ИМЕНА       дополнительные модули без вопроса: chamber_heater, all или none (через запятую)
  --printer-data DIR    каталог printer_data (по умолчанию ~/printer_data)
  --dry-run             показать, что будет сделано, ничего не менять
  -y, --yes             не задавать вопросов, где есть ответ по умолчанию
  -V, --version         показать версию установщика
  -h, --help            эта справка

Переменные окружения: PRINTER_DATA, VOSTOK_CFG_LOCAL (0 - всегда скачивать конфигурацию, ПУТЬ - свой каталог).
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --main) [[ $# -ge 2 ]] || die "--main требует аргумент"; OPT_MAIN=$2; shift ;;
            --heads) [[ $# -ge 2 ]] || die "--heads требует аргумент"; OPT_HEADS=$2; shift ;;
            --alps) [[ $# -ge 2 ]] || die "--alps требует аргумент"; OPT_ALPS=$2; shift ;;
            --config-source) [[ $# -ge 2 ]] || die "--config-source требует аргумент"; OPT_CONFIG_SOURCE=$2; shift ;;
            --electronics) [[ $# -ge 2 ]] || die "--electronics требует аргумент"; OPT_ELECTRONICS=$2; shift ;;
            --drivers) [[ $# -ge 2 ]] || die "--drivers требует аргумент"; OPT_DRIVERS=$2; shift ;;
            --reference) [[ $# -ge 2 ]] || die "--reference требует аргумент"; OPT_REFERENCE=$2; shift ;;
            --modules) [[ $# -ge 2 ]] || die "--modules требует аргумент"; OPT_MODULES=$2; shift ;;
            --printer-data) [[ $# -ge 2 ]] || die "--printer-data требует аргумент"
                PRINTER_DATA=$2; PRINTER_CFG_DIR=$2/config; LOG_FILE=$2/logs/vostok_configure.log; shift ;;
            --dry-run) DRY_RUN=1 ;;
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
    case $OPT_ALPS in ""|0|1|2) ;; *) die "--alps: 0, 1 или 2" ;; esac
}

# Подсказки по железу из существующего printer.cfg: заполняет OPT_MAIN/OPT_HEADS/OPT_ALPS, только если они не заданы
guess_from_printer_cfg() {
    local cfg=$PRINTER_CFG_DIR/printer.cfg list inc
    [[ $(cfg_state "$cfg") == vostok ]] || return 0   # пустой или чужой printer.cfg (например, пример KIAUH) не источник подсказок
    list=$(python3 -I "$INSTALL_DIR/tools/mcu_merge.py" "$cfg" --list 2>/dev/null || true)
    inc=$(sed -n 's/^[[:space:]]*\[include[[:space:]]\+\(electronics_[^]]*\.cfg\)\].*/\1/p' "$cfg" | head -n 1)
    if [[ -z $OPT_MAIN ]]; then
        if grep -q 'stm32h723xx' <<<"$list$inc" || grep -q '_h723_' <<<"$inc"; then OPT_MAIN=h723
        elif grep -q 'stm32f446xx' <<<"$list" || grep -q '_f446_' <<<"$inc"; then OPT_MAIN=f446; fi
    fi
    if [[ -z $OPT_HEADS ]]; then
        if grep -q '^mcu T0_EBB' <<<"$list"; then OPT_HEADS=ebb42
        elif grep -q '^mcu T0CB' <<<"$list"; then
            if [[ $inc == *H36v2* || $inc == *h36v2* ]]; then OPT_HEADS=v2; else OPT_HEADS=v1.3; fi
        elif [[ -n $list ]] && ! grep -qi 'can' <<<"$list"; then OPT_HEADS=none; fi
    fi
    if [[ -z $OPT_ALPS && -n $list ]]; then
        OPT_ALPS=$(grep -c '^mcu alps' <<<"$list" || true)
        [[ $OPT_ALPS -gt 2 ]] && OPT_ALPS=2
    fi
    return 0
}

# Значения [mcu ...] для новых секций: из printer.cfg, затем из devices.tsv и /dev/serial/by-id.
# Чего нет - остаётся пустым (в блоке будет ЗАПОЛНИТЕ, такие секции в printer.cfg не добавляются).
collect_mcu_state() {
    local cfg=$PRINTER_CFG_DIR/printer.cfg list name key val i f s
    [[ -f $DEVICES_FILE ]] && PREV_DEVICES=$(cat "$DEVICES_FILE")
    list=""
    [[ $(cfg_state "$cfg") == vostok ]] && list=$(python3 -I "$INSTALL_DIR/tools/mcu_merge.py" "$cfg" --list 2>/dev/null || true)
    while IFS=$'\t' read -r name key val; do
        [[ -n $name ]] || continue
        case $name in
            mcu)
                if [[ $key == canbus_uuid ]]; then RES_BRIDGE_UUID=$val
                else RES_MAIN_SERIAL=$(sed -n 's/^.*usb-Klipper_[^_]*_\(.*\)-if00$/\1/p' <<<"$val"); fi ;;
            "mcu ${HEAD_MCU[0]}") RES_HEAD_UUID[0]=$val ;;
            "mcu ${HEAD_MCU[1]}") RES_HEAD_UUID[1]=$val ;;
            "mcu alps") RES_ALPS_SERIAL[0]=$(sed -n 's/^.*usb-Klipper_[^_]*_\(.*\)-if00$/\1/p' <<<"$val") ;;
            "mcu alps_t1") RES_ALPS_SERIAL[1]=$(sed -n 's/^.*usb-Klipper_[^_]*_\(.*\)-if00$/\1/p' <<<"$val") ;;
        esac
    done <<<"$list"
    if [[ $MODE == usb && -z $RES_MAIN_SERIAL ]]; then
        f=$(byid_find "usb-Klipper_${MAIN}_*" | head -n 1)
        [[ -n $f ]] && RES_MAIN_SERIAL=$(sed -n 's/^.*usb-Klipper_[^_]*_\(.*\)-if00$/\1/p' <<<"$f")
    fi
    if [[ $MODE == bridge ]]; then
        [[ -n $RES_BRIDGE_UUID ]] || RES_BRIDGE_UUID=$(prev_keys "${MAIN}-canbridge.config" | head -n 1)
        if [[ -z ${RES_HEAD_UUID[0]} || -z ${RES_HEAD_UUID[1]} ]]; then
            local u0="" u1=""
            { read -r u0; read -r u1; } < <(prev_keys "$(head_cfg_name)") || true
            [[ -n ${RES_HEAD_UUID[0]} ]] || RES_HEAD_UUID[0]=$u0
            [[ -n ${RES_HEAD_UUID[1]} ]] || RES_HEAD_UUID[1]=$u1
        fi
    fi
    i=0
    for f in $(byid_find 'usb-Klipper_stm32f072xb_*'); do
        s=$(sed -n 's/^.*usb-Klipper_[^_]*_\(.*\)-if00$/\1/p' <<<"$f")
        [[ $i -lt $ALPS_COUNT && -z ${RES_ALPS_SERIAL[$i]:-} && " ${RES_ALPS_SERIAL[*]} " != *" $s "* ]] && RES_ALPS_SERIAL[$i]=$s
        i=$((i + 1))
    done
    return 0
}

main() {
    parse_args "${CONFIGURE_ARGS[@]}"
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    log_to_file "=== configure_vostok.sh $VOSTOK_INSTALLER_VERSION: ${CONFIGURE_ARGS[*]:-} ==="
    command -v python3 >/dev/null || die "нужен python3"
    [[ -d $PRINTER_DATA ]] || die "нет каталога $PRINTER_DATA (укажите --printer-data)"
    step "Настройка конфига VOSTOK (версия $VOSTOK_INSTALLER_VERSION)"
    info "Каталог конфига: $PRINTER_CFG_DIR"

    guess_from_printer_cfg
    detect_hardware
    info "Главная плата: $(main_label), платы голов: $([[ $HEADS == none ]] && echo нет || head_label), ALPS: $ALPS_COUNT"
    collect_mcu_state
    stage_config

    if [[ $DRY_RUN -eq 0 ]]; then
        info ""
        info "Готово. Чтобы применить конфиг, перезапустите Klipper (Fluidd: RESTART/FIRMWARE_RESTART или sudo systemctl restart klipper)."
    fi
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    main
fi
