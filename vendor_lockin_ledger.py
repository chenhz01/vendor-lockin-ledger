# -*- coding: utf-8 -*-
"""vendor-lockin-ledger — score proprietary dependency lock-in risk.

Pure standard library. Input: JSON dependency inventory. Output: per-dependency
replaceability grade (A..E), factor breakdown, and portfolio summary.
Exit codes: 0 = no high-risk findings, 1 = D/E grade present, 2 = usage/input error.
"""
import argparse
import json
import sys

DATA_EXPORT = ("open", "partial", "closed")
API_STANDARD = ("open", "partial", "proprietary")
SUBSTITUTES = ("many", "some", "none")
GRADES = ("A", "B", "C", "D", "E")

FACTOR_LABELS = {
    "proprietary": "proprietary vendor (closed source)",
    "data_export": "data export path (open/partial/closed)",
    "api_standard": "API standardness (open/partial/proprietary)",
    "substitutes": "ecosystem substitutes (many/some/none)",
    "contract_lock_months": "contract lock-in duration",
}

SUGGESTIONS = {
    "proprietary": "wrap the vendor SDK behind an internal interface so it stays swappable",
    "data_export": "contract for a documented data-export path in an open format",
    "api_standard": "prefer vendors exposing open/standard APIs; adapter for the rest",
    "substitutes": "keep a vetted fallback vendor list and re-test it quarterly",
    "contract_lock_months": "negotiate shorter terms or explicit exit clauses",
}


def validate_dep(dep, index):
    if not isinstance(dep, dict):
        raise ValueError("dependency #%d must be a JSON object" % index)
    name = dep.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("dependency #%d needs a non-empty string 'name'" % index)
    for key, allowed in (("data_export", DATA_EXPORT),
                         ("api_standard", API_STANDARD),
                         ("substitutes", SUBSTITUTES)):
        val = dep.get(key)
        if val is not None and val not in allowed:
            raise ValueError("dependency %r: %s=%r must be one of %s"
                             % (name, key, val, "/".join(allowed)))
    months = dep.get("contract_lock_months", 0)
    if isinstance(months, bool) or not isinstance(months, int) or months < 0:
        raise ValueError("dependency %r: contract_lock_months must be a non-negative int" % name)
    return dep


def factor_scores(dep):
    proprietary = bool(dep.get("proprietary", False))
    return {
        "proprietary": 2 if proprietary else 0,
        "data_export": DATA_EXPORT.index(dep.get("data_export", "partial")),
        "api_standard": API_STANDARD.index(dep.get("api_standard", "partial")),
        "substitutes": SUBSTITUTES.index(dep.get("substitutes", "some")),
        "contract_lock_months": (0 if dep.get("contract_lock_months", 0) <= 0
                                 else (1 if dep.get("contract_lock_months", 0) <= 24 else 2)),
    }


def grade_score(score):
    if score <= 2:
        return "A"
    if score <= 4:
        return "B"
    if score <= 6:
        return "C"
    if score <= 8:
        return "D"
    return "E"


def grade_verb(grade):
    return {"A": "replaceable", "B": "low risk", "C": "watch",
            "D": "high lock-in", "E": "critical lock-in"}[grade]


def assess(dep, index):
    validate_dep(dep, index)
    scores = factor_scores(dep)
    score = sum(scores.values())
    grade = grade_score(score)
    suggestions = [SUGGESTIONS[k] for k, v in scores.items() if v >= 2]
    return {
        "name": dep["name"],
        "score": score,
        "max_score": 10,
        "grade": grade,
        "verdict": grade_verb(grade),
        "factors": scores,
        "suggestions": suggestions,
    }


def analyze(doc):
    if not isinstance(doc, dict):
        raise ValueError("top-level JSON must be an object")
    deps = doc.get("dependencies")
    if not isinstance(deps, list):
        raise ValueError("top-level object needs a 'dependencies' array")
    results = [assess(dep, i) for i, dep in enumerate(deps)]
    n = len(results)
    avg = round(sum(r["score"] for r in results) / n, 2) if n else 0.0
    counts = {g: sum(1 for r in results if r["grade"] == g) for g in GRADES}
    blocked = counts["D"] + counts["E"]
    report = {
        "tool": "vendor-lockin-ledger",
        "summary": {"dependencies": n, "portfolio_avg": avg,
                    "grades": counts, "high_risk": blocked},
        "dependencies": results,
    }
    report["verdict"] = ("blocked: %d high lock-in dependencies" % blocked
                         if blocked else "portfolio replaceability acceptable")
    return report


def render_text(report):
    lines = ["vendor-lockin-ledger report", "=" * 28]
    for r in report["dependencies"]:
        lines.append("%s  score=%d/10  grade=%s (%s)" % (r["name"], r["score"], r["grade"], r["verdict"]))
        for s in r["suggestions"]:
            lines.append("    -> %s" % s)
    s = report["summary"]
    lines.append("summary: %d deps, portfolio avg %.2f/10, grades %s, high-risk %d"
                 % (s["dependencies"], s["portfolio_avg"],
                    "/".join("%s:%d" % (g, s["grades"][g]) for g in GRADES), s["high_risk"]))
    lines.append("verdict: %s" % report["verdict"])
    return "\n".join(lines)


def render_explain():
    lines = ["factor rubric (each factor 0..2, total 0..10):"]
    for key, label in FACTOR_LABELS.items():
        lines.append("  %-22s %s" % (key, label))
    lines.append("  grades: A<=2 B<=4 C<=6 D<=8 E<=10; D/E block (exit 1)")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="vendor-lockin-ledger",
        description="Score proprietary dependency lock-in risk from a JSON inventory.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check", help="assess a dependency inventory JSON")
    p_check.add_argument("file", help="inventory JSON path")
    p_check.add_argument("--format", choices=("text", "json"), default="text")
    sub.add_parser("explain", help="print the factor rubric")
    args = parser.parse_args(argv)

    if args.cmd == "explain":
        print(render_explain())
        return 0

    try:
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            doc = json.load(fh)
    except OSError as exc:
        print("error: cannot read %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print("error: invalid JSON in %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    try:
        report = analyze(doc)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 1 if report["summary"]["high_risk"] else 0


if __name__ == "__main__":
    sys.exit(main())
