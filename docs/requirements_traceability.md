# Requirements-to-implementation traceability

Scope: the local educational MVP in [BRD](../BRD.md), with developer evidence in
[UAT](UAT.md). All requirements below have implemented local behavior. The records
do not claim actual bank stakeholder acceptance or production compliance.

| Requirement | Code / artifact | Evidence and scope |
| --- | --- | --- |
| FR-01 Validate and load synthetic records | [Importer](../src/load_database.py) | [Database tests](../tests/test_database.py): headers, empty values, duplicates, dates/amounts, unchanged/different snapshots |
| FR-02 Link customers, accounts and transactions | [Schema](../sql/schema.sql), importer | Foreign keys and unresolved-reference tests; chronology validated before source inserts |
| FR-03 Four configurable risk rules | [Registry](../src/detect_risks.py), [config](../config/rules.json), rule modules | [R001 tests](../tests/test_unusual_amount.py), [R002 tests](../tests/test_detect_risks.py), [R003 tests](../tests/test_rapid_in_out.py), [R004 tests](../tests/test_cross_border.py): positive/negative boundaries, history/pairing and seeded inputs |
| FR-04 Explainable alerts | [Alert storage](../src/risk_storage.py), [inspection](../src/show_alerts.py), [app](../app.py) | Persisted rule/parameters/reasons/source IDs; complete baseline or pair evidence; browser drill-down |
| FR-05 Prioritize alerts | Storage priority mapping and individual rule scores | Priority boundaries, score caps and R004 single/both-signal tests; illustrative scores, not probabilities |
| FR-06 Filter and inspect | [Queue reads](../src/dashboard_data.py), app | Pagination/filter/query tests and Streamlit/browser evidence; queue filters are separate from global overview |
| FR-07 Persist review outcomes | [Review API](../src/review_alerts.py), reviews table, app | [Review/UI tests](../tests/test_reviews_dashboard.py): save, reopen, new connections/session, stale form and rollback |
| FR-08 Monitoring trends | Dashboard queries and charts | Daily counts/flows and rule/status distribution reconcile; chart objects and real browser render paths checked |
| FR-09 Export summary data | Queue CSV export and download control | Current visible page rows/columns match export; no full-snapshot or regulatory export claim |

## Non-functional evidence

| Requirement | Implemented evidence | Practical limit |
| --- | --- | --- |
| Usability | Filtered queue, evidence drill-down, review form and readable desktop/narrow screenshots | Developer/browser checks, not actual analyst usability research |
| Explainability | Saved thresholds, rule version, narrative and evidence links | Pattern explanations require real-world context |
| Reliability | Deterministic identities, unchanged repeat checks and atomic writes | Immutable snapshot workflow; no live incremental ingestion |
| Reproducibility | Fixed seed, optional labeled scenarios and pinned app dependencies | Generated datasets are local and need regeneration on a new clone |
| Performance measurement | Recorded 50,000-row import/detection runs | Observed development timings, including variability; not capacity benchmarks |
| Maintainability | Separate generation, import, rule, storage, read and UI modules | No production deployment or migration framework |

## Follow one requirement during an interview

For FR-07, open the BRD row, then `save_review` and the review schema. Show how
the expected revision is checked, the history row is appended and the status is
updated inside one transaction. In the dashboard, save/reopen a case and read
the history after refresh. Finish with the stale-form and write-failure tests.
This demonstrates a requirement, implementation choice and observable acceptance result.
