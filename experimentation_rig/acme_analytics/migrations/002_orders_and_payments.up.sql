CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    amount TEXT,
    currency TEXT,
    status TEXT NOT NULL,
    source_system TEXT NOT NULL
);

CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price TEXT NOT NULL,
    discount_pct REAL
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    paid_at TEXT NOT NULL
);

CREATE TABLE refunds (
    refund_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    customer_id INTEGER,
    amount TEXT NOT NULL,
    refunded_at TEXT NOT NULL
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_payments_order ON payments(order_id);
CREATE INDEX idx_refunds_order ON refunds(order_id);
