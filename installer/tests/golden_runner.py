#!/usr/bin/env python3
"""Golden-прогон: запускает старые/новые скрипты установщика в песочнице и сравнивает с tests/golden.

Использование (через run_golden.sh):
  run_golden.sh                      сравнить все эталоны (код 1 - есть расхождения, 2 - хост не подходит)
  run_golden.sh --filter ШАБЛОН      только эталоны, имя которых подходит под fnmatch (можно повторять)
  run_golden.sh --list               показать имена эталонов
  run_golden.sh --show ИМЯ           показать diff «эталон -> сейчас» для эталона/шаблона (--full: весь вывод)
  run_golden.sh --update [ШАБЛОН]    ПЕРЕСНЯТЬ эталоны (все или подходящие). Только по явному флагу
  опции: -j N (потоков, по умолчанию 4), --keep (не удалять песочницу), -v
"""
import argparse
import concurrent.futures
import difflib
import fnmatch
import gzip
import io
import os
import shutil
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from golden_lib import GOLDEN_DIR, Ctx, Sandbox   # noqa: E402
import golden_cases                                # noqa: E402

MARK = "@@@@ CASE "
GZ_THRESHOLD = 150 * 1024        # группа больше порога хранится в .txt.gz (mtime=0 - детерминированно)


# ----------------------------------------------------------------------------- хранилище эталонов

def _group_paths(group):
    return (os.path.join(GOLDEN_DIR, group + ".txt"), os.path.join(GOLDEN_DIR, group + ".txt.gz"))


def parse_group(text):
    res, cur, buf = {}, None, []
    for line in text.split("\n"):
        if line.startswith(MARK):
            if cur is not None:
                res[cur] = "\n".join(buf) + "\n"
            cur, buf = line[len(MARK):], []
        else:
            buf.append(line)
    if cur is not None:
        res[cur] = "\n".join(buf)
    return res


def load_group(group):
    """{имя: текст} или None, если файла нет."""
    for p in _group_paths(group):
        if os.path.exists(p):
            with open(p, "rb") as f:
                raw = f.read()
            if p.endswith(".gz"):
                raw = gzip.decompress(raw)
            return parse_group(raw.decode("utf-8"))
    return None


def norm_block(t):
    """Блок в хранилище всегда оканчивается переводом строки; сравниваем в этой форме."""
    return t if t.endswith("\n") else t + "\n"


def dump_group(cases):
    return "".join(MARK + name + "\n" + norm_block(cases[name]) for name in sorted(cases))


def save_group(group, cases):
    text = dump_group(cases).encode("utf-8")
    plain, gz = _group_paths(group)
    for p in (plain, gz):
        if os.path.exists(p):
            os.remove(p)
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    if len(text) > GZ_THRESHOLD:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(text)
        with open(gz, "wb") as f:
            f.write(buf.getvalue())
    else:
        with open(plain, "wb") as f:
            f.write(text)


def stored_groups():
    res = set()
    if os.path.isdir(GOLDEN_DIR):
        for fn in os.listdir(GOLDEN_DIR):
            if fn.endswith(".txt.gz"):
                res.add(fn[:-7])
            elif fn.endswith(".txt"):
                res.add(fn[:-4])
    return res


# ----------------------------------------------------------------------------- проверка хоста

def host_problems():
    bad = []
    if not os.path.isdir("/run/systemd/system"):
        bad.append("нет /run/systemd/system: проверки окружения install_vostok.sh требуют запущенный systemd")
    for mod in ("serial", "venv", "ensurepip"):
        try:
            __import__(mod)
        except ImportError:
            bad.append("у python3 нет модуля %s: проверки окружения install_vostok.sh дадут другой вывод" % mod)
    for exe in ("git", "curl", "bash", "awk", "sed"):
        if not shutil.which(exe):
            bad.append("нет команды " + exe)
    try:
        ver = subprocess.run(["bash", "-c", "echo ${BASH_VERSINFO[0]}.${BASH_VERSINFO[1]}"],
                             stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
        mj, mn = [int(x) for x in ver.split(".")]
        if (mj, mn) < (4, 4):
            bad.append("нужен bash 4.4+, сейчас " + ver)
    except Exception:
        bad.append("не удалось определить версию bash")
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            txt = f.read()
        if not any(k in txt for k in ("debian", "ubuntu", "armbian", "raspbian", "orangepi")):
            bad.append("ОС не Debian-подобная (эталоны сняты на Debian 11)")
    except OSError:
        bad.append("нет /etc/os-release")
    if os.geteuid() == 0:
        bad.append("запуск от root запрещён скриптами установщика")
    return bad


# ----------------------------------------------------------------------------- выполнение

def run_case(sb, name, fn):
    ctx = Ctx(sb, name)
    try:
        fn(ctx)
        text = ctx.text()
    except Exception:
        text = "ИСКЛЮЧЕНИЕ В HARNESS:\n" + traceback.format_exc()
    return name, norm_block(text)


def run_cases(selected, jobs, keep):
    sb = Sandbox(keep=keep)
    results = {}
    viol = []
    try:
        sb.prepare()
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = [ex.submit(run_case, sb, n, f) for n, f in selected]
            for fu in concurrent.futures.as_completed(futs):
                n, t = fu.result()
                results[n] = t
        viol = sb.violations()
    finally:
        sb.close()
        if keep:
            print("песочница сохранена: %s" % sb.tmp)
    return results, viol


def select(patterns):
    if not patterns:
        return list(golden_cases.CASES)
    res = []
    for n, f in golden_cases.CASES:
        if any(fnmatch.fnmatch(n, p) or n == p or (p.endswith("/") and n.startswith(p)) for p in patterns):
            res.append((n, f))
    return res


def unified(name, old, new):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        "эталон/" + name, "сейчас/" + name, n=3))


