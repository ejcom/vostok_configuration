"""Перечень golden-эталонов. Каждый эталон - функция ctx -> None, накапливающая текст через ctx.run/ctx.note.

Имя эталона 'группа/имя'. Эталоны снимаются со СТАРЫХ скриптов; новые реализации должны давать тот же текст.
Сценарии конфигуратора A-H (в CONFIGURATOR.md они не пронумерованы, нумерация harness):
  A чистая установка, generate, без голов, все драйверы 5160        (типовой сценарий 1)
  B существующий конфиг VOSTOK, смена драйверов на 2209             (типовой сценарий 2)
  C существующий конфиг, головы EBB42 вместо H36                    (типовой сценарий 3)
  D skip + --alps 2: дописать ALPS в printer.cfg                    (типовой сценарий 4)
  E skip + модуль chamber_heater                                    (типовой сценарий 5)
  F чистая установка, standard (стоковый main), головы v1.3
  G чистая установка, user (user_configs), головы EBB42
  H чистая установка, generate на другой главной плате (пресет Spider v3 / Manta)
"""
import os
import re

from golden_lib import FIXTURES

CASES = []          # [(имя, функция)]


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def group_of(name):
    return name.split("/", 1)[0]


# ----------------------------------------------------------------------------- реестр плат

def read_boards():
    """{id: {ПОЛЕ: значение}} из installer/boards/*.board (то же, что читает lib/boards.sh)."""
    from golden_lib import INSTALLER_SRC
    res = {}
    d = os.path.join(INSTALLER_SRC, "boards")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".board"):
            continue
        rec = {}
        with open(os.path.join(d, fn), encoding="utf-8") as f:
            for ln in f:
                m = re.match(r'^([A-Z_0-9]+)="(.*)"\s*$', ln)
                if m:
                    rec[m.group(1)] = m.group(2)
        res[fn[:-6]] = rec
    return res


BOARDS = read_boards()
MAIN_BOARDS = [b for b, r in BOARDS.items() if r.get("ROLE") == "main"]
HEADS = ["none", "v1.3", "v2", "ebb42"]
STOCK_ELEC = "electronics_octopus_pro_v1.1_h723_5x2240_2xH36v1.3.cfg"


# ----------------------------------------------------------------------------- справка и версия

SCRIPTS = ["install_vostok.sh", "update_klipper_mcu.sh", "configure_vostok.sh",
           "install_fluidd_button.sh", "install_fluidd_theme.sh", "install_klipperscreen_theme.sh"]


def _reg_help(script):
    base = script[:-3]

    @case("help/%s" % base)
    def _(ctx):
        ctx.run(script, ["--help"])
        ctx.run(script, ["-V"])
        ctx.run(script, ["--no-such-option"])


for _s in SCRIPTS:
    _reg_help(_s)


@case("boards/list_boards")
def _(ctx):
    ctx.run("install_vostok.sh", ["--list-boards"])


@case("boards/bad_args")
def _(ctx):
    ctx.run("install_vostok.sh", ["--main", "bogus", "--only-detect"])
    ctx.run("install_vostok.sh", ["--heads", "bogus", "--only-detect"])
    ctx.run("install_vostok.sh", ["--heads"])
    ctx.run("install_vostok.sh", ["--alps", "7", "--only-detect"])
    ctx.run("install_vostok.sh", ["--config-source", "bogus", "--only-detect"])
    ctx.run("install_vostok.sh", ["--main-flash", "bogus", "--only-detect"])
    ctx.run("install_vostok.sh", ["--skip-board", "bogus", "--only-detect"])
    ctx.run("configure_vostok.sh", ["--main", "bogus"])
    ctx.run("configure_vostok.sh", ["--heads", "bogus"])
    ctx.run("configure_vostok.sh", ["--alps", "9"])
    ctx.run("configure_vostok.sh", ["--printer-data", ctx.p("no-such-dir")])


# ----------------------------------------------------------------------------- install_vostok.sh: матрица

def _chip_device(chip):
    return "usb-Klipper_%s_0123456789AB-if00" % chip


