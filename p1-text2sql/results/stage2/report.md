# Stage 2: plain SQL accuracy on the clear questions

Gate (pre-registered): test lenient >= 0.50, point estimate. 95% CIs: bootstrap over questions (one reading per clear question, so this is the cluster bootstrap by question). Correct = same results as the gold SQL on both seeds.

| model | test lenient (n) | test strict | gate | dev lenient / strict (n) | valid 1st try | test queries that fail to run | infra errors | latency p50 | tok/s p50 | non-decode time p50 |
|---|---|---|---|---|---|---|---|---|---|---|
| llama3.2:3b | 0.36 [0.16, 0.56] (25) | 0.32 [0.16, 0.52] | FAIL | 0.80 / 0.80 (5) | 1.00 | 6 | 0 | 4.5 s | 15.4 | 0.5 s |
| qwen2.5:3b | 0.36 [0.16, 0.56] (25) | 0.36 [0.16, 0.56] | FAIL | 0.80 / 0.80 (5) | 0.97 | 6 | 0 | 4.7 s | 15.9 | 0.6 s |
| qwen2.5-coder:3b | 0.60 [0.40, 0.80] (25) | 0.60 [0.40, 0.80] | pass | 0.80 / 0.80 (5) | 1.00 | 3 | 0 | 3.8 s | 16.2 | 0.6 s |
| qwen2.5-coder:7b | 0.68 [0.48, 0.84] (25) | 0.64 [0.44, 0.84] | pass | 0.80 / 0.80 (5) | 1.00 | 0 | 0 | 8.1 s | 7.7 | 1.2 s |

## Paired differences, test lenient (row minus column; 95% CI, bootstrap over questions)

| | llama3.2:3b | qwen2.5:3b | qwen2.5-coder:3b | qwen2.5-coder:7b |
|---|---|---|---|---|
| llama3.2:3b |  | +0.00 [-0.20, +0.24] | -0.24 [-0.44, -0.04] | -0.32 [-0.52, -0.12] |
| qwen2.5:3b | +0.00 [-0.24, +0.20] |  | -0.24 [-0.48, +0.00] | -0.32 [-0.52, -0.16] |
| qwen2.5-coder:3b | +0.24 [+0.04, +0.44] | +0.24 [+0.00, +0.48] |  | -0.08 [-0.28, +0.12] |
| qwen2.5-coder:7b | +0.32 [+0.12, +0.52] | +0.32 [+0.16, +0.52] | +0.08 [-0.12, +0.28] |  |

## Failure types (lenient misses, test + dev; test only in brackets)

| model | syntax | schema | filter | date | aggregate | join | shape | timeout | empty | other | unclassified | total | extra columns only (strict miss) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llama3.2:3b |  | 10 (9) | 2 (2) | 2 (2) | 2 (2) | 1 (1) |  |  |  |  |  | 17 (16) | 1 |
| qwen2.5:3b |  | 7 (7) | 6 (6) | 2 (1) |  | 2 (2) |  |  |  |  |  | 17 (16) | 0 |
| qwen2.5-coder:3b |  | 3 (3) | 4 (3) |  | 2 (2) | 2 (2) |  |  |  |  |  | 11 (10) | 0 |
| qwen2.5-coder:7b |  | 3 (2) | 4 (4) |  | 2 (2) |  |  |  |  |  |  | 9 (8) | 1 |

## Every failure

### llama3.2:3b (17)

- **dev/dc2** `schema`: What was the total revenue in April 2026?  
  note: used products.list_price instead of order_items.unit_price
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-04-01' AND '2026-04-30'`
  - pred: `SELECT SUM(T1.list_price * T2.quantity) AS revenue FROM products AS T1 INNER JOIN order_items AS T2 ON T1.product_id = T2.product_id INNER JOIN orders AS T3 ON T2.order_id = T3.order_id WHERE T3.status NOT IN ('cancelled') AND T3.order_date BETWEEN '2026-04-01' AND '2026-04-30'`
  - seed 0: no column with the expected values

- **test/c01** `schema`: What was the revenue from customers based in Germany in 2025?  
  note: alias T2 does not exist; also no cancelled filter
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' AND c.country = 'Germany'`
  - pred: `SELECT SUM(CASE WHEN T2.country = 'Germany' THEN T1.value END) AS revenue FROM (SELECT SUM(order_items.quantity * order_items.unit_price) AS value FROM orders JOIN order_items ON orders.order_id = order_items.order_id JOIN customers ON orders.customer_id = customers.customer_id WHERE orders.order_date BETWEEN '2025-01-01' AND '2025-12-31' AND customers.country = 'Germany') T1`
  - seed 0: prediction failed (schema)

