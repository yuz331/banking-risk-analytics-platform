# Interview preparation: explain the project accurately

These answers describe the implemented code and documented choices. Practise
them against the repository. Adapt first-person wording to the work you have
personally reviewed or performed; implementation and testing used AI assistance.

## Business and requirements

**What business problem does the project address?**  
It models how an analyst moves from a transaction pattern to supporting evidence
and a recorded disposition. The value demonstrated is a consistent, explainable
workflow. Real analyst productivity or fraud-loss reduction was not measured.

**Who were the stakeholders?**  
The BRD defines simulated analyst, manager, business analyst and developer roles.
No bank stakeholders were interviewed or approved the requirements. The assumptions,
functional requirements and acceptance criteria are explicit portfolio artifacts.

**How do you show business analysis skills?**  
Walk through a requirement, its acceptance criterion, the implemented behavior
and its evidence. For FR-07, an analyst needs persistent notes: the review API
appends history, updates status atomically, rejects stale forms and is tested in
a new session. The traceability matrix provides the links.

**Why rule-based detection rather than machine learning?**  
The prototype has synthetic inputs and no representative fraud labels. Deterministic
rules make boundaries, baselines and explanations inspectable. A trained model
would need qualified labels, evaluation objectives and representative validation.

## Data and implementation

**Why SQLite?**  
It makes the local demonstration reproducible without a database service and
supports relational keys and transactions. This is not evidence that SQLite fits
a production bank's concurrent workloads. Those requirements would change the design.

**Why store cents rather than decimal-looking floating-point amounts?**  
Integer cents keep storage and sums exact. Historical medians can land on half a
cent, so the code stores twice the median in cents and compares integers. For
example, a CAD 500.005 median has an exact 4x threshold of CAD 2,000.02.

**How do you avoid historical leakage?**  
R001/R004 use a lower-inclusive, upper-exclusive history interval and assess a
whole timestamp batch before adding it. Current, same-time and future transactions
cannot influence the current median or destination history. Tests cover these cases.

**How are duplicate alerts avoided?**  
Logical identity hashes rule ID/version, exact parameters, account and ordered
evidence IDs. Unchanged runs resolve to the same ID and skip insertion. R002 also
groups overlapping qualifying windows into a single event. Parameter changes
create separate results, which remain visible alongside earlier configurations.

**What if a customer has too little history?**  
R001/R004 skip and count the assessment when the minimum history is unavailable.
They do not assign a safe classification. A production policy would need a
qualified cold-start treatment and explicit coverage monitoring.

**How does R003 match incoming and outgoing transactions?**  
For each outgoing, it chooses the most recent unmatched receipt that passes the
amount comparison within the time window. Both records are used once. The greedy
strategy is documented; it does not maximize pair count, aggregate outflows or
prove that the outgoing used those specific funds.

**Is every international transfer flagged?**  
No. R004 requires a non-CA posted outbound wire above the floor, sufficient prior
wire history, and destination novelty or unusual size. Novelty is relative to the
account's history window, not a jurisdiction risk score. Frequency changes are
outside R004 v1.

## Review workflow and validation

**What happens if two reviewers save?**  
The form keeps the last review ID it displayed. The save API checks it while
holding the write transaction. A newer saved review causes a conflict; the stale
submission cannot replace that decision. A successful save appends history and
updates status atomically. Reviewer aliases are not authenticated identities.

**What does the number 282 mean?**  
It is the alert count on one seed-42, 50,000-record, all-scenario synthetic
snapshot: 277/1/2/2 across the four rules. It is neither an accuracy score nor
282 confirmed fraud cases. The separately seeded examples show intended triggers;
the other synthetic hits are not a labeled performance evaluation.

**What did testing establish?**  
Seventy-nine automated tests passed, covering input validation, exact thresholds,
time/history boundaries, oracle comparisons, repeat safety, write rollback and
Streamlit review flows. Browser checks exercised actual charts and evidence tables.
These validate the local behavior, not production capacity or regulatory compliance.

**What would you change for production?**  
Start with actual stakeholders and approved metric/rule definitions. Add controlled
ingestion, authenticated roles, audit/evidence integrity, rule governance and
deployment/operations requirements. Then validate accuracy and review impact on
representative labeled data. Those are additional requirements, not completed work.

**How did you use AI?**  
"This is an AI-assisted portfolio project. I used an assistant for implementation,
documentation and testing, and I am working through the modules and recorded design
decisions. I distinguish the parts I have personally reviewed from the generated
implementation and can show the evidence in the repository."

Replace "working through" with a specific completed action only after doing it:
for example, a local run, a recomputed median, a changed threshold or a test you
have examined. Technical understanding is the useful follow-up to the artifact.
