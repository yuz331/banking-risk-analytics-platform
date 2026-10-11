# R001 — Unusual Amount, version 1

Implemented October 11, 2026. This is an educational rule, not an institutional
threshold, fraud conclusion or regulatory reporting decision.

## Trigger and baseline

Eligible records: POSTED outbound E_TRANSFER/WIRE transfers, grouped by account.
For each candidate at UTC time t, the baseline contains eligible transfers in
`[t - lookback_days, t)`. Defaults: 30 days, minimum 5 observations.

The candidate and all same-timestamp/future records are excluded. The inclusive
lower boundary includes a transfer exactly 30 days earlier. Assessment is skipped
when the baseline contains fewer than min_history rows; skipped counts are exposed
in the run summary, and skipping does not classify activity as safe.

Flag only if both strict comparisons hold:

- amount_cents > minimum_amount_cents (default 200000, CAD 2,000).
- amount_cents > multiplier * baseline median (default multiplier 4).

All four parameters are positive integers; lookback_days <=3650, minimum_amount_cents
must fit a SQLite integer. Boolean/fractional values are rejected. An account's
e-Transfer/wire amounts are pooled; no customer pooling, direction/type/status
exceptions, minimum age or country filter is added.

Median is represented as twice its value in cents. For even counts, the two middle
integer amounts are summed; for odd counts, the middle amount is doubled. Thus a
CAD 500.005 median is retained exactly, and a 4x threshold is CAD 2,000.02. Amount
CAD 2,000.02 does not exceed it; CAD 2,000.03 does. Comparisons never use floats.

All eligible historical transfers, including earlier alerted transfers, remain in
the baseline. There is no exclusion based on human review outcomes yet.

## Implementation and persistence

SQL selects eligible source rows ordered by account, timestamp and transaction ID.
An account scan maintains a chronological deque and sorted amounts, removes
expired history, and evaluates a whole timestamp batch before adding its members.
This avoids history leakage through same-time ID ordering. Sorted-list insertion
cost grows with per-account history size; this is a batch portfolio prototype.

One qualifying candidate produces one alert per rule configuration. Alert ID hashes
rule/version, parameters, account and ordered evidence IDs. Reruns on the immutable
snapshot/config skip existing IDs, preserving status, timestamps and evidence.
Changed configurations coexist with prior alerts. A multi-rule `--rule all` run uses
one transaction per rule, not a single transaction covering all rules.

Evidence comprises every baseline transaction plus the candidate. `alert_details`
contains trigger_transaction_id, history_count, exact median_twice_cents and first/
last history timestamps. This distinguishes baseline evidence from the trigger.
Alert event_start/end are the trigger timestamp; peak_count=1; evidence_count is
history_count+1. Source evidence remains linked to the immutable snapshot, not copied.
Alert, evidence and details are saved atomically.

Score: `min(100, 60 + 10 * (floor(amount / median) - multiplier))`.
This exact integer-ratio heuristic produces MEDIUM (60) near the threshold, HIGH
at 70+, and caps at 100. Priorities use the shared LOW <40, MEDIUM 40–69, HIGH >=70
mapping. R001 does not emit LOW. Scores are not calibrated probabilities.

## Validation

39 repository tests passed, including 13 R001 tests. Coverage includes:

| Case | Verified result |
| --- | --- |
| Five CAD 100 history rows, CAD 5,000 transfer | One HIGH alert, median CAD 100, 6 evidence rows |
| Amount equals CAD 2,000 or exactly 4x median | No alert; one cent above both qualifies |
| Even count with half-cent median | Exact strict boundary comparison |
| Four historical rows | Skipped despite a large transfer |
| Same-time/future rows | Excluded from the current baseline |
| Transfer exactly 30 days earlier / one second older | Included / expires |
| Other accounts, IN, bill payments, non-posted statuses | Cannot complete the baseline |
| WIRE history mixed with e-Transfer | Included |
| Identical rerun / changed multiplier | No new alert / distinct result retained |
| Detail write failure | Alert and evidence rolled back |
| Invalid parameters | Rejected before opening/creating the database |
| Optional seeded generator, minimum count, reproducibility | Detected without labels; flag requires >=11 transactions |
| 50 random small datasets | History/medians/hits match independent brute-force oracle |

Additional development verification compared new default generator files with the
prior seed-42 dataset byte-for-byte. Existing R002 ID, time, status and evidence
were unchanged after the shared-storage upgrade.

## 50,000-row optional-seed run

| Metric | Observed value |
| --- | --- |
| Customers / accounts / transactions | 300 / 450 / 50,000 |
| Eligible outbound transfers | 8,689 |
| R001 skipped for insufficient history | 3,379 |
| R001 events / first new alerts | 276 / 276 |
| R001 first runtime | Approximately 0.134 seconds |
| R002 events / first new alerts | 1 / 1 |
| R002 first runtime | Approximately 0.091 seconds |
| Repeated R001 / R002 new alerts | 0 / 0 |

The seeded R001 trigger was T0003056 on A00002 at 2026-01-06 12:00 UTC: CAD 5,000
versus median CAD 100 from five baseline transfers (HIGH, score 100). All 276
R001 baselines, comparisons and evidence sets were independently recalculated
using SQL date predicates and Fraction medians. SQLite integrity/foreign keys
and unchanged source re-import passed.

These counts reflect the artificial generator, including pooled wire/e-Transfer
amounts, not actual fraud counts or accuracy. Genuine false-positive rates require
representative labeled data and qualified review. The minimum history of five
is a teaching choice; sparse activity is frequently skipped. Runtime is development
evidence and cannot be extrapolated to production.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 src/generate_data.py --transactions 50000 --include-r001 --output-dir data/r001demo
python3 src/load_database.py --data-dir data/r001demo --db data/r001demo.db
python3 src/detect_risks.py --db data/r001demo.db --rule all
python3 src/show_alerts.py --db data/r001demo.db --rule R001 --account A00002 --with-evidence --limit 1
python3 src/detect_risks.py --db data/r001demo.db --rule all
```

Choose a fresh path if that database contains different CSV input. The optional
seed reserves six transactions within the requested count; the existing R002 seed
reserves five. Detection reads only database transactions, not scenario labels.
This records the R001 milestone. R003 is now implemented (see `R003_rule_spec.md`);
the current suite has 53 passing tests. R004, dashboard and review workflow remain pending.