- **test/c02** `schema`: How many orders placed in 2025 have the status 'cancelled'?  
  note: invented a table named date and used date('now') for the year
  - gold: `SELECT COUNT(*) FROM orders o WHERE o.status = 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - pred: `SELECT COUNT(DISTINCT o.order_id) FROM orders o WHERE o.order_date IN (SELECT MIN(order_date) FROM orders WHERE order_date IN (SELECT DATE('now', '-1 year') FROM date) AND status = 'cancelled') AND o.status = 'cancelled'`
  - seed 0: prediction failed (schema)

- **test/c03** `schema`: What was the total revenue in March 2026?  
  note: used products.list_price instead of order_items.unit_price
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-03-01' AND '2026-03-31'`
  - pred: `SELECT SUM(T1.list_price * T2.quantity) AS revenue FROM products AS T1 INNER JOIN order_items AS T2 ON T1.product_id = T2.product_id INNER JOIN orders AS T3 ON T2.order_id = T3.order_id WHERE T3.status NOT IN ('cancelled') AND T3.order_date BETWEEN '2026-03-01' AND '2026-03-31'`
  - seed 0: no column with the expected values

- **test/c06** `filter`: Which 5 customers had the highest revenue in 2025? List their names from highest to lowest.  
  note: cancelled orders not excluded; 5th customer differs (extra revenue column allowed)
  - gold: `SELECT c.name FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY c.customer_id ORDER BY SUM(i.quantity * i.unit_price) DESC, c.name LIMIT 5`
  - pred: `SELECT customers.name, SUM(order_items.quantity * order_items.unit_price) AS revenue FROM orders JOIN order_items ON orders.order_id = order_items.order_id JOIN customers ON orders.customer_id = customers.customer_id WHERE orders.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY customers.name ORDER BY revenue DESC LIMIT 5`
  - seed 0: no column with the expected values

- **test/c07** `filter`: For each product category, how many units were sold? Return the category and the units.  
  note: cancelled orders not excluded from units sold
  - gold: `SELECT p.category, SUM(i.quantity) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id WHERE o.status <> 'cancelled' GROUP BY p.category`
  - pred: `SELECT category, SUM(oi.quantity) AS units_sold FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id GROUP BY p.category ORDER BY units_sold DESC`
  - seed 0: no column with the expected values

- **test/c08** `schema`: For each product category, what was the revenue from 2026-01-01 to 2026-06-30? Return the category and the revenue.  
  note: orders.product_id does not exist (joined products to orders directly)
  - gold: `SELECT p.category, SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-01-01' AND '2026-06-30' GROUP BY p.category`
  - pred: `SELECT p.category, SUM(o.order_date >= '2026-01-01' AND o.order_date <= '2026-06-30') * SUM(oi.quantity) AS revenue FROM products p JOIN orders o ON p.product_id = o.product_id JOIN order_items oi ON o.order_id = oi.order_id GROUP BY p.category`
  - seed 0: prediction failed (schema)

- **test/c09** `aggregate`: How many orders were paid with more than one positive payment?  
  note: COUNT inside GROUP BY order_id: one row per order instead of one count
  - gold: `SELECT COUNT(*) FROM (SELECT order_id FROM payments WHERE amount > 0 GROUP BY order_id HAVING COUNT(*) > 1)`
  - pred: `SELECT COUNT(DISTINCT o.order_id) FROM orders o JOIN payments p ON o.order_id = p.order_id WHERE p.amount > 0 GROUP BY o.order_id HAVING COUNT(DISTINCT p.payment_id) > 1`
  - seed 0: 340 rows, expected 1

- **test/c10** `aggregate`: What was the total amount refunded in refund payments dated in 2025?  
  note: refund total returned as a negative number (glossary: positive)
  - gold: `SELECT -SUM(amount) FROM payments WHERE amount < 0 AND payment_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - pred: `SELECT SUM(amount) FROM payments WHERE payment_date LIKE '2025-%' AND amount < 0`
  - seed 0: no column with the expected values

- **test/c11** `schema`: Which country had the highest revenue in May 2026?  
  note: orders.value does not exist
  - gold: `SELECT c.country FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-05-01' AND '2026-05-31' GROUP BY c.country ORDER BY SUM(i.quantity * i.unit_price) DESC, c.country LIMIT 1`
  - pred: `SELECT c.country, SUM(o.value) AS revenue FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE o.order_date BETWEEN '2026-05-01' AND '2026-05-31' GROUP BY c.country ORDER BY revenue DESC LIMIT 1`
  - seed 0: prediction failed (schema)

