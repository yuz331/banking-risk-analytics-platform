# R004 — Unusual Cross-border Wire, version 1

Implemented October 11, 2026. Independent educational prototype; thresholds and
priorities are illustrative, not institutional or regulator standards.

## Decision and baseline

Candidates: same-account POSTED outbound WIRE transactions with counterparty
country !=CA. Account's baseline: all prior POSTED outbound WIRE transactions,
including domestic wires, in `[candidate time - wire_lookback_days, candidate time)`.
Current, same-timestamp and future records are excluded. Default lookback 90 days;
at least 5 baseline wires required. Insufficient history is counted and skipped.

For a candidate **strictly greater than CAD 2,000**, trigger when either:

- `NEW_DESTINATION`: its country is absent from that baseline window.
- `UNUSUAL_AMOUNT`: its amount strictly exceeds 4x the baseline wire median.

The OR condition creates one alert, with both reason codes if both apply. A known
country with a normal amount produces no alert. Domestic candidates never trigger.
Incoming wires, e-Transfers and non-posted records do not contribute history.
Foreign transactions below the floor still contribute to future wire history.

Novelty means not seen in this account's window, not never used in its lifetime.
Expired destinations can become new again. Countries are not assigned geographic
risk weights or blacklisted. This prototype's cross-border proxy is counterparty
country, not bank corridor/settlement metadata. All amounts are CAD, not foreign
currency denominations; no FX conversion is used.

## Parameters and exact comparisons

| Parameter | Default | Constraint |
| --- | --- | --- |
| min_wire_history | 5 | Positive integer |
| wire_lookback_days | 90 | Integer 1–3650 |
| wire_multiplier | 4 | Positive integer |
| minimum_cross_border_cents | 200000 | Positive SQLite integer cents |

Boolean/fractional parameters are rejected. The median is stored as twice its
integer-cents value, allowing exact half-cent medians for even counts. The size
comparison is `2 * amount_cents > wire_multiplier * median_twice_cents`; equality
does not trigger. CAD 2,000 equality also does not pass the amount floor.

## Implementation and persistence

SQL orders eligible outbound wires by account, timestamp and transaction ID. The
scan maintains a chronological history deque, sorted integer amounts and country
visit counts, expiring records older than the inclusive lower time boundary.
Country membership disappears only after its last retained visit expires. Each
timestamp batch is assessed before adding any batch members.

One candidate/configuration produces one alert. Identity uses shared rule/version/
parameter/account/ordered-evidence hashing. Evidence includes **all** retained
baseline wires plus the candidate, not only transactions sent to the same country.
Details save trigger ID/country, history count/times, exact median, known countries
and reasons. event_start/end are the trigger timestamp; peak_count=1;
evidence_count=history_count+1. Alert, evidence and details are atomic.

One reason scores 60 (MEDIUM); both score 80 (HIGH). Shared mapping is LOW <40,
MEDIUM 40–69, HIGH >=70. Scores are teaching priorities, not fraud probabilities.
Repeat runs on the immutable snapshot/configuration preserve IDs, timestamps,
status and evidence. Changed configuration results coexist with previous alerts.

## Acceptance evidence

All 70 repository tests passed, including 16 R004 tests:

| Case | Verified result |
| --- | --- |
| Five CAD 1,000 US wires then CAD 3,000 JP wire | One MEDIUM new-destination alert; six evidence rows |
| Known destination, normal amount | No alert |
| Known destination, amount exactly 4x / one cent greater | No alert / amount-only alert |
| New destination and unusual amount | One HIGH alert with both reasons |
| CAD 2,000 / one cent greater | Floor excludes equality / novelty can trigger |
| Domestic large candidate | No R004 alert |
| Even half-cent median | Exact strict comparison |
| Too little history / five domestic prior wires | Skip / eligible cross-border baseline |
| Same-timestamp and future history | Cannot alter current assessment |
| Exactly 90-day-old wire / one second older | Included / expires |
| Multiple visits to one country | Known until last retained visit expires |
| Wrong direction/type/status and another account | Cannot complete the baseline |
| Identical repeat / changed multiplier | Preserved existing result / separate configuration |
| Detail write failure | Alert and evidence rolled back |
| Invalid all-rule config | Rejected before any detector writes |
| Optional seed without labels and minimum counts | Detected; 11 rows alone, 19 with all flags |
| 100 random small datasets | Matches independent historical-baseline oracle |

