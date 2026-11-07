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

CREATE TRIGGER trg_customers_touch
AFTER UPDATE OF email, full_name, phone, region_id, status ON customers
BEGIN
    UPDATE customers SET updated_at = datetime('now') WHERE customer_id = NEW.customer_id;
    INSERT INTO customers_audit (customer_id, action, changed_at)
    VALUES (NEW.customer_id, 'updated', datetime('now'));
END;
