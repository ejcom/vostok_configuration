"""Песочница, заглушки команд, мок Moonraker и нормализация вывода для golden-прогона.

Только stdlib, Python 3.8. Скрипты установщика запускаются из КОПИИ репозитория во временном каталоге,
с подменённым HOME и PATH-заглушками (sudo запрещён и логируется), без tty (новая сессия).
"""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDEN_VERSION = "1.3a"                               # версия, с которой сняты эталоны (VERSION в песочнице)
INSTALLER_SRC = os.path.dirname(TESTS_DIR)          # реальный installer/ (исходник для копии)
FIXTURES = os.path.join(TESTS_DIR, "fixtures")
GOLDEN_DIR = os.path.join(TESTS_DIR, "golden")

# Неизменные «время/автор» для детерминированных sha в фикстурном git-репозитории
GIT_ENV = {
    "GIT_AUTHOR_NAME": "golden", "GIT_AUTHOR_EMAIL": "golden@example.invalid",
    "GIT_COMMITTER_NAME": "golden", "GIT_COMMITTER_EMAIL": "golden@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


# ----------------------------------------------------------------------------- заглушки команд

def _shim(body):
    return "#!/usr/bin/env bash\n" + body


def shim_files(real_git):
    """имя -> текст заглушки. Каждая пишет вызов в $GOLDEN_SHIM_LOG (кроме тихих)."""
    log = 'echo "${0##*/} $*" >> "${GOLDEN_SHIM_LOG:-/dev/null}"\n'
    return {
        # sudo запрещён: любой вызов фиксируется и попадает в эталон как нарушение
        "sudo": _shim('echo "sudo $*" >> "${GOLDEN_SUDO_LOG:-/dev/null}"\n'
                      'echo "sudo: заглушка harness, вызов запрещён" >&2\nexit 1\n'),
        "apt-get": _shim(log + "exit 0\n"),
        "dpkg": _shim("exit 0\n"),
        "systemctl": _shim(log + 'case "$1" in is-active|is-enabled|status) exit 3 ;; esac\nexit 0\n'),
        "lsusb": _shim("exit 1\n"),
        "ip": _shim('if [ "${GOLDEN_CAN_UP:-0}" = 1 ] && [ "$1" = link ]; then\n'
                    '  echo "3: can0: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group default qlen 128"\n'
                    "  exit 0\nfi\nexit 1\n"),
        "ss": _shim("exit 1\n"),
        "dfu-util": _shim(log + "exit 0\n"),
        "arm-none-eabi-gcc": _shim("exit 0\n"),
        "make": _shim(log + "exit 0\n"),
        "df": _shim('echo "Filesystem 1048576-blocks Used Available Capacity Mounted on"\n'
                    'echo "/dev/golden 100000 1000 99000 2% /"\n'),
        "uname": _shim('case "$1" in -m) echo aarch64 ;; -r) echo 5.15.0-golden ;; -s) echo Linux ;; '
                       '*) exec /usr/bin/uname "$@" ;; esac\n'),
        # git: ls-remote всегда «успешно» (без сети), остальное - настоящий git
        "git": _shim('if [ "$1" = ls-remote ]; then exit 0; fi\nexec %s "$@"\n' % real_git),
    }


# ----------------------------------------------------------------------------- мок Moonraker

class _Handler(BaseHTTPRequestHandler):
    server_version = "MockMoonraker/1"

    def log_message(self, *a):          # без шума в stderr
        pass

    def do_GET(self):
        scen, rest = self._split()
        data = self.server.scenarios.get(scen)
        if data is None:
            self._send(404, {"error": "no scenario"})
            return
        u = urllib.parse.urlparse(rest)
        q = urllib.parse.parse_qs(u.query, keep_blank_values=True)
        if u.path == "/server/info":
            self._send(200, {"result": {"klippy_state": "ready", "moonraker_version": "golden"}})
        elif u.path == "/printer/info":
            self._send(200, {"result": {"state": "ready", "state_message": "Printer is ready"}})
        elif u.path == "/printer/objects/query":
            status = {}
            if "print_stats" in q:
                status["print_stats"] = {"state": data.get("print_state", "standby")}
            if "configfile" in q:
                status["configfile"] = {"settings": data.get("settings", {})}
            for key in q:
                if key in data.get("versions", {}):
                    status[key] = {"mcu_version": data["versions"][key]}
            self._send(200, {"result": {"status": status}})
        else:
            self._send(404, {"error": "unknown"})

    def _split(self):
        path = self.path
        parts = path.split("/", 2)           # ['', scen, 'rest...']
        scen = parts[1] if len(parts) > 1 else ""
        rest = "/" + parts[2] if len(parts) > 2 else "/"
        return scen, rest

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MockMoonraker:
    """http.server в потоке; сценарии выбираются первым сегментом пути (MOONRAKER_URL=http://127.0.0.1:порт/имя)."""

    def __init__(self):
        self.httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.scenarios = {}
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, scenario):
        return "http://127.0.0.1:%d/%s" % (self.port, scenario)