The table splits some checks within shared test methods. An additional generator
test deliberately fails a CSV write after its first record and verifies the old
target and directory contents remain intact.

## Observed complete four-rule run

Seed 42; 50,000 transactions, 300 customers, 450 accounts, all optional flags enabled.

| Metric | Observed value |
| --- | --- |
| R004 eligible outbound wires (all countries) | 1,237 |
| Non-CA candidates (including small amounts) | 604 |
| Candidates skipped for insufficient wire history | 584 |
| R004 alerts | 2 |
| R004 first runtime | Approximately 0.192 seconds |
| R004 repeat new alerts | 0 |
| R001 / R002 / R003 alerts on this snapshot | 277 / 1 / 2 |
| Total alerts / repeated new alerts across all rules | 282 / 0 |

Seeded trigger T0008647 on A00004 at 2026-01-16 12:00 UTC: CAD 3,000 to JP,
history of five CAD 1,000 US wires, reason NEW_DESTINATION, MEDIUM score 60.
An independent oracle assessed all 604 candidates and reproduced skip counts,
the exact two alerts, baseline medians, known countries, reasons and evidence.
All four planted scenarios matched saved evidence. Database integrity and foreign
keys passed. Regenerated complete CSVs matched the stored snapshot and unchanged
re-import preserved all 282 alerts and evidence.

During validation a source CSV was found incomplete; the importer refused to
overwrite the existing complete database. Regeneration restored the matching
50,000-row snapshot. CSV writing now uses a temporary file and replacement after
successful completion. This protects one target at a time, not all four dataset
files as a single transaction; import only after generation completes.

Earlier generator variants (without R004 flag) remain byte-identical and their
R001/R002/R003 alerts remained unchanged. Observed runtimes vary with environment:
the first complete run took about 0.38s/0.24s/0.43s/0.19s for R001/R002/R003/R004;
one repeated R001 run took about 13.95s while the other repeats stayed below 0.4s.
These measurements are development observations, not a stable throughput claim.

## Limitations and remaining work

- Minimum five-wire history causes many sparse synthetic accounts to be skipped;
  skipping is not a risk clearance. The dashboard should expose that coverage gap.
- Destination novelty and large amount are account-relative patterns requiring
  context, not evidence of wrongdoing or a jurisdiction risk rating.
- Cross-border frequency changes, separate country-specific amount baselines and
  country/corridor risk assessments are outside R004 v1.
- Synthetic counts do not estimate real fraud or false-positive rates. Performance
  needs representative data and separate production engineering work.
- Four rule implementations are complete. Phase 4 now provides the dashboard,
  analyst reviews, trend UI and visible queue-page CSV export. Current suite:
  79 passing tests; see `UAT.md` for the later milestone and remaining limits.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 src/generate_data.py --transactions 50000 --include-r001 --include-r003 --include-r004 --output-dir data/allrulesdemo
python3 src/load_database.py --data-dir data/allrulesdemo --db data/allrulesdemo.db
python3 src/detect_risks.py --db data/allrulesdemo.db --rule all
python3 src/show_alerts.py --db data/allrulesdemo.db --rule R004 --account A00004 --with-evidence
python3 src/detect_risks.py --db data/allrulesdemo.db --rule all
```

Use a new snapshot path if that database contains different data. `--rule R004`
selects this rule only; `--rule all` selects all four. Configs are prevalidated;
each rule saves in its own transaction. Without a selector, R002 remains the default.

`--include-r004` reserves six rows within the total and uses A00004 (highest existing
account if fewer than four). Random outbound wires there through the trigger time
become inbound to isolate the seeded baseline. Scenario labels are test evidence
and never detection inputs. All seed amounts are denominated in CAD.