- **test/c13** `schema`: What is the total value of all orders, of any status, placed by the customer with id 42?  
  note: list_price instead of unit_price; also excluded cancelled and grouped by product
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE o.customer_id = 42`
  - pred: `SELECT SUM(T1.list_price * T2.quantity) FROM products AS T1 INNER JOIN order_items AS T2 ON T1.product_id = T2.product_id INNER JOIN orders AS T3 ON T2.order_id = T3.order_id WHERE T3.customer_id = 42 AND T3.status NOT IN ('cancelled') GROUP BY T1.product_id`
  - seed 0: 4 rows, expected 1

- **test/c18** `date`: Which customers signed up in 2026 and have placed at least 3 orders of any status? Return their names.  
  note: filtered order_date >= today instead of signup_date in 2026
  - gold: `SELECT c.name FROM customers c JOIN orders o ON o.customer_id = c.customer_id WHERE c.signup_date BETWEEN '2026-01-01' AND '2026-12-31' GROUP BY c.customer_id HAVING COUNT(*) >= 3`
  - pred: `SELECT customers.name FROM customers JOIN orders ON customers.customer_id = orders.customer_id WHERE orders.order_date >= '2026-06-30' AND orders.status IN ('placed', 'shipped', 'delivered') GROUP BY customers.customer_id HAVING COUNT(DISTINCT orders.order_id) >= 3`
  - seed 0: 0 rows, expected 41

- **test/c20** `schema`: Which products have never been ordered, in an order of any status, by a customer from Singapore? Return their names.  
  note: orders.order_item.product_id does not exist
  - gold: `SELECT name FROM products WHERE product_id NOT IN (SELECT i.product_id FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE c.country = 'Singapore')`
  - pred: `SELECT DISTINCT p.name FROM products p JOIN orders o ON p.product_id = o.order_item.product_id JOIN customers c ON o.customer_id = c.customer_id WHERE c.country = 'Singapore' AND o.order_id NOT IN (SELECT order_id FROM orders WHERE status IN ('placed', 'shipped', 'delivered'))`
  - seed 0: prediction failed (schema)

- **test/c21** `schema`: Which customers from Canada have a total revenue above 2000? Return their names.  
  note: order_items used without being joined; orders.country does not exist
  - gold: `SELECT c.name FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND c.country = 'Canada' GROUP BY c.customer_id HAVING SUM(i.quantity * i.unit_price) > 2000`
  - pred: `SELECT customers.name FROM customers JOIN orders ON customers.customer_id = orders.customer_id WHERE orders.country = 'Canada' AND orders.status NOT IN ('cancelled') GROUP BY customers.customer_id HAVING SUM(order_items.quantity * order_items.unit_price) > 2000`
  - seed 0: prediction failed (schema)

- **test/c23** `date`: How much was refunded, in refund payments dated in 2026, on orders from customers in the United States?  
  note: LIKE '2026-01-01%' keeps only 1 January; also negative sign
  - gold: `SELECT -SUM(pay.amount) FROM payments pay JOIN orders o ON o.order_id = pay.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE pay.amount < 0 AND c.country = 'United States' AND pay.payment_date BETWEEN '2026-01-01' AND '2026-12-31'`
  - pred: `SELECT SUM(p.amount) FROM payments p JOIN orders o ON p.order_id = o.order_id JOIN customers c ON o.customer_id = c.customer_id WHERE p.payment_date LIKE '2026-01-01%' AND p.amount < 0 AND c.country = 'United States'`
  - seed 0: no column with the expected values

- **test/c24** `join`: For every customer in Singapore, how many orders of any status have they placed? Include customers with no orders. Return the name and the count.  
  note: inner join drops the Singapore customer with no orders (LEFT JOIN needed)
  - gold: `SELECT c.name, COUNT(o.order_id) FROM customers c LEFT JOIN orders o ON o.customer_id = c.customer_id WHERE c.country = 'Singapore' GROUP BY c.customer_id`
  - pred: `SELECT customers.name, COUNT(DISTINCT orders.order_id) AS order_count FROM customers JOIN orders ON customers.customer_id = orders.customer_id WHERE customers.country = 'Singapore' GROUP BY customers.name`
  - seed 0: 7 rows, expected 8

- **test/c25** `schema`: What was the revenue from the Electronics category between 2026-01-01 and 2026-03-31?  
  note: used products.list_price instead of order_items.unit_price
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-01-01' AND '2026-03-31' AND p.category = 'Electronics'`
  - pred: `SELECT SUM(T1.list_price * T2.quantity) AS revenue FROM products AS T1 INNER JOIN order_items AS T2 ON T1.product_id = T2.product_id INNER JOIN orders AS T3 ON T2.order_id = T3.order_id WHERE T3.status NOT IN ('cancelled') AND T1.category = 'Electronics' AND T3.order_date BETWEEN '2026-01-01' AND '2026-03-31'`
  - seed 0: no column with the expected values

### qwen2.5:3b (17)