def _reg_install(mode, board, heads):
    name = "install_matrix/%s__%s__%s" % (mode, board, heads)
    flag = "--only-detect" if mode == "detect" else "--dry-run"

    @case(name)
    def _(ctx):
        ctx.touch_byid(_chip_device(BOARDS[board]["CHIP"]))
        ctx.run("install_vostok.sh", ["--main", board, "--heads", heads, "--alps", "0", "-y", flag])


for _b in MAIN_BOARDS:
    for _h in HEADS:
        _reg_install("detect", _b, _h)
        _reg_install("dry", _b, _h)


@case("install/detect_auto_h723_2alps")
def _(ctx):
    ctx.touch_byid(_chip_device("stm32h723xx"), "usb-Klipper_stm32f072xb_AAAA00000001-if00",
                   "usb-Klipper_stm32f072xb_AAAA00000002-if00")
    ctx.run("install_vostok.sh", ["--only-detect"])


@case("install/detect_auto_empty")
def _(ctx):
    ctx.run("install_vostok.sh", ["--only-detect", "--main", "h723"])


@case("install/detect_auto_f446_katapult")
def _(ctx):
    ctx.touch_byid("usb-katapult_stm32f446xx_BBBB00000001-if00")
    ctx.run("install_vostok.sh", ["--only-detect", "--main", "f446", "--heads", "none", "--alps", "0"])


@case("install/dry_alps2_v2_can_flash")
def _(ctx):
    ctx.touch_byid(_chip_device("stm32h723xx"), "usb-Klipper_stm32f072xb_AAAA00000001-if00",
                   "usb-Klipper_stm32f072xb_AAAA00000002-if00")
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "v2", "--alps", "2",
                                  "--heads-flash", "can", "-y"])


@case("install/dry_main_flash_katapult")
def _(ctx):
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "none", "--alps", "0",
                                  "--main-flash", "katapult", "-y"])


@case("install/dry_skip_all")
def _(ctx):
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "none", "--alps", "0", "-y",
                                  "--skip-software", "--skip-flash", "--skip-config", "--skip-button", "--skip-theme"])


@case("install/dry_skip_board_reflash")
def _(ctx):
    ctx.touch_byid(_chip_device("stm32h723xx"))
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "none", "--alps", "0", "-y",
                                  "--skip-board", "main"])
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "v1.3", "--alps", "0", "-y",
                                  "--skip-board", "heads", "--reflash"])


@case("install/dry_generate_drivers")
def _(ctx):
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "none", "--alps", "0", "-y",
                                  "--skip-software", "--config-source", "generate", "--drivers", "all=5160",
                                  "--modules", "none"])


@case("install/dry_no_klipper_upgrade")
def _(ctx):
    ctx.run("install_vostok.sh", ["--dry-run", "--upgrade", "--main", "h723", "--heads", "none", "--alps", "0", "-y"])


@case("install/dry_no_can_kernel")
def _(ctx):
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "v1.3", "--alps", "0", "-y"],
            env={"KERNEL_CONFIG": os.path.join(FIXTURES, "kernel_config_nocan")})


@case("install/dry_cfg_local_off")
def _(ctx):
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "none", "--alps", "0", "-y"],
            env={"VOSTOK_CFG_LOCAL": "0"})


@case("install/dry_check_can")
def _(ctx):
    ctx.run("install_vostok.sh", ["--check-can", "--dry-run", "--main", "h723", "--heads", "v1.3", "-y"])


@case("install/dry_no_tty_no_y")
def _(ctx):
    ctx.run("install_vostok.sh", ["--dry-run", "--main", "h723", "--heads", "none", "--alps", "0"])


# ----------------------------------------------------------------------------- gen_electronics.py: матрица

