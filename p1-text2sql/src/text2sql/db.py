"""Synthetic, seeded company database (SQLite).

    uv run python -m text2sql.db --seed 0          # -> p1-text2sql/data/company_s0.db

Same seed + same code => same data (checked by `canonical_sha`). Behaviour is built in, not
planted: every customer gets an independent order *frequency* and *basket size*, so "top
customer by revenue" and "top customer by order count" differ naturally; cancelled orders,
split payments, partial refunds (negative payments), customers with no orders and recent
not-yet-delivered orders make different readings of an ambiguous question give different
answers. "Today" is fixed (meta table) so relative dates ("last month") are deterministic.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import random
import sqlite3
from pathlib import Path

TODAY = dt.date(2026, 6, 30)
HISTORY_START = dt.date(2024, 7, 1)  # first possible order date (two years of orders)
SIGNUP_START = dt.date(2024, 1, 1)
FREQ_CAP = 6.0  # max relative order frequency of one customer

SCHEMA = """\
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    country     TEXT NOT NULL,
    signup_date TEXT NOT NULL            -- YYYY-MM-DD
);
CREATE TABLE products (
    product_id  INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL,
    list_price  REAL NOT NULL            -- current catalogue price
);
CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date  TEXT NOT NULL,           -- YYYY-MM-DD
    status      TEXT NOT NULL CHECK (status IN ('placed', 'shipped', 'delivered', 'cancelled'))
);
CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    REAL NOT NULL          -- price actually charged per unit (may be discounted)
);
CREATE TABLE payments (
    payment_id   INTEGER PRIMARY KEY,
    order_id     INTEGER NOT NULL REFERENCES orders(order_id),
    payment_date TEXT NOT NULL,          -- YYYY-MM-DD
    amount       REAL NOT NULL,          -- negative = refund
    method       TEXT NOT NULL CHECK (method IN ('card', 'upi', 'paypal', 'bank_transfer'))
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

FIRST = ["Aarav", "Maya", "Liam", "Sofia", "Noah", "Priya", "Ethan", "Chloe", "Arjun", "Emma",
         "Lucas", "Zara", "Omar", "Hana", "Mateo", "Isla", "Kenji", "Leah", "Ravi", "Nora"]
LAST = ["Sharma", "Smith", "Garcia", "Müller", "Chen", "Patel", "Brown", "Rossi", "Kim", "Silva",
        "Nguyen", "Khan", "Martin", "Ito", "Lopez", "Fischer", "Das", "Wilson", "Novak", "Haddad"]
COUNTRIES = [("India", 30), ("United States", 25), ("United Kingdom", 12), ("Germany", 10),
             ("Canada", 8), ("Australia", 7), ("France", 5), ("Singapore", 3)]
CATALOGUE = {  # category -> (price range, product nouns)
    "Electronics": ((25, 900), ["Headphones", "Speaker", "Monitor", "Keyboard", "Webcam",
                                "Router", "Tablet", "Smartwatch", "Charger", "Drive"]),
    "Books": ((8, 60), ["Novel", "Cookbook", "Atlas", "Biography", "Workbook",
                        "Anthology", "Guide", "Journal", "Comic", "Textbook"]),
    "Home": ((10, 300), ["Lamp", "Kettle", "Rug", "Vase", "Blender",
                         "Pillow", "Clock", "Mirror", "Toaster", "Shelf"]),
    "Clothing": ((12, 180), ["Jacket", "Sneakers", "Scarf", "Hoodie", "Jeans",
                             "Raincoat", "Sweater", "Cap", "Boots", "Gloves"]),
    "Sports": ((15, 400), ["Yoga Mat", "Racket", "Dumbbell", "Bicycle Helmet", "Football",
                           "Tent", "Water Bottle", "Jump Rope", "Backpack", "Skates"]),
    "Toys": ((6, 120), ["Puzzle", "Robot Kit", "Board Game", "Plush Bear", "Kite",
                        "Train Set", "Blocks", "Drone", "Doll House", "Yo-yo"]),
}
ADJECTIVES = ["Classic", "Pro", "Eco", "Compact", "Deluxe"]
METHODS = [("card", 55), ("upi", 25), ("paypal", 12), ("bank_transfer", 8)]


def _wchoice(rng: random.Random, pairs):
    return rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs], k=1)[0]


def _day(d: dt.date) -> str:
    return d.isoformat()


def _between(rng: random.Random, a: dt.date, b: dt.date) -> dt.date:
    return dt.date.fromordinal(rng.randint(a.toordinal(), b.toordinal()))


