import pytest
from pydantic import ValidationError

from text2sql.testset import TESTSET_DIR, Interpretation, Question, Spec, load, pairs, to_case
from text2sql.validate_testset import FILES, check, databases, flip_tiebreak


@pytest.fixture(scope="module")
def dbs():
    return databases()


def clear(qid, sql, ordered=False):
    return Question(id=qid, question=f"q {qid}", spec=Spec(
        label="clear", category="clear", note="n",
        interpretations=[Interpretation(id="r1", description="d", gold_sql=sql, ordered=ordered)]))


def ambiguous(qid, sqls, ordered=False):
    its = [Interpretation(id=f"r{k}", description="d", clarifying_answer="a", gold_sql=s,
                          ordered=ordered) for k, s in enumerate(sqls)]
    return Question(id=qid, question=f"q {qid}",
                    spec=Spec(label="ambiguous", category="metric", note="n", interpretations=its))


def test_spec_rules():
    with pytest.raises(ValidationError):
        Spec(label="clear", category="metric", note="n",
             interpretations=[Interpretation(id="r", description="d", gold_sql="SELECT 1")])
    with pytest.raises(ValidationError):  # ambiguous needs clarifying answers
        Spec(label="ambiguous", category="metric", note="n", interpretations=[
            Interpretation(id="a", description="d", gold_sql="SELECT 1"),
            Interpretation(id="b", description="d", gold_sql="SELECT 2")])


def test_round_trip_through_evalkit_case(tmp_path):
    q = ambiguous("x1", ["SELECT 1", "SELECT 2"])
    path = tmp_path / "t.jsonl"
    path.write_text(to_case(q).model_dump_json() + "\n", encoding="utf-8")
    assert load(path) == [q] and len(pairs([q])) == 2


def test_flip_tiebreak():
    assert flip_tiebreak("SELECT a FROM t ORDER BY n DESC, a LIMIT 3") == \
        "SELECT a FROM t ORDER BY n DESC, a DESC LIMIT 3"
    assert flip_tiebreak("SELECT a FROM t ORDER BY n DESC, a DESC LIMIT 1;").endswith("a ASC LIMIT 1")
    assert flip_tiebreak("SELECT a FROM t ORDER BY n LIMIT 1") is None


def test_validator_catches_each_rule(dbs):
    qs = [
        clear("e1", "SELECT nope FROM customers"),                                    # R1
        clear("e2", "SELECT date('now')"),                                            # R1 clock
        clear("e3", "SELECT name FROM customers LIMIT 3"),                            # R2
        clear("e4", "SELECT country FROM customers GROUP BY country "
                    "ORDER BY COUNT(*) > 0 DESC, country LIMIT 1"),                   # R2 tie
        clear("e5", "SELECT name FROM customers WHERE 0"),                            # R3
        ambiguous("e6", ["SELECT COUNT(*) FROM customers",
                         "SELECT COUNT(customer_id) FROM customers"]),               # R4
    ]
    errs = check({"x": qs}, dbs).errors
    for qid, rule in [("e1", "R1"), ("e2", "R1"), ("e3", "R2"), ("e4", "R2"), ("e5", "R3"),
                      ("e6", "R4")]:
        assert any(e.startswith(rule) and qid in e for e in errs), (qid, rule, errs)


def test_r4_respects_row_order(dbs):
    # Same set of rows, different order: distinct readings when the answer is a ranking.
    q = ambiguous("o1", ["SELECT category FROM products GROUP BY category ORDER BY category",
                         "SELECT category FROM products GROUP BY category ORDER BY category DESC"],
                  ordered=True)
    assert not [e for e in check({"x": [q]}, dbs).errors if e.startswith("R4")]


def test_committed_test_set_is_valid(dbs):
    splits = {name: load(TESTSET_DIR / fn) for name, fn in FILES.items()}
    rep = check(splits, dbs)
    assert rep.errors == []
