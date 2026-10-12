# Five-minute interview demonstration

Use the English talk track below after practising the local workflow. The project
is independent and AI-assisted; describe the design choices you have personally
reviewed. This demonstration uses simulated analyst roles and synthetic records.

## Preparation

From the repository root, with Python 3.10+:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 src/generate_data.py --transactions 50000 --include-r001 --include-r003 --include-r004 --output-dir data/portfolio
python3 src/load_database.py --data-dir data/portfolio --db data/portfolio.db
python3 src/detect_risks.py --db data/portfolio.db --rule all
python3 -m streamlit run app.py --server.address 127.0.0.1
```

Open `http://localhost:8501`; set **Database path** to `data/portfolio.db`.
Use a new database path if an existing snapshot has different input. If rehearsing
on the same database, prior reviews remain saved, so closed/open counts may differ.
The all-scenario seed-42 alert total is 282; a fresh snapshot begins with all cases NEW.

Keep the [BRD](../../BRD.md), [architecture](architecture.md) and
[traceability matrix](../requirements_traceability.md) available as follow-up tabs.

## Run of show

| Time | Action | English talk track |
| --- | --- | --- |
| 0:00–0:30 | Introduce the project | "This is an independent, AI-assisted banking analytics prototype using entirely synthetic data. It connects documented monitoring requirements to explainable alerts and a persistent analyst review workflow." |
| 0:30–1:05 | Show the overview | "The snapshot contains 50,000 transactions. These cards and charts use the full database. Queue filters below have a separate scope, so the transaction denominator does not change when I inspect a case." |
| 1:05–1:45 | Set Rule R002, Account A00001 | "Here five posted outgoing transfers occur over 40 minutes. The rule uses an inclusive 60-minute rolling window. Overlapping hits are grouped so the same burst does not flood the queue." |
| 1:45–2:25 | Set Rule R001, Account A00002 | "This CAD 5,000 transfer follows five CAD 100 transfers. The baseline uses only earlier records. The saved evidence lets us recompute the median and verify why the amount rule triggered." |
| 2:25–3:05 | Set Rule R003, Account A00003 | "This CAD 10,000 receipt is followed six hours later by a CAD 8,500 outgoing wire. The documented matching strategy pairs each receipt and outgoing once; it identifies a pattern, not the provenance of funds." |
| 3:05–3:40 | Set Rule R004, Account A00004 | "Five earlier wires went to US. The next CAD 3,000 wire goes to JP. It meets the amount floor and destination-novelty condition, while staying below the four-times-median amount condition." |
| 3:40–4:35 | Save a review on the seeded R004 case | "I can record a local outcome and notes. Saving appends history and updates status together. A stale form is rejected if another review has been saved. Escalation is only a stored recommendation." |
| 4:35–5:00 | Show history, then explain validation | "The note persists after refresh and a new session. The repository has 79 passing tests plus browser evidence. These are functional checks on synthetic data; real fraud accuracy and business time savings have not been measured." |

For each rule, leave **Priority** and **Status** at All, enter the exact account ID,
and select the seeded alert by event time if other alerts appear. Open **Detection
parameters and details** to show the exact configuration and reason codes.

## Seeded examples to recognize

| Rule | Account | Trigger time (UTC) | Expected evidence |
| --- | --- | --- | --- |
| R001 | A00002 | Jan 6, 2026, 12:00 | CAD 5,000 trigger + five CAD 100 historical transfers |
| R002 | A00001 | Feb 15, 2026, 10:00–10:40 | Five outgoing e-Transfers |
| R003 | A00003 | Mar 10, 2026, 09:00–15:00 | CAD 10,000 receipt + CAD 8,500 outgoing wire |
| R004 | A00004 | Jan 16, 2026, 12:00 | CAD 3,000 JP wire + five CAD 1,000 US historical wires |

Example review: alias **Demo analyst**, outcome **Close — no concern found**, notes:
"Demonstration only: inspected the prior wires and destination-change evidence in this synthetic case."
This is a local demonstration disposition, not a real investigation outcome.

Click **Refresh data** and inspect **Review history**. Reopening the browser/app
session should show the same saved record. Download the current queue page if
asked about export; explain that the file contains only that page's alerts.

## Rehearsal checklist

- Run all 79 tests with dependencies installed; complete one save/reopen yourself.
- Explain R001's strict comparisons and R002's inclusive time boundary without notes.
- Recompute a sample median/percentage from evidence to demonstrate understanding.
- Be ready to explain the distinction between a trigger, a priority and a review decision.
- Keep screenshots available for screen-sharing or connectivity problems. The
  screenshot snapshot already has one reviewed case; label it as an example copy.
