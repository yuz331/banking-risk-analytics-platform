# Business Requirements Document (BRD)

**Project:** Banking Transaction Monitoring & Risk Analytics Platform  
**Version:** 0.8 (Portfolio and traceability documentation)
**Date:** October 12, 2026
**Project type:** Independent portfolio project — educational prototype  
**Status:** Phases 1–4 implemented — local educational MVP with developer validation; no external bank stakeholder approval

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
| R003 | Posted receipt >=CAD 5,000 followed strictly later by one outbound transfer >=80% of that receipt within 24 hours; one-to-one latest-qualifying matching. |
| R004 | Posted outbound non-CA wire >CAD 2,000, with >=5 prior outbound wires in 90 days, and a new destination in that window OR amount >4x wire-history median. Frequency change detection is deferred. |

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

Implementation note: the BRD remains at repository root. `docs/UAT.md`, rule
specifications, data dictionary, `docs/user_stories.md` and
`docs/requirements_traceability.md` document the implemented workflows and checks.
The case study, architecture and presentation material are in `docs/portfolio/`.

## 12. Open Questions (To Resolve During Build)

- R003's incoming floor and outbound proportion are resolved in section 16; future expansion to aggregated outflows remains open.
- R001/R004 minimum-history treatment is resolved in sections 15/17; dashboard display of skipped assessments remains to be designed.
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

## 15. Phase 3 Progress — R001, October 11, 2026

- R001 v1 evaluates POSTED outbound E_TRANSFER/WIRE transactions against the
  account's preceding 30-day history, requiring at least five prior eligible rows.
  Baseline interval: [trigger time minus 30 days, trigger time); current,
  same-timestamp and future transactions are excluded. Too little history is
  counted and skipped, not assigned a safe/risky classification.
- Trigger remains strict: amount >CAD 2,000 AND amount >4x historical median.
  Thresholds/history parameters are configurable. Integer comparisons preserve
  exact half-cent medians for even counts. One qualifying transaction/configuration
  produces one alert with all baseline source IDs plus the trigger.
- `alert_details` stores exact median, history count/times and trigger ID without
  changing existing R002 rows. Shared storage preserves deterministic alert IDs,
  timestamps, status and evidence on reruns. Rule details and evidence are atomic.
- FR-03 now covers two of four rules. FR-04/FR-05 have R001 and R002 evidence;
  CLI filtering includes rule ID. Review workflow, dashboard and export are pending.
- Optional generator flag `--include-r001` provides a five-transfer CAD 100 baseline
  followed by CAD 5,000. Default generation is unchanged; use a new snapshot path
  for the optional dataset. Scenario labels are never inputs to detection.
- All 39 tests passed. Optional-seed 50,000-row run: 276 R001 alerts in about 0.13s,
  1 R002 alert in about 0.09s; both repeated with zero new alerts. All R001 baselines
  and evidence sets were independently recomputed. See `docs/R001_rule_spec.md`.

## 16. Phase 3 Progress — R003, October 11, 2026

- R003 v1 uses same-account POSTED incoming E_TRANSFER/WIRE/DIRECT_DEPOSIT/
  CASH_DEPOSIT receipts >=CAD 5,000 and outgoing E_TRANSFER/WIRE transfers.
  Default outbound threshold is >=80% of one receipt; time condition is strictly
  after receipt and <=24 hours. Thresholds and window are configurable.
- Chronological outgoing transfers choose the latest qualifying unmatched receipt,
  with transaction ID ordering for timestamp ties. Same-time receipts are not
  prior receipts. Both records are used once per rule/configuration. This is a
  documented timing/amount heuristic, not fund provenance or maximum matching.
- Evidence contains exactly the matched pair. Rule details record incoming/outgoing
  IDs, exact cents and elapsed seconds. Illustrative fixed score 70 maps to HIGH.
  Alert, evidence and details share one transaction and remain unchanged on reruns.
- `--rule all` now runs three rules; all configurations/overrides are checked before
  any detection writes. Existing default R002 CLI behavior is preserved.
- Optional generator flag `--include-r003` reserves a CAD 10,000 receipt and
  CAD 8,500 transfer six hours later. Existing default/R001-only outputs are
  unchanged. Use a new snapshot path for new scenario combinations.
- FR-03 now covers three of four rules, with positive/negative automated tests.
  R004, dashboard, review workflow and export remain pending.
