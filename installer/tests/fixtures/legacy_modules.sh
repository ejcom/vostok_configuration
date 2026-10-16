# Эталон: функции lib/vostok_config.sh 1.3a (удалён при переносе на Python), для сверки тестов cfgfile.
module_state() { # printer.cfg файл
    if grep -Eq "^[[:space:]]*\[include[[:space:]]+$2\]" "$1"; then echo active
    elif grep -Eq "^[[:space:]]*#[[:space:]]*\[include[[:space:]]+$2\]" "$1"; then echo commented
    else echo none; fi
}

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
