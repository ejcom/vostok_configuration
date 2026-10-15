Ты агент «cleanup-docs» проекта переноса установщика VOSTOK с bash на Python (репозиторий ~/vostok_configuration, каталог installer/).

Сначала прочитай (в этом порядке): migration/STATUS.md, migration/PLAN.md (разделы «Целевая архитектура», «Механизм запуска не меняется», «Контракты», «Общие правила для всех агентов», «Definition of Done»), migration/CONTRACTS.md, migration/MAP.md, ../AGENTS.md.

Рабочая ветка: py/cleanup-docs от py-migration (создай через git worktree; основной клон не трогай). Задача: Уборка: tools/gen_configs.sh → gen_configs.py, удаление lib/*.sh и старых tools/*.py (после grep на использование), обновление документации.
Исходники bash/Python: tools/gen_configs.sh, docs/*, CONFIGURATOR*.md, CHANGELOG*.md, VERSION, ../AGENTS.md, migration/
Владеешь файлами только: installer/tools/gen_configs.py, удаление lib/, tools/{gen_electronics,mcu_merge,pin_conflicts,can_uuid}.py, installer/docs/*, CONFIGURATOR*.md, CHANGELOG*.md, VERSION, ../AGENTS.md
Особенности: Публичные команды в документации не меняются; если что-то упоминает lib/*.sh или tools/*.py — обновить. VERSION → 1.4, CHANGELOG ru/en. gen_configs.py: --force/--board/--check/--build идентичны. migration/ удалить последним коммитом ТОЛЬКО по команде оркестратора.

Правила: только stdlib, Python 3.8; сообщения и комментарии на русском; поведение 1:1 (флаги, коды возврата, тексты, форматы файлов); никаких реальных прошивок, sudo и записи в ~/printer_data, тесты на копиях в scratchpad; маленькие коммиты на русском в своей ветке, без push. Колонку «Python» и статус в migration/MAP.md для своих функций заполни в последнем коммите.
Контрольные точки: коммит после каждого перенесённого блока из MAP.md; если останавливаешься не закончив, допиши в migration/STATUS.md (раздел «Решения / продолжить с») что сделано и с чего продолжить.
Итог: migration/reports/cleanup-docs.md — что перенесено (функция bash → Python), намеренные отличия, результаты `python3 -m unittest discover installer/tests` и golden-diff, открытые вопросы.
