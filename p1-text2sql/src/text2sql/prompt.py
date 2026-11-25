"""Schema, business glossary and SQL instructions shown to the model.

FROZEN with the test set (see docs/LOG.md for the hash): the glossary decides which questions
are clear and which are ambiguous, so editing it after seeing model output would move questions
between the two groups.

The system message is identical for every call (rules + schema + glossary) so Ollama can reuse
its prompt cache; only the user message (the question) changes.
"""

from __future__ import annotations

from text2sql.db import SCHEMA, TODAY

SCHEMA_TEXT = SCHEMA.split("CREATE TABLE meta")[0].strip()  # meta is internal, not shown

GLOSSARY = f"""\
- Today is {TODAY.isoformat()}. All relative dates are measured from this date.
- Dates are TEXT in YYYY-MM-DD form. "In March 2026" means 2026-03-01 to 2026-03-31 inclusive;
  "in 2025" means 2025-01-01 to 2025-12-31 inclusive.
- The value of an order is SUM(order_items.quantity * order_items.unit_price) over its items.
- Revenue is the total value of orders whose status is not 'cancelled'. Refunds do not reduce
  revenue. Revenue in a period uses orders.order_date.
- Units sold is SUM(order_items.quantity) over orders whose status is not 'cancelled'.
- A refund is a payment with a negative amount. An amount refunded is reported as a positive number.
- When a question asks which customers or products, return their names (customers.name,
  products.name), not their ids."""

RULES = """\
You translate a question about a company's database into ONE SQLite SELECT query.
- Return only the columns the question asks for. Do not add id, name or helper columns that
  were not asked for.
- Use the date given in the glossary as today. Never use date('now'), CURRENT_DATE or similar.
- Do not round numbers unless the question asks for rounding.
- When the question asks for a ranking or a list in a given order, add ORDER BY.
- Write a single statement: no comments, no explanation, no trailing text."""

SYSTEM = f"""{RULES}

Database schema (SQLite):
{SCHEMA_TEXT}

Glossary:
{GLOSSARY}"""


def sql_messages(question: str) -> list[dict]:
    """Chat messages for plain SQL generation (stage 2 and condition A)."""
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": question}]