def _gen_args(ctx, board, heads, drivers, alps):
    """Те же аргументы, что собирает lib/vostok_config.sh: gen_custom_electronics."""
    rec = BOARDS[board]
    stock = os.path.join(ctx.sb.repo, STOCK_ELEC)
    ref = stock if rec.get("ELEC_PATTERN") == "_h723_" else ""
    extra = []
    if rec.get("TEMPLATE") == "octopus_pro":
        if rec.get("ELEC_PATTERN") == "_h723_":
            extra.append("--octopus-extruders")
        if heads == "none":
            extra.append("--octopus-heads")
    if rec.get("CFG") == rec.get("CHIP"):
        alias = rec.get("ALIASES", "").split(" ")[0]
        board_args = ["--main", alias]
    else:
        board_args = ["--main", board, "--board-name", rec["LABEL"], "--board-file", board.replace("-", "_")]
    board_args += ["--template", rec.get("TEMPLATE") or "none"]
    names = rec.get("HEAD_NAMES") or "T0CB,T1CB"
    hb = {"v1.3": "h36-v1.3", "v2": "h36-v2", "ebb42": "ebb42"}.get(heads)
    hn = (BOARDS[hb].get("HEAD_NAMES") if hb else "") or "T0CB,T1CB"
    out = ctx.p("out")
    os.makedirs(out, exist_ok=True)
    return (["--templates", os.path.join(ctx.sb.install, "templates"), "--ref-cfg", ref, "--main-cfg", stock,
             "--heads", heads, "--head-names", hn, "--alps", str(alps), "--drivers", drivers]
            + board_args + extra + ["--out-dir", out])


def _reg_gen(board, heads, dname, drivers, alps):
    @case("gen_matrix/%s__%s__%s" % (board, heads, dname))
    def _(ctx):
        args = _gen_args(ctx, board, heads, drivers, alps)
        rc, out = ctx.run(os.path.join(ctx.sb.install, "tools", "gen_electronics.py"), args,
                          title="$ gen_electronics.py (board=%s heads=%s drivers=%s alps=%d)" % (board, heads, drivers, alps))
        m = re.search(r"(?m)^NAME\t(.+)$", out)
        if m:
            with open(os.path.join(ctx.p("out"), m.group(1)), encoding="utf-8") as f:
                ctx.note("## файл %s\n%s" % (m.group(1), f.read()))


STOCK_DRV = "x=2240,w=2240,yl=2240,yr=2240,z=2240,e0=2209,e1=2209"
for _b in MAIN_BOARDS:
    for _h in HEADS:
        _reg_gen(_b, _h, "stock", STOCK_DRV, 0)
        _reg_gen(_b, _h, "all5160plus_alps2", "all=5160plus", 2)


@case("gen_matrix/err_bad_args")
def _(ctx):
    base = ["--templates", os.path.join(ctx.sb.install, "templates"), "--out-dir", ctx.p("out")]
    ctx.run(os.path.join(ctx.sb.install, "tools", "gen_electronics.py"), base + ["--main", "nope"])
    ctx.run(os.path.join(ctx.sb.install, "tools", "gen_electronics.py"), base + ["--drivers", "all=9999"])
    ctx.run(os.path.join(ctx.sb.install, "tools", "gen_electronics.py"), base + ["--template", "nope"])
    ctx.run(os.path.join(ctx.sb.install, "tools", "gen_electronics.py"), base + ["--heads", "v9"])


# ----------------------------------------------------------------------------- конфигуратор

def seed_vostok_pd(ctx, with_alps=False, extra_mcu=""):
    """Существующая установка VOSTOK в pd/config (снимок корня репозитория)."""
    root = os.path.join(FIXTURES, "repo_root")
    for f in ("printer.cfg", "printer_base.cfg", "chamber_heater.cfg", STOCK_ELEC):
        ctx.copy_into(os.path.join(root, f), "pd/config/" + f)
    ctx.write("pd/config/postprocessing/fast_tool_swaps.py", "# пользовательская копия\n")
    if with_alps:
        with open(ctx.p("pd/config/printer.cfg"), "a", encoding="utf-8") as f:
            f.write("\n[mcu alps]\nserial: /dev/serial/by-id/usb-Klipper_stm32f072xb_AAAA00000001-if00\n")
    if extra_mcu:
        with open(ctx.p("pd/config/printer.cfg"), "a", encoding="utf-8") as f:
            f.write(extra_mcu)


def seed_foreign_pd(ctx):
    ctx.copy_into(os.path.join(FIXTURES, "kiauh_printer.cfg"), "pd/config/printer.cfg")


def seed_blank_pd(ctx):
    ctx.write("pd/config/printer.cfg", "\n# пусто\n\n")


ALPS2 = ["usb-Klipper_stm32f072xb_AAAA00000001-if00", "usb-Klipper_stm32f072xb_AAAA00000002-if00"]


