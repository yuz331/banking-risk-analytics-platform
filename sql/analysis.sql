-- Named, read-only queries used by src/analyze_data.py.
-- Amounts ending in _cents remain exact integers. These are activity metrics,
-- not balances, fraud decisions or regulatory thresholds. UTC calendar days.

-- name: overview
SELECT
    (SELECT COUNT(*) FROM customers) AS customers,
    (SELECT COUNT(*) FROM accounts) AS accounts,
    COUNT(*) AS all_transactions,
    COALESCE(SUM(CASE WHEN status = 'POSTED' THEN 1 ELSE 0 END), 0) AS posted_transactions,
    MIN(transaction_time) AS first_transaction_utc,
    MAX(transaction_time) AS last_transaction_utc,
    COALESCE(SUM(CASE WHEN status = 'POSTED' AND direction = 'IN' THEN amount_cents ELSE 0 END), 0) AS inbound_cents,
    COALESCE(SUM(CASE WHEN status = 'POSTED' AND direction = 'OUT' THEN amount_cents ELSE 0 END), 0) AS outbound_cents
FROM transactions;

-- name: daily_activity
SELECT DATE(transaction_time) AS day_utc, COUNT(*) AS transaction_count,
    SUM(CASE WHEN direction = 'IN' THEN amount_cents ELSE 0 END) AS inbound_cents,
    SUM(CASE WHEN direction = 'OUT' THEN amount_cents ELSE 0 END) AS outbound_cents
FROM transactions
WHERE status = 'POSTED'
GROUP BY DATE(transaction_time)
ORDER BY day_utc;

-- name: type_distribution
SELECT transaction_type, direction, COUNT(*) AS transaction_count,
    SUM(amount_cents) AS total_cents
FROM transactions
WHERE status = 'POSTED'
GROUP BY transaction_type, direction
ORDER BY transaction_count DESC, transaction_type, direction;

-- name: top_outbound_accounts
SELECT a.account_id, c.customer_id, c.segment, COUNT(*) AS transaction_count,
    SUM(t.amount_cents) AS outbound_cents
FROM transactions t
JOIN accounts a ON a.account_id = t.account_id
JOIN customers c ON c.customer_id = a.customer_id
WHERE t.status = 'POSTED' AND t.direction = 'OUT'
GROUP BY a.account_id, c.customer_id, c.segment
ORDER BY outbound_cents DESC, a.account_id
LIMIT 10;

-- name: cross_border_activity
SELECT counterparty_country, direction, COUNT(*) AS transaction_count,
    SUM(amount_cents) AS total_cents
FROM transactions
WHERE status = 'POSTED' AND counterparty_country <> 'CA'
GROUP BY counterparty_country, direction
ORDER BY total_cents DESC, counterparty_country, direction;

-- name: large_outbound_transfers
-- CAD 2,000 is an exploratory filter only. This does NOT implement R001,
-- which also requires an account historical median and a 4x comparison.
SELECT transaction_id, account_id, transaction_time AS transaction_time_utc,
    transaction_type, amount_cents, counterparty_country
FROM transactions
WHERE status = 'POSTED' AND direction = 'OUT'
    AND transaction_type IN ('E_TRANSFER', 'WIRE') AND amount_cents > 200000
ORDER BY amount_cents DESC, transaction_id
LIMIT 20;