def main():
    ap = argparse.ArgumentParser(prog="run_golden.sh", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--filter", action="append", default=[], metavar="ШАБЛОН")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", metavar="ИМЯ", action="append")
    ap.add_argument("--full", action="store_true", help="с --show: печатать весь вывод, а не diff")
    ap.add_argument("--update", nargs="*", metavar="ШАБЛОН", help="пересъём эталонов (все или подходящие)")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    if a.list:
        for n, _ in select(a.filter):
            print(n)
        return 0

    bad = host_problems()
    if bad:
        print("ПРОПУСК: хост не подходит для golden-прогона:", file=sys.stderr)
        for b in bad:
            print("  - " + b, file=sys.stderr)
        return 2

    if a.show:
        selected = select(a.show)
        if not selected:
            print("нет эталона с таким именем: %s (см. --list)" % ", ".join(a.show), file=sys.stderr)
            return 2
        results, viol = run_cases(selected, a.jobs, a.keep)
        rc = 0
        for n, _ in selected:
            g = load_group(golden_cases.group_of(n)) or {}
            new = results[n]
            if a.full:
                sys.stdout.write("===== %s =====\n%s" % (n, new))
            elif n not in g:
                print("===== %s: НЕТ эталона, текущий вывод:\n%s" % (n, new))
                rc = 1
            elif norm_block(g[n]) == new:
                print("===== %s: совпадает с эталоном" % n)
            else:
                rc = 1
                sys.stdout.write("===== %s: РАСХОЖДЕНИЕ\n%s" % (n, unified(n, norm_block(g[n]), new)))
        for v in viol:
            print("НАРУШЕНИЕ: " + v)
        return 1 if viol else rc

    if a.update is not None:
        selected = select(a.update)
        results, viol = run_cases(selected, a.jobs, a.keep)
        if viol:
            for v in viol:
                print("НАРУШЕНИЕ: " + v, file=sys.stderr)
            print("эталоны НЕ записаны: скрипты писали вне песочницы", file=sys.stderr)
            return 1
        for n, t in results.items():
            if "ВЫЗВАН sudo" in t or "ИСКЛЮЧЕНИЕ В HARNESS" in t:
                print("эталоны НЕ записаны: в %s sudo/исключение" % n, file=sys.stderr)
                return 1
        by_group = {}
        for n, t in results.items():
            by_group.setdefault(golden_cases.group_of(n), {})[n] = t
        full = not a.update
        known = set(n for n, _ in golden_cases.CASES)
        for grp, cs in sorted(by_group.items()):
            old = {} if full else (load_group(grp) or {})
            old.update(cs)
            old = {k: v for k, v in old.items() if k in known}   # убрать эталоны, которых больше нет в перечне
            save_group(grp, old)
            print("записано: %s (%d эталонов)" % (grp, len(old)))
        if full:
            known_groups = set(golden_cases.group_of(n) for n in known)
            for grp in stored_groups() - known_groups:
                for p in _group_paths(grp):
                    if os.path.exists(p):
                        os.remove(p)
                        print("удалён устаревший " + os.path.basename(p))
        return 0

    # --- сравнение
    selected = select(a.filter) if a.filter else list(golden_cases.CASES)
    results, viol = run_cases(selected, a.jobs, a.keep)
    groups = {}
    failed = []
    for n, _ in selected:
        grp = golden_cases.group_of(n)
        if grp not in groups:
            groups[grp] = load_group(grp)
        g = groups[grp]
        if g is None or n not in g:
            failed.append((n, "нет эталона (run_golden.sh --update %s)" % n))
        elif norm_block(g[n]) != results[n]:
            failed.append((n, "расхождение: run_golden.sh --show %s" % n))
        elif a.verbose:
            print("ok   " + n)
    stale = []
    if not a.filter:
        names = set(n for n, _ in golden_cases.CASES)
        for grp in sorted(stored_groups()):
            for n in (load_group(grp) or {}):
                if n not in names:
                    stale.append(n)
    for n, why in failed:
        print("FAIL %s: %s" % (n, why))
    for n in stale:
        print("FAIL %s: эталон есть, а случая в перечне нет (устарел)" % n)
    for v in viol:
        print("FAIL нарушение изоляции: " + v)
    nbad = len(failed) + len(stale) + len(viol)
    print("golden: %d эталонов, расхождений %d" % (len(selected), nbad))
    return 1 if nbad else 0


if __name__ == "__main__":
    sys.exit(main())
