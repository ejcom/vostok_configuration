#!/usr/bin/env bash
# Установка темы K3D VOSTOK в KlipperScreen: палитра k3d.tech/vostok, шрифт Tektur, знак K3D на заставке.
#
# Что делает (повторный запуск безопасен):
#   1. собирает <KlipperScreen>/styles/vostok/: все иконки из material-dark (набор должен быть полным),
#      поверх них наш klipper.svg, style.css и style.conf из klipperscreen-theme/;
#   2. ставит шрифт Tektur в ~/.local/share/fonts (без sudo) и обновляет кэш шрифтов;
#   3. включает тему: theme = vostok в [main] файла <printer_data>/config/KlipperScreen.conf.
#   Для применения перезапустите KlipperScreen (или выберите тему в Настройки -> Тема).
#
# Запускать от обычного пользователя (не root), от того же, под которым работает KlipperScreen.

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
VOSTOK_INSTALLER_VERSION=$(head -n1 "$SCRIPT_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || true)
VOSTOK_INSTALLER_VERSION=${VOSTOK_INSTALLER_VERSION:-неизвестна}
THEME_SRC=$SCRIPT_DIR/klipperscreen-theme
THEME_MARK="VOSTOK-THEME"          # маркер в первой строке нашего style.css
THEME_ID="vostok"
THEME_NAME="K3D VOSTOK"
BASE_THEME="material-dark"
FONT_GLOB="Tektur*.ttf"

PRINTER_DATA=${PRINTER_DATA:-$HOME/printer_data}
KS_DIR=${KS_DIR:-$HOME/KlipperScreen}
FONT_DIR=${FONT_DIR:-$HOME/.local/share/fonts}
ACTIVATE=1
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
Использование: install_klipperscreen_theme.sh [опции]

  --ks-dir DIR        каталог KlipperScreen (по умолчанию ~/KlipperScreen)
  --printer-data DIR  каталог printer_data (по умолчанию ~/printer_data)
  --no-activate       только установить тему и шрифт, в KlipperScreen.conf не писать
  --force             перезаписать чужой каталог styles/vostok и сменить уже выбранную другую тему
  --uninstall         удалить тему и шрифт, вернуть тему material-dark
  --dry-run           ничего не менять, только показать план
  -y, --yes           не задавать вопросов
  -V, --version       показать версию установщика
  -h, --help          эта справка

Переменные окружения: PRINTER_DATA, KS_DIR, FONT_DIR.
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
        --ks-dir) [[ $# -ge 2 ]] || die "--ks-dir требует аргумент"; KS_DIR=$2; shift ;;
        --printer-data) [[ $# -ge 2 ]] || die "--printer-data требует аргумент"; PRINTER_DATA=$2; shift ;;
        --no-activate) ACTIVATE=0 ;;
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

STYLES_DIR=$KS_DIR/styles
DST=$STYLES_DIR/$THEME_ID
KS_CONF=$PRINTER_DATA/config/KlipperScreen.conf

# py <код> [аргументы]: python3 -I
py() { python3 -I -c "$@"; }

# Каталог темы создан нами (маркер в первой строке style.css)
is_ours() { [[ -f $DST/style.css ]] && head -n1 "$DST/style.css" | grep -q "$THEME_MARK"; }

# Правка KlipperScreen.conf: set|reset. Значение theme сначала ищется в машинном блоке (#~#),
# он перекрывает пользовательскую часть; иначе правится/добавляется [main] в пользовательской части.
# Печатает "текущая_тема|результат". Резервная копия + атомарная запись.
edit_ks_conf() {
    py 'import sys,os,re,shutil,time
mode,path,theme,base=sys.argv[1:5]
MARK="#~# --- Do not edit below this line. This section is auto generated --- #~#"
lines=open(path,encoding="utf-8").read().split("\n") if os.path.exists(path) else []
if lines and lines[-1]=="": lines.pop()
try: cut=lines.index(MARK)
except ValueError: cut=len(lines)
user,saved=lines[:cut],lines[cut:]
want=theme if mode=="set" else base
opt=re.compile(r"^(#~#\s*)?theme\s*[=:]")
def find(block,prefix):
    sec=None
    for i,l in enumerate(block):
        s=l[len(prefix):].strip() if prefix and l.startswith(prefix) else l.strip()
        m=re.match(r"^\[(.+)\]$",s)
        if m: sec=m.group(1); continue
        if sec=="main" and re.match(r"^theme\s*[=:]",s): return i,sec
    return None,sec
def val(l,prefix): return l[len(prefix):].split("=",1)[-1].strip() if "=" in l else ""
cur=""
si,_=find(saved,"#~# ")
ui,_=find(user,"")
if si is not None: cur=val(saved[si],"#~# ")
elif ui is not None: cur=val(user[ui],"")
print_cur=cur or base
if cur==want: print(print_cur+"|без изменений"); sys.exit(0)
if mode=="reset" and cur!=theme: print(print_cur+"|без изменений"); sys.exit(0)
if os.path.exists(path): shutil.copy2(path,path+".bak-"+time.strftime("%Y%m%d-%H%M%S"))
if si is not None: saved[si]="#~# theme = "+want
if ui is not None: user[ui]="theme = "+want
if si is None and ui is None:
    mi=next((i for i,l in enumerate(user) if l.strip()=="[main]"),None)
    if mi is None: user=["[main]","theme = "+want,""]+user
    else: user.insert(mi+1,"theme = "+want)
tmp=path+".tmp"
with open(tmp,"w",encoding="utf-8") as f: f.write("\n".join(user+saved)+"\n")
os.replace(tmp,path)
print(print_cur+"|обновлён")' "$1" "$KS_CONF" "$THEME_ID" "$BASE_THEME"
}

# Значение theme (машинный блок приоритетнее), пусто если не задано
current_theme() {
    py 'import sys,re,os
p=sys.argv[1]
if not os.path.exists(p): sys.exit(0)
t=""; sec=None; saved=False
for l in open(p,encoding="utf-8"):
    l=l.rstrip("\n")
    if l.startswith("#~# ---"): saved=True; continue
    if l.startswith("#~#"): l=l[3:].strip()
    elif saved: continue
    s=l.strip(); m=re.match(r"^\[(.+)\]$",s)
    if m: sec=m.group(1); continue
    m=re.match(r"^theme\s*[=:]\s*(\S+)",s)
    if sec=="main" and m: t=m.group(1)
print(t)' "$KS_CONF"
}

# ------------------------------------------------------------------ удаление

if [[ $UNINSTALL -eq 1 ]]; then
    step "Удаление темы $THEME_NAME"
    if [[ -d $DST ]]; then
        if is_ours; then
            [[ $DRY_RUN -eq 1 ]] && info "[dry-run] rm -r $DST" || { rm -rf "$DST"; ok "удалён $DST"; }
        else
            warn "$DST создан не нами, не удаляю"
        fi
    fi
    if [[ -f $KS_CONF ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] theme = $BASE_THEME в $KS_CONF, если выбран $THEME_ID"
        else r=$(edit_ks_conf reset); info "KlipperScreen.conf: ${r#*|}"; fi
    fi
    for f in "$FONT_DIR"/$FONT_GLOB; do
        [[ -f $f ]] || continue
        [[ $DRY_RUN -eq 1 ]] && info "[dry-run] rm $f" || { rm -f "$f"; ok "удалён шрифт $(basename "$f")"; }
    done
    if [[ $DRY_RUN -eq 0 ]] && command -v fc-cache >/dev/null; then fc-cache -f "$FONT_DIR" >/dev/null 2>&1 || true; fi
    info "Перезапустите KlipperScreen: sudo systemctl restart KlipperScreen"
    exit 0
fi

# ------------------------------------------------------------------ проверки

step "Проверки"
for f in style.css style.conf images/klipper.svg; do
    [[ -f $THEME_SRC/$f ]] || die "нет $THEME_SRC/$f"
done
compgen -G "$THEME_SRC/fonts/$FONT_GLOB" >/dev/null || die "нет шрифта Tektur в $THEME_SRC/fonts"
[[ -d $STYLES_DIR/$BASE_THEME/images ]] || die "нет $STYLES_DIR/$BASE_THEME: KlipperScreen не установлен? (--ks-dir)"
command -v fc-cache >/dev/null || warn "нет fc-cache (fontconfig): шрифт Tektur может не подхватиться"
if [[ -d $DST ]] && ! is_ours && [[ $FORCE -eq 0 ]]; then
    die "$DST уже есть и создан не нами (используйте --force, чтобы перезаписать)"
fi
if [[ $ACTIVATE -eq 1 && ! -d $PRINTER_DATA/config ]]; then
    die "нет каталога $PRINTER_DATA/config (--printer-data) или запустите с --no-activate"
fi
ok "проверки пройдены"

# --------------------------------------------------------------------- тема

step "Тема в $DST"
if [[ $DRY_RUN -eq 1 ]]; then
    info "[dry-run] собрать $DST: иконки из $BASE_THEME + klipper.svg, style.css, style.conf"
else
    rm -rf "$DST.new"
    mkdir -p "$DST.new/images"
    cp -p "$STYLES_DIR/$BASE_THEME"/images/* "$DST.new/images/"
    cp -p "$THEME_SRC"/images/* "$DST.new/images/"
    install -m 0644 "$THEME_SRC/style.css" "$DST.new/style.css"
    install -m 0644 "$THEME_SRC/style.conf" "$DST.new/style.conf"
    rm -rf "$DST"
    mv "$DST.new" "$DST"
    ok "тема: $DST ($(find "$DST/images" -type f | wc -l) иконок)"
fi

step "Шрифт Tektur в $FONT_DIR"
if [[ $DRY_RUN -eq 1 ]]; then
    info "[dry-run] скопировать $THEME_SRC/fonts/$FONT_GLOB и OFL.txt, fc-cache -f"
else
    mkdir -p "$FONT_DIR"
    install -m 0644 "$THEME_SRC"/fonts/$FONT_GLOB "$FONT_DIR/"
    [[ ! -f $THEME_SRC/fonts/OFL.txt ]] || install -m 0644 "$THEME_SRC/fonts/OFL.txt" "$FONT_DIR/Tektur-OFL.txt"
    if command -v fc-cache >/dev/null; then fc-cache -f "$FONT_DIR" >/dev/null 2>&1 || warn "fc-cache завершился с ошибкой"; fi
    ok "шрифт установлен"
fi

# ----------------------------------------------------------------- активация

if [[ $ACTIVATE -eq 1 ]]; then
    step "Включение темы"
    cur=$(current_theme)
    if [[ -n $cur && $cur != "$THEME_ID" && $cur != "$BASE_THEME" && $FORCE -eq 0 ]]; then
        # с -y чужую тему без --force не меняем: установщик всегда зовёт скрипт с -y
        { [[ $ASSUME_YES -eq 0 ]] && confirm "В KlipperScreen выбрана другая тема ($cur). Заменить на $THEME_NAME?"; } || {
            warn "тему не меняю; выберите \"$THEME_ID\" в Настройки -> Тема"
            ACTIVATE=0
        }
    fi
fi
if [[ $ACTIVATE -eq 1 ]]; then
    if [[ $DRY_RUN -eq 1 ]]; then info "[dry-run] theme = $THEME_ID в $KS_CONF"
    else r=$(edit_ks_conf set); ok "KlipperScreen.conf: ${r#*|} (была тема: ${r%%|*})"; fi
fi

step "Готово"
info "Перезапустите KlipperScreen: sudo systemctl restart KlipperScreen"
info "(или выберите тему \"$THEME_ID\" в Настройки -> Тема — применяется сразу)."
info "Удалить: $0 --uninstall"