- **dev/dc2** `date`: What was the total revenue in April 2026?  
  note: outer query keeps only 2026-04-01; also status = 'shipped' only
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-04-01' AND '2026-04-30'`
  - pred: `SELECT SUM(T1.value) AS revenue FROM (SELECT SUM(order_items.quantity * order_items.unit_price) AS value, orders.order_date FROM orders JOIN order_items ON orders.order_id = order_items.order_id WHERE orders.status = 'shipped' AND orders.order_date BETWEEN '2026-04-01' AND '2026-04-30' GROUP BY orders.order_date) T1 WHERE T1.order_date = '2026-04-01' AND T1.value > 0`
  - seed 0: no column with the expected values

- **test/c01** `schema`: What was the revenue from customers based in Germany in 2025?  
  note: products.unit_price does not exist
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' AND c.country = 'Germany'`
  - pred: `SELECT SUM(T2.unit_price * T1.quantity) AS revenue FROM order_items AS T1 JOIN products AS T2 ON T1.product_id = T2.product_id JOIN orders AS T3 ON T1.order_id = T3.order_id JOIN customers AS T4 ON T3.customer_id = T4.customer_id WHERE T4.country = 'Germany' AND strftime('%Y', T3.order_date) = '2025' AND T3.status NOT IN ('placed', 'shipped', 'delivered', 'cancelled') GROUP BY T4.customer_id`
  - seed 0: prediction failed (schema)

- **test/c03** `schema`: What was the total revenue in March 2026?  
  note: unqualified order_id is ambiguous after the join
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-03-01' AND '2026-03-31'`
  - pred: `SELECT SUM(T1.value) AS revenue FROM ( SELECT order_id, SUM(order_items.quantity * order_items.unit_price) AS value FROM orders JOIN order_items ON orders.order_id = order_items.order_id WHERE orders.order_date BETWEEN '2026-03-01' AND '2026-03-31' AND orders.status != 'cancelled' GROUP BY order_id ) T1 JOIN orders ON T1.order_id = orders.order_id WHERE orders.status != 'cancelled' AND orders.order_date BETWEEN '2026-03-01' AND '2026-03-31'`
  - seed 0: prediction failed (schema)

- **test/c06** `join`: Which 5 customers had the highest revenue in 2025? List their names from highest to lowest.  
  note: joined payments and kept only refunds (amount < 0)
  - gold: `SELECT c.name FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY c.customer_id ORDER BY SUM(i.quantity * i.unit_price) DESC, c.name LIMIT 5`
  - pred: `SELECT c.name FROM customers AS c JOIN orders AS o ON c.customer_id = o.customer_id JOIN order_items AS oi ON o.order_id = oi.order_id JOIN payments AS p ON o.order_id = p.order_id WHERE o.status NOT IN ('cancelled') AND p.amount < 0 AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY c.name ORDER BY SUM(oi.quantity * oi.unit_price * p.amount / ABS(p.amount)) DESC LIMIT 5`
  - seed 0: no column with the expected values

- **test/c08** `schema`: For each product category, what was the revenue from 2026-01-01 to 2026-06-30? Return the category and the revenue.  
  note: unqualified order_id is ambiguous; also joined products on order_id
  - gold: `SELECT p.category, SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-01-01' AND '2026-06-30' GROUP BY p.category`
  - pred: `SELECT p.category, SUM(o.value) AS revenue FROM products p JOIN (SELECT order_id, SUM(order_items.quantity * order_items.unit_price) AS value FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status NOT IN ('cancelled') AND o.order_date BETWEEN '2026-01-01' AND '2026-06-30' GROUP BY order_id) o ON p.product_id = o.order_id GROUP BY p.category`
  - seed 0: prediction failed (schema)

- **test/c09** `filter`: How many orders were paid with more than one positive payment?  
  note: self-join with payment_date < misses orders paid twice on the same day
  - gold: `SELECT COUNT(*) FROM (SELECT order_id FROM payments WHERE amount > 0 GROUP BY order_id HAVING COUNT(*) > 1)`
  - pred: `SELECT COUNT(DISTINCT o.order_id) FROM orders o JOIN payments p1 ON o.order_id = p1.order_id JOIN payments p2 ON o.order_id = p2.order_id WHERE p1.amount > 0 AND p2.amount > 0 AND p1.payment_date < p2.payment_date`
  - seed 0: no column with the expected values

