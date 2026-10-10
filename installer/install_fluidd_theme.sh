#!/usr/bin/env bash
# Установка темы K3D VOSTOK в Fluidd: пресет темы (цвет, логотип) и стили шрифта/фона.
#
# Что делает (повторный запуск безопасен):
#   1. кладёт logo_vostok.svg и custom.css в <printer_data>/config/.fluidd-theme/
#      (Fluidd сам подхватывает custom.css оттуда, каталог переживает обновления Fluidd);
#   2. добавляет пресет «K3D VOSTOK» в <fluidd>/config.json (он в persistent_files Moonraker);
#   3. включает тему: пишет uiSettings.theme в базу Moonraker (namespace fluidd).
#   Для применения обновите вкладку браузера (Ctrl+F5).
#
# Запускать от обычного пользователя (не root).

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
VOSTOK_INSTALLER_VERSION=$(head -n1 "$SCRIPT_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || true)
VOSTOK_INSTALLER_VERSION=${VOSTOK_INSTALLER_VERSION:-неизвестна}
THEME_SRC=$SCRIPT_DIR/fluidd-theme
THEME_MARK="VOSTOK-THEME"          # маркер в первой строке нашего custom.css
THEME_NAME="K3D VOSTOK"

PRINTER_DATA=${PRINTER_DATA:-$HOME/printer_data}
FLUIDD_DIR=${FLUIDD_DIR:-$HOME/fluidd}
MOONRAKER_URL=${MOONRAKER_URL:-http://localhost:7125}
ACTIVATE=1
LOGO_COPY=0
FORCE=0
UNINSTALL=0
DRY_RUN=0
ASSUME_YES=0

if [[ -t 1 ]]; then
    C_RED=$'\033[91m'; C_GREEN=$'\033[92m'; C_YELLOW=$'\033[93m'; C_OFF=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_OFF=""
fi
info() { printf '%s\n' "$*"; }
ok()   { printf '%s%s%s\n' "$C_GREEN" "$*" "$C_OFF"; }
warn() { printf '%sВНИМАНИЕ: %s%s\n' "$C_YELLOW" "$*" "$C_OFF" >&2; }
die()  { printf '%sОШИБКА: %s%s\n' "$C_RED" "$*" "$C_OFF" >&2; exit 1; }
step() { printf '\n== %s ==\n' "$*"; }

usage() {
    cat <<'EOF2'
Использование: install_fluidd_theme.sh [опции]

  --printer-data DIR  каталог printer_data (по умолчанию ~/printer_data)
  --fluidd-dir DIR    каталог Fluidd (по умолчанию ~/fluidd)
  --no-activate       только добавить пресет и файлы, тему не включать
  --logo-copy         положить логотип ещё и в каталог Fluidd и брать его оттуда (нужно, если
                      Moonraker требует авторизацию и логотип из config не грузится;
                      после обновления Fluidd запустите скрипт снова)
  --force             перезаписать изменённый custom.css и сменить уже выбранную другую тему
  --uninstall         удалить пресет и файлы темы, вернуть тему Fluidd по умолчанию
  --dry-run           ничего не менять, только показать план
  -y, --yes           не задавать вопросов
  -V, --version       показать версию установщика
  -h, --help          эта справка

Переменные окружения: PRINTER_DATA, FLUIDD_DIR, MOONRAKER_URL.
EOF2
}

confirm() {
    [[ $ASSUME_YES -eq 1 ]] && return 0
    [[ -r /dev/tty ]] || return 1
    local answer
    read -r -p "$1 [y/N] " answer </dev/tty
    [[ $answer == [yYдД]* ]]
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --printer-data) [[ $# -ge 2 ]] || die "--printer-data требует аргумент"; PRINTER_DATA=$2; shift ;;
        --fluidd-dir) [[ $# -ge 2 ]] || die "--fluidd-dir требует аргумент"; FLUIDD_DIR=$2; shift ;;
        --no-activate) ACTIVATE=0 ;;
        --logo-copy) LOGO_COPY=1 ;;
        --force) FORCE=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -y|--yes) ASSUME_YES=1 ;;
        -V|--version) echo "VOSTOK installer $VOSTOK_INSTALLER_VERSION"; exit 0 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "неизвестная опция: $1" ;;
    esac
    shift
done

[[ $EUID -ne 0 ]] || die "не запускайте от root: файлы должны принадлежать обычному пользователю"
command -v python3 >/dev/null || die "нет python3"
command -v curl >/dev/null || die "нет curl"

