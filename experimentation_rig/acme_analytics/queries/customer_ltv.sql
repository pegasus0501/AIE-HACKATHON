SELECT customer_id,
       COUNT(*) AS order_count,
       ROUND(SUM(CAST(amount AS REAL)), 2) AS lifetime_value
FROM orders
WHERE status NOT IN ('cancelled', 'pending')
GROUP BY customer_id
