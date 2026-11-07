SELECT substr(order_date, 1, 7) AS month,
       ROUND(SUM(CAST(amount AS REAL)), 2) AS revenue
FROM orders
WHERE status <> 'cancelled'
GROUP BY substr(order_date, 1, 7)
ORDER BY month
