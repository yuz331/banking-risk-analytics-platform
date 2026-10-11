# Banking Transaction Monitoring & Risk Analytics Platform

An independent educational portfolio project showcasing banking transaction data, SQL, Python, and risk monitoring requirements. **This is a prototype, not a banking or regulatory reporting system. All generated records are synthetic.**

## Progress

- [x] Business requirements document (`BRD.md`)
- [x] Phase 1 — synthetic CSV transaction generator
- [x] Phase 1 — automated generator tests
- [x] Phase 2 — normalized SQLite database, validated import and SQL exploration
- [x] Phase 3 — R002 high-velocity detection, persisted alerts and evidence
- [ ] Phase 3 — four explainable risk detection rules
- [ ] Phase 4 — Streamlit dashboard, case review and UAT

## Phase 1: Run the generator

Install Python 3.10+ and open a terminal in this repository's folder. No third-party packages are needed for the current generator.

```bash
python3 src/generate_data.py
```

This creates `data/customers.csv`, `data/accounts.csv`, `data/transactions.csv` and `data/injected_scenarios.csv` with 300 customers, 450 accounts, and 1,000 transactions. A reproducible R002 test case adds five outgoing e-Transfers from account `A00001` within 40 minutes.

For a larger run:

```bash
python3 src/generate_data.py --transactions 50000
```

Run the automated tests:

```bash
python3 -m unittest discover -s tests -v
```

Use `--seed 42` (default) to reproduce the same dataset, or provide a different integer seed. Use `--output-dir mydata` to choose the destination.

All dates and times in CSV files are illustrative and stored in UTC. `amount_cad` is formatted with two decimal places. The artificial customer and account identifiers do not identify real people.

Generated CSVs under `data/` are ignored by Git. The scenario labels provide **test input**, not model performance evidence. R002 detection is implemented below; R001, R003 and R004 remain pending. Rule R002 is an illustrative prototype criterion, not a regulatory reporting threshold.

## Phase 2: Load SQLite and explore activity

Run from the repository root, using Python 3.10+. SQLite is included with Python;
no pandas, database server or third-party packages are required.

```bash
python3 src/generate_data.py --transactions 50000
python3 src/load_database.py
python3 src/analyze_data.py --query overview
```

The importer reads the three source CSVs and creates `data/banking.db`. It validates
headers, required values, duplicate IDs, linked customer/account IDs, allowed
categories, dates and positive CAD amounts with at most two decimal places.
Accounts cannot open before customer onboarding, and transactions cannot occur
before account opening. Errors identify the file and row where applicable;
validation failure leaves the database untouched. Valid inserts share one transaction.

An identical import reports `Already loaded (unchanged)` without adding duplicate
rows. A changed snapshot is refused to preserve existing records. For example,
to try another seed, use a separate database:

```bash
python3 src/generate_data.py --transactions 50000 --seed 7 --output-dir data/seed7
python3 src/load_database.py --data-dir data/seed7 --db data/seed7.db
python3 src/analyze_data.py --db data/seed7.db --query overview
```

The generator overwrites CSVs in its chosen output folder. Choose a new output
folder when keeping previous CSV snapshots. Generated CSVs under `data/` and
local SQLite files/sidecars are ignored by Git. If you choose a CSV output folder
outside `data/`, add it to `.gitignore` before committing.

### Available SQL queries

Queries live in `sql/analysis.sql`; run one by name or use `--query all`.
The CLI prints JSON. Monetary columns ending in `_cents` are integer CAD cents:
`12345` means CAD 123.45.

| Query | What it shows |
| --- | --- |
| `overview` | Customer/account counts, all/posted transaction counts, date range and posted inbound/outbound totals |
| `daily_activity` | Posted transaction count and inbound/outbound totals by UTC day |
| `type_distribution` | Posted count and amount by transaction type and direction |
| `top_outbound_accounts` | Top 10 accounts by posted outbound amount, joined to customer segment |
| `cross_border_activity` | Posted activity with a non-CA counterparty country, grouped by country and direction |
| `large_outbound_transfers` | Top 20 posted outbound e-Transfers/wires above CAD 2,000 |

```bash
python3 src/analyze_data.py --query top_outbound_accounts
python3 src/analyze_data.py --query daily_activity
python3 src/analyze_data.py --query all
```

These queries describe activity. They do not generate alerts. The CAD 2,000
exploration filter does not implement R001's historical-median comparison.
Inbound/outbound sums are flows across synthetic accounts, not account balances,
bank revenue, or a measure of fraud. Non-posted records are excluded from monetary
activity metrics; overview still counts all records and displays their date range.

### Validation evidence

On October 11, 2026, all **12 automated tests passed**. A seed-42 run loaded
300 customers, 450 accounts and **50,000 transactions** in approximately **0.89
seconds**, including CSV validation, on the development container. An identical
re-import made no changes; all six SQL queries ran; daily and overview totals
reconciled to the source CSVs; SQLite integrity and foreign-key checks passed.
The default 1,000-transaction pipeline also passed. Runtime depends on hardware
and is not a production throughput claim. R002 detection evidence is recorded below.

See `docs/data_dictionary.md` and `docs/phase2_validation.md` for design choices
and reproducible checks.

## Phase 3, first rule: R002 high velocity

R002 looks for at least **5 posted outbound e-Transfers/wires within an inclusive
60-minute rolling window for one account**. It merges qualifying windows sharing
transactions into one explainable event and persists it in `alerts`, with evidence
links in `alert_transactions`. It reads transactions, not injected scenario labels.

If you already loaded a database during Phase 2, these commands add the alert
tables automatically and preserve your source records:

```bash
python3 src/detect_risks.py
python3 src/show_alerts.py --account A00001 --with-evidence
```

For a fresh setup, run the Phase 1/2 commands first. All current code uses the Python
standard library. `--db` selects a different existing SQLite snapshot.

The default seed-42 50,000-row dataset yielded **1 event**: account `A00001`,
5 outgoing transfers from 2026-02-15 10:00 to 10:40 UTC, score 60, MEDIUM priority.
Detection processed 8,684 eligible transfers in approximately **0.11 seconds** on
the development container, including initial alert schema creation and persistence.
Repeating detection reported 0 new alerts and 1 existing alert. The planted
scenario's five transaction IDs matched the saved evidence. Counts can differ
with another seed, dataset size or configuration; this is not accuracy evidence.

### Configure and inspect

Defaults live in `config/rules.json`. Override them for an experiment:

```bash
python3 src/detect_risks.py --min-count 6 --window-minutes 30
python3 src/show_alerts.py --priority HIGH --status NEW --limit 20
python3 src/show_alerts.py --account A00001 --with-evidence
```

Alerts retain the rule version and parameters used. Changed configurations produce
separate results; older alerts remain visible. Identical snapshot/configuration
reruns retain IDs, creation timestamps, status and evidence. The inspector is
read-only; editing statuses and saving review notes through a UI remain pending.

R002's illustrative score is `min(100, 60 + 10 * (peak_count - min_count))`.
Scores <40 map to LOW, 40–69 to MEDIUM, and 70–100 to HIGH. This rule produces
MEDIUM/HIGH alerts and its score is not a probability or bank-approved risk rating.

All **26 automated tests passed** after R002 implementation. See
`docs/R002_rule_spec.md` for event grouping, parameter semantics, limitations and
validation evidence. Next: R001 unusual amount detection, then R003/R004 and the dashboard.

See `BRD.md` for the planned business requirements.