def _reg_cfg(key, setup, args, byid=(), env=None, real=True):
    """Регистрирует key_dry (с --dry-run) и key_real (запись в копию pd + дерево/файлы)."""
    @case("configure/%s_dry" % key)
    def _(ctx):
        setup(ctx)
        ctx.touch_byid(*byid)
        ctx.run("configure_vostok.sh", list(args) + ["--dry-run"], env=env)
        ctx.dump_tree("pd/config")

    if real:
        @case("configure/%s_real" % key)
        def _(ctx):
            setup(ctx)
            ctx.touch_byid(*byid)
            ctx.run("configure_vostok.sh", list(args), env=env)
            ctx.dump_tree("pd/config")


def seed_none(ctx):
    pass


H723_DEV = ["usb-Klipper_stm32h723xx_120026000A51333231343036-if00"]

# A
_reg_cfg("A_generate_clean_none_5160", seed_none,
         ["--config-source", "generate", "--main", "h723", "--heads", "none", "--alps", "0", "--drivers", "all=5160",
          "--modules", "none", "-y"], byid=H723_DEV)
# B
_reg_cfg("B_existing_drivers_2209", lambda c: seed_vostok_pd(c),
         ["--config-source", "generate", "--drivers", "all=2209", "--modules", "none", "-y"], byid=H723_DEV)
# C
_reg_cfg("C_existing_ebb42", lambda c: seed_vostok_pd(c),
         ["--config-source", "generate", "--heads", "ebb42", "--drivers", "all=2209", "--modules", "none", "-y"],
         byid=H723_DEV)
# D
_reg_cfg("D_skip_alps2", lambda c: seed_vostok_pd(c), ["--config-source", "skip", "--alps", "2", "--modules", "none", "-y"],
         byid=H723_DEV + ALPS2)
# E
_reg_cfg("E_skip_chamber_heater", lambda c: seed_vostok_pd(c),
         ["--config-source", "skip", "--modules", "chamber_heater", "-y"], byid=H723_DEV)
# F
_reg_cfg("F_standard_clean_v13", seed_none,
         ["--config-source", "standard", "--main", "h723", "--heads", "v1.3", "--alps", "0", "--modules", "none", "-y"],
         byid=H723_DEV)
# G
_reg_cfg("G_user_clean_ebb42", seed_none,
         ["--config-source", "user", "--electronics", "electronics_octopus_pro_v1.1_h723_5x2209_2xebb42.cfg",
          "--main", "h723", "--heads", "ebb42", "--alps", "0", "--modules", "none", "-y"], byid=H723_DEV)
# H
_reg_cfg("H_generate_spider_v3", seed_none,
         ["--config-source", "generate", "--main", "spider-v3-h723", "--heads", "none", "--alps", "0",
          "--drivers", "x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209", "--modules", "none", "-y"],
         byid=["usb-Klipper_stm32h723xx_SPIDER000001-if00"])
_reg_cfg("H_generate_manta_v2_heads_v2", seed_none,
         ["--config-source", "generate", "--main", "manta-m8p-v2.0", "--heads", "v2", "--alps", "1",
          "--drivers", "all=2209", "--modules", "none", "-y"], byid=["usb-Klipper_stm32f072xb_AAAA00000001-if00"])
_reg_cfg("H_generate_f446_noref", seed_none,
         ["--config-source", "generate", "--main", "f446", "--heads", "none", "--alps", "0", "--drivers", "all=2130",
          "--modules", "none", "-y"])
_reg_cfg("H_generate_fly_c8", seed_none,
         ["--config-source", "generate", "--main", "fly-c8", "--heads", "none", "--alps", "0", "--drivers", "all=2208",
          "--modules", "none", "-y"])
# Доп. сценарии
_reg_cfg("I_foreign_kiauh_generate", seed_foreign_pd,
         ["--config-source", "generate", "--main", "h723", "--heads", "none", "--alps", "0", "--drivers", "all=2240",
          "--modules", "none", "-y"], byid=H723_DEV)
_reg_cfg("I_blank_standard", seed_blank_pd,
         ["--config-source", "standard", "--main", "h723", "--heads", "v1.3", "--alps", "0", "--modules", "none", "-y"],
         byid=H723_DEV)
