"""Small shared helpers."""
from __future__ import annotations

CURRENCY_SYMBOLS = "$€£¥"


def to_number(value):
    """Convert a stored amount to a float. Returns None when there is nothing to convert."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    for symbol in CURRENCY_SYMBOLS:
        text = text.replace(symbol, "")
    text = text.replace(",", "").replace(" ", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def month_key(date_text: str) -> str:
    """Return the YYYY-MM prefix of an ISO date string."""
    return date_text[:7]


def format_money(amount: float, currency: str = "USD") -> str:
    return f"{amount:,.2f} {currency}"
