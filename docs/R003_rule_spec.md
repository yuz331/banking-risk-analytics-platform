# R003 — Rapid In/Out, version 1

Implemented October 11, 2026. Independent educational prototype; thresholds and
scores are illustrative and do not represent institutional or regulator standards.

## Business behavior

Flag one material incoming receipt followed by one substantial outbound transfer
on the same account, with defaults:

- Receipt amount >=CAD 5,000 (`minimum_inbound_cents=500000`).
- Outbound amount >=80% of that receipt (`outbound_percentage=80`).
- `0 < outbound_time - inbound_time <=24 hours` (`window_hours=24`).

Both must be POSTED. Eligible incoming types: E_TRANSFER, WIRE, DIRECT_DEPOSIT,
CASH_DEPOSIT. Eligible outgoing types: E_TRANSFER, WIRE. Other types/statuses,
other accounts, same-timestamp and earlier outgoing records do not form pairs.
Domestic and international counterparties both qualify; differing counterparty
IDs are not required. An outbound larger than the receipt can qualify.

Amount equality qualifies for both thresholds. Ratio comparison uses exact
integers: `100 * outbound_cents >= outbound_percentage * inbound_cents`.
Thus an incoming CAD 5,000.01 needs at least CAD 4,000.01 at 80%; CAD 4,000.00
is insufficient. There is no floating-point rounding.

Parameters are positive integers, percentage <=100, hours <=8760 and minimum
incoming cents <=SQLite integer maximum. Boolean/fractional values are rejected.

## Pairing and grouping decision

1. SQL selects eligible rows sorted by account, UTC timestamp and transaction ID.
2. For each account, maintain unmatched material receipts within the configured
   window. Expire receipts strictly older than the window.
3. Process outgoing records at a timestamp before adding incoming records at that
   same timestamp. Same-time incoming records cannot masquerade as earlier funds.
4. Each outgoing chooses the **most recent unmatched receipt that meets the amount
   comparison**, skipping more recent receipts whose amount is too large.
   Receipt timestamp/transaction ID determine recency; outgoing timestamp/ID
   determine processing order when timestamps tie.
5. Consume that receipt and save one pair. Each receipt and outgoing is used once
   per rule/configuration. An outgoing with no match consumes nothing.

Example: receive CAD 5,000, then CAD 10,000; outgoing CAD 6,000 matches the older
CAD 5,000 receipt because it fails 80% of CAD 10,000. A later CAD 8,000 outgoing
can match the remaining CAD 10,000 receipt.

This is a deterministic greedy heuristic. It does not enumerate every possible
pair, optimize matching cardinality, allocate partial receipts, sum receipts or
accumulate outgoing transfers. Two CAD 2,500 outflows after CAD 5,000 incoming
do not trigger, because neither individually reaches 80%. Different greedy choices
can yield different pairs/counts; the choice here is explicit and tested.

## Alert, evidence and score

One pair is one logical alert. Evidence is exactly [incoming ID, outgoing ID].
Alert ID uses shared rule/version/parameter/account/ordered-evidence hashing.
Reruns preserve ID, time, status, details and evidence; changed configurations
produce separate historical results. Direct source changes are unsupported.
A transaction may be used by a different rule or configuration.

Event start/end are incoming/outgoing timestamps. peak_count=2 and evidence_count=2
describe the pair, not an R002 velocity peak. Details contain incoming/outgoing
transaction IDs, exact amount cents and elapsed seconds. Score is fixed 70 (HIGH)
for a qualifying R003 v1 pair; this is a teaching priority choice, not fraud odds.
Alert, evidence and details share one transaction; failures roll them back.

The pair establishes a timing/amount pattern, **not actual fund tracing**. Existing
balances and other account movements are not reconstructed. Routine legitimate
payments can satisfy this rule and require context before any risk judgment.

## Acceptance checks

All 53 repository tests passed, including 14 R003 tests:

| Case | Verified result |
| --- | --- |
| Incoming exactly CAD 5,000, outgoing exactly 80%, exactly 24 hours | One HIGH alert, two evidence records |
| Receipt one cent below floor / outgoing one cent below exact ratio | No pair |
| CAD 5,000.01 receipt | CAD 4,000.00 fails; CAD 4,000.01 qualifies |
| Outgoing before/same-time/24h+1s | No pair; +1s and exactly 24h qualify |
| Multiple receipts, latest too large | Latest qualifying older receipt selected |
| Same-time receipts/outgoings | Deterministic ID ordering; incoming batch excluded until strictly later |
| Two outflows against one receipt | Receipt used once |
| Two small outflows reaching 80% only in sum | No aggregated trigger |
| Latest and older receipts both qualify | Latest chosen |
| Wrong type/status or another account | Excluded; eligible cash/direct-deposit/e-Transfer incoming supported |
| Identical repeat / changed percentage | Existing record preserved / separate result |
| Detail insert failure | No partially persisted pair |
| Invalid config in multi-rule CLI | Rejected before an earlier valid rule can write |
| Seeded pair without labels; minimum datasets | Detected; 7 rows needed for R003, 13 with R001 too |
| 100 random small datasets | Matches independent candidate-selection oracle |

The table splits some checks within shared test methods.

## Observed 50,000-row run

Seed 42; both optional scenario flags enabled; 300 customers and 450 accounts.

| Metric | Observed value |
| --- | --- |
| Eligible material receipts | 1,050 |
| Eligible outgoing transfers | 8,690 |
| R003 pairs / first new alerts | 2 / 2 |
| Unmatched receipts | 1,048 |
| R003 first runtime | Approximately 0.278 seconds |
| R003 repeated new alerts | 0 |
| R001 / R002 alerts on this snapshot | 277 / 1 |
| All rules repeated new alerts | 0 |

Seeded account A00003: incoming T0038023 at 2026-03-10 09:00 UTC (CAD 10,000),
outgoing T0038164 at 15:00 UTC (CAD 8,500); elapsed 21,600 seconds, 85% outgoing.
An independent oracle over all eligible source rows matched both R003 pairs,
and evidence/one-use checks passed. All three planted scenarios matched persisted
evidence. SQLite integrity/foreign-key checks passed; unchanged source re-import
preserved all alerts. Earlier default and R001-only CSVs remained byte-identical,
and their existing R001/R002 alert records remained unchanged.

Counts, unmatched receipts and runtime describe artificial inputs, not true risk,
false-positive rates or production capacity. The unmatched count includes expired
and otherwise unpaired receipts; it does not mean those receipts are safe.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
python3 src/generate_data.py --transactions 50000 --include-r001 --include-r003 --output-dir data/r003demo
python3 src/load_database.py --data-dir data/r003demo --db data/r003demo.db
python3 src/detect_risks.py --db data/r003demo.db --rule all
python3 src/show_alerts.py --db data/r003demo.db --rule R003 --account A00003 --with-evidence
python3 src/detect_risks.py --db data/r003demo.db --rule all
```

Use a fresh snapshot path if the database already contains different data. Each
selected rule saves in its own transaction; all configs are validated first.
R003-only: `--rule R003`; no selector continues to default to R002.

`--include-r003` reserves two records within the total and places its pair on
A00003 (highest existing account if fewer than three). Random transactions on
that account from 24 hours before receipt through outgoing time become outbound
domestic bill payments, isolating the demonstration from competing receipts and
outgoings. The generator never changes existing databases. Scenario CSV labels
are test evidence and are not used by detection.

R004, dashboard and analyst review workflow remain pending.
