# R002 — High Velocity, version 1

Implementation date: October 11, 2026. Independent educational prototype.
Parameters and scores are illustrative, not financial institution or regulator standards.

## Business decision and scope

Surface concentrated outbound transfer activity for human review. The alert does
not conclude that a customer committed fraud. Eligible records must have:

- The same account ID.
- `status = POSTED` and `direction = OUT`.
- `transaction_type` E_TRANSFER or WIRE.

Bill payments, purchases, withdrawals, deposits, incoming transfers and non-posted
records do not count. There is no amount/country filter or customer-level pooling.

## Rolling window and grouping

Defaults: `min_count = 5`, `window_minutes = 60`; config: `config/rules.json`.
The minimum count must be an integer >=2 and window minutes an integer >=1.
CLI overrides are recorded in each alert's parameters.

1. SQL selects eligible rows sorted by account, UTC timestamp and transaction ID.
2. For each account, a two-pointer scan visits every eligible transaction and
   counts all earlier/current records no more than window_minutes before it.
   The time boundary is inclusive; a 60-minute span qualifies, 60 minutes +1
   second does not qualify at defaults. Windows cross midnight normally.
3. Each count >=min_count is a qualifying window. Qualifying windows sharing at
   least one evidence transaction are merged transitively. Windows without shared
   transactions form separate events; accounts are never merged.
4. Evidence is the union of records in the grouped qualifying windows. peak_count
   is the largest count in an actual rolling window; evidence_count can be larger.

Example: transfers at minutes 0,15,30,45,60,75,90 qualify repeatedly. They form one
event spanning 90 minutes, with 7 evidence transactions and peak_count 5. This
does not assert that all seven occurred within one hour.

## Persistence, explanation and score

`alerts` stores the account, rule/version, serialized parameters, event start/end,
peak/evidence counts, score, priority, actual UTC creation time, status and
explanation. `alert_transactions` links all evidence source IDs. The source
snapshot remains immutable through the supported importer; direct SQL updates to
source records are unsupported and evidence is not frozen separately.

Alert ID is SHA-256 over the rule ID/version, canonical parameters, account ID
and ordered evidence IDs. Identical input/configuration repeats resolve to the
same ID. A conflict skips insertion, preserving existing status, creation time and
evidence. Alert/evidence inserts share a transaction; failure rolls them back.
Configuration changes have different IDs and coexist with prior results; there
is no automatic retirement of earlier configurations' alerts.

Score: `min(100, 60 + 10 * (peak_count - min_count))`.
Priority mapping: LOW <40; MEDIUM 40–69; HIGH >=70. At defaults, a peak of five
scores 60 (MEDIUM), six scores 70 (HIGH), and nine scores 100 (HIGH). R002 does
not emit LOW alerts. Scores are teaching heuristics, not calibrated probabilities.

## Acceptance and observed evidence

All 26 repository tests passed, including 14 R002 tests:

| Case | Expected and verified result |
| --- | --- |
| Five qualifying transfers across exactly 60 minutes | One alert, peak 5, score 60, five evidence records |
| Four transfers / five spanning 61 minutes | No alert |
| IN, purchase, bill payment, PENDING, FAILED, REVERSED | Excluded |
| WIRE mixed with E_TRANSFER | Counts toward the same threshold |
| Six transfers within 50 minutes | One merged alert, peak/evidence 6, score 70 |
| Nine spaced transfers across 120 minutes | One event, evidence 9, peak 5 |
| Two disjoint bursts and another account | Three separate events |
| Midnight crossing and identical timestamps | Detected with deterministic ordering |
| Identical rerun | Zero new alerts; ID/time/status/evidence unchanged |
| Changed threshold | Distinct configuration results retained |
| Evidence insert failure | No partially saved alert |
| Missing DB / invalid config | Clear failure without creating a missing DB |
| Score boundaries and large burst | Priority mapping correct; score capped at 100 |
| 100 random small datasets | Window/grouping results match independent brute-force oracle |
| Generator's planted R002 case | Detected without reading scenario labels |

The seeded-scenario check is included among the 14 tests; the table lists some
individual checks within shared test methods.

Seed-42 50,000-row run:

- 8,684 eligible transfers; one grouped event; five evidence records.
- Account A00001, 2026-02-15 10:00–10:40 UTC; MEDIUM, score 60.
- Evidence IDs: T0025260, T0025265, T0025269, T0025272, T0025277.
- First detection approximately 0.107 seconds including additive schema creation
  and persistence; repeat approximately 0.124 seconds with zero new alerts.
- SQLite integrity/foreign-key checks, evidence counts and evidence account links
  passed. Unchanged CSV re-import preserved the alert and evidence.

Runtime depends on environment. Synthetic records and one planted event do not
estimate false-positive/false-negative rates or production capacity. This section
records the R002 milestone before R001 was added. R001 is now implemented (see
`R001_rule_spec.md`), R003 and R004 are implemented (see their rule specs).
The dashboard remains pending. Current suite: 70 passing tests; the original
default generator output and saved R002 IDs remain unchanged.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 src/generate_data.py --transactions 50000 --seed 42 --output-dir data/r002check
python3 src/load_database.py --data-dir data/r002check --db data/r002check.db
python3 src/detect_risks.py --db data/r002check.db
python3 src/show_alerts.py --db data/r002check.db --account A00001 --with-evidence
python3 src/detect_risks.py --db data/r002check.db
```

Use a fresh database path if that snapshot already exists with different input.
CLI inspection is read-only. Dashboard filters, analyst review notes and dispositions
will be implemented later.
