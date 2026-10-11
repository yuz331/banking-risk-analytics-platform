# Banking Transaction Monitoring & Risk Analytics Platform

An independent educational portfolio project showcasing banking transaction data, SQL, Python, and risk monitoring requirements. **This is a prototype, not a banking or regulatory reporting system. All generated records are synthetic.**

## Progress

- [x] Business requirements document (`BRD.md`)
- [x] Phase 1 — synthetic CSV transaction generator
- [x] Phase 1 — automated generator tests
- [ ] Phase 2 — normalized SQLite database and SQL exploration
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

See `BRD.md` for the planned business requirements.
