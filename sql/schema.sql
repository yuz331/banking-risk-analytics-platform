-- Phase 2: synthetic source data. All timestamps are UTC; amounts are CAD cents.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY NOT NULL,
    segment TEXT NOT NULL CHECK (segment IN ('PERSONAL', 'SMALL_BUSINESS')),
    onboarding_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    account_type TEXT NOT NULL CHECK (account_type IN ('CHEQUING', 'SAVINGS')),
    opening_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    transaction_time TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (typeof(amount_cents) = 'integer' AND amount_cents > 0),
    direction TEXT NOT NULL CHECK (direction IN ('IN', 'OUT')),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN (
        'E_TRANSFER', 'BILL_PAYMENT', 'DIRECT_DEPOSIT', 'DEBIT_PURCHASE',
        'WIRE', 'CASH_DEPOSIT', 'ATM_WITHDRAWAL'
    )),
    counterparty_id TEXT NOT NULL,
    counterparty_country TEXT NOT NULL CHECK (
        length(counterparty_country) = 2 AND counterparty_country GLOB '[A-Z][A-Z]'
    ),
    status TEXT NOT NULL CHECK (status IN ('POSTED', 'PENDING', 'FAILED', 'REVERSED'))
);

CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account_time
    ON transactions(account_id, transaction_time);
CREATE INDEX IF NOT EXISTS idx_transactions_time ON transactions(transaction_time);

-- Phase 3: persisted detection results. Review workflow remains a later phase.
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY NOT NULL,
    rule_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    parameters_json TEXT NOT NULL,
    event_start_utc TEXT NOT NULL,
    event_end_utc TEXT NOT NULL,
    peak_count INTEGER NOT NULL CHECK (peak_count > 0),
    evidence_count INTEGER NOT NULL CHECK (evidence_count >= peak_count),
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    priority TEXT NOT NULL CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH')),
    created_time_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW' CHECK (status IN ('NEW', 'IN_REVIEW', 'CLOSED')),
    explanation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_transactions (
    alert_id TEXT NOT NULL REFERENCES alerts(alert_id),
    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    PRIMARY KEY (alert_id, transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_account ON alerts(account_id);
CREATE INDEX IF NOT EXISTS idx_alerts_priority_status ON alerts(priority, status);

-- Rule-specific details, added without changing previously saved R002 alerts.
CREATE TABLE IF NOT EXISTS alert_details (
    alert_id TEXT PRIMARY KEY NOT NULL REFERENCES alerts(alert_id),
    details_json TEXT NOT NULL
);
