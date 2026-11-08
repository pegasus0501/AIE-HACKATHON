"""Plain data containers for rows used by the reports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .helpers import to_number


@dataclass
class Customer:
    customer_id: int
    email: str
    full_name: str
    region_id: Optional[int]
    status: str


@dataclass
class Order:
    order_id: int
    customer_id: int
    order_date: str
    amount: Optional[float]
    status: str
    source_system: str


def customer_from_row(row) -> Customer:
    return Customer(row["customer_id"], row["email"], row["full_name"], row["region_id"], row["status"])


def order_from_row(row) -> Order:
    return Order(row["order_id"], row["customer_id"], row["order_date"], to_number(row["amount"]),
                 row["status"], row["source_system"])
