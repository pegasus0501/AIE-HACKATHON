DROP TRIGGER IF EXISTS trg_customers_touch;
DROP TRIGGER IF EXISTS trg_orders_touch_customer;
DROP VIEW IF EXISTS v_monthly_revenue;
DROP VIEW IF EXISTS v_orders_clean;
DROP INDEX IF EXISTS idx_orders_amount;
