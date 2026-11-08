from src import procedures


def test_refresh_customer_ltv_writes_rows(conn):
    written = procedures.refresh_customer_ltv(conn)
    customers_with_orders = conn.execute("SELECT COUNT(DISTINCT customer_id) FROM orders").fetchone()[0]
    assert written == customers_with_orders


def test_set_customer_status(conn):
    customer_id = conn.execute("SELECT MIN(customer_id) FROM customers").fetchone()[0]
    procedures.set_customer_status(conn, customer_id, "inactive")
    status = conn.execute("SELECT status FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()[0]
    assert status == "inactive"
