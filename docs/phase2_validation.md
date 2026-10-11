# Phase 2 validation record

Date: October 11, 2026. Scope: synthetic data, SQLite ingestion and exploratory SQL.
This is a development check, not bank stakeholder UAT or regulatory validation.

## Requirements and evidence

| Requirement | Evidence | Result |
| --- | --- | --- |
| FR-01 valid input loads; duplicate/invalid records reported | Generator plus importer tests; malformed headers, required values, dates, amounts and enum cases | Passed |
| FR-02 customer/account/transaction links resolve | Missing customer/account rejection; SQLite foreign-key enforcement and foreign_key_check | Passed |
| Phase 2 amount accuracy | Integer cents, 0.29 and integer-limit checks; independent CSV-to-SQL sum reconciliation | Passed |
| Phase 2 repeat safety | Identical import is a no-op; changed snapshot rejected and existing DB bytes preserved | Passed |
| Phase 2 analytics | Six queries execute; counts and monetary sums reconcile; PENDING excluded from activity totals | Passed |
| Phase 2 missing DB behavior | Read-only analysis fails without creating a database file | Passed |
| MVP scale: 50,000 valid records | Seed-42 import: 300 customers, 450 accounts, 50,000 transactions | Passed for import only |
| FR-03 through FR-09 / remaining MVP | Detection, priorities, alert UI, reviews, dashboard and export | Not implemented |

## Reproduce

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 src/generate_data.py --transactions 50000 --seed 42 --output-dir data/check
python3 src/load_database.py --data-dir data/check --db data/check.db
python3 src/load_database.py --data-dir data/check --db data/check.db
python3 src/analyze_data.py --db data/check.db --query all
```

Use a fresh output folder/database path if `data/check.db` already contains a
different dataset. Expected: 12 passing tests; first import succeeds; repeated
identical import says unchanged. All six analytical queries return JSON rows.

## Observed large-run results

The seed-42 50,000-transaction validation plus initial import took approximately
0.89 seconds in the development container. SQLite `integrity_check` returned `ok`
and `foreign_key_check` returned no violations. Independent CSV sums matched the
SQL overview and daily totals. A default 1,000-transaction pipeline also passed.

| Metric | Observed value |
| --- | --- |
| Customers | 300 |
| Accounts | 450 |
| All / posted transactions | 50,000 / 50,000 |
| First transaction (UTC) | 2026-01-01 00:00:00 |
| Last transaction (UTC) | 2026-03-31 23:51:00 |
| Inbound CAD | 24,839,084.48 |
| Outbound CAD | 7,694,482.57 |

These values describe an artificial dataset. They do not estimate banking activity,
fraud rates, risk accuracy, or production throughput. Detection runtime and
positive/negative risk-rule tests will be added during Phase 3.
