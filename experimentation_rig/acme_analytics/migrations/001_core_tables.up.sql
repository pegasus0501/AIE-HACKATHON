CREATE TABLE regions (
    region_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES regions(region_id)
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

CREATE TABLE customer_addresses (
    address_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    postal_code TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    list_price REAL NOT NULL
);

CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_addresses_customer ON customer_addresses(customer_id);
