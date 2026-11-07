from src.models import customer_from_row, order_from_row


def test_order_from_row_parses_amount(conn):
    row = conn.execute("SELECT * FROM orders ORDER BY order_id LIMIT 1").fetchone()
    order = order_from_row(row)
    assert order.order_id == row["order_id"]
    assert order.amount is None or isinstance(order.amount, float)


def test_customer_from_row(conn):
    row = conn.execute("SELECT * FROM customers ORDER BY customer_id LIMIT 1").fetchone()
    customer = customer_from_row(row)
    assert customer.customer_id == row["customer_id"]
    assert customer.email == row["email"]