- **test/c10** `filter`: What was the total amount refunded in refund payments dated in 2025?  
  note: added method = 'card'; also negative sign
  - gold: `SELECT -SUM(amount) FROM payments WHERE amount < 0 AND payment_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - pred: `SELECT SUM(amount) FROM payments WHERE payment_date >= '2025-01-01' AND payment_date < '2026-01-01' AND method = 'card' AND amount < 0`
  - seed 0: no column with the expected values

- **test/c11** `schema`: Which country had the highest revenue in May 2026?  
  note: orders.value does not exist
  - gold: `SELECT c.country FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-05-01' AND '2026-05-31' GROUP BY c.country ORDER BY SUM(i.quantity * i.unit_price) DESC, c.country LIMIT 1`
  - pred: `SELECT customers.country, SUM(CASE WHEN o.status = 'shipped' THEN o.value ELSE 0 END) AS revenue FROM orders o JOIN customers ON o.customer_id = customers.customer_id JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status IN ('shipped', 'delivered') AND o.order_date BETWEEN '2026-05-01' AND '2026-05-31' GROUP BY customers.country ORDER BY revenue DESC LIMIT 1`
  - seed 0: prediction failed (schema)

- **test/c12** `filter`: How many distinct customers placed at least one order, of any status, in May 2026?  
  note: excluded cancelled orders although the question says any status
  - gold: `SELECT COUNT(DISTINCT o.customer_id) FROM orders o WHERE o.order_date BETWEEN '2026-05-01' AND '2026-05-31'`
  - pred: `SELECT COUNT(DISTINCT customer_id) FROM orders WHERE order_date BETWEEN '2026-05-01' AND '2026-05-31' AND status NOT IN ('cancelled')`
  - seed 0: no column with the expected values

- **test/c13** `date`: What is the total value of all orders, of any status, placed by the customer with id 42?  
  note: added order_date = today only; also excluded cancelled
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE o.customer_id = 42`
  - pred: `SELECT SUM(order_items.unit_price * order_items.quantity) AS total_value FROM orders JOIN order_items ON orders.order_id = order_items.order_id JOIN customers ON orders.customer_id = customers.customer_id WHERE orders.customer_id = 42 AND orders.status != 'cancelled' AND orders.order_date BETWEEN '2026-06-30' AND '2026-06-30' ORDER BY orders.order_date ASC`
  - seed 0: no column with the expected values

- **test/c15** `filter`: How many orders, including cancelled ones, were placed in each month of 2025? Return the month as YYYY-MM and the count, in month order.  
  note: excluded cancelled orders although the question says including cancelled
  - gold: `SELECT strftime('%Y-%m', o.order_date) AS month, COUNT(*) FROM orders o WHERE o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY month ORDER BY month`
  - pred: `SELECT strftime('%Y-%m', orders.order_date) AS month, COUNT(*) AS order_count FROM orders WHERE orders.order_date >= '2025-01-01' AND orders.order_date < '2026-01-01' AND orders.status != 'cancelled' GROUP BY strftime('%Y-%m', orders.order_date) ORDER BY month`
  - seed 0: no column with the expected values

- **test/c19** `schema`: What is the average value of the orders with the status 'delivered'?  
  note: unqualified order_id is ambiguous after the join
  - gold: `SELECT AVG(v) FROM (SELECT SUM(i.quantity * i.unit_price) AS v FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE o.status = 'delivered' GROUP BY o.order_id)`
  - pred: `SELECT AVG(total_value) FROM (SELECT order_id, SUM(order_items.quantity * order_items.unit_price) AS total_value FROM orders JOIN order_items ON orders.order_id = order_items.order_id WHERE orders.status = 'delivered' GROUP BY order_id)`
  - seed 0: prediction failed (schema)

- **test/c20** `filter`: Which products have never been ordered, in an order of any status, by a customer from Singapore? Return their names.  
  note: contradictory conditions (NOT IN Singapore products AND ordered by Singapore): empty
  - gold: `SELECT name FROM products WHERE product_id NOT IN (SELECT i.product_id FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE c.country = 'Singapore')`
  - pred: `SELECT p.name FROM products p LEFT JOIN order_items oi ON p.product_id = oi.product_id LEFT JOIN orders o ON oi.order_id = o.order_id WHERE p.product_id NOT IN (SELECT DISTINCT oi.product_id FROM order_items oi JOIN orders o ON oi.order_id = o.order_id WHERE o.customer_id IN (SELECT customer_id FROM customers WHERE country = 'Singapore')) AND o.customer_id IN (SELECT customer_id FROM customers WHERE country = 'Singapore') ORDER BY p.name`
  - seed 0: 0 rows, expected 3

- **test/c21** `join`: Which customers from Canada have a total revenue above 2000? Return their names.  
  note: joined payments: each item counted once per payment (fan-out), one extra customer
  - gold: `SELECT c.name FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND c.country = 'Canada' GROUP BY c.customer_id HAVING SUM(i.quantity * i.unit_price) > 2000`
  - pred: `SELECT c.name FROM customers AS c JOIN orders AS o ON c.customer_id = o.customer_id JOIN order_items AS oi ON o.order_id = oi.order_id JOIN payments AS p ON o.order_id = p.order_id WHERE c.country = 'Canada' AND o.status NOT IN ('cancelled') AND p.amount > 0 GROUP BY c.name HAVING SUM(oi.quantity * oi.unit_price) > 2000`
  - seed 0: 20 rows, expected 19

- **test/c22** `filter`: What percentage of the orders placed in 2025 were cancelled?  
  note: status = 'cancelled' in WHERE makes the share 100%
  - gold: `SELECT 100.0 * SUM(o.status = 'cancelled') / COUNT(*) FROM orders o WHERE o.order_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - pred: `SELECT CAST(COUNT(*) AS REAL) * 100 / COUNT(order_id) AS cancellation_percentage FROM orders WHERE status = 'cancelled' AND order_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - seed 0: no column with the expected values

- **test/c23** `schema`: How much was refunded, in refund payments dated in 2026, on orders from customers in the United States?  
  note: payments.customer_id does not exist
  - gold: `SELECT -SUM(pay.amount) FROM payments pay JOIN orders o ON o.order_id = pay.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE pay.amount < 0 AND c.country = 'United States' AND pay.payment_date BETWEEN '2026-01-01' AND '2026-12-31'`
  - pred: `SELECT SUM(amount) AS total_refunded FROM payments WHERE payment_date BETWEEN '2026-01-01' AND '2026-12-31' AND method = 'card' AND customer_id IN (SELECT customer_id FROM customers WHERE country = 'United States') AND amount < 0`
  - seed 0: prediction failed (schema)

- **test/c25** `schema`: What was the revenue from the Electronics category between 2026-01-01 and 2026-03-31?  
  note: used products.list_price instead of order_items.unit_price
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-01-01' AND '2026-03-31' AND p.category = 'Electronics'`
  - pred: `SELECT SUM(T2.list_price * T1.quantity) AS Revenue FROM order_items AS T1 JOIN products AS T2 ON T1.product_id = T2.product_id JOIN orders AS T3 ON T1.order_id = T3.order_id WHERE T3.status NOT IN ('cancelled') AND T2.category = 'Electronics' AND T3.order_date BETWEEN '2026-01-01' AND '2026-03-31'`
  - seed 0: no column with the expected values

