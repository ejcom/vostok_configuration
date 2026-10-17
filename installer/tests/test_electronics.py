"""Тесты vostok.electronics: побайтовая сверка со старым tools/gen_electronics.py и проверка отсутствия глобалов."""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTALLER = HERE.parent
sys.path.insert(0, str(INSTALLER))

from vostok import electronics as el          # noqa: E402
from vostok.boards import Registry            # noqa: E402

FIXTURES = HERE / "fixtures" / "repo_root"
STOCK = FIXTURES / "electronics_octopus_pro_v1.1_h723_5x2240_2xH36v1.3.cfg"
USER_CFGS = sorted((FIXTURES / "user_configs").glob("electronics_*.cfg"))
OLD_TOOL = INSTALLER / "tools" / "gen_electronics.py"
STOCK_DRV = "x=2240,w=2240,yl=2240,yr=2240,z=2240,e0=2209,e1=2209"
HEAD_NAMES = {"none": "T0CB,T1CB", "v1.3": "T0CB,T1CB", "v2": "T0CB,T1CB", "ebb42": "T0_EBB,T1_EBB"}


def read_boards():
    """{id: {ПОЛЕ: значение}} из boards/*.board."""
    res = {}
    for p in sorted((INSTALLER / "boards").glob("*.board")):
        rec = {}
        for ln in p.read_text(encoding="utf-8").split("\n"):
            m = re.match(r'^([A-Z_0-9]+)="(.*)"\s*$', ln)
            if m:
                rec[m.group(1)] = m.group(2)
        res[p.stem] = rec
    return res


BOARDS = read_boards()
MAIN_BOARDS = [b for b, r in BOARDS.items() if r.get("ROLE") == "main"]


def cli_args(board, heads, drivers, alps, ref, outdir):
    """Аргументы так, как их собирает конфигуратор (lib/vostok_config.sh: gen_custom_electronics)."""
    rec = BOARDS[board]
    extra = []
    if rec.get("TEMPLATE") == "octopus_pro":
        if rec.get("ELEC_PATTERN") == "_h723_":
            extra.append("--octopus-extruders")
        if heads == "none":
            extra.append("--octopus-heads")
    if rec.get("CFG") == rec.get("CHIP"):
        board_args = ["--main", rec.get("ALIASES", "").split(" ")[0]]
    else:
        board_args = ["--main", board, "--board-name", rec["LABEL"], "--board-file", board.replace("-", "_")]
    board_args += ["--template", rec.get("TEMPLATE") or "none"]
    return (["--templates", str(INSTALLER / "templates"), "--ref-cfg", str(ref or ""), "--main-cfg", str(STOCK),
             "--heads", heads, "--head-names", HEAD_NAMES[heads], "--alps", str(alps), "--drivers", drivers]
            + board_args + extra + ["--out-dir", str(outdir)])