- All 53 tests passed. 50,000-row snapshot with both optional flags: R001 277,
  R002 1, R003 2 alerts; R003 ran in approximately 0.28s. All planted scenarios
  matched evidence. Full-dataset independent R003 pairing matched both events;
  all three reruns produced zero new alerts. See `docs/R003_rule_spec.md`.

## 17. Phase 3 Progress — R004 and four-rule completion, October 11, 2026

- R004 v1 evaluates same-account POSTED outbound non-CA WIRE candidates >CAD 2,000
  against >=5 previous POSTED outbound wires in 90 days. Domestic wires contribute
  to the baseline. Interval [candidate time minus 90 days, candidate time) excludes
  the entire current timestamp batch and future records. Insufficient history is
  counted and skipped, not classified as safe.
- Either destination absent from that window OR amount >4x its wire median triggers
  one alert; both signals share one alert. Exact integer comparisons preserve
  half-cent medians. Thresholds/history parameters are configurable. Cross-border
  frequency change detection is deferred; novelty is not a country risk rating.
- Details retain trigger ID/country, history count/times, exact median, known
  countries and reason codes. Evidence includes all baseline wires plus the trigger.
  One signal scores 60/MEDIUM; both score 80/HIGH. These are teaching heuristics.
- Optional `--include-r004` seeds five CAD 1,000 wires to US followed by CAD 3,000
  to JP. Previous generator variants remain unchanged. Each CSV now writes to a
  temporary file and replaces its target only after a complete successful write;
  this protects individual files, not an entire multi-file dataset transaction.
- FR-03/FR-04/FR-05 are implemented for all four rules, with positive/negative tests,
  deterministic deduplication and persistent evidence. FR-06 has CLI filters and
  drill-down; the dashboard, FR-07 review workflow, FR-08 trends UI and FR-09 export
  remain pending. MVP completion still requires those later-phase deliverables.
- All 70 tests passed. Seed-42 50,000-row all-scenario snapshot: R001 277, R002 1,
  R003 2, R004 2 alerts. All four planted scenarios matched evidence; all repeated
  rules added zero alerts. All 604 R004 candidates were independently assessed.
  Exact baseline/reason/evidence and database integrity checks passed. See
  `docs/R004_rule_spec.md` for definitions, limitations and recorded timings.

## 18. Phase 4 Progress — October 12, 2026

- `app.py` implements the local Streamlit dashboard with full-snapshot volume,
  saved/open/closed alerts, daily posted activity and rule/status breakdown.
  Rule/priority/status/account filters apply to a paginated queue, not global
  overview cards/charts. All metrics use the existing SQLite snapshot.
- Alert drill-down shows explanation, parameters, rule details and source evidence.
  CSV export downloads the visible queue page with its documented bounded scope.
- `reviews` stores an append-only history through the supported app/API: reviewer
  alias, notes, outcome and UTC timestamp. Saving atomically updates alert status.
  IN_REVIEW stays open; NO_CONCERN/ESCALATE close the local case. Escalation sends
  no messages. Closed cases can be reopened with another IN_REVIEW review.
- Optimistic revision checks reject stale forms. Existing Phase 3 databases receive
  additive review schema setup; supported re-import and detection preserve reviews.
  Aliases are local labels, not authenticated identity or a tamper-proof audit log.
- FR-06/FR-07/FR-08/FR-09 now have local dashboard, review, chart and page-export
  implementations. All MVP success criteria have developer evidence, including
  browser screenshots; institutional/user stakeholder approval is not claimed.
- 79 automated tests passed (70 existing plus nine review/dashboard checks).
  A 50,000-row/282-alert app smoke test, fresh-session persistence, real server
  health, Chromium rendering/filtering and desktop/narrow visual inspection passed.
  See `docs/UAT.md` for definitions, tests and practical limitations.

## 19. Portfolio Documentation — October 12, 2026

- Case study, architecture/module map, five-minute demonstration, interview Q&A
  and project resume wording are available in `docs/portfolio/`.
- Simulated user stories and requirement-to-code/test traceability link the BRD
  to implemented local behavior and recorded acceptance evidence.
- Project ownership is presented as independent, AI-assisted development using
  synthetic data. The documents distinguish functional validation from unmeasured
  fraud accuracy, business savings and production experience.
- This update adds documentation only; detector/UI behavior and the previously
  verified 79-test implementation are unchanged.