# ----------------------------------------------------------------------------- песочница

def _run(argv, **kw):
    return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, **kw)


class Sandbox:
    """Общая часть: копия репозитория, заглушки в PATH, фикстурные git-репозитории, мок Moonraker."""

    def __init__(self, keep=False, base=None):
        self.keep = keep
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="vostok-golden-", dir=base))
        self.repo = os.path.join(self.tmp, "repo")
        self.install = os.path.join(self.repo, "installer")
        self.bin = os.path.join(self.tmp, "bin")
        self.shared = os.path.join(self.tmp, "shared")
        self.cases = os.path.join(self.tmp, "cases")
        self.moon = MockMoonraker()
        self.real_home = os.path.expanduser("~")
        self._guard_before = None

    # --- подготовка
    def prepare(self):
        os.makedirs(self.cases)
        self._copy_repo()
        self._make_shims()
        self._make_klipper_fixture()
        self.moon.start()
        self._guard_before = self._guard_snapshot()

    def _copy_repo(self):
        root = os.path.join(FIXTURES, "repo_root")
        shutil.copytree(root, self.repo, symlinks=True)
        ign = shutil.ignore_patterns("tests", "migration", "__pycache__", "build", "firmware",
                                     "devices.tsv", ".DS_Store", "*.pyc")
        shutil.copytree(INSTALLER_SRC, self.install, ignore=ign, symlinks=True)
        # эталоны сняты с bash 1.3a: номер версии релиза не должен влиять на сравнение вывода
        with open(os.path.join(self.install, "VERSION"), "w", encoding="utf-8") as f:
            f.write(GOLDEN_VERSION + "\n")
        # firmware/, build/ и devices.tsv в копию не попадают (рабочие данные), но их появление или
        # изменение должно ловиться: заводим пустые каталоги/файл и снимаем их вместе с остальным деревом
        for d in ("firmware", "build"):
            os.makedirs(os.path.join(self.install, d), exist_ok=True)
        self.install_snapshot = self._tree_snapshot(self.install)

    def _make_shims(self):
        os.makedirs(self.bin)
        real_git = shutil.which("git")
        if not real_git:
            raise RuntimeError("в системе нет git (нужен harness)")
        for name, text in shim_files(real_git).items():
            p = os.path.join(self.bin, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(p, 0o755)

    def _git(self, cwd, *args):
        env = dict(os.environ)
        env.update(GIT_ENV)
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        _run(["git", "-C", cwd] + list(args), env=env)

    def _make_klipper_fixture(self):
        """Фикстурный git-репозиторий Klipper с upstream (для update_klipper_mcu.sh), sha детерминирован."""
        os.makedirs(self.shared)
        remote = os.path.join(self.shared, "klipper-remote.git")
        kd = os.path.join(self.shared, "klipper")
        os.makedirs(kd)
        self._git(kd, "init", "-q")
        self._git(kd, "symbolic-ref", "HEAD", "refs/heads/master")
        with open(os.path.join(kd, "README"), "w") as f:
            f.write("klipper golden fixture\n")
        os.makedirs(os.path.join(kd, "scripts"))
        with open(os.path.join(kd, "scripts", "klippy-requirements.txt"), "w") as f:
            f.write("")
        self._git(kd, "add", "-A")
        self._git(kd, "commit", "-q", "-m", "init")
        self._git(kd, "tag", "v0.12.0")
        with open(os.path.join(kd, "README"), "a") as f:
            f.write("second\n")
        self._git(kd, "commit", "-q", "-am", "second")
        env = dict(os.environ)
        env.update(GIT_ENV)
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        _run(["git", "clone", "-q", "--bare", kd, remote], env=env)
        self._git(kd, "remote", "add", "origin", remote)
        self._git(kd, "fetch", "-q", "origin")
        self._git(kd, "branch", "-q", "--set-upstream-to=origin/master", "master")
        # katapult и klippy-env: только то, что проверяет preflight
        os.makedirs(os.path.join(self.shared, "katapult", "scripts"))
        open(os.path.join(self.shared, "katapult", "scripts", "flashtool.py"), "w").close()
        os.makedirs(os.path.join(self.shared, "klippy-env", "bin"))
        pip = os.path.join(self.shared, "klippy-env", "bin", "pip")
        with open(pip, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(pip, 0o755)

    # --- защита от записи за пределами песочницы
    def _guard_paths(self):
        h = self.real_home
        out = []
        for sub in ("printer_data", "klipper_mcu"):
            base = os.path.join(h, sub)
            if os.path.isdir(base):
                for dp, _dn, fn in os.walk(base):
                    for n in fn:
                        rel = os.path.relpath(os.path.join(dp, n), base)
                        # на живом хосте работают klipper/moonraker и пишут свои логи, БД и сокеты: их не сторожим
                        if sub == "printer_data" and not (
                                rel.startswith("config" + os.sep) or n.startswith("vostok_")
                                or n.startswith("klipper_mcu")):
                            continue
                        out.append(os.path.join(dp, n))
        return out

    def _guard_snapshot(self):
        snap = {}
        for p in self._guard_paths():
            try:
                st = os.stat(p)
                snap[p] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
        return snap

    @staticmethod
    def _tree_snapshot(root):
        snap = {}
        for dp, dn, fn in os.walk(root):
            dn.sort()
            for n in sorted(fn):
                p = os.path.join(dp, n)
                rel = os.path.relpath(p, root)
                snap[rel] = sha256_file(p) if not os.path.islink(p) else "link"
            for n in dn:
                if not os.listdir(os.path.join(dp, n)):
                    snap[os.path.relpath(os.path.join(dp, n), root) + "/"] = "emptydir"
        return snap

    def violations(self):
        """Список нарушений «не пишем вне временных каталогов»."""
        bad = []
        after = self._guard_snapshot()
        for p, v in after.items():
            if self._guard_before.get(p) != v:
                bad.append("изменён/создан реальный файл: " + p)
        for p in self._guard_before:
            if p not in after:
                bad.append("удалён реальный файл: " + p)
        now = self._tree_snapshot(self.install)
        for rel in sorted(set(now) | set(self.install_snapshot)):
            if now.get(rel) != self.install_snapshot.get(rel):
                bad.append("изменена копия installer/: " + rel)
        return bad

    def close(self):
        try:
            self.moon.stop()
        except Exception:
            pass
        if not self.keep:
            shutil.rmtree(self.tmp, ignore_errors=True)

    # --- окружение запуска
    def base_env(self, case_dir):
        home = os.path.join(case_dir, "home")
        env = {
            "PATH": self.bin + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": home, "USER": "golden", "LOGNAME": "golden",
            "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "TZ": "UTC", "TERM": "dumb",
            "PRINTER_DATA": os.path.join(case_dir, "pd"),
            "DEVICES_FILE": os.path.join(case_dir, "devices.tsv"),
            "BUILD_DIR": os.path.join(case_dir, "build"),
            "FIRMWARE_DIR": os.path.join(case_dir, "firmware"),
            "BYID_DIR": os.path.join(case_dir, "byid"),
            "KERNEL_CONFIG": os.path.join(FIXTURES, "kernel_config_can"),
            "MIN_FREE_MB": "0", "MIN_MEM_MB": "0",
            "GOLDEN_SHIM_LOG": os.path.join(case_dir, "shim.log"),
            "GOLDEN_SUDO_LOG": os.path.join(case_dir, "sudo.log"),
        }
        return env

    # --- нормализация
    def normalizer(self, case_dir):
        subs = [(case_dir, "<CASE>"), (self.install, "<INSTALL>"), (self.repo, "<REPO>"),
                (self.shared, "<SHARED>"), (self.tmp, "<TMP>"), (TESTS_DIR, "<TESTS>"),
                (INSTALLER_SRC, "<SRC-INSTALLER>")]
        subs = sorted([s for s in subs if s[0]], key=lambda s: -len(s[0]))
        rx = [
            (re.compile(r"127\.0\.0\.1:\d+"), "127.0.0.1:<PORT>"),
            (re.compile(r"\.bak-\d{8}-\d{6}"), ".bak-<ДАТА>"),
            (re.compile(r"-g[0-9a-f]{7,40}"), "-g<SHA>"),
            (re.compile(r"(?m)^ОС: .*$"), "ОС: <ОС хоста>"),
            (re.compile(r"python3 \d+\.\d+"), "python3 <версия>"),
            (re.compile(r"(память \(ОЗУ \+ swap\): )\d+"), r"\g<1><N>"),
            (re.compile(r"(?m)^(mkstemp|tmp)\.[A-Za-z0-9]{6,}$"), "<mktemp>"),
        ]

        def norm(text):
            for a, b in subs:
                text = text.replace(a, b)
            for r, b in rx:
                text = r.sub(b, text)
            # список /dev/serial/by-id берётся скриптом прямо с хоста (в обход BYID_DIR): скрываем
            text = re.sub(r"(?s)(Устройства в /dev/serial/by-id:\n).*?(?=Устройств в режиме DFU)",
                          r"\1  <список by-id хоста скрыт нормализацией>\n", text)
            return text
        return norm


class Ctx:
    """Контекст одного эталона: каталог, запуск скриптов, сбор текста."""

    def __init__(self, sb, name):
        self.sb = sb
        self.name = name
        self.dir = os.path.join(sb.cases, name.replace("/", "__"))
        os.makedirs(self.dir, exist_ok=True)
        for d in ("pd/config", "pd/logs", "byid", "home"):
            os.makedirs(os.path.join(self.dir, d), exist_ok=True)
        self.env = sb.base_env(self.dir)
        self.parts = []
        self.slow = False     # True: пауза после каждого запуска, чтобы метки .bak-<дата> не совпадали

    # --- утилиты фикстур
    def p(self, *a):
        return os.path.join(self.dir, *a)

    def touch_byid(self, *names):
        for n in names:
            open(self.p("byid", n), "w").close()

    def write(self, rel, text):
        path = self.p(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def copy_into(self, src, rel):
        dst = self.p(rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return dst

    # --- запуск
    def run(self, script, args=(), env=None, stdin_text=None, timeout=300, cwd=None, title=None, record=True):
        """script: имя файла в installer/ (напр. install_vostok.sh) или путь; возвращает (rc, raw_text)."""
        path = script if os.path.isabs(script) else os.path.join(self.sb.install, script)
        e = dict(self.env)
        if env:
            e.update(env)
        argv = [path] + list(args)
        if path.endswith(".py"):
            argv = ["python3", "-I", path] + list(args)
        pr = subprocess.run(argv, input=(stdin_text.encode("utf-8") if stdin_text is not None else None),
                            stdin=None if stdin_text is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=e,
                            cwd=cwd or self.dir, timeout=timeout, start_new_session=True)
        out = pr.stdout.decode("utf-8", "replace")
        if self.slow:
            time.sleep(1.1)
        if record:
            label = title or ("$ %s %s" % (os.path.basename(script), " ".join(args)))
            self.parts.append("%s\n# rc=%d\n%s" % (label, pr.returncode, out if out.endswith("\n") or not out else out + "\n"))
            self.check_sudo()
        return pr.returncode, out

    def check_sudo(self):
        log = self.p("sudo.log")
        if os.path.exists(log):
            with open(log, encoding="utf-8") as f:
                self.parts.append("!!! ВЫЗВАН sudo (нарушение правил harness):\n" + f.read())
            os.remove(log)

    def note(self, text):
        self.parts.append(text if text.endswith("\n") else text + "\n")

    def dump_tree(self, rel, full_globs=("printer.cfg", "electronics_*.cfg")):
        """Дерево каталога: путь, размер, sha256; полный текст для printer.cfg/electronics_*.cfg (кроме *.bak-*)."""
        import fnmatch
        root = self.p(rel)
        lines = ["## дерево %s" % rel]
        fulls = []
        bak_names = set()
        for dp, dn, fn in os.walk(root):
            dn.sort()
            if ".cache" in dn:
                dn.remove(".cache")      # кэш fontconfig: имена с UUID
            for n in sorted(fn):
                full = os.path.join(dp, n)
                r = os.path.relpath(full, root)
                if n == ".uuid":
                    continue
                if n.endswith(".log"):          # логи содержат время; состав проверяет дерево, не содержимое
                    lines.append("%s\t(лог)" % r)
                    continue
                if ".bak-" in n:
                    # резервные копии с меткой времени: при совпадении секунд копии перезаписывают друг друга,
                    # поэтому в эталон идёт только множество имён (без размеров/хэшей и без кратности)
                    bak_names.add(re.sub(r"\.bak-\d{8}-\d{6}", ".bak-<ДАТА>", r))
                    continue
                with open(full, "rb") as f:
                    data = f.read()
                lines.append("%s\t%d\t%s" % (r, len(data), sha256_bytes(data)[:16]))
                if ".bak-" not in n and any(fnmatch.fnmatch(n, g) for g in full_globs):
                    fulls.append((r, data.decode("utf-8", "replace")))
        for b in sorted(bak_names):
            lines.append("%s\t(резервная копия)" % b)
        for r, t in fulls:
            lines.append("## файл %s" % r)
            lines.append(t if t.endswith("\n") else t + "\n")
        self.parts.append("\n".join(lines) + ("\n" if not lines[-1].endswith("\n") else ""))

    def text(self):
        return self.sb.normalizer(self.dir)("".join(self.parts))
