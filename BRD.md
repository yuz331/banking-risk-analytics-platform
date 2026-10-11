# Business Requirements Document (BRD)

**Project:** Banking Transaction Monitoring & Risk Analytics Platform  
**Version:** 0.3 (R002 implementation update)
**Date:** October 11, 2026  
**Project type:** Independent portfolio project — educational prototype  
**Status:** Partially implemented — generation, SQLite, SQL exploration and R002 alerts complete; R001/R003/R004, review workflow and dashboard pending

## 1. Business Problem

Financial institutions process high volumes of customer transactions across channels such as e-Transfers, bill payments, deposits, and wires. Reviewing transactions individually is time-consuming, and unusual patterns may not be obvious when activity is viewed in isolation. Risk operations teams need a consistent way to surface potentially unusual patterns and record review outcomes.

## 2. Project Objective

Develop a demonstrable transaction-monitoring prototype that uses **fully synthetic banking data** to:

- Ingest and validate customer, account, and transaction records.
- Detect explainable transaction patterns using configurable SQL/Python rules.
- Generate prioritized alerts for analyst review.
- Display monitoring trends and risk metrics in an interactive dashboard.
- Record review decisions and demonstrate traceability from requirements to tests.

This is an educational prototype, **not** a bank production system, a fraud verdict engine, or a regulatory reporting solution.

## 3. Stakeholders and Users

| Role | Needs |
| --- | --- |
| Risk Operations Analyst | Review alerts, inspect related transactions, document outcomes. |
| Risk / Compliance Manager | Track volumes, priorities, review status, and trend indicators. |
| Business Systems Analyst | Maintain requirements, workflow, data definitions, and UAT evidence. |
| Developer / Data Analyst | Maintain synthetic data pipelines, detection queries, and dashboard. |

These are **simulated project roles**, not actual stakeholders interviewed for this portfolio project.

## 4. Scope

### In scope (MVP)

1. Generate approximately 50,000 synthetic transactions across simulated customers and accounts.
2. Store normalized customer, account, transaction, alert, and review records in SQLite.
3. Implement and document four illustrative monitoring rules:
   - **R001 — Unusual Amount:** transfer noticeably exceeds an account's historical baseline.
   - **R002 — High Velocity:** frequent outbound transfers within a rolling time window.
   - **R003 — Rapid In/Out:** incoming funds followed by substantial outbound movement in a short interval.
   - **R004 — Unusual Cross-border:** atypical international transfer activity relative to prior behavior.
4. Create explainable alert records with rule ID, triggering transactions, score, priority, status, and timestamp.
5. Provide a Streamlit dashboard with summary KPIs, filtering, drill-down, and an alert review queue.
6. Record analyst review notes and dispositions in a persistent local database.
7. Document test cases, run results, and known limitations.

### Out of scope

- Access to real customer data or live banking systems.
- Real-time transaction processing, identity verification, or user authentication.
- Actual fraud determinations, suspicious transaction reporting, or legal advice.
- Production security, regulatory compliance certification, and enterprise-scale deployment.
- Machine learning in the initial version.

## 5. Functional Requirements

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-01 | Load and validate synthetic transaction records | Must | Import completes; invalid and duplicate IDs are reported. |
| FR-02 | Link accounts to customers and transactions | Must | All transaction account IDs resolve to valid accounts. |
| FR-03 | Run four configurable risk detection rules | Must | Seeded scenarios cause the intended rule to trigger. |
| FR-04 | Generate explainable alerts | Must | Each alert identifies its account, rule, supporting transactions, and detection time. |
| FR-05 | Prioritize alerts | Must | Consistent score-to-priority logic is documented and tested. |
| FR-06 | Filter and inspect alerts | Must | Analysts can filter by severity/status and inspect transaction details. |
| FR-07 | Record review outcomes | Should | Notes, disposition, and review time persist after the app restarts. |
| FR-08 | View monitoring trends | Should | Dashboard displays transaction counts, alerts, and rule distribution. |
| FR-09 | Export summary data | Could | User can download a non-sensitive synthetic-data report. |

## 6. Initial Business Rules

These are **illustrative project parameters**, not thresholds adopted by FINTRAC or any financial institution.

| Rule | Proposed demonstration trigger |
| --- | --- |
| R001 | Transaction > 4x account historical median **and** > CAD 2,000. |
| R002 | At least 5 outgoing transfers within 60 minutes for the same account. |
| R003 | Material inbound funds followed by a substantial outbound transfer within 24 hours. Detailed threshold to be defined during implementation. |
| R004 | International transfer with unusual destination/frequency/size versus available account history. Detailed threshold to be defined during implementation. |

Alerts are indicators for **human review**, not proof of wrongdoing. The first release should de-duplicate repeated hits associated with the same event. Rule thresholds should be configurable and documented.

## 7. Data Requirements

Minimum data entities:

- **Customers:** customer ID, segment, onboarding date.
- **Accounts:** account ID, customer ID, account type, opening date.
- **Transactions:** transaction ID, account ID, timestamp, amount in CAD, direction, transaction type, counterparty identifier, counterparty country, transaction status.
- **Alerts:** alert ID, rule ID, account ID, score, priority, created time, status, explanation.
- **Reviews:** review ID, alert ID, outcome, reviewer alias, review notes, review time.

