# Source and alert data dictionary

All records are synthetic. One snapshot spans one currency (CAD). Dates and
timestamps are text in ISO order; timestamps mean UTC without a suffix.

| Table | Field | SQLite type | Meaning / constraints |
| --- | --- | --- | --- |
| customers | customer_id | TEXT | Unique nonempty primary key |
| customers | segment | TEXT | PERSONAL or SMALL_BUSINESS |
| customers | onboarding_date | TEXT | YYYY-MM-DD |
| accounts | account_id | TEXT | Unique nonempty primary key |
| accounts | customer_id | TEXT | Foreign key to customers |
| accounts | account_type | TEXT | CHEQUING or SAVINGS |
| accounts | opening_date | TEXT | YYYY-MM-DD; on/after customer onboarding |
| transactions | transaction_id | TEXT | Unique nonempty primary key |
| transactions | account_id | TEXT | Foreign key to accounts |
| transactions | transaction_time | TEXT | YYYY-MM-DD HH:MM:SS UTC; on/after opening |
| transactions | amount_cents | INTEGER | Positive CAD cents; CSV amount_cad converted with Decimal |
| transactions | direction | TEXT | IN or OUT from the account's perspective |
| transactions | transaction_type | TEXT | E_TRANSFER, BILL_PAYMENT, DIRECT_DEPOSIT, DEBIT_PURCHASE, WIRE, CASH_DEPOSIT, ATM_WITHDRAWAL |
| transactions | counterparty_id | TEXT | Synthetic identifier; not a customer foreign key |
| transactions | counterparty_country | TEXT | Two uppercase letters; generator uses CA, US, GB, JP |
| transactions | status | TEXT | POSTED, PENDING, FAILED, REVERSED; generator currently emits POSTED |

Primary/foreign keys and categorical/amount constraints are enforced by SQLite.
CSV import additionally enforces required values, canonical dates and chronological
relationships. The country check is a format check, not an ISO country registry
lookup. Currency conversion and reversal netting are not implemented; analytics
simply exclude records whose status is not POSTED.

## Why these choices

- **Three source tables:** one customer can have multiple accounts, and one
  account can have multiple transactions. Joins link activity to customer segment.
- **Integer cents:** exact money storage and sums avoid binary floating-point
  rounding. Queries retain integer cents; divide by 100 when displaying CAD.
- **Account/time index:** prepares for rolling account-history queries in Phase 3.
  A timestamp index supports later date filtering; customer index supports joins.
- **Full validated snapshot:** input is checked before a database is opened.
  Inserts are transactional. Identical input is a no-op; different input is
  refused in an existing populated database. No partial updates or automatic reset.
- **Separate scenario labels:** `injected_scenarios.csv` remains test evidence,
  outside the source database. Detection must inspect transactions, not read labels.
- **Read-only exploration:** the query runner opens an existing database in
  read-only mode. It does not create alerts or modify transaction records.

## Phase 3 alert tables

| Table | Fields | Meaning / constraints |
| --- | --- | --- |
| alerts | alert_id | Deterministic primary key from rule, version, parameters, account and ordered evidence IDs |
| alerts | rule_id, rule_version, parameters_json | Detection rule and exact thresholds used |
| alerts | account_id | Foreign key to accounts |
| alerts | event_start_utc, event_end_utc | First/last evidence transaction timestamps; grouped event can exceed one window |
| alerts | peak_count, evidence_count | Maximum rolling-window count; number of linked source transactions |
| alerts | score, priority | 0–100 illustrative score; LOW/MEDIUM/HIGH |
| alerts | created_time_utc | Actual detection/save time in UTC |
| alerts | status | NEW, IN_REVIEW or CLOSED; detection initializes NEW and preserves existing status |
| alerts | explanation | Human-readable trigger and event description |
| alert_transactions | alert_id, transaction_id | Composite primary key; foreign keys to alerts and transactions |

Detection saves an alert and its evidence in one transaction. Evidence is joined
to the immutable source snapshot, not copied. Direct source edits are unsupported.
Rule configuration experiments coexist; inspect parameters when comparing alerts.
The alert reader opens in read-only mode and can filter account, ID, priority and
status. Review notes, dispositions and a review UI are not implemented yet.
