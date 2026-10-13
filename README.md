# vendor-lockin-ledger

Score how hard it would be to walk away from each proprietary dependency you run.
Feed it a JSON inventory; it returns a 0–10 lock-in score, an A–E replaceability
grade, and concrete de-risking actions per dependency. If you buy or embed
vendor software and need an auditable exit-cost view, this is for you. If you
only use open-source libraries with healthy forks, you likely don't need it.

## Problem

Lock-in is invisible until the renewal email arrives. Teams discover that their
billing vendor holds their data in a closed format, exposes no standard API, and
has a 36-month contract — all at once, during a migration deadline. Procurement
spreadsheets track spend, not **exit cost**. There was no small, offline,
deterministic tool that turns a dependency list into a graded replaceability
report you can put in front of an architect or an auditor.

## How it works

Each dependency is scored on five factors (0–2 each, total 0–10):

| Factor | 0 | 1 | 2 |
|---|---|---|---|
| `proprietary` | open source | — | closed source |
| `data_export` | open format | partial | closed format |
| `api_standard` | open/standard API | partial | proprietary API |
| `substitutes` | many vendors | some | none |
| `contract_lock_months` | 0 | 1–24 | >24 |

Grades: **A** ≤2 (replaceable), **B** ≤4 (low risk), **C** ≤6 (watch),
**D** ≤8 (high lock-in), **E** ≤10 (critical). Any D or E makes the CLI exit 1,
so it drops straight into CI. Every factor scoring 2 emits a targeted
suggestion (abstraction layer, contractual export path, fallback vendor list…).

## Quickstart (~2 min)

```bash
# 30 s: score a single worst-case dependency
cat > /tmp/dep.json <<'EOF'
{"dependencies": [{"name": "acme-billing", "proprietary": true,
  "data_export": "closed", "api_standard": "proprietary",
  "substitutes": "none", "contract_lock_months": 36}]}
EOF
python vendor_lockin_ledger.py check /tmp/dep.json   # exit 1, grade E

# 30 s: read the rubric
python vendor_lockin_ledger.py explain

# 1 min: full JSON report for CI
python vendor_lockin_ledger.py check inventory.json --format json
```

Optional fields default to the middle of each scale (`partial` / `some`),
so a bare `{"name": "x"}` entry scores 3 (B). Grades use `<=` boundaries:
a score of exactly 2 is still A.

## Why not X?

- **Procurement dashboards / vendor-scorecard SaaS** (e.g. the Gartner-tier
  vendor-management platforms): they track spend, SLAs and renewals. They do
  not model technical exit cost per dependency, and they are themselves a
  vendor you can get locked into.
- **Vendor-Performance-Analysis** (Polo-04) and similar notebook projects:
  excellent EDA on *procurement* performance — margins, bulk purchasing,
  inventory turnover. Different problem: they rank suppliers by profitability,
  not by how expensive it is to technically replace a software dependency.
- **SBOM tools** (CycloneDX/SPDX generators): they inventory *what* you use,
  including license fields, but emit no exit-cost model, no grading, and no
  "what to negotiate next" output. This tool consumes such an inventory.

## How this differs from Vendor-Performance-Analysis

That project analyzes vendor and inventory performance for retail/wholesale
procurement — underperforming brands, bulk-purchase discounts, stock tied up
in unsold goods — using EDA over transaction data. This repo is a software
supply-chain tool: it takes a declarative JSON inventory of *technical*
dependencies and grades replacement difficulty (data format openness, API
standardness, substitutes, contract terms). One ranks suppliers by commercial
performance; the other grades dependencies by technical exit cost. No shared
code, format, or output.

## Performance

[Measured] On the reference laptop (Windows 10, Python 3.13, single run set
2026-10-13): checking a 200-dependency inventory took **5.9 ms** in-process
(warm) and **331.7 ms** including interpreter start (cold subprocess).
The tool is O(n) in dependency count; memory scales with the report size.

Reproduce:

```bash
python - <<'EOF'
import json, time, tempfile, os, io, contextlib, sys
import vendor_lockin_ledger as m
deps=[{"name":"dep-%04d"%i,"proprietary":i%3==0,
       "data_export":["open","partial","closed"][i%3],
       "api_standard":["open","partial","proprietary"][i%3],
       "substitutes":["many","some","none"][i%3],
       "contract_lock_months":(i*7)%40} for i in range(200)]
p=os.path.join(tempfile.mkdtemp(),"inv.json")
json.dump({"dependencies":deps},open(p,"w",encoding="utf-8",newline=""))
t=time.perf_counter()
for _ in range(50):
    with contextlib.redirect_stdout(io.StringIO()):
        m.main(["check",p,"--format","json"])
print("warm_ms=%.1f"%((time.perf_counter()-t)/50*1000))
EOF
```

## Minimal Fallback

No JSON editor? No script runner? Open `vendor_lockin_ledger.py` and read
`FACTOR_LABELS`, `SUGGESTIONS`, and `grade_score` (all <60 lines combined).
The rubric is the product; the CLI is a convenience. You can score five
dependencies by hand on a whiteboard in ten minutes using the table above.

## Design Trade-offs

When priorities conflict, this project picks: **determinism > coverage >
convenience**. Every input maps to exactly one score; there is no ML, no
network, no "AI-ish" weighting. That means the model is crude (five binary-ish
factors), but two auditors running it a year apart get the same answer, and a
grade can be defended line-by-line in a review. Weighted/fuzzy scoring was
rejected because it makes grades unfalsifiable.

## Limits & Second-order Effects

- The five factors ignore data *volume* and integration *breadth* — a tiny
  closed-format widget and a company-wide ERP score the same way. Mitigate by
  running the ledger per service, not per company.
- Grades can become a target: teams may game `data_export=open` without real
  exportability. Treat grades as conversation starters, not compliance proofs.
- Widespread adoption inside one org can create a false sense of safety for
  dependencies nobody bothered to list. An absent row scores nothing.

## FAQ

**Q: Can I add my own factors?**
A: Fork the table — it is 5 dict entries. Keep the 0–2 scale or grades lose meaning.

**Q: Does it talk to vendors or scrape the web?**
A: Never. Input is the JSON you wrote; nothing leaves the machine.

**Q: When NOT to use this?**
A: When your real question is "which vendor is cheapest?" (use procurement
analytics) or "is this npm package maintained?" (use SBOM/health tools).
This tool answers one narrow question: *how expensive is it to leave?*

## [Core Assumptions]

1. Software exit cost is dominated by data portability, API openness,
   substitute availability, and contract terms — not by licence fees alone.
2. A 0–2 ordinal scale per factor is granular enough for decisions yet coarse
   enough to be filled in consistently by different people.
3. The JSON inventory is maintained by humans who know the vendors; the tool
   cannot discover lock-in facts by itself.
4. Exit-1-on-D/E is the desired CI behavior; strict gates are more useful
   than noisy warnings for this artifact class.

Confidence: **High (≥80%)** that the factor model is directionally correct for
typical SaaS dependencies — each factor maps to a well-documented lock-in
mechanism. **Medium (60–79%)** that the specific 0–2 weights fit your context;
tune the table before institutional use.

*Data and measurements as of 2026-10-13.*

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [session-token-hygiene](https://github.com/chenhz01/session-token-hygiene) · [docs-info-leak-scan](https://github.com/chenhz01/docs-info-leak-scan) · [data-classification-schema](https://github.com/chenhz01/data-classification-schema)
