# Общая библиотека настройки конфига VOSTOK (подключается через source из install_vostok.sh и configure_vostok.sh).
# Здесь определение железа, меню выбора конфига, генерация своего конфига, слияние [mcu] и модули.
# Перед подключением нужны функции вывода и пути из update_klipper_mcu.sh (info, warn, die, ...).

# Значения по умолчанию (скрипты могут переопределить до или после подключения)
: "${DRY_RUN:=0}" "${ONLY_DETECT:=0}"
OPT_MAIN=${OPT_MAIN:-}; OPT_HEADS=${OPT_HEADS:-}; OPT_ALPS=${OPT_ALPS:-}
OPT_ELECTRONICS=${OPT_ELECTRONICS:-}; OPT_CONFIG_SOURCE=${OPT_CONFIG_SOURCE:-}; OPT_DRIVERS=${OPT_DRIVERS:-}
MAIN=${MAIN:-}; HEADS=${HEADS:-}; ALPS_COUNT=${ALPS_COUNT:-0}; MODE=${MODE:-}
RES_MAIN_SERIAL=${RES_MAIN_SERIAL:-}; RES_BRIDGE_UUID=${RES_BRIDGE_UUID:-}
RES_HEAD_UUID=("${RES_HEAD_UUID[@]:-}" ""); RES_HEAD_UUID=("${RES_HEAD_UUID[0]:-}" "${RES_HEAD_UUID[1]:-}")
RES_ALPS_SERIAL=("${RES_ALPS_SERIAL[0]:-}" "${RES_ALPS_SERIAL[1]:-}")
PREV_DEVICES=${PREV_DEVICES:-}
OPT_REFERENCE=${OPT_REFERENCE:-}   # ФАЙЛ|none: эталонный electronics-файл (по умолчанию свой конфиг пользователя, при чистой установке стоковый main)
OPT_MODULES=${OPT_MODULES:-}       # chamber_heater|all|none (через запятую): подключать дополнительные модули без вопроса
: "${BYID_DIR:=/dev/serial/by-id}"
: "${PRINTER_CFG_DIR:=$PRINTER_DATA/config}"
: "${VOSTOK_CFG_LOCAL:=auto}"
: "${VOSTOK_CFG_TARBALL:=https://codeload.github.com/dmitry-sorkin/vostok_configuration/tar.gz/refs/heads/main}"
: "${INSTALL_DIR:=$SCRIPT_DIR}"

# ------------------------------------------------------------------ интерактив

have_tty() { { : </dev/tty; } 2>/dev/null; }
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


# Ключи (serial/uuid) из devices.tsv прошлого запуска для конфига сборки, по порядку
prev_keys() { # имя_конфига
    [[ -n $PREV_DEVICES ]] || return 0
    awk -F'\t' -v c="$1" '$2 == c {print $1}' <<<"$PREV_DEVICES"
}

# ---------------------------------------------------------------- этап 3: обнаружение

byid_find() { # шаблон: список путей по возрастанию
    local f
    for f in $BYID_DIR/$1; do [[ -e $f ]] && printf '%s\n' "$f"; done
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

# Адрес 12-байтного UID чипа по семейству (ROM-загрузчик отдаёт его по DFU)
uid_addr() { # f0|f4|h7|g
    case $1 in
        f0) echo 0x1FFFF7AC ;; f4) echo 0x1FFF7A10 ;; h7) echo 0x1FF1E800 ;; g) echo 0x1FFF7590 ;;
    esac
}

# canbus_uuid по UID, прочитанному из платы в DFU (плата остаётся в DFU). Результат: DFU_UID_UUID (пусто при ошибке)
DFU_UID_UUID=""
dfu_read_uid() { # семейство
    local addr tmp
    DFU_UID_UUID=""
    addr=$(uid_addr "$1"); [[ -n $addr ]] || return 1
    [[ $DRY_RUN -eq 1 ]] && { info "[dry-run] dfu-util -U UID ($addr) -> canbus_uuid"; DFU_UID_UUID=000000000000; return 0; }
    tmp=$(mktemp -d)
    if sudo dfu-util -a 0 -s "$addr:12:force" -U "$tmp/uid.bin" -d 0483:df11 >>"${LOG_FILE:-/dev/null}" 2>&1 \
        && DFU_UID_UUID=$(python3 -I "$INSTALL_DIR/tools/can_uuid.py" --uid-file "$tmp/uid.bin" 2>/dev/null); then
        rm -rf "$tmp"; return 0
    fi
    rm -rf "$tmp"; DFU_UID_UUID=""
    return 1
}

can_uuid_from_serial() { # serial (UID в hex, как у USB-устройства Klipper)
    python3 -I "$INSTALL_DIR/tools/can_uuid.py" --uid-hex "$1" 2>/dev/null
}

