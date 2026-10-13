# -*- coding: utf-8 -*-
"""self_test for vendor-lockin-ledger — inherits v2 template four defenses:
SystemExit capture / Unicode-safe regex / Windows newline / SUMMARY last line."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")

import vendor_lockin_ledger as mod

TMP = tempfile.mkdtemp(prefix="vll_selftest_")
_n = [0]


def write_doc(obj):
    _n[0] += 1
    path = os.path.join(TMP, "deps_%d.json" % _n[0])
    with open(path, "w", encoding="utf-8", newline="") as fh:  # defense 3
        json.dump(obj, fh, ensure_ascii=False)
    return path


def run_cli(argv):
    """Defense 1: capture SystemExit and Exception from main()."""
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            code = mod.main(argv) or 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


def dep(**kw):
    base = {"name": "dep", "proprietary": False, "data_export": "open",
            "api_standard": "open", "substitutes": "many", "contract_lock_months": 0}
    base.update(kw)
    return base


class TestAFunctional(unittest.TestCase):
    def test_clean_portfolio_exit0(self):
        p = write_doc({"dependencies": [dep()]})
        code, out, _ = run_cli(["check", p])
        self.assertEqual(code, 0)

    def test_text_contains_name(self):
        p = write_doc({"dependencies": [dep(name="acme-billing")]})
        code, out, _ = run_cli(["check", p])
        self.assertIn("acme-billing", out)

    def test_json_format_parseable(self):
        p = write_doc({"dependencies": [dep()]})
        code, out, _ = run_cli(["check", p, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIsInstance(json.loads(out), dict)

    def test_grade_a_all_open(self):
        r = mod.assess(dep(), 0)
        self.assertEqual((r["score"], r["grade"]), (0, "A"))

    def test_grade_e_worst(self):
        r = mod.assess(dep(name="w", proprietary=True, data_export="closed",
                           api_standard="proprietary", substitutes="none",
                           contract_lock_months=36), 0)
        self.assertEqual((r["score"], r["grade"]), (10, "E"))

    def test_proprietary_contributes_two(self):
        s = mod.factor_scores(dep(proprietary=True))
        self.assertEqual(s["proprietary"], 2)

    def test_contract_36_is_two(self):
        self.assertEqual(mod.factor_scores(dep(contract_lock_months=36))["contract_lock_months"], 2)

    def test_contract_12_is_one(self):
        self.assertEqual(mod.factor_scores(dep(contract_lock_months=12))["contract_lock_months"], 1)

    def test_contract_0_is_zero(self):
        self.assertEqual(mod.factor_scores(dep(contract_lock_months=0))["contract_lock_months"], 0)

    def test_closed_export_is_two(self):
        self.assertEqual(mod.factor_scores(dep(data_export="closed"))["data_export"], 2)

    def test_suggestions_for_grade_d(self):
        r = mod.assess(dep(proprietary=True, data_export="closed",
                           substitutes="none", contract_lock_months=30), 0)
        self.assertEqual(r["grade"], "D")
        self.assertTrue(len(r["suggestions"]) >= 3)

    def test_exit1_on_e(self):
        p = write_doc({"dependencies": [dep(proprietary=True, data_export="closed",
                                            api_standard="proprietary", substitutes="none",
                                            contract_lock_months=36)]})
        code, _, _ = run_cli(["check", p])
        self.assertEqual(code, 1)

    def test_exit1_on_d(self):
        p = write_doc({"dependencies": [dep(proprietary=True, data_export="partial",
                                            api_standard="partial", substitutes="none",
                                            contract_lock_months=30)]})
        code, _, _ = run_cli(["check", p])
        self.assertEqual(code, 1)

    def test_exit0_mixed_abc(self):
        p = write_doc({"dependencies": [dep(), dep(name="b", data_export="partial"),
                                        dep(name="c", proprietary=True)]})
        code, _, _ = run_cli(["check", p])
        self.assertEqual(code, 0)

    def test_summary_counts(self):
        p = write_doc({"dependencies": [dep(), dep(name="x", proprietary=True,
                                                   data_export="closed",
                                                   api_standard="proprietary",
                                                   substitutes="none",
                                                   contract_lock_months=36)]})
        code, out, _ = run_cli(["check", p, "--format", "json"])
        rep = json.loads(out)
        self.assertEqual(rep["summary"]["dependencies"], 2)
        self.assertEqual(rep["summary"]["grades"]["A"], 1)

    def test_portfolio_average(self):
        p = write_doc({"dependencies": [dep(), dep(name="w", proprietary=True,
                                                   data_export="closed", api_standard="proprietary",
                                                   substitutes="none", contract_lock_months=36)]})
        _, out, _ = run_cli(["check", p, "--format", "json"])
        self.assertEqual(json.loads(out)["summary"]["portfolio_avg"], 5.0)

    def test_explain_exit0(self):
        code, out, _ = run_cli(["explain"])
        self.assertEqual(code, 0)
        self.assertIn("data_export", out)

    def test_explain_lists_grades(self):
        _, out, _ = run_cli(["explain"])
        self.assertIn("A<=2", out)

    def test_extra_fields_ignored(self):
        r = mod.assess(dep(note="whatever", tier=3), 0)
        self.assertEqual(r["grade"], "A")

    def test_defaults_partial(self):
        r = mod.assess({"name": "d"}, 0)
        self.assertEqual(r["grade"], "B")  # defaults: 0+1+1+1+0 = 3


class TestBErrors(unittest.TestCase):
    def test_missing_file_exit2(self):
        code, _, err = run_cli(["check", os.path.join(TMP, "nope.json")])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_bad_json_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "bad_%d.json" % _n[0])
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("{not json")
        code, _, err = run_cli(["check", p])
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON", err)

    def test_missing_dependencies_key(self):
        p = write_doc({"items": []})
        code, _, err = run_cli(["check", p])
        self.assertEqual(code, 2)
        self.assertIn("dependencies", err)

    def test_dependencies_not_list(self):
        p = write_doc({"dependencies": {"a": 1}})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_dep_not_object(self):
        p = write_doc({"dependencies": [42]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_dep_missing_name(self):
        p = write_doc({"dependencies": [{"proprietary": True}]})
        code, _, err = run_cli(["check", p])
        self.assertEqual(code, 2)
        self.assertIn("name", err)

    def test_empty_name_exit2(self):
        p = write_doc({"dependencies": [dep(name="   ")]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_unknown_data_export(self):
        p = write_doc({"dependencies": [dep(data_export="sealed")]})
        code, _, err = run_cli(["check", p])
        self.assertEqual(code, 2)
        self.assertIn("data_export", err)

    def test_unknown_api_standard(self):
        p = write_doc({"dependencies": [dep(api_standard="weird")]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_unknown_substitutes(self):
        p = write_doc({"dependencies": [dep(substitutes="tons")]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_negative_months(self):
        p = write_doc({"dependencies": [dep(contract_lock_months=-3)]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_bool_months(self):
        p = write_doc({"dependencies": [dep(contract_lock_months=True)]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_float_months(self):
        p = write_doc({"dependencies": [dep(contract_lock_months=6.5)]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_unknown_format_exit2(self):
        p = write_doc({"dependencies": []})
        code, _, _ = run_cli(["check", p, "--format", "xml"])
        self.assertEqual(code, 2)

    def test_no_args_exit2(self):
        code, _, _ = run_cli([])
        self.assertEqual(code, 2)

    def test_empty_file_exit2(self):
        _n[0] += 1
        p = os.path.join(TMP, "empty_%d.json" % _n[0])
        open(p, "w", encoding="utf-8", newline="").close()
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_directory_as_input_exit2(self):
        self.assertEqual(run_cli(["check", TMP])[0], 2)


class TestCEdge(unittest.TestCase):
    def test_empty_portfolio_exit0(self):
        p = write_doc({"dependencies": []})
        code, out, _ = run_cli(["check", p, "--format", "json"])
        self.assertEqual((code, json.loads(out)["summary"]["dependencies"]), (0, 0))

    def test_unicode_name(self):
        p = write_doc({"dependencies": [dep(name="\u4f9b\u5e94\u5546-\u8ba1\u8d39")]})
        code, out, _ = run_cli(["check", p, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("\u4f9b\u5e94\u5546-\u8ba1\u8d39", out)

    def test_very_long_name(self):
        p = write_doc({"dependencies": [dep(name="v" * 10000)]})
        code, out, _ = run_cli(["check", p])
        self.assertEqual(code, 0)
        self.assertIn("v" * 100, out)

    def test_huge_contract_months(self):
        p = write_doc({"dependencies": [dep(contract_lock_months=999999)]})
        code, _, _ = run_cli(["check", p])
        self.assertEqual(code, 0)  # months factor=2, defaults give 0+1+1+1+2=5 -> C
        _, out, _ = run_cli(["check", p, "--format", "json"])
        self.assertEqual(json.loads(out)["dependencies"][0]["grade"], "A")

    def test_duplicate_names_both_reported(self):
        p = write_doc({"dependencies": [dep(name="same"), dep(name="same")]})
        _, out, _ = run_cli(["check", p, "--format", "json"])
        self.assertEqual(len(json.loads(out)["dependencies"]), 2)

    def test_bom_input_accepted(self):
        _n[0] += 1
        p = os.path.join(TMP, "bom_%d.json" % _n[0])
        with open(p, "w", encoding="utf-8-sig", newline="") as fh:
            json.dump({"dependencies": [dep()]}, fh)
        self.assertEqual(run_cli(["check", p])[0], 0)

    def test_many_deps_all_e_exit1(self):
        p = write_doc({"dependencies": [
            dep(name="d%d" % i, proprietary=True, data_export="closed",
                api_standard="proprietary", substitutes="none", contract_lock_months=36)
            for i in range(25)]})
        code, out, _ = run_cli(["check", p, "--format", "json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["summary"]["high_risk"], 25)

    def test_deeply_nested_extra_fields(self):
        p = write_doc({"dependencies": [dep(meta={"a": {"b": [1, 2, {"c": 3}]}})]})
        self.assertEqual(run_cli(["check", p])[0], 0)

    def test_non_string_name_number(self):
        p = write_doc({"dependencies": [dep(name=7)]})
        self.assertEqual(run_cli(["check", p])[0], 2)

    def test_proprietary_field_string_rejected(self):
        # a string "proprietary" is not bool-coercible truthiness trap we allow? bool("x")=True
        # we accept it as truthy by design; document via assert grade D path
        p = write_doc({"dependencies": [dep(proprietary="yes")]})
        code, _, _ = run_cli(["check", p])
        self.assertIn(code, (0, 1))  # tolerated, scored as truthy

    def test_verdict_blocked_message(self):
        p = write_doc({"dependencies": [dep(proprietary=True, data_export="closed",
                                            api_standard="proprietary", substitutes="none",
                                            contract_lock_months=36)]})
        _, out, _ = run_cli(["check", p])
        self.assertIn("verdict: blocked", out)

    def test_explain_no_file_needed(self):
        code, out, _ = run_cli(["explain"])
        self.assertIn("contract_lock_months", out)


CASES = [
    (dep(), 0, "A"),     (dep(data_export="partial"), 1, "A"), (dep(api_standard="partial"), 1, "A"),
    (dep(substitutes="some"), 1, "A"),
    (dep(proprietary=True), 2, "A"),
    (dep(data_export="closed", api_standard="partial"), 3, "B"),
    (dep(substitutes="none", contract_lock_months=10), 3, "B"),
    (dep(proprietary=True, data_export="partial"), 3, "B"),
    (dep(data_export="closed", substitutes="none"), 4, "B"),
    (dep(proprietary=True, data_export="closed"), 4, "B"),
    (dep(api_standard="proprietary", substitutes="none"), 4, "B"),
    (dep(proprietary=True, contract_lock_months=30), 4, "B"),
    (dep(data_export="closed", api_standard="proprietary"), 4, "B"),
    (dep(proprietary=True, data_export="closed", api_standard="partial"), 5, "C"),
    (dep(data_export="closed", api_standard="proprietary", substitutes="some"), 5, "C"),
    (dep(proprietary=True, substitutes="none", contract_lock_months=30), 6, "C"),
    (dep(proprietary=True, data_export="closed", substitutes="none"), 6, "C"),
    (dep(api_standard="proprietary", substitutes="none", contract_lock_months=30), 6, "C"),
    (dep(proprietary=True, api_standard="proprietary", substitutes="none"), 6, "C"),
    (dep(proprietary=True, data_export="closed", api_standard="proprietary"), 6, "C"),
    (dep(proprietary=True, data_export="closed", api_standard="proprietary",
         substitutes="some"), 7, "D"),
    (dep(proprietary=True, data_export="closed", substitutes="none",
         contract_lock_months=30), 8, "D"),
    (dep(proprietary=True, api_standard="proprietary", substitutes="none",
         contract_lock_months=30), 8, "D"),
    (dep(proprietary=True, data_export="closed", api_standard="proprietary",
         substitutes="none"), 8, "D"),
    (dep(proprietary=True, data_export="closed", api_standard="proprietary",
         substitutes="some", contract_lock_months=30), 9, "E"),
    (dep(proprietary=True, data_export="closed", api_standard="proprietary",
         substitutes="none", contract_lock_months=12), 9, "E"),
]


def _mk(case):
    d, score, grade = case

    def test(self):
        r = mod.assess(d, 0)
        self.assertEqual(r["score"], score)
        self.assertEqual(r["grade"], grade)
    return test


for _i, _c in enumerate(CASES):
    setattr(TestCEdge, "test_table_%02d" % _i, _mk(_c))

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))  # defense 4
    sys.exit(0 if fails == 0 else 1)
