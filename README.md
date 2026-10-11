# Banking Transaction Monitoring & Risk Analytics Platform

An independent educational portfolio project showcasing banking transaction data, SQL, Python, and risk monitoring requirements. **This is a prototype, not a banking or regulatory reporting system. All generated records are synthetic.**

## Progress

- [x] Business requirements document (`BRD.md`)
- [x] Phase 1 — synthetic CSV transaction generator
- [x] Phase 1 — automated generator tests
- [x] Phase 2 — normalized SQLite database, validated import and SQL exploration
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

Generated `data/*.csv` files are ignored by Git. The scenario labels provide **test input**, not model performance evidence. The monitoring engine has not been implemented yet. Rule R002 is an illustrative prototype criterion, not a regulatory reporting threshold.

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
and is not a production throughput claim. Detection runtime is not yet measured.

See `docs/data_dictionary.md` and `docs/phase2_validation.md` for design choices
and reproducible checks. Next: Phase 3 risk rules, explainable alerts and evidence links.

See `BRD.md` for the planned business requirements.