THEME_DIR=$PRINTER_DATA/config/.fluidd-theme
FLUIDD_CFG=$FLUIDD_DIR/config.json
LOGO_NAME=logo_vostok.svg
LOGO_SRC_CONFIG=server/files/config/.fluidd-theme/$LOGO_NAME
if [[ $LOGO_COPY -eq 1 ]]; then LOGO_SRC=$LOGO_NAME; else LOGO_SRC=$LOGO_SRC_CONFIG; fi

# py <код> [аргументы]: python3 -I, JSON-операции без jq
py() { python3 -I -c "$@"; }

# Значение uiSettings.theme из базы Moonraker (пусто, если нет). Код возврата 0 всегда.
db_get_theme() {
    curl -sf --max-time 5 "$MOONRAKER_URL/server/database/item?namespace=fluidd&key=uiSettings.theme" 2>/dev/null \
        | py 'import sys,json
try: print(json.dumps(json.load(sys.stdin)["result"]["value"]))
except Exception: pass' || true
}

# Путь к логотипу активной темы (пусто, если тема не задана)
db_theme_logo() {
    local t; t=$(db_get_theme)
    [[ -n $t ]] || return 0
    py 'import sys,json
print((json.loads(sys.argv[1]).get("logo") or {}).get("src",""))' "$t"
}

# Логотип относится к нам, если называется logo_vostok.svg
is_ours() { [[ $1 == *"$LOGO_NAME" ]]; }

# Правка config.json: add|remove. Резервная копия + атомарная запись.
edit_fluidd_cfg() {
    local mode=$1 preset=$2
    py 'import sys,json,os,shutil,time
mode,path,preset=sys.argv[1],sys.argv[2],json.loads(sys.argv[3])
with open(path,encoding="utf-8") as f: cfg=json.load(f)
lst=cfg.setdefault("themePresets",[])
rest=[p for p in lst if p.get("name")!=preset["name"]]
new=rest+[preset] if mode=="add" else rest
if mode=="add" and lst==new: print("без изменений"); sys.exit(0)
if mode=="remove" and len(rest)==len(lst): print("без изменений"); sys.exit(0)
shutil.copy2(path,path+".bak-"+time.strftime("%Y%m%d-%H%M%S"))
cfg["themePresets"]=new
tmp=path+".tmp"
with open(tmp,"w",encoding="utf-8") as f: json.dump(cfg,f,ensure_ascii=False,indent=2); f.write("\n")
os.replace(tmp,path)
print("обновлён")' "$mode" "$FLUIDD_CFG" "$preset"
}

preset_json() {
    py 'import sys,json
p=json.load(open(sys.argv[1],encoding="utf-8")); p["logo"]["src"]=sys.argv[2]
print(json.dumps(p,ensure_ascii=False))' "$THEME_SRC/preset.json" "$LOGO_SRC"
}

# ------------------------------------------------------------------ удаление

if [[ $UNINSTALL -eq 1 ]]; then
    step "Удаление темы $THEME_NAME"
    [[ -f $FLUIDD_CFG ]] && {
        if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] убрать пресет из $FLUIDD_CFG"
        else info "config.json: $(edit_fluidd_cfg remove "$(py 'import json;print(json.dumps({"name":"'"$THEME_NAME"'"}))')")"; fi
    }
    cur=$(db_theme_logo)
    if [[ -n $cur ]] && is_ours "$cur"; then
        if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] DELETE uiSettings.theme (вернуть тему по умолчанию)"
        else
            curl -sf --max-time 10 -X DELETE "$MOONRAKER_URL/server/database/item?namespace=fluidd&key=uiSettings.theme" >/dev/null \
                && ok "активная тема сброшена на стандартную" || warn "не удалось сбросить тему, выберите другую в Настройки -> Тема"
        fi
    fi
    if [[ -f $THEME_DIR/custom.css ]] && head -n1 "$THEME_DIR/custom.css" | grep -q "$THEME_MARK"; then
        [[ $DRY_RUN -eq 1 ]] && info "[dry-run] rm $THEME_DIR/custom.css" || { rm -f "$THEME_DIR/custom.css"; ok "удалён custom.css"; }
    fi
    for f in "$LOGO_NAME" background.png; do
        [[ -f $THEME_DIR/$f ]] || continue
        [[ $DRY_RUN -eq 1 ]] && info "[dry-run] rm $THEME_DIR/$f" || { rm -f "$THEME_DIR/$f"; ok "удалён $f"; }
    done
    [[ $DRY_RUN -eq 1 ]] || rmdir --ignore-fail-on-non-empty "$THEME_DIR" 2>/dev/null || true
    [[ ! -f $FLUIDD_DIR/$LOGO_NAME ]] || { [[ $DRY_RUN -eq 1 ]] && info "[dry-run] rm $FLUIDD_DIR/$LOGO_NAME" || rm -f "$FLUIDD_DIR/$LOGO_NAME"; }
    info "Обновите вкладку браузера (Ctrl+F5)."
    exit 0