### qwen2.5-coder:3b (11)

- **dev/dc2** `filter`: What was the total revenue in April 2026?  
  note: status = 'delivered' only; also GROUP BY order_id gives one row per order
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-04-01' AND '2026-04-30'`
  - pred: `SELECT SUM(T2.value) AS total_revenue FROM orders AS T1 INNER JOIN ( SELECT order_id, SUM(order_items.quantity * order_items.unit_price) AS value FROM order_items GROUP BY order_id ) AS T2 ON T1.order_id = T2.order_id WHERE T1.status = 'delivered' AND T1.order_date BETWEEN '2026-04-01' AND '2026-04-30' GROUP BY T1.order_id`
  - seed 0: 211 rows, expected 1

- **test/c03** `schema`: What was the total revenue in March 2026?  
  note: products.quantity does not exist (aliases swapped)
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-03-01' AND '2026-03-31'`
  - pred: `SELECT SUM(T2.unit_price * T3.quantity) AS total_revenue FROM orders AS T1 INNER JOIN order_items AS T2 ON T1.order_id = T2.order_id INNER JOIN products AS T3 ON T2.product_id = T3.product_id WHERE T1.status = 'delivered' AND T1.order_date BETWEEN '2026-03-01' AND '2026-03-31' GROUP BY T1.order_id`
  - seed 0: prediction failed (schema)

- **test/c06** `schema`: Which 5 customers had the highest revenue in 2025? List their names from highest to lowest.  
  note: orders.value does not exist
  - gold: `SELECT c.name FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY c.customer_id ORDER BY SUM(i.quantity * i.unit_price) DESC, c.name LIMIT 5`
  - pred: `SELECT c.name FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.status != 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY c.customer_id ORDER BY SUM(o.value) DESC LIMIT 5`
  - seed 0: prediction failed (schema)

- **test/c07** `join`: For each product category, how many units were sold? Return the category and the units.  
  note: orders not joined, so cancelled orders cannot be excluded
  - gold: `SELECT p.category, SUM(i.quantity) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id WHERE o.status <> 'cancelled' GROUP BY p.category`
  - pred: `SELECT category, SUM(quantity) AS units_sold FROM products JOIN order_items ON products.product_id = order_items.product_id WHERE order_items.quantity > 0 GROUP BY category`
  - seed 0: no column with the expected values

