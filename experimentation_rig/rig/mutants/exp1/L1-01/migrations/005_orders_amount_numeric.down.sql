-- Restore orders.amount as TEXT, putting quarantined originals back.
DROP VIEW IF EXISTS v_monthly_revenue;
DROP VIEW IF EXISTS v_orders_clean;
DROP INDEX IF EXISTS idx_orders_amount;
DROP INDEX IF EXISTS idx_orders_customer;

CREATE TABLE orders_old (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    amount TEXT,
    currency TEXT,
    status TEXT NOT NULL,
    source_system TEXT NOT NULL
);

INSERT INTO orders_old (order_id, customer_id, order_date, amount, currency, status, source_system)
SELECT o.order_id, o.customer_id, o.order_date,
       COALESCE(q.original_amount, CASE WHEN o.amount IS NULL THEN NULL ELSE printf('%.2f', o.amount) END),
       o.currency, o.status, o.source_system
FROM orders o
LEFT JOIN orders_amount_quarantine q ON q.order_id = o.order_id;

DROP TABLE orders;
ALTER TABLE orders_old RENAME TO orders;
DROP TABLE orders_amount_quarantine;

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