fi

# ------------------------------------------------------------------ проверки

step "Проверки"
[[ -f $THEME_SRC/$LOGO_NAME && -f $THEME_SRC/custom.css && -f $THEME_SRC/preset.json ]] \
    || die "нет файлов темы в $THEME_SRC"
[[ -f $FLUIDD_CFG ]] || die "нет $FLUIDD_CFG: Fluidd не установлен? (--fluidd-dir)"
py 'import json,sys; json.load(open(sys.argv[1],encoding="utf-8"))' "$FLUIDD_CFG" 2>/dev/null \
    || die "$FLUIDD_CFG не разобрать как JSON"
[[ -d $PRINTER_DATA/config ]] || die "нет каталога $PRINTER_DATA/config (--printer-data)"
if [[ $ACTIVATE -eq 1 ]]; then
    curl -sf --max-time 5 "$MOONRAKER_URL/server/info" >/dev/null 2>&1 \
        || die "Moonraker недоступен ($MOONRAKER_URL), либо запустите с --no-activate"
fi
ok "проверки пройдены"

# --------------------------------------------------------------------- файлы

step "Файлы темы в $THEME_DIR"
if [[ $DRY_RUN -eq 1 ]]; then
    info "[dry-run] скопировать $LOGO_NAME и custom.css в $THEME_DIR"
else
    mkdir -p "$THEME_DIR"
    install -m 0644 "$THEME_SRC/$LOGO_NAME" "$THEME_DIR/$LOGO_NAME"
    ok "логотип: $THEME_DIR/$LOGO_NAME"
    dst=$THEME_DIR/custom.css
    if [[ ! -f $dst ]] || cmp -s "$THEME_SRC/custom.css" "$dst" || head -n1 "$dst" | grep -q "$THEME_MARK" || [[ $FORCE -eq 1 ]]; then
        # файл свой (или совпадает, или перезапись разрешена): при --force сохраняем чужую версию
        if [[ -f $dst ]] && ! head -n1 "$dst" | grep -q "$THEME_MARK"; then cp -p "$dst" "$dst.bak-$(date +%Y%m%d-%H%M%S)"; fi
        install -m 0644 "$THEME_SRC/custom.css" "$dst"
        ok "стили: $dst"
    else
        warn "$dst уже есть и создан не нами, не перезаписываю (добавьте стили вручную из $THEME_SRC/custom.css или запустите с --force)"
    fi
    if [[ $LOGO_COPY -eq 1 ]]; then
        install -m 0644 "$THEME_SRC/$LOGO_NAME" "$FLUIDD_DIR/$LOGO_NAME"
        ok "логотип скопирован в $FLUIDD_DIR (после обновления Fluidd запустите скрипт ещё раз)"
    fi
fi

step "Пресет в $FLUIDD_CFG"
if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] добавить пресет \"$THEME_NAME\" (logo.src=$LOGO_SRC)"
else info "$(edit_fluidd_cfg add "$(preset_json)")"; fi

# ----------------------------------------------------------------- активация

if [[ $ACTIVATE -eq 1 ]]; then
    step "Включение темы"
    cur=$(db_theme_logo)
    if [[ -n $cur ]] && ! is_ours "$cur" && [[ $FORCE -eq 0 ]]; then
        if confirm "В Fluidd уже выбрана другая тема ($cur). Заменить на $THEME_NAME?"; then :; else
            warn "тему не меняю; выберите \"$THEME_NAME\" в Настройки -> Тема"
            ACTIVATE=0
        fi
    fi
fi
if [[ $ACTIVATE -eq 1 ]]; then
    value=$(py 'import sys,json
p=json.load(open(sys.argv[1],encoding="utf-8"))
print(json.dumps({"namespace":"fluidd","key":"uiSettings.theme","value":{"color":p["color"],"isDark":p["isDark"],"logo":{"src":sys.argv[2]},"backgroundLogo":True}}))' \
        "$THEME_SRC/preset.json" "$LOGO_SRC")
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] POST $MOONRAKER_URL/server/database/item $value"
    else
        curl -sf --max-time 10 -X POST -H 'Content-Type: application/json' -d "$value" \
            "$MOONRAKER_URL/server/database/item" >/dev/null \
            || die "не удалось записать тему в базу Moonraker"
        ok "тема включена"
    fi
fi

step "Готово"
info "Обновите вкладку Fluidd (Ctrl+F5). Пресет «$THEME_NAME» также доступен в Настройки -> Тема."
info "Удалить: $0 --uninstall"
