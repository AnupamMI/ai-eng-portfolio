import sqlite3

import pytest

from text2sql.db import TODAY, build, canonical_sha


@pytest.fixture(scope="module", params=[0, 1])
def db(request):
    return build(sqlite3.connect(":memory:"), request.param)


def q(conn, sql):
    return conn.execute(sql).fetchall()


def test_same_seed_same_data_different_seed_different_data():
    a = canonical_sha(build(sqlite3.connect(":memory:"), 0))
    b = canonical_sha(build(sqlite3.connect(":memory:"), 0))
    c = canonical_sha(build(sqlite3.connect(":memory:"), 1))
    assert a == b and a != c


def test_sizes(db):
    (n_c,), (n_p,), (n_o,) = (q(db, f"SELECT COUNT(*) FROM {t}")[0] for t in
                              ["customers", "products", "orders"])
    assert (n_c, n_p, n_o) == (300, 60, 3000)
    assert 5000 < q(db, "SELECT COUNT(*) FROM order_items")[0][0] < 12000
    assert 2500 < q(db, "SELECT COUNT(*) FROM payments")[0][0] < 4000


def test_referential_integrity_and_dates(db):
    db.execute("PRAGMA foreign_keys = ON")
    assert q(db, "PRAGMA foreign_key_check") == []
    today = TODAY.isoformat()
    assert q(db, f"SELECT COUNT(*) FROM orders WHERE order_date > '{today}'")[0][0] == 0
    assert q(db, f"SELECT COUNT(*) FROM payments WHERE payment_date > '{today}'")[0][0] == 0
    assert q(db, "SELECT COUNT(*) FROM orders o JOIN customers c USING (customer_id) "
                 "WHERE o.order_date < c.signup_date")[0][0] == 0
    assert q(db, "SELECT COUNT(*) FROM orders WHERE order_id NOT IN "
                 "(SELECT order_id FROM order_items)")[0][0] == 0
    assert q(db, "SELECT value FROM meta WHERE key = 'today'") == [(today,)]


def test_features_that_make_interpretations_diverge(db):
    assert q(db, "SELECT COUNT(*) FROM orders WHERE status = 'cancelled'")[0][0] > 100
    assert q(db, "SELECT COUNT(*) FROM payments WHERE amount < 0")[0][0] > 50  # refunds
    assert q(db, "SELECT COUNT(*) FROM (SELECT order_id FROM payments WHERE amount > 0 "
                 "GROUP BY order_id HAVING COUNT(*) > 1)")[0][0] > 50  # split payments
    assert q(db, "SELECT COUNT(*) FROM customers WHERE customer_id NOT IN "
                 "(SELECT customer_id FROM orders)")[0][0] > 10
    assert q(db, "SELECT COUNT(*) FROM order_items oi JOIN products p USING (product_id) "
                 "WHERE oi.unit_price < p.list_price")[0][0] > 200  # discounts
    by_revenue = q(db, "SELECT o.customer_id FROM orders o JOIN order_items i USING (order_id) "
                       "WHERE o.status != 'cancelled' GROUP BY o.customer_id "
                       "ORDER BY SUM(i.quantity * i.unit_price) DESC, o.customer_id LIMIT 5")
    by_count = q(db, "SELECT customer_id FROM orders WHERE status != 'cancelled' "
                     "GROUP BY customer_id ORDER BY COUNT(*) DESC, customer_id LIMIT 5")
    assert by_revenue[0] != by_count[0]
    assert len(set(by_revenue) & set(by_count)) <= 3  # rankings differ beyond the top spot


def test_no_customer_dominates(db):
    share = q(db, "SELECT MAX(n) * 1.0 / SUM(n) FROM "
                  "(SELECT COUNT(*) n FROM orders GROUP BY customer_id)")[0][0]
    assert share < 0.03
