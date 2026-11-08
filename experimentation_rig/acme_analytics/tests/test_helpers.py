from src.helpers import format_money, month_key, to_number


def test_to_number_plain():
    assert to_number("12.50") == 12.5


def test_to_number_symbol_and_commas():
    assert to_number("$1,234.50") == 1234.5


def test_to_number_whitespace():
    assert to_number("  7.25 ") == 7.25


def test_to_number_empty_values():
    assert to_number(None) is None
    assert to_number("") is None


def test_to_number_numeric_input():
    assert to_number(3) == 3.0


def test_month_key():
    assert month_key("2024-03-15") == "2024-03"


def test_format_money():
    assert format_money(1234.5) == "1,234.50 USD"
