# Simulated user stories and acceptance criteria

These roles are educational design assumptions, not actual bank stakeholders.
Stories describe the implemented local workflow and link to the BRD requirements.

| ID | Story | Acceptance criteria | BRD |
| --- | --- | --- | --- |
| US-01 | As a simulated data analyst, I need validated, linked transaction data so monitoring uses consistent input. | Invalid/duplicate IDs, bad amounts/dates and unresolved references fail import; inserts are transactional; unchanged import is a no-op. | FR-01, FR-02 |
| US-02 | As a simulated risk analyst, I need configurable patterns so I can inspect why an account was flagged. | All four rules read recorded parameters; seeded positive and boundary-negative cases behave as specified. | FR-03 |
| US-03 | As a simulated reviewer, I need the rule and transaction evidence behind an alert. | A selected alert shows explanation, version, parameters and all linked evidence; R001/R004 show history details, R003 shows pair details. | FR-04 |
| US-04 | As a simulated operations analyst, I need a prioritized queue to choose a case for review. | Score-to-priority mapping is documented; sorting and rule/priority/status/account filters return the intended alerts. | FR-05, FR-06 |
| US-05 | As a simulated reviewer, I need saved decisions and notes so work survives refresh and can be revisited. | Save appends alias/outcome/notes/time and updates status atomically; earlier history persists; stale forms fail; closed cases can reopen. | FR-07 |
| US-06 | As a simulated manager, I need activity and workload summaries to understand the snapshot. | Posted daily counts/flows and saved/open/closed alert counts reconcile; charts remain global when queue filters change. | FR-08 |
| US-07 | As a simulated analyst, I need a portable copy of the cases currently displayed. | Download exports exactly the visible queue page with the stated filters and CSV columns. | FR-09 |

## Example acceptance scenarios

**US-03 / explainability:** Given five prior CAD 100 posted outbound transfers,
when a CAD 5,000 transfer is assessed under default R001 parameters, then the
saved alert identifies the trigger, prior count, exact median and six evidence rows.

**US-05 / stale submission:** Given a form displaying review revision A,
when another review B is saved before that form is submitted, then the stale save
fails and review B/status remain unchanged. Explicit refresh displays current history.

**US-06 / filter scope:** Given the full 50,000-record snapshot and a queue filter
for R004/A00004, when the user inspects that case, then the overview remains the
full-snapshot overview and the queue/export reflect only the selected scope.

Detailed tests, setup and result scope: [UAT](UAT.md).
