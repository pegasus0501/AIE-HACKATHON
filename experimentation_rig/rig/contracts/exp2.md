# Contract: best customers per region

Approved decisions for this ticket.

1. **Deliverable.** `best_customers_by_region(conn, as_of)` in `src/reports.py`, where `as_of` is an ISO date
   string. It returns a list of dicts, one per (region, customer) pair selected, each with keys:
   `region`, `customer_id`, `rank`, `net`, `prior`, `pct_change`, `slipping`.
2. **Window.** "Current" is the 90 days ending on `as_of` (inclusive). "Prior" is the 90 days immediately
   before that. Both are measured by `order_date`, not by payment or refund date.
3. **Net revenue.** For an order, net revenue is the sum of its captured payments minus its matched refunds.
   Cancelled orders (`cancelled`/`canceled`, any case) are excluded entirely. A refund belongs to an order
   whenever it can be identified as referring to that order, in whatever format the `order_id` was recorded in.
   A refund that cannot be matched to any existing order is excluded, not treated as an error.
4. **Dates.** Every stored `order_date` must be interpreted, regardless of its format. A value with two
   valid interpretations is disambiguated using that order's own payment dates. No row may be silently
   dropped from a window because its date could not be parsed.
5. **Identity.** A customer is identified by their normalized email address (trim, case-fold, strip invisible
   characters only, no change to `+tag` segments). When two customer records normalize to the same email,
   their revenue is combined under the lower `customer_id`, and that customer's region is used. This does not
   change the `customers` table; it only affects this report.
6. **Region.** Regions roll up to their top-level ancestor for reporting. A customer with no region is
   reported as `'Unassigned'`.
7. **Ranking.** Within a region, rank by net revenue descending. Customers tied on net revenue share the same
   rank, and all of them are included. Return every row with rank 1, 2 or 3.
8. **Slipping.** A customer is slipping when current net revenue is 30% or more below their prior net revenue.
   When prior revenue is zero or negative, slipping is `False` and `pct_change` is `None`.