_reg_cfg("J_skip_diff_todo", lambda c: seed_vostok_pd(c, with_alps=True),
         ["--config-source", "skip", "--alps", "2", "--modules", "none", "-y"],
         byid=H723_DEV + ["usb-Klipper_stm32f072xb_ZZZZ99999999-if00"])
_reg_cfg("K_existing_reference_none", lambda c: seed_vostok_pd(c),
         ["--config-source", "generate", "--reference", "none", "--drivers", "all=5160plus", "--modules", "all", "-y"],
         byid=H723_DEV)
_reg_cfg("L_no_tty_default_skip", lambda c: seed_vostok_pd(c), [], byid=H723_DEV)
_reg_cfg("M_all_modules_clean", seed_none,
         ["--config-source", "standard", "--main", "h723", "--heads", "v1.3", "--alps", "0", "--modules", "all", "-y"],
         byid=H723_DEV)
_reg_cfg("N_cfg_local_off", seed_none,
         ["--config-source", "standard", "--main", "h723", "--heads", "none", "--alps", "0", "--modules", "none", "-y"],
         env={"VOSTOK_CFG_LOCAL": "0"}, real=False)
_reg_cfg("O_user_cfg_missing", seed_none,
         ["--config-source", "user", "--electronics", "no_such.cfg", "--main", "h723", "--heads", "none", "--alps", "0",
          "--modules", "none", "-y"], byid=H723_DEV)


@case("configure/P_printer_data_env")
def _(ctx):
    seed_vostok_pd(ctx)
    ctx.touch_byid(*H723_DEV)
    other = ctx.p("other_pd")
    os.makedirs(other + "/config")
    ctx.run("configure_vostok.sh", ["--config-source", "skip", "--modules", "none", "-y", "--dry-run"],
            env={"PRINTER_DATA": other}, title="$ PRINTER_DATA=<другой> configure_vostok.sh ... (пустой config)")
    ctx.run("configure_vostok.sh", ["--printer-data", ctx.p("pd"), "--config-source", "skip", "--modules", "none",
                                    "-y", "--dry-run"], env={"PRINTER_DATA": other})


# ----------------------------------------------------------------------------- update_klipper_mcu.sh --list

def _update_env(ctx, scenario, can_up=False):
    ctx.write("devices.tsv", (
        "120026000A51333231343036\tstm32h723xx.config\tusb\n"
        "SPIDER000001\tspider-v3-h723.config\tusb\n"
        "821a4dc3b8eb\tstm32h723xx-canbridge.config\tbridge\n"
        "bcc1147e110d\tstm32g0b1xx-can.config\tcan\n"
        "21ad41ca6772\tstm32g0b1xx-can.config\tcan\n"
        "AAAA00000001\tstm32f072xb.config\tusb\n"))
    # конфиги сборки - копия реальных из installer/configs (CONFIGS_DIR по умолчанию рядом со скриптом)
    return {
        "MOONRAKER_URL": ctx.sb.moon.url(scenario),
        "KLIPPER_DIR": os.path.join(ctx.sb.shared, "klipper"),
        "KATAPULT_DIR": os.path.join(ctx.sb.shared, "katapult"),
        "KLIPPY_ENV": os.path.join(ctx.sb.shared, "klippy-env"),
        "KIAUH_DIR": os.path.join(ctx.dir, "no_kiauh"),
        "GOLDEN_CAN_UP": "1" if can_up else "0",
    }


def _scenario(ctx, name, **kw):
    byid = ctx.p("byid")
    settings = {
        "mcu": {"serial": byid + "/usb-Klipper_stm32h723xx_120026000A51333231343036-if00"},
        "mcu T0CB": {"canbus_uuid": "bcc1147e110d"},
        "mcu T1CB": {"canbus_uuid": "21ad41ca6772"},
        "mcu alps": {"serial": byid + "/usb-Klipper_stm32f072xb_AAAA00000001-if00"},
        "mcu ghost": {"serial": byid + "/usb-Klipper_stm32f072xb_NOTPLUGGED-if00"},
        "printer": {"kinematics": "generic_cartesian"},
    }
    settings.update(kw.get("settings_override", {}))
    versions = {"mcu": "v0.12.0-1-gdeadbee", "mcu T0CB": "v0.12.0-0-gabcdef0", "mcu alps": "v0.11.0-5-g1234567-dirty"}
    versions.update(kw.get("versions_override", {}))
    ctx.sb.moon.httpd.scenarios[name] = {
        "settings": settings, "versions": versions, "print_state": kw.get("print_state", "standby")}