def generate(seed: int) -> dict[str, list[tuple]]:
    """All rows, by table, as plain tuples (pure function of the seed)."""
    rng = random.Random(seed)

    names = rng.sample([f"{f} {l}" for f in FIRST for l in LAST], 300)
    customers, profile = [], {}
    for cid, name in enumerate(names, 1):
        email = f"{name.lower().replace(' ', '.').replace('ü', 'u')}{cid}@example.com"
        customers.append((cid, name, email, _wchoice(rng, COUNTRIES),
                          _day(_between(rng, SIGNUP_START, TODAY - dt.timedelta(days=3)))))
        # Independent frequency and basket size; ~10% of customers never order. Frequency is
        # capped at 6x the minimum: uncapped, one customer took 8.7% of all orders on seed 1
        # and won every ranking (see docs/LOG.md).
        freq = 0.0 if rng.random() < 0.10 else min(rng.paretovariate(1.6), FREQ_CAP)
        profile[cid] = (freq, rng.lognormvariate(0, 0.55))

    products, pid = [], 0
    for cat, ((lo, hi), nouns) in CATALOGUE.items():
        for noun in nouns:
            pid += 1
            products.append((pid, f"{rng.choice(ADJECTIVES)} {noun}", cat,
                             round(rng.uniform(lo, hi), 2)))
    price = {p[0]: p[3] for p in products}

    buyers = [c for c in profile if profile[c][0] > 0]
    weights = [profile[c][0] for c in buyers]
    signup = {c[0]: dt.date.fromisoformat(c[4]) for c in customers}
    drafts = []
    for _ in range(3000):
        cid = rng.choices(buyers, weights=weights, k=1)[0]
        d = _between(rng, max(signup[cid], HISTORY_START), TODAY)
        drafts.append((d, cid))
    drafts.sort()  # order ids increase with date

    orders, items, payments = [], [], []
    for oid, (d, cid) in enumerate(drafts, 1):
        age = (TODAY - d).days
        if rng.random() < 0.08:
            status = "cancelled"
        elif age <= 3:
            status = rng.choice(["placed", "shipped"])
        elif age <= 7:
            status = rng.choice(["shipped", "delivered"])
        else:
            status = "delivered"
        orders.append((oid, cid, _day(d), status))

        basket = profile[cid][1]
        n_items = max(1, min(6, round(rng.gauss(1.6 * basket, 0.9))))
        total = 0.0
        for p in rng.sample(range(1, len(products) + 1), n_items):
            qty = rng.choices([1, 2, 3, 4], weights=[60, 25, 10, 5], k=1)[0]
            unit = round(price[p] * (0.9 if rng.random() < 0.15 else 1.0), 2)
            items.append((len(items) + 1, oid, p, qty, unit))
            total += qty * unit
        total = round(total, 2)

        def pay(amount: float, day: dt.date) -> None:
            payments.append((len(payments) + 1, oid, _day(min(day, TODAY)), round(amount, 2),
                             _wchoice(rng, METHODS)))

        if status == "cancelled":
            if rng.random() < 0.5:  # paid, then fully refunded
                pay(total, d)
                pay(-total, d + dt.timedelta(days=rng.randint(1, 3)))
        elif status == "placed" and rng.random() < 0.4:
            pass  # not paid yet
        elif rng.random() < 0.12:  # split payment
            first = round(total * 0.5, 2)
            pay(first, d)
            pay(total - first, d + dt.timedelta(days=rng.randint(0, 10)))
        else:
            pay(total, d)
        if status == "delivered" and rng.random() < 0.06:  # partial or full refund
            pay(-round(total * rng.choice([0.2, 0.5, 1.0]), 2),
                d + dt.timedelta(days=rng.randint(5, 30)))

    meta = [("today", _day(TODAY)), ("seed", str(seed)), ("currency", "USD")]
    return {"customers": customers, "products": products, "orders": orders,
            "order_items": items, "payments": payments, "meta": meta}


def build(conn: sqlite3.Connection, seed: int) -> sqlite3.Connection:
    conn.executescript(SCHEMA)
    for table, rows in generate(seed).items():
        if rows:
            conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
    conn.commit()
    return conn


def canonical_sha(conn: sqlite3.Connection) -> str:
    """Hash of the SQL dump: identical data => identical hash, independent of file layout."""
    return hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()[:16]


def default_path(seed: int) -> Path:
    return Path(__file__).resolve().parents[2] / "data" / f"company_s{seed}.db"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = a.out or default_path(a.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()  # generated artifact; rebuilt from seed + code
    conn = build(sqlite3.connect(out), a.seed)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["customers", "products", "orders", "order_items", "payments"]}
    print(f"{out}: {counts} sha {canonical_sha(conn)}")
    conn.close()


if __name__ == "__main__":
    main()