Use consistent time zones and documented currency assumptions. Transaction IDs must be unique; keys must preserve referential integrity. Store all records as **synthetic**; do not upload real banking statements, customer information, passwords, or API keys.

## 8. Non-functional Requirements

- **Usability:** A reviewer can find and inspect a flagged account using the dashboard without writing SQL.
- **Explainability:** Each alert shows the rule and evidence that caused it to be generated.
- **Reliability:** Running detection twice on unchanged inputs does not create duplicate logical alerts.
- **Reproducibility:** Synthetic generation uses a fixed random seed and a documented setup process.
- **Performance:** Record actual import and batch detection runtime for 50,000 transactions; do not claim production throughput.
- **Maintainability:** Separate data generation, detection, dashboard, and tests into modules.

## 9. MVP Success Criteria

1. At least 50,000 valid synthetic transactions are loaded successfully.
2. All four rules run on the dataset and have documented positive and negative test cases.
3. Seeded high-velocity scenarios can be detected and explained.
4. Alerts are de-duplicated for repeated runs on unchanged data.
5. An analyst can filter alerts, inspect evidence, and save a review decision.
6. GitHub README explains setup, architecture, test results, and limitations; screenshots demonstrate the app.

## 10. Assumptions, Risks, and Limitations

- Synthetic data may not reproduce real bank transaction distributions or alert false-positive rates.
- The thresholds are configurable teaching examples and should not be presented as industry standards.
- No stakeholders from an actual bank have approved these requirements.
- This prototype does not determine whether activity is suspicious for regulatory purposes.
- Additional scope (authentication, cloud deployment, machine learning) is deferred until MVP completion.

## 11. Planned Deliverables

- `src/generate_data.py` — synthetic transaction generator.
- `sql/schema.sql` and `sql/analysis.sql` — database and analytical queries.
- `src/detect_risks.py` — detection rules and alert creation.
- `app.py` — Streamlit dashboard and review workflow.
- `tests/` — automated rule and data-validation tests.
- `docs/BRD.md`, `docs/user_stories.md`, `docs/UAT.md` — project documentation.
- `README.md` — setup instructions and portfolio overview.

## 12. Open Questions (To Resolve During Build)

- What exact proportion of an incoming payment should R003 regard as a substantial outbound movement?
- How should accounts with little historical transaction data be handled by R001 and R004?
- What rules will group multiple triggering transactions into a single alert event?
- Should reviewing an alert lock a copy of the original supporting transactions?

---

*Document control: initial, unapproved portfolio-project requirements draft. Update this document as design choices and test results become available.*

## 13. Phase 2 Progress Record — October 11, 2026

- Phase 1: reproducible synthetic generator and an injected R002 scenario implemented.
- Phase 2: `sql/schema.sql`, `sql/analysis.sql`, `src/load_database.py` and
  `src/analyze_data.py` implemented. FR-01/FR-02 are covered by validated import,
  duplicate checks, foreign keys and tests; see `docs/phase2_validation.md`.
- Amounts use integer CAD cents in SQLite; source CSV amounts retain two decimal
  places. All timestamps use the generator's documented UTC convention.
- Unchanged snapshot imports are no-ops. Changed snapshots require a new database
  path to preserve existing records. There is no incremental ingestion in Phase 2.
- Customers, accounts and transactions exist in the current schema. Alerts,
  evidence links and reviews remain Phase 3/4 work; their schema is deferred until
  rule and review designs are resolved.
- A 50,000-transaction import and all 12 current automated tests passed. No risk
  detection accuracy, false-positive rate or production performance is claimed.
- The remaining MVP criteria and open rule-design questions are still pending.

## 14. Phase 3 Progress — R002, October 11, 2026

- R002 v1 detects POSTED outbound E_TRANSFER/WIRE transactions, default >=5 in an
  inclusive 60-minute rolling window. Parameters are configurable; see
  `docs/R002_rule_spec.md` for the resolved R002 grouping and score choices.
- Overlapping qualifying windows sharing transactions are grouped into one event.
  Disjoint windows remain separate. Event evidence can span longer than 60 minutes;
  peak_count records the maximum count in an actual qualifying rolling window.
- `alerts` and `alert_transactions` persist the account, rule version, parameters,
  event times, explanation, score/priority, status, detection time and source IDs.
  Existing Phase 2 databases are upgraded additively.
- Re-running on the same immutable snapshot/configuration generates no duplicate
  alerts and preserves existing status/evidence. Changing rule parameters creates
  a distinct detection result; historical alerts are not retired automatically.
- FR-03 is partially implemented (one of four rules). FR-04 and FR-05 have R002
  evidence. FR-06 has CLI filters/drill-down, with dashboard implementation pending.
  FR-07/FR-08/FR-09 remain pending.
- Source transaction evidence is referenced in the immutable snapshot; frozen
  evidence copies and review locking remain unresolved for a future mutable system.
- All 26 tests passed. On the seed-42 50,000-row snapshot, 8,684 eligible transfers
  produced one alert in about 0.11 seconds, with all five planted scenario IDs.
  A repeat produced zero new alerts. This is functional evidence, not model accuracy.
