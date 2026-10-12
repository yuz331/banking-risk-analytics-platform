# Local dashboard and review validation — Phase 4

Date: October 12, 2026. Owner: developer validation for an independent educational
portfolio project. This is simulated analyst acceptance, not bank approval.

## Brief and source

Audience: simulated risk operations analysts inspecting monitoring patterns and
recording local case decisions. Main questions: how much posted activity exists,
what patterns were flagged, which cases remain open, and what evidence supports
a review? Source of truth: one immutable synthetic SQLite transaction snapshot
plus its saved alerts and local append-only review history.

`app.py` is the Streamlit entrypoint. Reads: `src/dashboard_data.py`,
`src/show_alerts.py`. Review writes: `src/review_alerts.py`. Schema:
`sql/schema.sql`. Source amounts are exact CAD cents; timestamps mean UTC.

## Metric and filter contract

| Display | Definition / scope |
| --- | --- |
| Posted transactions | COUNT of POSTED source transactions across the entire snapshot |
| Saved alerts | COUNT of all persisted alerts, including coexisting rule configurations |
| Open alerts | NEW + IN_REVIEW alerts across the snapshot |
| Closed alerts | CLOSED alerts, including no-concern and escalation recommendations |
| Review records | COUNT of all review history entries; not distinct alerts |
| Transaction activity chart | POSTED transaction count grouped by UTC calendar day |
| Inbound/outbound flow totals | SUM of POSTED integer cents by direction, displayed in CAD; not balances |
| Rule/status chart | Saved alert counts grouped by rule ID and status |
| Transaction coverage | Minimum/maximum time of all source transactions |
| Latest saved detection | Maximum alert creation time; unchanged detector reruns do not refresh it |
| Queue filters | Rule, priority, status and exact account ID; affect queue/export only |
| Queue pagination | 25 rows per page, ordered by score descending then event time/ID |
| CSV download | Exactly the current visible queue page; no review notes or full dataset export |

Global cards/charts do not follow queue filters, explicitly labeled in the sidebar.
Source remains synthetic. R001/R004 assessment skips for insufficient history are
explained in the interpretation panel; the UI does not claim every account was
cleared or show an invented coverage rate.

## Review contract

| Outcome | Status after save | Action |
| --- | --- | --- |
| IN_REVIEW | IN_REVIEW | Continue/reopen local work |
| NO_CONCERN | CLOSED | Record local educational disposition |
| ESCALATE | CLOSED | Record recommendation; no external message or regulatory report |

Alias and notes are required, with 60/2000-character limits. Every save creates a
new UUID review row and updates status atomically. The form retains the revision
it was based on. If a newer review exists, the stale save is rejected; explicit
Refresh data reads the latest history. Existing reviews and statuses survive
unchanged source re-import, detector reruns and new Streamlit sessions.

## Automated acceptance results

79 tests passed after installing `requirements.txt`: 70 existing generator,
ingestion and detector tests, plus these nine dashboard/review checks.

| Check | Result |
| --- | --- |
| Save IN_REVIEW, close NO_CONCERN, reopen; read from new connections | Passed; three history rows retained, status consistent |
| Duplicate/stale initial revision | Passed; existing review not overwritten |
| Blank/overlong inputs, invalid outcome, missing alert | Passed; no partial review |
| Status update failure after review insert | Passed; review and status rollback |
| Cards/daily totals/rule distribution; filters/pagination/CSV; closed count | Passed; integer totals reconcile and page scopes match |
| Additive old-schema review setup; nonexistent DB | Passed; source preserved and no missing DB silently created |
| Streamlit charts, filters, evidence, save and fresh session | Passed; actual AppTest element/interaction paths |
| Empty queue and missing snapshot UI | Passed; helpful states without runtime exceptions |
| Stale UI form after another saved review | Passed; newer history preserved |

Streamlit AppTest provides simulated app interactions via the official testing
API: [AppTest documentation](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
Chart objects and native dataframe paths were exercised, not only app startup.
UI tests skip if Streamlit is absent; install requirements to reproduce all 79.

## Larger snapshot and real browser evidence

The seed-42 all-scenario snapshot contains 50,000 transactions and 282 alerts
(277/1/2/2 for R001/R002/R003/R004). A copy was used for dashboard tests.
Saving a demonstration no-concern review on the seeded A00004/R004 alert produced
281 open/1 closed alerts and one review record. A new app session showed the same
closed count and history. The pristine detector snapshot remained unchanged.

The local Streamlit server returned HTTP 200/ok from its health endpoint.
Chromium loaded the real app, rendered both charts, filtered R004/A00004,
displayed source evidence/review controls and rendered at 390px width. Desktop
and narrow screenshots were visually inspected:

- `screenshots/dashboard_overview.jpg` — full-snapshot cards and charts, 1440px.
- `screenshots/alert_review.jpg` — filtered evidence and review form.
- `screenshots/dashboard_mobile.jpg` — stacked readable cards, 390px.

Tested dependencies: Streamlit 1.65.0, pandas 2.2.3, Altair 5.5.0; Python 3.12
in the development container. Declared app target is Python 3.10+. Playwright/
Chromium were used only for development browser QA, not required to run the app.

## Reproduce

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 src/generate_data.py --transactions 50000 --include-r001 --include-r003 --include-r004 --output-dir data/demo
python3 src/load_database.py --data-dir data/demo --db data/demo.db
python3 src/detect_risks.py --db data/demo.db --rule all
python3 -m streamlit run app.py --server.address 127.0.0.1
```

In the sidebar choose `data/demo.db`, then R004/A00004. Inspect explanation and
evidence, enter a demo alias/notes, save no-concern, refresh and restart. Expected:
one closed case, retained notes/history, unchanged transaction data. Choose a new
dataset path if `data/demo.db` already contains different input.

## Practical limitations

- Local app only; no hosted service, user authentication or authenticated audit log.
- Reviews are append-only through supported APIs; direct SQL edits are unsupported.
- Escalation is a stored recommendation and does not contact anyone.
- Alerts are illustrative patterns; scores are not fraud probabilities. Multiple
  configurations coexist, and no alerts is not a risk clearance.
- Sidebar filters scope only the queue; page download is intentionally bounded.
- Read queries rerun after interaction so review state stays fresh; this is not a
  real-time banking feed or production-scale performance claim.
- The prototype provides developer acceptance evidence. Actual bank stakeholder
  approval, production access/security controls and real-data validation are absent.
