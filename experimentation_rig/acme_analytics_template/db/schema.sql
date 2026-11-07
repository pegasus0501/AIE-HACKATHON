-- Current schema (generated from migrations 001-004). Do not edit by hand.

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE customer_addresses (
    address_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    postal_code TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE customer_ltv (
    customer_id INTEGER PRIMARY KEY,
    order_count INTEGER NOT NULL,
    lifetime_value REAL NOT NULL,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    region_id INTEGER REFERENCES regions(region_id),
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    legacy_id TEXT,
    source_system TEXT NOT NULL
);

CREATE TABLE customers_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE TABLE customers_merge_log (
    merge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    survivor_id INTEGER NOT NULL,
    merged_id INTEGER NOT NULL,
    merged_at TEXT NOT NULL,
    details TEXT
);

CREATE TABLE legacy_customer_map (
    map_id INTEGER PRIMARY KEY,
    legacy_id TEXT NOT NULL,
    customer_id INTEGER NOT NULL
);

CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price TEXT NOT NULL,
    discount_pct REAL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    amount TEXT,
    currency TEXT,
    status TEXT NOT NULL,
    source_system TEXT NOT NULL
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    paid_at TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    list_price REAL NOT NULL
);

CREATE TABLE refunds (
    refund_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    customer_id INTEGER,
    amount TEXT NOT NULL,
    refunded_at TEXT NOT NULL
);

CREATE TABLE regions (
    region_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES regions(region_id)
);

CREATE TABLE sessions (
    session_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    login_ts TEXT,
    device TEXT NOT NULL
);

CREATE INDEX idx_addresses_customer ON customer_addresses(customer_id);

CREATE INDEX idx_customers_email ON customers(email);

CREATE INDEX idx_items_order ON order_items(order_id);

CREATE INDEX idx_legacy_map_customer ON legacy_customer_map(customer_id);

CREATE INDEX idx_orders_amount ON orders(amount);

CREATE INDEX idx_orders_customer ON orders(customer_id);

CREATE INDEX idx_payments_order ON payments(order_id);

CREATE INDEX idx_refunds_order ON refunds(order_id);

CREATE INDEX idx_sessions_customer ON sessions(customer_id);

CREATE VIEW v_monthly_revenue AS
SELECT substr(order_date, 1, 7) AS month,
       COUNT(*) AS order_count,
       ROUND(SUM(amount), 2) AS revenue
FROM v_orders_clean
WHERE status NOT IN ('cancelled')
GROUP BY substr(order_date, 1, 7);

CREATE VIEW v_orders_clean AS
SELECT order_id, customer_id, order_date, CAST(amount AS REAL) AS amount,
       currency, status, source_system
FROM orders;

CREATE TRIGGER trg_customers_touch
AFTER UPDATE OF email, full_name, phone, region_id, status ON customers
BEGIN
    UPDATE customers SET updated_at = datetime('now') WHERE customer_id = NEW.customer_id;
    INSERT INTO customers_audit (customer_id, action, changed_at)
    VALUES (NEW.customer_id, 'updated', datetime('now'));
END;

CREATE TRIGGER trg_orders_touch_customer
AFTER INSERT ON orders
BEGIN
    UPDATE customers SET updated_at = datetime('now') WHERE customer_id = NEW.customer_id;
    INSERT INTO customers_audit (customer_id, action, changed_at)
    VALUES (NEW.customer_id, 'order_added', datetime('now'));
END;

CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);