def run_new(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = el.main(args)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    return rc, out.getvalue(), err.getvalue()


def run_old(args):
    p = subprocess.run([sys.executable, "-I", str(OLD_TOOL)] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True)
    return p.returncode, p.stdout, p.stderr


def snapshot(d):
    return {f: Path(d, f).read_bytes() for f in os.listdir(d)}


@unittest.skipUnless(OLD_TOOL.is_file() and "vostok" not in OLD_TOOL.read_text(encoding="utf-8"),
                     "tools/gen_electronics.py стал обёрткой над vostok.electronics: сверку со старым кодом заменяет golden gen_matrix")
class TestMatchesOldGenerator(unittest.TestCase):
    """Вывод (stdout, stderr, код) и файл побайтно совпадают со старым скриптом."""

    def check(self, board, heads, drivers, alps, ref):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            old = run_old(cli_args(board, heads, drivers, alps, ref, d1))
            new = run_new(cli_args(board, heads, drivers, alps, ref, d2))
            f1, f2 = snapshot(d1), snapshot(d2)
        msg = "%s %s %s alps=%s ref=%s" % (board, heads, drivers, alps, ref)
        self.assertEqual(old[0], new[0], msg)
        self.assertEqual(old[1].replace(d1, "<D>"), new[1].replace(d2, "<D>"), msg)
        self.assertEqual(old[2], new[2], msg)
        self.assertEqual(f1, f2, msg)

    def test_all_boards_all_heads_stock(self):
        for board in MAIN_BOARDS:
            for heads in el.HEADS_CHOICES:
                with self.subTest(board=board, heads=heads):
                    self.check(board, heads, STOCK_DRV, 0, STOCK if BOARDS[board].get("ELEC_PATTERN") == "_h723_" else "")

    def test_alps_and_driver_variants(self):
        for board, heads, drivers, alps in (
                ("octopus-pro-h723", "none", "all=5160plus", 2),
                ("octopus-pro-h723", "ebb42", "all=2209", 1),
                ("octopus-pro-f446", "none", "all=2130", 0),
                ("spider-v3-h723", "none", "x=5160,w=5160,yl=5160,yr=5160,z=2209,e0=2209,e1=2209", 0),
                ("manta-m8p-v2.0", "v2", "all=2208", 1),
                ("fly-c8", "none", "all=tmc2240", 2),
                ("octopus-pro-h723", "v1.3", "all=5160,e0=2209", 0)):
            with self.subTest(board=board, heads=heads, drivers=drivers):
                self.check(board, heads, drivers, alps, "")

    def test_user_configs_as_reference(self):
        for ref in USER_CFGS:
            for board, heads in (("octopus-pro-h723", "none"), ("octopus-pro-h723", "v2"), ("octopus-pro-f446", "none")):
                with self.subTest(ref=ref.name, board=board, heads=heads):
                    self.check(board, heads, "all=2209", 0, ref)

    def test_errors_match(self):
        base = ["--templates", str(INSTALLER / "templates"), "--out-dir", tempfile.gettempdir()]
        for extra in (["--main", "nope"], ["--drivers", "all=9999"], ["--template", "nope"], ["--heads", "v9"],
                      ["--drivers", "q=2209"], ["--drivers", "x=2209"], ["--main", "h723", "--drivers", "all=2209", "--heads", "v1.3",
                                                                          "--drivers", "z=1234"]):
            with self.subTest(extra=extra):
                old, new = run_old(base + extra), run_new(base + extra)
                self.assertEqual(old[0], new[0])
                self.assertEqual(old[1], new[1])
                self.assertEqual(old[2].replace(tempfile.gettempdir(), "<T>"), new[2].replace(tempfile.gettempdir(), "<T>"))


class TestGeneratorState(unittest.TestCase):
    """Глобалы TABLE_OPTS/SVERIT/TABLE_SRC убраны: прогоны не влияют друг на друга."""

    def gen(self, **kw):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        opts = dict(templates=str(INSTALLER / "templates"), board_name="Octopus", board_file="octopus", drivers=STOCK_DRV,
                    out_dir=d, main_cfg=str(STOCK))
        opts.update(kw)
        gen = el.Generator(el.GenOptions(**opts))
        return gen, gen.generate()

    def test_no_module_globals(self):
        for name in ("TABLE_OPTS", "SVERIT", "TABLE_SRC", "BOARD_NAMES", "BOARD_FILE"):
            self.assertFalse(hasattr(el, name), name)

    def test_runs_are_independent(self):
        _, first = self.gen(template="octopus_pro", ref_cfg=str(STOCK), octopus_extruders=True, octopus_heads=True)
        g_preset, _ = self.gen(template="manta_m8p_v2.0", board_name="BTT Manta M8P v2.0", board_file="manta_m8p_v2.0")
        self.assertIn("BTT Manta M8P v2.0", g_preset.sverit)
        self.assertEqual(g_preset.table_src, "BTT Manta M8P v2.0")
        # после прогона с пресетом новый прогон Octopus снова использует свои значения
        g_oct, again = self.gen(template="octopus_pro", ref_cfg=str(STOCK), octopus_extruders=True, octopus_heads=True)
        self.assertEqual(g_oct.sverit, el.SVERIT_OCTOPUS)
        self.assertEqual(g_oct.table_src, "Octopus Pro")
        self.assertEqual(first.protocol(), again.protocol())
        self.assertEqual(first.path.read_bytes(), again.path.read_bytes())

    def test_result_fields(self):
        _, res = self.gen(template="octopus_pro", ref_cfg=str(STOCK), octopus_extruders=True, octopus_heads=True,
                          board_name="BigTreeTech Octopus Pro v1.1 H723", board_file="octopus_pro_v1.1_h723",
                          drivers="all=5160")
        self.assertEqual(res.name, "electronics_octopus_pro_v1.1_h723_7x5160.cfg")
        self.assertTrue(res.path.is_file())
        self.assertEqual(list(res.fill), ["ref", "octopus", "board"])
        self.assertEqual(res.fill["ref"], 42)
        self.assertEqual(res.fill["octopus"], 14)
        self.assertEqual(res.empty, [("extruder", "heater_pin")])
        self.assertTrue(res.table_warn.startswith("Пины из таблицы разъёмов Octopus Pro"))
        self.assertEqual(len(res.warns), 1)       # PA2 занят мотором YL
        lines = res.protocol()
        self.assertEqual(lines[0], "NAME\t" + res.name)
        self.assertEqual(lines[1][:5], "WARN\t")
        self.assertIn("EMPTY\t[extruder]\theater_pin", lines)
        self.assertEqual(res.all_warnings()[0], res.table_warn)
        self.assertIn("ЗАПОЛНИТЕ", res.path.read_text(encoding="utf-8"))

    def test_out_file_name_override(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        out = os.path.join(d, "custom.cfg")
        res = el.Generator(el.GenOptions(templates=str(INSTALLER / "templates"), board_name="B", board_file="b",
                                         drivers=STOCK_DRV, out=out, template="none")).generate()
        self.assertEqual(res.name, "custom.cfg")
        self.assertTrue(os.path.isfile(out))

    def test_errors_are_exceptions(self):
        with self.assertRaises(el.ElectronicsUsageError):
            self.gen(template="no_such_preset")
        with self.assertRaises(el.ElectronicsError) as cm:
            self.gen(drivers="x=2209")
        self.assertIn("не задан драйвер для", str(cm.exception))
        with self.assertRaises(el.ElectronicsError):
            self.gen(drivers="all=1")


class TestHelpers(unittest.TestCase):
    def test_parse_drivers(self):
        d = el.parse_drivers("all=TMC-2209", True)
        self.assertEqual(d, {m: "2209" for m in ("x", "w", "yl", "yr", "z")})
        d = el.parse_drivers("all=5160pro,e0=5160t_plus", False)
        self.assertEqual(d["x"], "5160")
        self.assertEqual(d["e0"], "5160plus")
        self.assertEqual(el.parse_drivers("", False), {})
        with self.assertRaises(el.ElectronicsError):
            el.parse_drivers("zz=2209", False)

    def test_driver_groups_and_names(self):
        drv = {"x": "2240", "w": "2240", "yl": "2240", "yr": "2240", "z": "2209", "e0": "2209", "e1": "2209"}
        groups = el.driver_groups(drv, list(el.MOTORS))
        self.assertEqual(groups, [(4, "2240"), (3, "2209")])
        self.assertEqual(el.config_name("octopus_pro_v1.1_h723", "none", groups),
                         "electronics_octopus_pro_v1.1_h723_4x2240_3x2209.cfg")
        self.assertEqual(el.config_name("x", "v2", [(7, "5160plus")]), "electronics_x_7x5160tplus_2xH36v2.0.cfg")

    def test_pin_id(self):
        self.assertEqual(el.pin_id("!pa2 # c"), "mcu:PA2")
        self.assertEqual(el.pin_id("^T0CB:pb9"), "T0CB:PB9")
        self.assertIsNone(el.pin_id("probe:z_virtual_endstop"))
        self.assertIsNone(el.pin_id(""))

    def test_block_set_inserts_after_last_option(self):
        b = el.Block("extruder", ["[extruder]", "step_pin: PA1", "", "# конец"])
        b.set("dir_pin", ["dir_pin: PA2"])
        self.assertEqual(b.lines, ["[extruder]", "step_pin: PA1", "dir_pin: PA2", "", "# конец"])
        b.set("step_pin", ["step_pin: PB1", "  продолжение"])
        self.assertEqual(b.lines[1:3], ["step_pin: PB1", "  продолжение"])

    def test_board_naming_uses_registry(self):
        reg = Registry(INSTALLER / "boards")
        self.assertEqual(el.board_naming(reg, "h723"),
                         ("BigTreeTech Octopus Pro v1.1 H723", "octopus_pro_v1.1_h723"))
        self.assertEqual(el.board_naming(reg, "octopus-pro-f446")[1], "octopus_pro_v1.0_f446")
        self.assertEqual(el.board_naming(reg, "spider-v3-h723"), ("", ""))
        self.assertEqual(el.board_naming(reg, "nope"), ("", ""))

    def test_cli_exit_codes(self):
        base = ["--templates", str(INSTALLER / "templates"), "--out-dir", tempfile.gettempdir()]
        rc, out, err = run_new(base + ["--main", "nope"])
        self.assertEqual(rc, 2)
        self.assertIn("gen_electronics.py: error: для платы 'nope' нужны --board-name и --board-file", err)
        rc, out, err = run_new(base + ["--drivers", "all=9999"])
        self.assertEqual((rc, out), (1, ""))
        self.assertEqual(err, "--drivers: драйвер '9999' не из 2130/2160/2208/2209/2240/5160/5160plus\n")


if __name__ == "__main__":
    unittest.main()
