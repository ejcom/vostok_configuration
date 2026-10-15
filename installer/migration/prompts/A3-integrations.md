Ты агент «integrations» проекта переноса установщика VOSTOK с bash на Python (репозиторий ~/vostok_configuration, каталог installer/).

Сначала прочитай (в этом порядке): migration/STATUS.md, migration/PLAN.md (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила для всех агентов», «Definition of Done»), migration/CONTRACTS.md, migration/MAP.md, ../AGENTS.md.

Рабочая ветка: py/integrations от py-migration (создай через git worktree; основной клон не трогай). Задача: Перенести install_fluidd_button.sh, install_fluidd_theme.sh, install_klipperscreen_theme.sh в vostok/integrations.py + обёртки.
Исходники bash/Python: install_fluidd_button.sh, install_fluidd_theme.sh, install_klipperscreen_theme.sh, mcu-update.service.in
Владеешь файлами только: installer/vostok/integrations.py, installer/install_fluidd_button.sh, installer/install_fluidd_theme.sh, installer/install_klipperscreen_theme.sh, installer/tests/test_integrations.py
Особенности: Сохранить: --uninstall, --dry-run, --force, --no-activate, --logo-copy, --with-macro, --flash-args, маркер VOSTOK-THEME, бэкапы *.bak-<дата>, атомарную запись, поведение -y с чужой темой (не заменять без --force), moonraker.asvc, sudoers через visudo, drop-in After=. systemd/sudo в тестах через Runner-заглушку.

Правила: только stdlib, Python 3.8; сообщения и комментарии на русском; поведение 1:1 (флаги, коды возврата, тексты, форматы файлов); никаких реальных прошивок, sudo и записи в ~/printer_data, тесты на копиях в scratchpad; маленькие коммиты на русском в своей ветке, без push. Колонку «Python» и статус в migration/MAP.md для своих функций заполни в последнем коммите.
Контрольные точки: коммит после каждого перенесённого блока из MAP.md; если останавливаешься не закончив, допиши в migration/STATUS.md (раздел «Решения / продолжить с») что сделано и с чего продолжить.
Итог: migration/reports/integrations.md — что перенесено (функция bash → Python), намеренные отличия, результаты `python3 -m unittest discover installer/tests` и golden-diff, открытые вопросы.
