import sqlite3

import pytest

from text2sql.db import build, default_path
from text2sql.execute import ExecResult, compare, connect_ro, execute, guard


@pytest.fixture(scope="module")
def conn():
    return guard(build(sqlite3.connect(":memory:"), 0))


def R(columns, rows):
    return ExecResult(ok=True, columns=columns, rows=rows)


# ---- safety -------------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DROP TABLE customers",
    "DELETE FROM orders",
    "UPDATE products SET list_price = 0",
    "INSERT INTO meta VALUES ('x', 'y')",
    "ATTACH DATABASE 'evil.db' AS evil",
    "PRAGMA writable_schema = ON",
    "CREATE TABLE t (x)",
])
def test_writes_and_side_effects_are_refused(conn, sql):
    r = execute(conn, sql)
    assert not r.ok and r.error_kind == "denied"
    assert execute(conn, "SELECT COUNT(*) FROM customers").rows == [(300,)]


def test_read_only_file_connection_refuses_writes_even_without_authorizer(tmp_path):
    path = tmp_path / "c.db"
    build(sqlite3.connect(path), 0).close()
    ro = connect_ro(path)
    ro.set_authorizer(None)  # second layer: the URI itself is read-only
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.execute("DELETE FROM orders")
    assert default_path(0).name == "company_s0.db"


def test_runaway_query_times_out(conn):
    r = execute(conn, "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) "
                      "SELECT COUNT(*) FROM n", timeout_s=0.2)
    assert not r.ok and r.error_kind == "timeout"
    assert execute(conn, "SELECT 1").ok  # handler removed afterwards


def test_error_kinds_and_row_cap(conn):
    assert execute(conn, "SELEC * FROM orders").error_kind == "syntax"
    assert execute(conn, "SELECT * FROM order").error_kind == "syntax"  # reserved word
    assert execute(conn, "SELECT * FROM clients").error_kind == "schema"
    assert execute(conn, "SELECT revenue FROM orders").error_kind == "schema"
    assert execute(conn, "SELECT 1; SELECT 2").error_kind == "multiple_statements"
    r = execute(conn, "SELECT * FROM order_items", max_rows=10)
    assert r.ok and r.truncated and len(r.rows) == 10
    assert execute(conn, "SELECT 1;  ").rows == [(1,)]  # trailing semicolon is fine


def test_uses_now_flag(conn):
    assert execute(conn, "SELECT date('now')").uses_now
    assert execute(conn, "SELECT CURRENT_DATE").uses_now
    assert not execute(conn, "SELECT date('2026-06-30', '-1 month')").uses_now


# ---- comparison ---------------------------------------------------------------------------

def test_equivalent_queries_match_on_real_data(conn):
    gold = execute(conn, "SELECT c.name FROM customers c JOIN orders o USING (customer_id) "
                         "WHERE o.status = 'cancelled' GROUP BY c.customer_id")
    pred = execute(conn, "SELECT name FROM customers WHERE customer_id IN "
                         "(SELECT customer_id FROM orders WHERE status = 'cancelled')")
    assert compare(gold, pred).match


def test_number_normalisation():
    assert compare(R(["n"], [(1,)]), R(["x"], [(1.0,)])).match
    assert compare(R(["n"], [(2.004,)]), R(["x"], [(2.0,)])).match
    assert not compare(R(["n"], [(2.01,)]), R(["x"], [(2.0,)])).match
    assert compare(R(["n"], [(None,)]), R(["x"], [(None,)])).match
    assert not compare(R(["n"], [(None,)]), R(["x"], [(0,)])).match


def test_duplicates_count_as_multiset():
    assert not compare(R(["a"], [(1,), (1,), (2,)]), R(["a"], [(1,), (2,), (2,)])).match
    assert not compare(R(["a"], [(1,), (1,)]), R(["a"], [(1,)])).match


def test_permuted_and_extra_columns():
    gold = R(["id", "total"], [(1, 10.0), (2, 20.0)])
    m = compare(gold, R(["total", "id"], [(20.0, 2), (10.0, 1)]))
    assert m.match and not m.extra_columns
    m = compare(gold, R(["name", "id", "total"], [("a", 1, 10.0), ("b", 2, 20.0)]))
    assert m.match and m.extra_columns
    assert not compare(gold, R(["id"], [(1,), (2,)])).match  # missing a column


def test_columns_individually_right_but_paired_wrong():
    gold = R(["id", "total"], [(1, 10.0), (2, 20.0)])
    m = compare(gold, R(["id", "total"], [(1, 20.0), (2, 10.0)]))
    assert not m.match and "rows differ" in m.reason


def test_two_identical_value_columns_need_distinct_assignment():
    gold = R(["a", "b"], [(1, 1), (2, 2)])
    assert compare(gold, R(["x", "y"], [(1, 1), (2, 2)])).match
    assert not compare(gold, R(["x", "y"], [(1, 3), (2, 4)])).match


def test_order_only_when_requested():
    gold = R(["id"], [(1,), (2,), (3,)])
    pred = R(["id"], [(3,), (1,), (2,)])
    assert compare(gold, pred).match
    assert not compare(gold, pred, ordered=True).match
    assert compare(gold, R(["id"], [(1,), (2,), (3,)]), ordered=True).match


def test_failed_prediction_and_empty_results():
    assert not compare(R(["a"], [(1,)]), ExecResult(ok=False, error="x", error_kind="syntax")).match
    assert compare(R(["a"], []), R(["b", "c"], [])).match
    with pytest.raises(ValueError):
        compare(ExecResult(ok=False, error="bad gold"), R(["a"], []))