- **test/c09** `aggregate`: How many orders were paid with more than one positive payment?  
  note: COUNT inside GROUP BY order_id: one row per order instead of one count
  - gold: `SELECT COUNT(*) FROM (SELECT order_id FROM payments WHERE amount > 0 GROUP BY order_id HAVING COUNT(*) > 1)`
  - pred: `SELECT COUNT(order_id) FROM payments WHERE amount > 0 GROUP BY order_id HAVING COUNT(payment_id) > 1`
  - seed 0: 340 rows, expected 1

- **test/c10** `aggregate`: What was the total amount refunded in refund payments dated in 2025?  
  note: refund total returned as a negative number (glossary: positive)
  - gold: `SELECT -SUM(amount) FROM payments WHERE amount < 0 AND payment_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - pred: `SELECT SUM(amount) AS total_refund FROM payments WHERE payment_date BETWEEN '2025-01-01' AND '2025-12-31' AND amount < 0`
  - seed 0: no column with the expected values

- **test/c13** `filter`: What is the total value of all orders, of any status, placed by the customer with id 42?  
  note: status = 'placed' only, although the question says any status
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE o.customer_id = 42`
  - pred: `SELECT SUM(order_items.quantity * order_items.unit_price) AS total_value FROM orders JOIN order_items ON orders.order_id = order_items.order_id WHERE orders.customer_id = 42 AND orders.status = 'placed'`
  - seed 0: no column with the expected values

- **test/c20** `filter`: Which products have never been ordered, in an order of any status, by a customer from Singapore? Return their names.  
  note: subquery lost the Singapore condition: products never ordered by anyone (empty)
  - gold: `SELECT name FROM products WHERE product_id NOT IN (SELECT i.product_id FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE c.country = 'Singapore')`
  - pred: `SELECT name FROM products WHERE product_id NOT IN (SELECT product_id FROM order_items)`
  - seed 0: 0 rows, expected 3

