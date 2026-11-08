-- Convert orders.amount from TEXT to REAL, quarantining anything that is not a trustworthy amount.
DROP VIEW IF EXISTS v_monthly_revenue;
DROP VIEW IF EXISTS v_orders_clean;
DROP INDEX IF EXISTS idx_orders_amount;
DROP INDEX IF EXISTS idx_orders_customer;

CREATE TABLE orders_amount_quarantine (
    order_id INTEGER NOT NULL,
    original_amount TEXT,
    reason TEXT NOT NULL
);

CREATE TEMP TABLE amt_clean AS
SELECT order_id, source_system, amount AS raw,
       replace(replace(replace(replace(replace(amount, char(160), ''), char(8203), ''), char(65279), ''), char(9), ''), ' ', '') AS s1
FROM orders
WHERE amount IS NOT NULL;

CREATE TEMP TABLE amt_stripped AS
SELECT order_id, source_system, raw,
       replace(replace(replace(replace(replace(replace(replace(replace(s1, '$', ''), '€', ''), '£', ''), '¥', ''), 'USD', ''), 'EUR', ''), 'GBP', ''), 'CAD', '') AS s
FROM amt_clean;

CREATE TEMP TABLE amt_norm AS
SELECT order_id, source_system, raw,
       0 AS paren,
       s AS inner
FROM amt_stripped;

CREATE TEMP TABLE amt_norm2 AS
SELECT order_id, source_system, raw, paren,
       CASE source_system
            WHEN 'eu_legacy' THEN replace(replace(inner, '.', ''), ',', '.')
            ELSE replace(inner, ',', '')
       END AS n
FROM amt_norm;

CREATE TEMP TABLE amt_kind AS
SELECT order_id, source_system, raw, n,
       CASE WHEN paren = 1 OR n LIKE '-%' THEN 1 ELSE 0 END AS neg,
       ltrim(ltrim(n, '-'), '+') AS a
FROM amt_norm2;

CREATE TEMP TABLE amt_class AS
SELECT order_id, source_system, raw, neg, a,
       CASE
            WHEN n IN ('-1', '-999') THEN 'placeholder'
            WHEN a = '' THEN 'blank'
            WHEN a NOT GLOB '*[^0-9.]*' AND a GLOB '*[0-9]*' AND length(a) - length(replace(a, '.', '')) <= 1 THEN 'plain'
            WHEN a NOT GLOB '*[^0-9.eE+-]*' AND a GLOB '[0-9]*[eE]*' AND length(a) - length(replace(replace(a, 'e', ''), 'E', '')) = 1 THEN 'sci'
            ELSE 'unconvertible'
       END AS kind,
       substr(a, 1, instr(a || '.', '.') - 1) AS ip,
       substr(a, instr(a || '.', '.') + 1) AS fp
FROM amt_kind;

CREATE TEMP TABLE amt_result AS
SELECT order_id, raw, neg, kind,
       CASE kind
            WHEN 'plain' THEN
                CASE WHEN source_system = 'pos_v2' AND instr(a, '.') = 0 THEN CAST(a AS INTEGER)
                     ELSE CAST(CASE WHEN ip = '' THEN '0' ELSE ip END AS INTEGER) * 100
                          + CAST(substr(fp || '00', 1, 2) AS INTEGER)
                          + CASE WHEN CAST(substr(fp || '000', 3, 1) AS INTEGER) >= 5 THEN 1 ELSE 0 END
                END
            WHEN 'sci' THEN CAST(ROUND(CAST(a AS REAL) * 100) AS INTEGER)
       END AS cents
FROM amt_class;

CREATE TABLE orders_new (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    amount REAL,
    currency TEXT,
    status TEXT NOT NULL,
    source_system TEXT NOT NULL
);

INSERT INTO orders_new (order_id, customer_id, order_date, amount, currency, status, source_system)
SELECT o.order_id, o.customer_id, o.order_date,
       CASE WHEN r.kind IN ('plain', 'sci')
            THEN ROUND((CASE WHEN r.neg = 1 THEN -r.cents ELSE r.cents END) / 100.0, 2)
       END,
       o.currency, o.status, o.source_system
FROM orders o
LEFT JOIN amt_result r ON r.order_id = o.order_id;

INSERT INTO orders_amount_quarantine (order_id, original_amount, reason)
SELECT order_id, raw, kind FROM amt_result WHERE kind NOT IN ('plain', 'sci');

DROP TABLE orders;
ALTER TABLE orders_new RENAME TO orders;

DROP TABLE amt_clean;
DROP TABLE amt_stripped;
DROP TABLE amt_norm;
DROP TABLE amt_norm2;
DROP TABLE amt_kind;
DROP TABLE amt_class;
DROP TABLE amt_result;

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_amount ON orders(amount);

CREATE VIEW v_orders_clean AS
SELECT order_id, customer_id, order_date, CAST(amount AS REAL) AS amount,
       currency, status, source_system
FROM orders;

CREATE VIEW v_monthly_revenue AS
SELECT substr(order_date, 1, 7) AS month,
       COUNT(*) AS order_count,
       ROUND(SUM(amount), 2) AS revenue
FROM v_orders_clean
WHERE status NOT IN ('cancelled')
GROUP BY substr(order_date, 1, 7);

CREATE TRIGGER trg_orders_touch_customer
AFTER INSERT ON orders
BEGIN
    UPDATE customers SET updated_at = datetime('now') WHERE customer_id = NEW.customer_id;
    INSERT INTO customers_audit (customer_id, action, changed_at)
    VALUES (NEW.customer_id, 'order_added', datetime('now'));
END;