def _upd_dev(ctx):
    ctx.touch_byid("usb-Klipper_stm32h723xx_120026000A51333231343036-if00",
                   "usb-Klipper_stm32f072xb_AAAA00000001-if00",
                   "usb-Klipper_stm32f072xb_CCCC00000003-if00",
                   "usb-Klipper_stm32f446xx_NOCFG0000001-if00",
                   "usb-katapult_stm32f446xx_DDDD00000004-if00")


@case("update/list_full")
def _(ctx):
    sc = "full_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc)
    _upd_dev(ctx)
    env = _update_env(ctx, sc, can_up=True)
    ctx.run("update_klipper_mcu.sh", ["--list"], env=env)
    ctx.run("update_klipper_mcu.sh", ["--list", "-y"], env=env)


@case("update/list_can_down")
def _(ctx):
    sc = "candown_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc)
    _upd_dev(ctx)
    ctx.run("update_klipper_mcu.sh", ["--list"], env=_update_env(ctx, sc, can_up=False))


@case("update/list_no_moonraker")
def _(ctx):
    _upd_dev(ctx)
    env = _update_env(ctx, "none")
    env["MOONRAKER_URL"] = "http://127.0.0.1:1"
    ctx.run("update_klipper_mcu.sh", ["--list"], env=env)
    ctx.run("update_klipper_mcu.sh", ["--list", "--ignore-moonraker"], env=env)


@case("update/list_printing")
def _(ctx):
    sc = "printing_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc, print_state="printing")
    _upd_dev(ctx)
    ctx.run("update_klipper_mcu.sh", ["--list"], env=_update_env(ctx, sc))
    sc2 = "paused_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc2, print_state="paused")
    ctx.run("update_klipper_mcu.sh", ["--list"], env=_update_env(ctx, sc2))


@case("update/list_state_file_and_empty_byid")
def _(ctx):
    sc = "empty_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc, versions_override={"mcu": "?"})
    ctx.touch_byid("usb-Klipper_stm32h723xx_120026000A51333231343036-if00")
    env = _update_env(ctx, sc)
    env["STATE_FILE"] = ctx.write("flashed.tsv", "120026000A51333231343036\tv0.12.0-1-gdeadbee-dirty\n")
    ctx.run("update_klipper_mcu.sh", ["--list"], env=env)
    # пустой by-id и Moonraker без MCU
    for fn in os.listdir(ctx.p("byid")):
        os.remove(ctx.p("byid", fn))
    ctx.run("update_klipper_mcu.sh", ["--list", "--ignore-moonraker"], env=env)


@case("update/list_ambiguous_chip_board")
def _(ctx):
    sc = "amb_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc)
    ctx.touch_byid("usb-Klipper_stm32h723xx_UNKNOWNSERIAL1-if00")
    env = _update_env(ctx, sc)
    env["DEVICES_FILE"] = ctx.p("none.tsv")
    ctx.run("update_klipper_mcu.sh", ["--list"], env=env)


@case("update/preflight_errors")
def _(ctx):
    sc = "pre_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc)
    env = _update_env(ctx, sc)
    bad = dict(env, KLIPPER_DIR=ctx.p("no_klipper"))
    ctx.run("update_klipper_mcu.sh", ["--list"], env=bad, title="$ --list (KLIPPER_DIR не репозиторий)")
    bad = dict(env, KATAPULT_DIR=ctx.p("no_katapult"))
    ctx.run("update_klipper_mcu.sh", ["--list"], env=bad, title="$ --list (нет katapult)")
    bad = dict(env, KLIPPY_ENV=ctx.p("no_env"))
    ctx.run("update_klipper_mcu.sh", ["--list"], env=bad, title="$ --list (нет klippy-env, git-update)")
    ctx.run("update_klipper_mcu.sh", ["--list", "--no-update"], env=bad, title="$ --list --no-update (klippy-env не нужен)")


@case("update/uptodate_no_update_no_flash")
def _(ctx):
    sc = "uptd_" + ctx.name.replace("/", "_")
    _scenario(ctx, sc)
    _upd_dev(ctx)
    ctx.run("update_klipper_mcu.sh", ["--no-update", "--no-flash", "-y"], env=_update_env(ctx, sc))