- **test/c22** `schema`: What percentage of the orders placed in 2025 were cancelled?  
  note: orders.product_id / products.status do not exist
  - gold: `SELECT 100.0 * SUM(o.status = 'cancelled') / COUNT(*) FROM orders o WHERE o.order_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - pred: `SELECT CAST(SUM(CASE WHEN T2.status = 'cancelled' THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(T1.order_id) FROM orders AS T1 INNER JOIN products AS T2 ON T1.product_id = T2.product_id WHERE T1.order_date BETWEEN '2025-01-01' AND '2025-12-31' AND T1.status = 'placed'`
  - seed 0: prediction failed (schema)

- **test/c23** `filter`: How much was refunded, in refund payments dated in 2026, on orders from customers in the United States?  
  note: added method = 'card'; also negative sign
  - gold: `SELECT -SUM(pay.amount) FROM payments pay JOIN orders o ON o.order_id = pay.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE pay.amount < 0 AND c.country = 'United States' AND pay.payment_date BETWEEN '2026-01-01' AND '2026-12-31'`
  - pred: `SELECT SUM(amount) AS total_refund FROM payments WHERE method = 'card' AND payment_date LIKE '2026%' AND order_id IN (SELECT order_id FROM orders WHERE customer_id IN (SELECT customer_id FROM customers WHERE country = 'United States')) AND amount < 0`
  - seed 0: no column with the expected values

- **test/c24** `join`: For every customer in Singapore, how many orders of any status have they placed? Include customers with no orders. Return the name and the count.  
  note: inner join drops the Singapore customer with no orders (LEFT JOIN needed)
  - gold: `SELECT c.name, COUNT(o.order_id) FROM customers c LEFT JOIN orders o ON o.customer_id = c.customer_id WHERE c.country = 'Singapore' GROUP BY c.customer_id`
  - pred: `SELECT customers.name, COUNT(*) AS order_count FROM customers JOIN orders ON customers.customer_id = orders.customer_id WHERE customers.country = 'Singapore' GROUP BY customers.customer_id`
  - seed 0: 7 rows, expected 8

### qwen2.5-coder:7b (9)

- **dev/dc2** `schema`: What was the total revenue in April 2026?  
  note: revenue computed from payments instead of order items
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-04-01' AND '2026-04-30'`
  - pred: `SELECT SUM(p.amount) AS total_revenue FROM payments p JOIN orders o ON p.order_id = o.order_id WHERE o.status != 'cancelled' AND p.payment_date BETWEEN '2026-04-01' AND '2026-04-30'`
  - seed 0: no column with the expected values

- **test/c01** `schema`: What was the revenue from customers based in Germany in 2025?  
  note: revenue computed from payments instead of order items
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' AND c.country = 'Germany'`
  - pred: `SELECT SUM(T3.amount) AS revenue FROM customers AS T1 INNER JOIN orders AS T2 ON T1.customer_id = T2.customer_id INNER JOIN payments AS T3 ON T2.order_id = T3.order_id WHERE T1.country = 'Germany' AND T2.order_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - seed 0: no column with the expected values

- **test/c03** `schema`: What was the total revenue in March 2026?  
  note: revenue computed from payments instead of order items
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id  WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-03-01' AND '2026-03-31'`
  - pred: `SELECT SUM(T1.amount) AS total_revenue FROM payments AS T1 INNER JOIN orders AS T2 ON T1.order_id = T2.order_id WHERE T2.status != 'cancelled' AND T1.payment_date BETWEEN '2026-03-01' AND '2026-03-31'`
  - seed 0: no column with the expected values

- **test/c06** `filter`: Which 5 customers had the highest revenue in 2025? List their names from highest to lowest.  
  note: cancelled orders not excluded; 5th customer differs (extra revenue column allowed)
  - gold: `SELECT c.name FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY c.customer_id ORDER BY SUM(i.quantity * i.unit_price) DESC, c.name LIMIT 5`
  - pred: `SELECT c.name, SUM(oi.quantity * oi.unit_price) AS total_revenue FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id WHERE o.order_date BETWEEN '2025-01-01' AND '2025-12-31' GROUP BY c.customer_id ORDER BY total_revenue DESC LIMIT 5`
  - seed 0: no column with the expected values

- **test/c09** `aggregate`: How many orders were paid with more than one positive payment?  
  note: COUNT inside GROUP BY order_id: one row per order instead of one count
  - gold: `SELECT COUNT(*) FROM (SELECT order_id FROM payments WHERE amount > 0 GROUP BY order_id HAVING COUNT(*) > 1)`
  - pred: `SELECT COUNT(DISTINCT o.order_id) FROM orders o JOIN payments p ON o.order_id = p.order_id WHERE p.amount > 0 GROUP BY o.order_id HAVING COUNT(p.payment_id) > 1`
  - seed 0: 340 rows, expected 1

- **test/c10** `filter`: What was the total amount refunded in refund payments dated in 2025?  
  note: method = 'refund' does not exist (refunds are negative amounts): NULL
  - gold: `SELECT -SUM(amount) FROM payments WHERE amount < 0 AND payment_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - pred: `SELECT SUM(-amount) AS total_refunded FROM payments WHERE method = 'refund' AND payment_date BETWEEN '2025-01-01' AND '2025-12-31'`
  - seed 0: no column with the expected values

- **test/c19** `aggregate`: What is the average value of the orders with the status 'delivered'?  
  note: AVG over item lines, not over order totals
  - gold: `SELECT AVG(v) FROM (SELECT SUM(i.quantity * i.unit_price) AS v FROM orders o JOIN order_items i ON i.order_id = o.order_id WHERE o.status = 'delivered' GROUP BY o.order_id)`
  - pred: `SELECT AVG(order_items.quantity * order_items.unit_price) AS average_value FROM orders JOIN order_items ON orders.order_id = order_items.order_id WHERE orders.status = 'delivered'`
  - seed 0: no column with the expected values

- **test/c23** `filter`: How much was refunded, in refund payments dated in 2026, on orders from customers in the United States?  
  note: method = 'refund' and status = 'cancelled': NULL
  - gold: `SELECT -SUM(pay.amount) FROM payments pay JOIN orders o ON o.order_id = pay.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE pay.amount < 0 AND c.country = 'United States' AND pay.payment_date BETWEEN '2026-01-01' AND '2026-12-31'`
  - pred: `SELECT SUM(-amount) AS total_refunded FROM payments WHERE payment_date LIKE '2026%' AND method = 'refund' AND order_id IN ( SELECT order_id FROM orders WHERE customer_id IN ( SELECT customer_id FROM customers WHERE country = 'United States' ) AND status = 'cancelled' )`
  - seed 0: no column with the expected values

- **test/c25** `filter`: What was the revenue from the Electronics category between 2026-01-01 and 2026-03-31?  
  note: cancelled orders not excluded from revenue
  - gold: `SELECT SUM(i.quantity * i.unit_price) FROM orders o JOIN order_items i ON i.order_id = o.order_id JOIN products p ON p.product_id = i.product_id WHERE o.status <> 'cancelled' AND o.order_date BETWEEN '2026-01-01' AND '2026-03-31' AND p.category = 'Electronics'`
  - pred: `SELECT SUM(order_items.quantity * order_items.unit_price) AS revenue FROM order_items JOIN orders ON order_items.order_id = orders.order_id JOIN products ON order_items.product_id = products.product_id WHERE products.category = 'Electronics' AND orders.order_date BETWEEN '2026-01-01' AND '2026-03-31'`
  - seed 0: no column with the expected values

