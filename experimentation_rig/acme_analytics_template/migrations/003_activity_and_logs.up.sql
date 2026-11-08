CREATE TABLE sessions (
    session_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    login_ts TEXT,
    device TEXT NOT NULL
);

CREATE TABLE legacy_customer_map (
    map_id INTEGER PRIMARY KEY,
    legacy_id TEXT NOT NULL,
    customer_id INTEGER NOT NULL
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

CREATE TABLE customer_ltv (
    customer_id INTEGER PRIMARY KEY,
    order_count INTEGER NOT NULL,
    lifetime_value REAL NOT NULL,
    refreshed_at TEXT NOT NULL
);

CREATE INDEX idx_sessions_customer ON sessions(customer_id);
CREATE INDEX idx_legacy_map_customer ON legacy_customer_map(customer_id);