# ----------------------------------------------------------------------------- темы и кнопка Fluidd (dry-run, песочница)

def _fluidd_fixture(ctx):
    fd = ctx.p("home", "fluidd")
    os.makedirs(fd, exist_ok=True)
    ctx.write("home/fluidd/index.html", "<html></html>\n")
    ctx.write("home/fluidd/config.json", "{}\n")
    ctx.write("pd/config/.theme/.keep", "")
    ctx.write("pd/config/moonraker.conf", "[server]\nhost: 0.0.0.0\n")
    return fd


@case("integrations/button_dry_run")
def _(ctx):
    ctx.write("pd/config/moonraker.conf", "[server]\nhost: 0.0.0.0\n")
    ctx.write("pd/moonraker.asvc", "klipper\nmoonraker\n")
    env = {"KLIPPER_DIR": os.path.join(ctx.sb.shared, "klipper"), "KATAPULT_DIR": os.path.join(ctx.sb.shared, "katapult"),
           "KLIPPY_ENV": os.path.join(ctx.sb.shared, "klippy-env"), "KIAUH_DIR": ctx.p("no_kiauh"),
           "MOONRAKER_URL": ctx.sb.moon.url("btn_" + ctx.name.replace("/", "_"))}
    _scenario(ctx, "btn_" + ctx.name.replace("/", "_"))
    ctx.run("install_fluidd_button.sh", ["--dry-run", "-y"], env=env)
    ctx.run("install_fluidd_button.sh", ["--dry-run", "-y", "--with-macro", "--flash-args", "--no-update --force-flash"], env=env)
    ctx.run("install_fluidd_button.sh", ["--dry-run", "-y", "--uninstall"], env=env)
    ctx.dump_tree("pd")


@case("integrations/fluidd_theme")
def _(ctx):
    ctx.slow = True
    fd = _fluidd_fixture(ctx)
    env = {"FLUIDD_DIR": fd, "MOONRAKER_URL": "http://127.0.0.1:1"}
    ctx.run("install_fluidd_theme.sh", ["--dry-run", "-y", "--no-activate"], env=env)
    ctx.run("install_fluidd_theme.sh", ["-y", "--no-activate"], env=env)
    ctx.dump_tree("pd", full_globs=("moonraker.conf",))
    ctx.run("install_fluidd_theme.sh", ["-y", "--no-activate"], env=env, title="$ install_fluidd_theme.sh -y --no-activate (повтор)")
    ctx.run("install_fluidd_theme.sh", ["-y", "--logo-copy", "--no-activate"], env=env)
    ctx.dump_tree("pd", full_globs=("moonraker.conf",))
    ctx.dump_tree("home/fluidd")
    ctx.run("install_fluidd_theme.sh", ["-y", "--uninstall", "--no-activate"], env=env)
    ctx.dump_tree("pd", full_globs=("moonraker.conf",))
    ctx.dump_tree("home/fluidd")


@case("integrations/klipperscreen_theme")
def _(ctx):
    ctx.slow = True
    ks = ctx.p("home", "KlipperScreen")
    os.makedirs(ks + "/styles/material-dark/images", exist_ok=True)
    ctx.write("home/KlipperScreen/styles/material-dark/images/icon.svg", "<svg/>\n")
    ctx.write("pd/config/KlipperScreen.conf", "[main]\ntheme: material-dark\n")
    env = {"KS_DIR": ks, "FONT_DIR": ctx.p("home", ".fonts")}
    ctx.run("install_klipperscreen_theme.sh", ["--dry-run", "-y"], env=env)
    ctx.run("install_klipperscreen_theme.sh", ["-y", "--no-activate"], env=env)
    ctx.dump_tree("pd", full_globs=("KlipperScreen.conf",))
    ctx.run("install_klipperscreen_theme.sh", ["-y"], env=env)
    ctx.dump_tree("pd", full_globs=("KlipperScreen.conf",))
    ctx.run("install_klipperscreen_theme.sh", ["-y", "--uninstall"], env=env)
    ctx.dump_tree("pd", full_globs=("KlipperScreen.conf",))
    ctx.dump_tree("home")
