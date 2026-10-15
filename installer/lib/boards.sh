#!/usr/bin/env bash
# Реестр плат VOSTOK: чтение boards/<id>.board (строки KEY="значение", без исполнения кода).
# Подключается через source из install_vostok.sh / update_klipper_mcu.sh / lib/vostok_config.sh / tools/gen_configs.sh.
#
# Переменные (можно задать до source): BOARDS_DIR (по умолчанию <каталог установщика>/boards),
# CONFIGS_DIR (configs/), KATAPULT_CONFIGS (configs/katapult/).
#
# Функции:
#   board_load ID            загрузить плату в B_ID, B_LABEL, B_CHIP ... (ошибка, если нет файла или обязательного поля)
#   boards_list [роль]       id плат (main|head|alps), по одной в строке
#   board_resolve ИМЯ        id или алиас -> id
#   boards_for_chip ЧИП [роль], boards_for_family СЕМЕЙСТВО [роль]
#   board_by_cfg ФАЙЛ.config -> "<id> <usb|bridge|can|katapult>" (путь с /katapult/ означает katapult)
#   board_cfg ID usb|bridge|can|katapult -> путь к конфигу сборки (код 1, если такого конфига у платы нет)
#   board_has_bridge ID      есть ли у платы режим USB-CAN моста (ROLE=main, USB и CAN заданы)
#   board_field ID КЛЮЧ      значение одного поля без загрузки остальных

_BOARDS_LIB_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
BOARDS_DIR=${BOARDS_DIR:-$(dirname "$_BOARDS_LIB_DIR")/boards}
CONFIGS_DIR=${CONFIGS_DIR:-$(dirname "$_BOARDS_LIB_DIR")/configs}
KATAPULT_CONFIGS=${KATAPULT_CONFIGS:-$CONFIGS_DIR/katapult}

# Все поля формата .board
BOARD_KEYS=(LABEL ROLE CHIP FAMILY MACH CLOCK APP_OFFSET USB CAN CAN_KIND INITIAL_PINS BRIDGE_INITIAL_PINS
    KATAPULT_INITIAL_PINS KATAPULT_LED KATAPULT_DOUBLE_RESET CFG ALIASES DFU_HINT DFU_HOW ELEC_PATTERN
    TEMPLATE HEAD_NAMES VERIFIED DOC NOTE)
# Обязательные (непустые) поля; CAN_KIND обязателен, если задан CAN
BOARD_REQUIRED=(LABEL ROLE CHIP FAMILY MACH CLOCK APP_OFFSET CFG VERIFIED)

_board_err() { echo "boards: $*" >&2; }

_board_file() { echo "$BOARDS_DIR/$1.board"; }

# Кэш разобранных плат: заполняется при подключении библиотеки (boards_preload), чтобы board_field
# в подоболочках $(...) не разбирал файл заново. Ключи: "<каталог>/<id>" и "<каталог>/<id>/<поле>".
declare -gA _BCV=() _BCF=()

# Разбор файла платы в ассоциативный массив _BP (без source), из кэша, если плата уже разобрана.
_board_parse() { # id
    local id=$1 k
    declare -gA _BP=()
    if [[ -n ${_BCV["$BOARDS_DIR/$id"]:-} ]]; then
        for k in "${BOARD_KEYS[@]}"; do _BP[$k]=${_BCF["$BOARDS_DIR/$id/$k"]:-}; done
        return 0
    fi
    _board_parse_file "$id" || return 1
    _BCV["$BOARDS_DIR/$id"]=1
    for k in "${BOARD_KEYS[@]}"; do _BCF["$BOARDS_DIR/$id/$k"]=${_BP[$k]:-}; done
}

