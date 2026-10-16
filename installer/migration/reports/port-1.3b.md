# S6: перенос 1.3b (168b26f) в Python

Ветка `py/port-1.3b` от `py-migration`. VERSION не менялась (1.4), изменения описаны в CHANGELOG как часть 1.4.

## Сделано
- `boards/`: ebb42 (LABEL «BTT EBB42/EBB36», ALIASES=ebb36, VERIFIED=yes, NOTE), h36-v1.3, h36-v2, manta-m8p-v2.0 - файлы взяты из 168b26f как есть.
- `Registry.rank(id)` в `vostok/boards.py`: 0 - `resolve("h723")`, 1 - VERIFIED=yes, 2 - остальные.
- `rank_main_boards` (configurator.py) - единственная точка выбора: ключи rank, чип по убыванию, id; её используют и `main_candidates`, и `guess_main_board`. Порядок как в bash (`sort -k1,1 -k2,2r -k3,3`; в guess_main_board у bash чип одинаков, остаётся rank, затем id). `install.py` собственной логики выбора не содержит (только предупреждение о VERIFIED).
- Docs: hardware, tested, CONFIGURATOR, README (ru/en) - патч 168b26f, конфликт в tested решён с `gen_configs.py`; ссылок на удалённые файлы нет. CHANGELOG ru/en: три пункта в разделе 1.4.
- Тесты: `test_rank`, `test_ebb_alias_and_verified` (test_boards); порядок «плата гайда, проверенные, остальные», rank не убывает, плата гайда первая при любом порядке входа (test_configurator); обновлены тексты с «BTT EBB42/EBB36» (меню голов, план установки).

## Golden
Пересняты только затронутые группы (`--update` по именам 27 расходящихся кейсов; харнесс пишет группы файлом целиком, остальные кейсы в группах не изменились). Дифф до пересъёмки: `migration/reports/port-1.3b-golden-diffs.txt` (852 строки). Все различия сводятся к:
1. `boards/list_boards`: `yes` вместо `no` у h36-v1.3, h36-v2, manta-m8p-v2.0; ebb42 - `yes`, подпись «BTT EBB42/EBB36 [head] (ebb36)» (VERIFIED/LABEL/ALIASES из 168b26f).
2. `install_matrix/*__ebb42`, `configure/*ebb42*` (24 кейса): везде «BTT EBB42» -> «BTT EBB42/EBB36» (LABEL).
3. `install_matrix/*manta-m8p-v2.0__{none,v1.3,v2}`: исчезла строка «ВНИМАНИЕ: BTT Manta M8P v2.0 не проверена на железе» (VERIFIED=yes).
Порядок предложения плат golden-кейсы не затронули (выбор в них задаётся явно).

Сверка с bash: 168b26f распакован `git archive` в песочницу, туда скопирован текущий harness, те же 27 кейсов пересняты на bash-скриптах; `boards.txt` и `configure.txt.gz` совпали побайтно, `install_matrix` - построчно, кроме 20 строк `fatal: cannot change to '<CASE>/home/klipper'` (шум git вне репозитория в песочнице, к 1.3b не относится).

## Итог
unittest: 412 тестов, OK (4 skip). `tests/run_golden.sh`: 231 эталон, расхождений 0. Ничего не пушилось, add-installer и docs-verified-boards не менялись, ~/printer_data и железо не трогались.