# USB-serial моста USB-CAN (1d50:606f)
bridge_usb_serial() {
    local d
    for d in /sys/bus/usb/devices/*; do
        [[ $(cat "$d/idVendor" 2>/dev/null) == 1d50 && $(cat "$d/idProduct" 2>/dev/null) == 606f ]] || continue
        cat "$d/serial" 2>/dev/null && return 0
    done
    return 1
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
            local def_lbl="нет (пассивная плата, например fly miniAB)"
            [[ $heads_guess != none ]] && def_lbl="Fysetc H36 v2"
            ans=$(ask_choice "Платы голов по CAN (при их наличии Octopus станет мостом USB-CAN):" "$def_lbl" \
                "нет (пассивная плата, например fly miniAB)" "Fysetc H36 v1.3" "Fysetc H36 v2" "BTT EBB42")
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

# ---------------------------------------------------------------- этап 6: конфигурация

# ---------------------------------------------------------------- свой конфиг электроники

TEMPLATES_DIR=${TEMPLATES_DIR:-$INSTALL_DIR/templates}
GEN_NAME=""         # имя сгенерированного файла (electronics_<плата>_<N>x<драйвер>[_2x<головы>].cfg)
GEN_FILL=""         # строки FILL<TAB>источник<TAB>число
GEN_EMPTY=""        # строки EMPTY<TAB>[секция]<TAB>опция из gen_electronics.py
GEN_WARN=""         # строки WARN<TAB>текст
GEN_USED=0
DRIVERS_SPEC=""
DRV_LBL_2130="TMC2130 (SPI)"; DRV_LBL_2208="TMC2208 (UART)"; DRV_LBL_2209="TMC2209 (UART)"; DRV_LBL_2240="TMC2240 (SPI)"
DRV_LBL_5160="TMC5160 / 5160T Pro (SPI, sense 0.075)"; DRV_LBL_5160P="TMC5160T Plus (SPI, sense 0.022)"
DRIVER_DEFAULT_SPEC="x=2240,w=2240,yl=2240,yr=2240,z=2240,e0=2209,e1=2209"

drv_pick() { # вопрос -> 2209|2240|5160
    local a def=$DRV_LBL_2240
    a=$(ask_choice "$1" "$def" "$DRV_LBL_2130" "$DRV_LBL_2208" "$DRV_LBL_2209" "$DRV_LBL_2240" "$DRV_LBL_5160" "$DRV_LBL_5160P")
    case $a in
        "$DRV_LBL_2130") echo 2130 ;; "$DRV_LBL_2208") echo 2208 ;; "$DRV_LBL_2209") echo 2209 ;;
        "$DRV_LBL_5160") echo 5160 ;; "$DRV_LBL_5160P") echo 5160plus ;; *) echo 2240 ;;
    esac
}

# Пошаговый выбор драйверов: «все одинаковые» или по каждому мотору. Результат в DRIVERS_SPEC.
drivers_wizard() {
    local m same_lbl="Все драйверы одинаковые" diff_lbl="Разные драйверы" mode spec="" list t
    if [[ -n $OPT_DRIVERS ]]; then DRIVERS_SPEC=$OPT_DRIVERS; return; fi
    if [[ $ASSUME_YES -eq 1 ]] || ! have_tty; then
        DRIVERS_SPEC=$DRIVER_DEFAULT_SPEC
        info "Драйверы моторов: как в стоковом конфиге ($DRIVERS_SPEC). Другие задаются опцией --drivers."
        return
    fi
    info ""
    info "Драйверы моторов. Пины драйверов останутся пустыми, ток и режимы берутся из стокового конфига."
    [[ $HEADS != none ]] && info "Драйверы экструдеров не спрашиваю: на платах голов распаян TMC2209, он берётся из пресета платы."
    mode=$(ask_choice "Какие драйверы стоят на плате?" "$same_lbl" "$same_lbl" "$diff_lbl")
    if [[ $mode == "$same_lbl" ]]; then
        DRIVERS_SPEC="all=$(drv_pick "Тип драйверов:")"
        return
    fi
    list=(x w yl yr z)
    [[ $HEADS == none ]] && list=(e0 e1 x w yl yr z)
    for m in "${list[@]}"; do
        case $m in
            e0) t="экструдера T0 (левая голова)" ;; e1) t="экструдера T1 (правая голова)" ;;
            x) t="мотора X" ;; w) t="мотора W (правая голова по X)" ;; yl) t="левого мотора Y" ;;
            yr) t="правого мотора Y" ;; z) t="мотора Z" ;;
        esac
        spec+="${spec:+,}$m=$(drv_pick "Драйвер $t:")"
    done
    DRIVERS_SPEC=$spec
}

# Стоковый main-файл электроники (для H723 - с _h723_ в имени) из корня конфигов
stock_electronics() { # корень
    local f first=""
    for f in "$1"/electronics_*.cfg; do
        [[ -f $f ]] || continue
        [[ -n $first ]] || first=$f
        if [[ $MAIN == stm32h723xx && $f == *_h723_* ]]; then printf '%s' "$f"; return; fi
    done
    printf '%s' "$first"
}

# Эталон для подстановки пинов и параметров: свой конфиг пользователя (активный include electronics_*.cfg в printer.cfg)
# всегда основа; стоковый main - только при чистой установке (своего конфига нет), для H723.
# Результат: REF_CFG (путь или пусто) и REF_KIND (user|stock|none)
REF_CFG=""; REF_KIND=none
CFG_STATE=""   # none|blank|foreign|vostok: состояние printer.cfg (выставляет stage_config)

# Состояние printer.cfg: none (нет файла), blank (пустой или только комментарии), foreign (не конфиг VOSTOK:
# нет [include printer_base.cfg], например пример KIAUH), vostok (конфиг VOSTOK пользователя).
# Всё, кроме vostok, считается чистой установкой.
cfg_state() { # printer.cfg
    [[ -f $1 ]] || { echo none; return 0; }
    if ! grep -Eqv '^[[:space:]]*(#.*)?$' "$1"; then echo blank
    elif grep -Eq '^[[:space:]]*\[include[[:space:]]+printer_base\.cfg\]' "$1"; then echo vostok
    else echo foreign; fi
}

find_reference() { # корень
    local cfg=$PRINTER_CFG_DIR/printer.cfg inc="" stock
    REF_CFG=""; REF_KIND=none
    if [[ $OPT_REFERENCE == none ]]; then return 0; fi
    if [[ -n $OPT_REFERENCE ]]; then
        [[ -f $OPT_REFERENCE ]] || die "--reference: файл не найден: $OPT_REFERENCE"
        REF_CFG=$OPT_REFERENCE; REF_KIND=user; return 0
    fi
    if [[ -f $cfg && ${CFG_STATE:-vostok} == vostok ]]; then
        inc=$(sed -n 's/^[[:space:]]*\[include[[:space:]]\+\(electronics_[^]]*\.cfg\)\].*/\1/p' "$cfg" | head -n 1)
        if [[ -n $inc && -f $PRINTER_CFG_DIR/$inc ]]; then REF_CFG=$PRINTER_CFG_DIR/$inc; REF_KIND=user; return 0; fi
    fi
    if [[ $MAIN == stm32h723xx ]]; then
        stock=$(stock_electronics "$1")
        [[ -n $stock ]] && { REF_CFG=$stock; REF_KIND=stock; }
    fi
    return 0
}

