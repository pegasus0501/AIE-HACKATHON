# Contract: numeric order amounts

Approved decisions for this ticket.

1. **Deliverable.** A new migration numbered 005 with an up file and a down file in `migrations/`. It is applied by
   the existing runner (`python -m src.migrate up`).
2. **Result.** `orders.amount` becomes a numeric (`REAL`) column. Every stored value has exactly two decimals.
   Rounding rule: round half up to two decimals.
3. **Rows.** Every order survives. The row count is unchanged and no other column of `orders` changes.
4. **Values that are not trustworthy amounts.** Anything in the old column that cannot be converted, or that
   does not represent a real amount, must never be dropped or turned into zero silently. The new column holds
   `NULL` for it, and the original text is recorded in a quarantine table:
   `orders_amount_quarantine(order_id INTEGER, original_amount TEXT, reason TEXT)`, one row per such order.
   A value that was already `NULL` stays `NULL` and is not quarantined.
5. **Reconciliation.** Row count and per-source totals must reconcile: for every `source_system`, the sum of the
   converted amounts of an order set must match the sum of those orders' line items, within rounding.
6. **Dependent objects.** Every view, index and trigger that existed before the migration must exist afterwards
   with the same name and behavior.
7. **Down file.** It restores the text column, including the original text of quarantined values, and leaves the
   other objects in place.
