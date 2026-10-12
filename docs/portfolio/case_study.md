# Case study: explainable banking transaction monitoring

**Project owner:** Yuzhan Gao  
**Type:** Independent portfolio prototype, built with AI-assisted development  
**Stack:** Python, SQLite, SQL, Streamlit, pandas, Altair

## Problem and objective

When transaction activity is viewed record by record, patterns across time can be
hard to inspect. An analyst needs both a consistent trigger and the transactions
behind it to make a review decision. This project models that workflow with
synthetic banking data: validate transactions, detect explainable patterns,
prioritize alerts, inspect evidence, and retain review outcomes.

The project combines an interest in banking service workflows with computer science
and management training. Its simulated user roles and requirements are documented
assumptions; they were not elicited from an actual bank's stakeholders.

## From requirements to working behavior

The [BRD](../../BRD.md) defines nine functional requirements, from validated import
to review notes and export. The implementation separates CSV generation, data
validation, relational storage, detection, dashboard queries and review writes.
This makes individual requirements visible in both code and acceptance tests.

| Monitoring rule | Implemented behavior |
| --- | --- |
| Unusual amount | Transfer >CAD 2,000 and >4x prior 30-day transfer median, requiring five historical rows |
| High velocity | At least five posted outgoing transfers within an inclusive 60-minute rolling window; overlapping hits are grouped |
| Rapid in/out | Receipt >=CAD 5,000 followed by one outgoing transfer >=80% within 24 hours, using documented one-to-one pairing |
| Cross-border wire | Non-CA wire >CAD 2,000, with five prior wires in 90 days, and a new destination or amount >4x historical wire median |

Each saved alert includes rule/version, exact parameters, an explanation, priority
and linked source evidence. Historical rules exclude current, same-time and future
transactions. CAD amounts are stored as integer cents; median comparisons preserve
half-cent precision where necessary.

The dashboard supports filtered, paginated review and evidence drill-down. Saving
a review appends notes/outcome/history and updates alert status in one transaction.
A revision check rejects a stale form, and prior reviews remain available after
refresh, detector reruns and a new application session.

## Development results

| Evidence | Observed result |
| --- | --- |
| Reproducible synthetic dataset | 50,000 transactions, 300 customers, 450 accounts |
| All-scenario seed-42 alerts | R001 277; R002 1; R003 2; R004 2 |
| Unchanged detection repeat | Zero additional logical alerts across all four rules |
| Automated validation | 79 passing tests, including boundary, history, persistence and Streamlit interaction checks |
| Browser validation | Real charts and evidence/review controls rendered; desktop and 390px screenshots inspected |

## Design judgment and limits

SQLite and batch processing keep the local demo reproducible. Rules were chosen
for explanation and testability; the scoring is illustrative, not a fraud probability.
R003 uses a single-transfer pairing heuristic, and R004 checks destination novelty
and amount rather than frequency. Sparse history is skipped and disclosed.

The outcome is a working educational workflow with traceable requirements and
development evidence. Real fraud accuracy, analyst time savings and production
capacity were not measured. The most useful next step would be qualified feedback
on alert explanations, historical coverage and review usability.

**Explore:** [Architecture](architecture.md) · [Traceability](../requirements_traceability.md)
· [Five-minute demonstration](demo_script.md) · [Validation record](../UAT.md)