# Генерирует electronics_*.cfg по шаблону. Аргументы: корень_конфигов каталог_вывода
gen_custom_electronics() { # корень каталог_вывода; имя файла по образцу user_configs - в GEN_NAME
    local root=$1 outdir=$2 main_std res extra=() line
    main_std=$(stock_electronics "$root")
    find_reference "$root"
    [[ -d $TEMPLATES_DIR ]] || die "нет каталога шаблонов: $TEMPLATES_DIR"
    [[ $MAIN == stm32h723xx ]] && extra+=(--octopus-extruders)
    [[ $HEADS == none ]] && extra+=(--octopus-heads)
    case $REF_KIND in
        user) info "Основа - ваш текущий конфиг электроники: $REF_CFG (пины и параметры берутся из него)" ;;
        stock) info "Чистая установка: пины и параметры моторов берутся из стокового конфига main ($(basename "$REF_CFG"))" ;;
        *) info "Эталонного конфига нет: пины моторов и драйверов останутся пустыми" ;;
    esac
    res=$(python3 -I "$INSTALL_DIR/tools/gen_electronics.py" --templates "$TEMPLATES_DIR" --ref-cfg "$REF_CFG" --main-cfg "$main_std" \
        --heads "$HEADS" --head-names "${HEAD_MCU[0]},${HEAD_MCU[1]}" --alps "$ALPS_COUNT" \
        --drivers "$DRIVERS_SPEC" --main "$([[ $MAIN == stm32h723xx ]] && echo h723 || echo f446)" "${extra[@]}" \
        --out-dir "$outdir") || die "не удалось сгенерировать конфиг электроники"
    GEN_NAME=$(sed -n 's/^NAME\t//p' <<<"$res")
    [[ -n $GEN_NAME ]] || die "генератор не вернул имя файла"
    GEN_EMPTY=$(grep '^EMPTY' <<<"$res" || true)
    GEN_WARN=$(grep '^WARN' <<<"$res" || true)
    GEN_FILL=$(grep '^FILL' <<<"$res" || true)
    GEN_USED=1
    ok "конфиг электроники сгенерирован: $GEN_NAME (драйверы: $DRIVERS_SPEC)"
    while IFS=$'\t' read -r _ line n; do
        [[ -n $line && ${n:-0} -gt 0 ]] || continue
        case $line in
            ref) info "  подставлено пинов из эталона: $n" ;;
            octopus) info "  подставлено пинов экструдеров на разъёмы MOTOR4 (E0) и MOTOR5 (E1): $n" ;;
        esac
    done <<<"$GEN_FILL"
}