# Разбор файла платы в _BP. Ошибка: код 1 и сообщение в stderr.
_board_parse_file() { # id
    local id=$1 f line key val k known
    f=$(_board_file "$id")
    [[ $id =~ ^[a-z0-9][a-z0-9._-]*$ && -f $f ]] || { _board_err "нет описания платы '$id' ($f)"; return 1; }
    declare -gA _BP=()
    while IFS= read -r line || [[ -n $line ]]; do
        line=${line%$'\r'}
        [[ $line =~ ^[[:space:]]*(#.*)?$ ]] && continue
        if [[ $line =~ ^([A-Z_]+)=(.*)$ ]]; then
            key=${BASH_REMATCH[1]}; val=${BASH_REMATCH[2]}
            val=${val%"${val##*[![:space:]]}"}
            if [[ $val =~ ^\"(.*)\"$ ]]; then val=${BASH_REMATCH[1]}
            elif [[ $val == *[[:space:]]* || $val == \"* ]]; then
                _board_err "$f: значение $key надо взять в двойные кавычки"; return 1
            fi
            known=0
            for k in "${BOARD_KEYS[@]}"; do [[ $k == "$key" ]] && known=1; done
            [[ $known -eq 1 ]] || { _board_err "$f: неизвестное поле $key"; return 1; }
            _BP[$key]=$val
        else
            _board_err "$f: не разобрана строка: $line"; return 1
        fi
    done <"$f"
    for k in "${BOARD_REQUIRED[@]}"; do
        [[ -n ${_BP[$k]:-} ]] || { _board_err "$f: не задано обязательное поле $k"; return 1; }
    done
    [[ -z ${_BP[CAN]:-} || -n ${_BP[CAN_KIND]:-} ]] || { _board_err "$f: для CAN нужно поле CAN_KIND"; return 1; }
    case ${_BP[ROLE]} in main|head|alps) ;; *) _board_err "$f: ROLE должен быть main|head|alps"; return 1 ;; esac
    case ${_BP[CAN_KIND]:-} in ""|cmenu|mmenu|direct) ;; *) _board_err "$f: CAN_KIND должен быть cmenu|mmenu|direct"; return 1 ;; esac
    case ${_BP[VERIFIED]} in yes|no) ;; *) _board_err "$f: VERIFIED должен быть yes|no"; return 1 ;; esac
    return 0
}

# Разобрать все платы заранее (вызывается при подключении библиотеки); платы с ошибкой пропускаются,
# сообщение появится при первом обращении к ним
boards_preload() {
    local f id
    for f in "$BOARDS_DIR"/*.board; do
        [[ -f $f ]] || continue
        id=$(basename "$f" .board)
        _board_parse "$id" 2>/dev/null || true
    done
}

board_load() { # id
    local id=$1 k v
    for v in $(compgen -v B_); do unset "$v"; done
    _board_parse "$id" || return 1
    for k in "${BOARD_KEYS[@]}"; do printf -v "B_$k" '%s' "${_BP[$k]:-}"; done
    B_ID=$id
}

board_field() { # id ключ
    _board_parse "$1" || return 1
    printf '%s\n' "${_BP[$2]:-}"
}

boards_list() { # [роль]
    local f id role=${1:-}
    for f in "$BOARDS_DIR"/*.board; do
        [[ -f $f ]] || continue
        id=$(basename "$f" .board)
        [[ -z $role || $(board_field "$id" ROLE 2>/dev/null) == "$role" ]] && echo "$id"
    done
    return 0
}

board_resolve() { # имя (id или алиас)
    local name=${1,,} id a
    [[ -n $name ]] || return 1
    [[ -f $(_board_file "$name") ]] && { echo "$name"; return 0; }
    for id in $(boards_list); do
        for a in $(board_field "$id" ALIASES 2>/dev/null); do
            [[ ${a,,} == "$name" ]] && { echo "$id"; return 0; }
        done
    done
    return 1
}

_boards_by() { # ключ значение [роль]
    local id
    for id in $(boards_list "${3:-}"); do
        [[ $(board_field "$id" "$1") == "$2" ]] && echo "$id"
    done
    return 0
}
boards_for_chip() { _boards_by CHIP "$1" "${2:-}"; }
boards_for_family() { _boards_by FAMILY "$1" "${2:-}"; }

board_has_bridge() { # id
    _board_parse "$1" || return 1
    [[ ${_BP[ROLE]} == main && -n ${_BP[USB]} && -n ${_BP[CAN]} ]]
}

board_cfg() { # id usb|bridge|can|katapult
    local id=$1 kind=$2 cfg role usb
    _board_parse "$id" || return 1
    cfg=${_BP[CFG]}; role=${_BP[ROLE]}; usb=${_BP[USB]}
    case $kind in
        usb)      [[ $role != head && -n $usb ]] || return 1; echo "$CONFIGS_DIR/$cfg.config" ;;
        bridge)   [[ $role == main && -n $usb && -n ${_BP[CAN]} ]] || return 1; echo "$CONFIGS_DIR/$cfg-canbridge.config" ;;
        can)      [[ $role == head ]] || return 1; echo "$CONFIGS_DIR/$cfg-can.config" ;;
        katapult) if [[ $role == head ]]; then echo "$KATAPULT_CONFIGS/$cfg-can.config"; else echo "$KATAPULT_CONFIGS/$cfg.config"; fi ;;
        *) _board_err "board_cfg: неизвестный вид '$kind'"; return 1 ;;
    esac
}

board_by_cfg() { # файл.config (имя или путь) -> "id вид"
    local path=$1 base id kind want=klipper
    base=$(basename "$path")
    [[ $path == */katapult/* || $path == katapult/* ]] && want=katapult
    for id in $(boards_list); do
        if [[ $want == katapult ]]; then
            [[ $(basename "$(board_cfg "$id" katapult)") == "$base" ]] && { echo "$id katapult"; return 0; }
        else
            for kind in usb bridge can; do
                [[ $(basename "$(board_cfg "$id" "$kind" 2>/dev/null)" 2>/dev/null) == "$base" ]] \
                    && board_cfg "$id" "$kind" >/dev/null 2>&1 && { echo "$id $kind"; return 0; }
            done
        fi
    done
    return 1
}

boards_preload