print_gen_warnings() { # файл
    local n; n=$(grep -c . <<<"$GEN_EMPTY" || true)
    if [[ $n -gt 0 ]]; then warn "Сгенерирован $1: Klipper не запустится, пока вы не впишете пины."
    else warn "Сгенерирован $1: пустых пинов нет, но проверьте проводку и параметры."; fi
    case $REF_KIND in
        user) printf '  0. Пины и параметры взяты из вашего конфига (%s): проверьте, что драйверы стоят в тех же разъёмах.\n' "$(basename "$REF_CFG")" >&2 ;;
        stock) printf '  0. Пины моторов и драйверов взяты из стокового конфига main (X: MOTOR2, W: MOTOR0, YL: MOTOR3, YR: MOTOR1, Z: MOTOR7%s): проверьте, что драйверы стоят в этих разъёмах.\n' "$([[ $HEADS == none ]] && echo ', экструдеры: MOTOR4 и MOTOR5')" >&2 ;;
    esac
    [[ $n -gt 0 ]] && printf '  1. Впишите пины по схеме СВОЕЙ платы (пустых пинов: %s). Они помечены ЗАПОЛНИТЕ:\n' "$n" >&2
    [[ $n -gt 0 ]] && awk -F'\t' '{ if ($2 != sec) { if (sec != "") printf "\n"; sec = $2; printf "       %s: %s", $2, $3 } else printf ", %s", $3 } END { if (sec != "") printf "\n" }' <<<"$GEN_EMPTY" >&2
    cat >&2 <<EOF
  2. Проверьте параметры моторов (run_current, stealthchop_threshold, interpolate): они взяты из эталонного конфига (по умолчанию ваш; для чистой установки стоковый main под TMC2240),
     у вашего драйвера и мотора они могут быть другими. sense_resistor выставлен по документации BTT (5160 и 5160T Pro 0.075, 5160T Plus 0.022, 2130/2208/2209 0.110); если у вас другой модуль, исправьте.
  3. Проверьте направления моторов (знак ! у dir_pin) и full_steps_per_rotation после первого запуска.
  4. Если используете chamber_heater.cfg, проверьте, что его пины не пересекаются с вашей проводкой.
EOF
    [[ -n $GEN_WARN ]] && while IFS=$'\t' read -r _ w; do warn "$w"; done <<<"$GEN_WARN"
    return 0
}

# Режим «Пропустить редактирование конфига»: дописывает недостающие [mcu ...] в существующий printer.cfg
merge_mcus_into_cfg() { # printer.cfg блоки_файл [--dry]
    local cfg=$1 blocks=$2 dry=${3:-} res kind name a b c d added=0
    [[ -f $INSTALL_DIR/tools/mcu_merge.py ]] || die "нет $INSTALL_DIR/tools/mcu_merge.py"
    res=$(python3 -I "$INSTALL_DIR/tools/mcu_merge.py" "$cfg" "$blocks" --dry) || die "не удалось обработать $cfg"
    if [[ -z $dry ]] && grep -q '^ADD' <<<"$res"; then
        cp -p "$cfg" "$cfg.bak-$(date +%Y%m%d-%H%M%S)" || die "не удалось сделать резервную копию $cfg"
        python3 -I "$INSTALL_DIR/tools/mcu_merge.py" "$cfg" "$blocks" >/dev/null || die "не удалось обработать $cfg"
        added=1
    fi
    while IFS=$'\t' read -r kind name a b c d; do
        [[ -n $kind ]] || continue
        case $kind in
            ADD) ok "[$name] добавлена в $(basename "$cfg")${dry:+ (dry-run: запись не выполнена)}" ;;
            OK) info "[$name] уже есть в конфиге${a:+ ($a)}" ;;
            DIFF) warn "[$name]: в конфиге $a: $b, а прошито: $c. Файл не менял, проверьте вручную" ;;
            TODO) warn "[$name]: плата не прошита, секцию не добавляю" ;;
        esac
    done <<<"$res"
    [[ $added -eq 1 ]] && info "Резервная копия: $cfg.bak-*"
    return 0
}


# Выбор electronics_*.cfg: сначала источник (корень main или user_configs), затем файл.
# Результат: EL_SRC (standard|user) и EL_NAME. Аргумент - корень распакованного архива.
EL_SRC=""; EL_NAME=""
SRC_LBL_STD="Стандартный (корень main)"
SRC_LBL_USR="Пользовательский (user_configs)"
SRC_LBL_GEN="Сгенерировать свой конфиг"
SRC_LBL_SKIP="Пропустить редактирование конфига"

el_matches() { # имя: подходит ли файл под выбранные главную плату и платы голов
    local f=$1 chip_pat head_pat=""
    [[ $MAIN == stm32h723xx ]] && chip_pat="_h723_" || chip_pat="_f446_"
    [[ $f == *$chip_pat* ]] || return 1
    case $HEADS in v1.3) head_pat="H36v1.3" ;; v2) head_pat="H36v2" ;; ebb42) head_pat="ebb42" ;; esac
    [[ -z $head_pat || $f == *$head_pat* ]]
}

pick_electronics() { # корень_архива allow_skip(0|1)
    local root=$1 allow_skip=${2:-0} f d std=() usr=() def_src="" def_file="" labels=() names=() ans k src_ans
    for f in "$root"/electronics_*.cfg; do [[ -f $f ]] && std+=("$(basename "$f")"); done
    for f in "$root"/user_configs/electronics_*.cfg; do [[ -f $f ]] && usr+=("$(basename "$f")"); done
    [[ ${#std[@]} -gt 0 || ${#usr[@]} -gt 0 || -d $root/installer/templates || -d $INSTALL_DIR/templates ]] || die "в архиве нет electronics_*.cfg"

    # Явно заданный файл: ищем в обоих каталогах
    if [[ -n $OPT_ELECTRONICS ]]; then
        for f in "${std[@]}"; do [[ $f == "$OPT_ELECTRONICS" ]] && { EL_SRC=standard; EL_NAME=$f; return; }; done
        for f in "${usr[@]}"; do [[ $f == "$OPT_ELECTRONICS" ]] && { EL_SRC=user; EL_NAME=$f; return; }; done
        die "файл $OPT_ELECTRONICS не найден ни в корне main, ни в user_configs"
    fi

    # Источник
    local labs=() def_lbl
    [[ ${#std[@]} -gt 0 ]] && labs+=("$SRC_LBL_STD")
    [[ ${#usr[@]} -gt 0 ]] && labs+=("$SRC_LBL_USR")
    labs+=("$SRC_LBL_GEN")
    [[ $allow_skip -eq 1 ]] && labs+=("$SRC_LBL_SKIP")
    if [[ -n $OPT_CONFIG_SOURCE ]]; then
        EL_SRC=$OPT_CONFIG_SOURCE
        [[ $EL_SRC == skip && $allow_skip -eq 0 ]] && die "--config-source skip: printer.cfg ещё не существует, пропускать нечего"
    else
        def_src=user
        for f in "${std[@]}"; do el_matches "$f" && def_src=standard; done
        [[ ${#std[@]} -eq 0 ]] && def_src=user
        [[ ${#usr[@]} -eq 0 ]] && def_src=standard
        if [[ $allow_skip -eq 1 ]]; then def_lbl=$SRC_LBL_SKIP
        elif [[ $def_src == standard && ${#std[@]} -gt 0 ]]; then def_lbl=$SRC_LBL_STD
        elif [[ ${#usr[@]} -gt 0 ]]; then def_lbl=$SRC_LBL_USR
        else def_lbl=$SRC_LBL_GEN; fi
        info ""
        info "Конфиг электроники можно взять из репозитория vostok_configuration:"
        [[ ${#std[@]} -gt 0 ]] && info "  - стандартный: корень main, поддерживается автором (${std[*]});"
        [[ ${#usr[@]} -gt 0 ]] && info "  - пользовательский: каталог user_configs, конфиги пользователей (${#usr[@]} шт.), могут не совпадать с документацией;"
        info "  - сгенерировать свой: шаблон без плат и драйверов + пресеты найденных плат, пины драйверов и моторов вы впишете сами;"
        [[ $allow_skip -eq 1 ]] && info "  - пропустить: printer.cfg уже есть, будут дописаны только недостающие секции [mcu ...]."
        src_ans=$(ask_choice "Откуда взять конфиг?" "$def_lbl" "${labs[@]}")
        case $src_ans in
            "$SRC_LBL_USR") EL_SRC=user ;;
            "$SRC_LBL_GEN") EL_SRC=generate ;;
            "$SRC_LBL_SKIP") EL_SRC=skip ;;
            *) EL_SRC=standard ;;
        esac
    fi
    if [[ $EL_SRC == skip ]]; then EL_NAME=""; return; fi
    if [[ $EL_SRC == generate ]]; then EL_NAME=""; return; fi
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

# Плата, не прошитая установщиком, получает заглушку ЗАПОЛНИТЕ: Klipper сообщит об ошибке, пока её не заменят
TODO_MARK="ЗАПОЛНИТЕ"
mcu_blocks() {
    local i v
    if [[ $MODE == bridge ]]; then
        printf '[mcu]\ncanbus_uuid: %s\n\n' "${RES_BRIDGE_UUID:-$TODO_MARK}"
        for i in 0 1; do
            printf '[mcu %s]\ncanbus_uuid: %s\n\n' "${HEAD_MCU[$i]}" "${RES_HEAD_UUID[$i]:-$TODO_MARK}"
        done
    else
        printf '[mcu]\nserial: /dev/serial/by-id/usb-Klipper_%s_%s-if00\n\n' "$MAIN" "${RES_MAIN_SERIAL:-$TODO_MARK}"
    fi
    for ((i = 0; i < ALPS_COUNT; i++)); do
        v=${RES_ALPS_SERIAL[$i]:-$TODO_MARK}
        printf '[mcu alps%s]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_%s-if00\n\n' "$([[ $i -eq 1 ]] && echo _t1)" "$v"
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
    local blocks local_root has_cfg=0 tmp tarball el src_dir cfg_root stamp f
    blocks=$(mcu_blocks); local_root=$(local_cfg_root)
    CFG_STATE=$(cfg_state "$PRINTER_CFG_DIR/printer.cfg")
    [[ $CFG_STATE == vostok ]] && has_cfg=1   # существующий конфиг: меняем только электронику; иначе чистая установка
    if [[ $DRY_RUN -eq 1 && -z $local_root ]]; then
        info "[dry-run] взял бы конфигурацию из $VOSTOK_CFG_TARBALL, скопировал printer.cfg, printer_base.cfg, chamber_heater.cfg, electronics_*.cfg, postprocessing/ в $PRINTER_CFG_DIR"
        printf '%s\n' "$blocks"
        return 0
    fi
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
    case $CFG_STATE in
        vostok) info "$PRINTER_CFG_DIR/printer.cfg уже существует: заменю только электронику, остальное оставлю как есть" ;;
        blank) warn "$PRINTER_CFG_DIR/printer.cfg пустой: считаю это чистой установкой (всё из main)" ;;
        foreign) warn "$PRINTER_CFG_DIR/printer.cfg не похож на конфиг VOSTOK (нет [include printer_base.cfg]): считаю это чистой установкой (всё из main), прежний файл сохраню в *.bak" ;;
    esac
    # Без терминала и без --config-source существующий конфиг не трогаем (только дописываем [mcu])
    if [[ $has_cfg -eq 1 && -z $OPT_CONFIG_SOURCE && $ASSUME_YES -eq 0 ]] && ! have_tty; then OPT_CONFIG_SOURCE=skip; fi
    pick_electronics "$cfg_root" "$has_cfg"
    el=$EL_NAME

    if [[ $EL_SRC == skip ]]; then
        printf '%s' "$blocks" >"$tmp/mcu_blocks.txt"
        merge_mcus_into_cfg "$PRINTER_CFG_DIR/printer.cfg" "$tmp/mcu_blocks.txt" "$([[ $DRY_RUN -eq 1 ]] && echo --dry)"
        stage_modules "$cfg_root"
        rm -rf "$tmp"
        return 0
    fi

    if [[ $EL_SRC == generate ]]; then
        drivers_wizard
        gen_custom_electronics "$cfg_root" "$tmp"
        el=$GEN_NAME; EL_NAME=$GEN_NAME
        src_dir=$tmp
    elif [[ $EL_SRC == user ]]; then src_dir=$cfg_root/user_configs; else src_dir=$cfg_root; fi
    [[ $EL_SRC == generate ]] || sync_head_names "$src_dir/$el"
    blocks=$(mcu_blocks)

    if [[ $DRY_RUN -eq 1 ]]; then
        if [[ $has_cfg -eq 1 ]]; then
            info "[dry-run] существующий конфиг: записал бы $el (источник: $EL_SRC) и заменил в printer.cfg только [mcu ...] и [include electronics_...]; printer.cfg и $el сохранились бы как *.bak-<дата>; printer_base.cfg, chamber_heater.cfg, postprocessing/ не тронул бы (докопировал только отсутствующие)"
        else
            info "[dry-run] чистая установка: записал бы в $PRINTER_CFG_DIR из main printer.cfg, printer_base.cfg, chamber_heater.cfg, postprocessing/ и $el (источник: $EL_SRC)"
            [[ $CFG_STATE != none ]] && info "[dry-run] прежние файлы сохранились бы как *.bak-<дата>"
        fi
        printf '%s\n' "$blocks"
        [[ $GEN_USED -eq 1 ]] && print_gen_warnings "$el"
        stage_modules "$cfg_root"
        rm -rf "$tmp"
        return 0
    fi

    mkdir -p "$PRINTER_CFG_DIR"
    stamp=$(date +%Y%m%d-%H%M%S)
    if [[ $has_cfg -eq 1 ]]; then
        for f in printer.cfg "$el"; do
            [[ -f $PRINTER_CFG_DIR/$f ]] && cp -p "$PRINTER_CFG_DIR/$f" "$PRINTER_CFG_DIR/$f.bak-$stamp"
        done
        info "Прежние printer.cfg и $el сохранены как *.bak-$stamp"
        # существующий конфиг: файлы пользователя не трогаем, докладываем только отсутствующие
        for f in printer_base.cfg chamber_heater.cfg; do
            [[ -f $cfg_root/$f && ! -f $PRINTER_CFG_DIR/$f ]] && cp "$cfg_root/$f" "$PRINTER_CFG_DIR/"
        done
        [[ -d $cfg_root/postprocessing && ! -d $PRINTER_CFG_DIR/postprocessing ]] && cp -r "$cfg_root/postprocessing" "$PRINTER_CFG_DIR/"
        cp "$src_dir/$el" "$PRINTER_CFG_DIR/"
    else
        for f in printer.cfg printer_base.cfg chamber_heater.cfg "$el"; do
            [[ -f $PRINTER_CFG_DIR/$f ]] && cp -p "$PRINTER_CFG_DIR/$f" "$PRINTER_CFG_DIR/$f.bak-$stamp"
        done
        [[ $CFG_STATE != none ]] && warn "прежние файлы сохранены как *.bak-$stamp"
        cp "$cfg_root/printer_base.cfg" "$PRINTER_CFG_DIR/"
        [[ -f $cfg_root/chamber_heater.cfg ]] && cp "$cfg_root/chamber_heater.cfg" "$PRINTER_CFG_DIR/"
        cp "$src_dir/$el" "$PRINTER_CFG_DIR/"
        [[ -d $cfg_root/postprocessing ]] && cp -r "$cfg_root/postprocessing" "$PRINTER_CFG_DIR/"
        cp "$cfg_root/printer.cfg" "$PRINTER_CFG_DIR/"
    fi
    printf '%s' "$blocks" >"$tmp/mcu_blocks.txt"
    # В готовый printer.cfg: заменить набор [mcu ...] и строку [include electronics_...]. SAVE_CONFIG и остальное не меняется.
    # Существующий printer.cfg пользователя берётся из каталога конфига, при чистой установке - из main (уже скопирован выше).
    python3 -I - "$PRINTER_CFG_DIR/printer.cfg" "$el" "$tmp/mcu_blocks.txt" <<'PYEND'
import sys, re
path, electronics, blocks_path = sys.argv[1:4]
text = open(path, encoding="utf-8").read().split("\n")
blocks = open(blocks_path, encoding="utf-8").read().rstrip("\n").split("\n")
hdr = re.compile(r"\s*(\[|#\*#)")
out, i, inserted, has_inc = [], 0, False, False
while i < len(text):
    line = text[i]
    if re.match(r"\s*\[mcu(\s+[^\]]+)?\]", line):
        # убрать секцию [mcu ...] целиком (до следующего заголовка или блока SAVE_CONFIG), вставить свои блоки на место первой
        if not inserted:
            out.extend(blocks + [""])
            inserted = True
        i += 1
        body = []
        while i < len(text) and not hdr.match(text[i]):
            body.append(text[i]); i += 1
        # комментарии прямо перед следующим заголовком относятся к нему, их оставляем
        keep = []
        while body and body[-1].lstrip().startswith("#"):
            keep.insert(0, body.pop())
        out.extend(keep)
        continue
    if re.match(r"\s*\[include\s+electronics_.*\.cfg\]", line):
        tail = line.split("]", 1)[1]
        line = "[include %s]%s" % (electronics, tail)
        has_inc = True
    out.append(line)
    i += 1
if not has_inc:
    for k, l in enumerate(out):
        if re.match(r"\s*\[include\s+printer_base\.cfg\]", l):
            out.insert(k + 1, "[include %s]" % electronics); break
if not inserted:
    out = blocks + [""] + out
open(path, "w", encoding="utf-8").write("\n".join(out))
PYEND
    stage_modules "$cfg_root"
    rm -rf "$tmp"
    ok "конфигурация записана в $PRINTER_CFG_DIR (electronics: $el, источник: $(case $EL_SRC in user) echo user_configs ;; generate) echo "сгенерирован" ;; *) echo "корень main" ;; esac))"
    if [[ $GEN_USED -eq 1 ]]; then
        print_gen_warnings "$el"
    elif [[ $HEADS == none ]]; then
        warn "в $el могут быть включены платы голов по CAN. Без них адаптируйте этот файл под вашу проводку (гайд, раздел «Конфигурация», п. 3)"
    fi
    report_pin_conflicts "$PRINTER_CFG_DIR/printer.cfg"
}

# ---------------------------------------------------------------- дополнительные модули

# Дополнительные модули: "файл|название". Файл лежит в корне vostok_configuration, подключается через [include].
CFG_MODULES=(
    "chamber_heater.cfg|Подогрев термокамеры (Smart Chamber Heater)"
)

# Повторяющиеся пины в конфиге: печатает предупреждения. Возврат 0 всегда.
report_pin_conflicts() { # printer.cfg
    local out
    [[ -f $1 && -f $INSTALL_DIR/tools/pin_conflicts.py ]] || return 0
    out=$(python3 -I "$INSTALL_DIR/tools/pin_conflicts.py" "$1" 2>/dev/null || true)
    [[ -n $out ]] || return 0
    warn "в конфиге есть пины, которые используются сразу в нескольких секциях (Klipper не запустится):"
    while IFS=$'\t' read -r _ pin where; do printf '  - %s: %s\n' "$pin" "$where" >&2; done <<<"$out"
}

# Модуль включён через [include] (активный/закомментированный) в printer.cfg: active|commented|none
module_state() { # printer.cfg файл
    if grep -Eq "^[[:space:]]*\[include[[:space:]]+$2\]" "$1"; then echo active
    elif grep -Eq "^[[:space:]]*#[[:space:]]*\[include[[:space:]]+$2\]" "$1"; then echo commented
    else echo none; fi
}

# Ответ на вопрос про модуль: 0 = подключать. OPT_MODULES: all|none|имена через запятую (без .cfg)
module_wanted() { # имя название файл
    local name=$1 label=$2 file=$3
    case ",$OPT_MODULES," in
        *,all,*|*,"$name",*) return 0 ;;
        *,none,*) return 1 ;;
    esac
    [[ -n $OPT_MODULES ]] && return 1
    [[ $ASSUME_YES -eq 1 ]] && return 1
    have_tty || return 1
    ask_yn "Подключить дополнительный модуль: $label ($file)?" n
}

# Добавляет [include файл] в printer.cfg: раскомментирует готовую строку, иначе ставит после include электроники
# (или перед блоком SAVE_CONFIG, или в конец).
module_add_include() { # printer.cfg файл
    local cfg=$1 file=$2
    if [[ $(module_state "$cfg" "$file") == commented ]]; then
        sed -i "s|^\([[:space:]]*\)#[[:space:]]*\(\[include[[:space:]]\+$file\]\)|\1\2|" "$cfg"
    elif grep -Eq '^[[:space:]]*\[include[[:space:]]+electronics_[^]]*\]' "$cfg"; then
        sed -i "0,/^[[:space:]]*\[include[[:space:]]\+electronics_[^]]*\].*/s||&\n[include $file]|" "$cfg"
    elif grep -q '^#\*# <' "$cfg"; then
        sed -i "0,/^#\*# </s||[include $file]\n\n&|" "$cfg"
    else
        printf '\n[include %s]\n' "$file" >>"$cfg"
    fi
}

# Спрашивает про каждый дополнительный модуль, проверяет пересечения пинов с вашей проводкой и подключает.
stage_modules() { # корень_конфигов
    local root=$1 cfg=$PRINTER_CFG_DIR/printer.cfg m file label name state src tmpcfg before after new bak=0
    if [[ $DRY_RUN -eq 1 && ! -f $cfg ]]; then info "[dry-run] после записи конфига спросил бы про дополнительные модули: ${CFG_MODULES[*]%%|*}"; return 0; fi
    [[ -f $cfg ]] || { info "printer.cfg нет, дополнительные модули не настраиваю"; return 0; }
    for m in "${CFG_MODULES[@]}"; do
        file=${m%%|*}; label=${m#*|}; name=${file%.cfg}
        state=$(module_state "$cfg" "$file")
        if [[ $state == active ]]; then info "Модуль $label: уже подключён ($file)"; continue; fi
        src=$PRINTER_CFG_DIR/$file
        [[ -f $src ]] || src=$root/$file
        [[ -f $src ]] || { warn "модуль $label: файл $file не найден (ни в $PRINTER_CFG_DIR, ни в $root)"; continue; }
        module_wanted "$name" "$label" "$file" || { info "Модуль $label: не подключаю (позже: --modules $name)"; continue; }
        # пересечения пинов: сравниваем конфиг с модулем и без него, интересуют только новые
        tmpcfg=$(mktemp -d)
        cp "$PRINTER_CFG_DIR"/*.cfg "$tmpcfg/" 2>/dev/null || true
        [[ -f $PRINTER_CFG_DIR/$file ]] || cp "$src" "$tmpcfg/$file"
        before=$(python3 -I "$INSTALL_DIR/tools/pin_conflicts.py" "$tmpcfg/printer.cfg" 2>/dev/null || true)
        module_add_include "$tmpcfg/printer.cfg" "$file"
        after=$(python3 -I "$INSTALL_DIR/tools/pin_conflicts.py" "$tmpcfg/printer.cfg" 2>/dev/null || true)
        rm -rf "$tmpcfg"
        new=$(comm -13 <(sort <<<"$before") <(sort <<<"$after") | grep . || true)
        if [[ -n $new ]]; then
            warn "модуль $label использует пины, уже занятые вашей проводкой:"
            while IFS=$'\t' read -r _ pin where; do printf '  - %s: %s\n' "$pin" "$where" >&2; done <<<"$new"
            if [[ $ASSUME_YES -eq 1 ]] || ! have_tty; then
                warn "модуль $label не подключён из-за пересечения пинов (измените пины и подключите позже: --modules $name)"; continue
            fi
            ask_yn "Всё равно подключить $file (пины придётся поменять вручную)?" n || { info "Модуль $label не подключён"; continue; }
        fi
        if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] подключил бы модуль $label ($file)"; continue; fi
        if [[ $bak -eq 0 ]]; then cp -p "$cfg" "$cfg.bak-$(date +%Y%m%d-%H%M%S)"; bak=1; fi
        [[ -f $PRINTER_CFG_DIR/$file ]] || cp "$src" "$PRINTER_CFG_DIR/$file"
        module_add_include "$cfg" "$file"
        ok "Модуль $label подключён: [include $file] в printer.cfg"
    done
    return 0
}
