"""
models.py – Database layer for TripPool AI
Uses raw SQLite for simplicity and zero external deps.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "trippool.db")


def get_db():
    """Return a new database connection with row_factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS trips (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS members (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id               INTEGER NOT NULL,
        name                  TEXT    NOT NULL,
        initial_contribution  REAL    NOT NULL DEFAULT 0,
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
        UNIQUE(trip_id, name)
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id     INTEGER NOT NULL,
        paid_by     INTEGER NOT NULL,
        amount      REAL    NOT NULL,
        title       TEXT    NOT NULL,
        category    TEXT    NOT NULL DEFAULT 'General',
        type        TEXT    NOT NULL DEFAULT 'pool_expense',
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
        FOREIGN KEY (paid_by) REFERENCES members(id)
    );

    CREATE TABLE IF NOT EXISTS splits (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_id      INTEGER NOT NULL,
        member_id       INTEGER NOT NULL,
        amount_consumed REAL    NOT NULL DEFAULT 0,
        is_participant  INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE,
        FOREIGN KEY (member_id) REFERENCES members(id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id         INTEGER NOT NULL,
        from_member_id  INTEGER NOT NULL,
        to_member_id    INTEGER NOT NULL,
        amount          REAL    NOT NULL,
        settled         INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
        FOREIGN KEY (from_member_id) REFERENCES members(id),
        FOREIGN KEY (to_member_id) REFERENCES members(id)
    );
    """)

    # Attempt to add treasurer_id column to handle legacy databases gracefully
    try:
        conn.execute("ALTER TABLE trips ADD COLUMN treasurer_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass # Column already exists

    conn.commit()
    conn.close()


# ───────────────── Trip CRUD ─────────────────

def create_trip(name):
    """Create a new trip and return its id."""
    conn = get_db()
    cur = conn.execute("INSERT INTO trips (name) VALUES (?)", (name,))
    trip_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trip_id


def get_all_trips():
    """Return all trips as list of dicts."""
    conn = get_db()
    rows = conn.execute(
        "SELECT t.*, "
        "(SELECT COUNT(*) FROM members m WHERE m.trip_id = t.id) AS member_count, "
        "(SELECT COALESCE(SUM(e.amount),0) FROM expenses e WHERE e.trip_id = t.id) AS total_expense "
        "FROM trips t ORDER BY t.created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trip(trip_id):
    """Return a single trip dict or None."""
    conn = get_db()
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_trip_treasurer(trip_id, member_id):
    """Update the trip's elected treasurer."""
    conn = get_db()
    conn.execute("UPDATE trips SET treasurer_id = ? WHERE id = ?", (member_id, trip_id))
    conn.commit()
    conn.close()


def delete_trip(trip_id):
    """Delete a trip and all cascaded data."""
    conn = get_db()
    conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
    conn.commit()
    conn.close()


# ───────────────── Member CRUD ─────────────────

def add_member(trip_id, name, contribution=0):
    """Add a member to a trip. Returns member id."""
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO members (trip_id, name, initial_contribution) VALUES (?, ?, ?)",
        (trip_id, name, contribution),
    )
    member_id = cur.lastrowid
    conn.commit()
    conn.close()
    return member_id


def get_members(trip_id):
    """Return all members for a trip."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM members WHERE trip_id = ? ORDER BY id", (trip_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member_by_name(trip_id, name):
    """Find a member by name (case-insensitive)."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM members WHERE trip_id = ? AND LOWER(name) = LOWER(?)",
        (trip_id, name),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_member_contribution(member_id, contribution):
    """Update a member's base pool contribution."""
    conn = get_db()
    conn.execute(
        "UPDATE members SET initial_contribution = ? WHERE id = ?",
        (contribution, member_id),
    )
    conn.commit()
    conn.close()


# ───────────────── Expense CRUD ─────────────────

def add_expense(trip_id, paid_by, amount, title, category="General",
                expense_type="pool_expense", splits=None):
    """
    Add an expense with splits.
    splits: list of dicts {member_id, amount_consumed, is_participant}
    If splits is None, split equally among all members.
    """
    conn = get_db()

    cur = conn.execute(
        "INSERT INTO expenses (trip_id, paid_by, amount, title, category, type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (trip_id, paid_by, amount, title, category, expense_type),
    )
    expense_id = cur.lastrowid

    if splits is None:
        # Equal split among ALL members
        members = conn.execute(
            "SELECT id FROM members WHERE trip_id = ?", (trip_id,)
        ).fetchall()
        per_person = round(amount / len(members), 2) if members else 0
        for m in members:
            conn.execute(
                "INSERT INTO splits (expense_id, member_id, amount_consumed, is_participant) "
                "VALUES (?, ?, ?, 1)",
                (expense_id, m["id"], per_person),
            )
    else:
        for s in splits:
            conn.execute(
                "INSERT INTO splits (expense_id, member_id, amount_consumed, is_participant) "
                "VALUES (?, ?, ?, ?)",
                (expense_id, s["member_id"], s["amount_consumed"], s.get("is_participant", 1)),
            )

    conn.commit()
    conn.close()
    return expense_id


def get_expenses(trip_id):
    """Return all expenses for a trip, newest first, with payer name."""
    conn = get_db()
    rows = conn.execute(
        "SELECT e.*, m.name AS payer_name "
        "FROM expenses e JOIN members m ON e.paid_by = m.id "
        "WHERE e.trip_id = ? ORDER BY e.created_at DESC",
        (trip_id,),
    ).fetchall()
    expenses = []
    for r in rows:
        exp = dict(r)
        # Attach splits
        split_rows = conn.execute(
            "SELECT s.*, m.name AS member_name "
            "FROM splits s JOIN members m ON s.member_id = m.id "
            "WHERE s.expense_id = ?",
            (exp["id"],),
        ).fetchall()
        exp["splits"] = [dict(sr) for sr in split_rows]
        # Find excluded members
        exp["excluded"] = [
            sr["member_name"] for sr in exp["splits"] if not sr["is_participant"]
        ]
        expenses.append(exp)
    conn.close()
    return expenses


def delete_expense(expense_id):
    """Delete an expense and its splits."""
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()


# ───────────────── Balance Calculation ─────────────────

def get_balances(trip_id):
    """
    Calculate net balance for each member.
    Balance = (initial_contribution + total_paid) - total_consumed
    Positive → should receive money
    Negative → owes money
    """
    conn = get_db()
    
    trip_row = conn.execute("SELECT treasurer_id FROM trips WHERE id = ?", (trip_id,)).fetchone()
    raw_treasurer = trip_row["treasurer_id"] if trip_row else None
    no_treasurer = (raw_treasurer == -1)
    treasurer_id = None if no_treasurer else raw_treasurer

    members = conn.execute(
        "SELECT * FROM members WHERE trip_id = ?", (trip_id,)
    ).fetchall()

    balances = {}
    for m in members:
        mid = m["id"]
        name = m["name"]
        contribution = m["initial_contribution"]

        # Total paid by this member
        if mid == treasurer_id:
            # Treasurer is spending the pool cash. We do NOT count pool_expenses as an out-of-pocket addition for them.
            paid_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
                "WHERE trip_id = ? AND paid_by = ? AND type != 'pool_expense'",
                (trip_id, mid),
            ).fetchone()
        else:
            # Non-treasurers don't hold the pool, so their payments are always out-of-pocket credits.
            paid_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
                "WHERE trip_id = ? AND paid_by = ?",
                (trip_id, mid),
            ).fetchone()
            
        total_paid = paid_row["total"]

        # Total consumed by this member
        consumed_row = conn.execute(
            "SELECT COALESCE(SUM(s.amount_consumed), 0) AS total "
            "FROM splits s JOIN expenses e ON s.expense_id = e.id "
            "WHERE e.trip_id = ? AND s.member_id = ? AND s.is_participant = 1",
            (trip_id, mid),
        ).fetchone()
        total_consumed = consumed_row["total"]

        net = round((0 if no_treasurer else contribution) + total_paid - total_consumed, 2)

        balances[mid] = {
            "member_id": mid,
            "name": name,
            "contribution": contribution,
            "total_paid": total_paid,
            "total_consumed": total_consumed,
            "net_balance": net,
        }

    conn.close()
    return balances


# ───────────────── Summary Stats ─────────────────

def get_trip_summary(trip_id):
    """Return aggregate stats for the dashboard."""
    conn = get_db()

    trip_row = conn.execute("SELECT treasurer_id FROM trips WHERE id = ?", (trip_id,)).fetchone()
    raw_treasurer = trip_row["treasurer_id"] if trip_row else None
    no_treasurer = (raw_treasurer == -1)
    treasurer_id = None if no_treasurer else raw_treasurer

    # Total spent across all expenses
    total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE trip_id = ?",
        (trip_id,),
    ).fetchone()["total"]

    # Calculate real-time stats based on current balances
    balances = get_balances(trip_id)
    
    if no_treasurer:
        pool_collected = 0
        pool_balance = 0
    elif treasurer_id:
        pool_collected = sum(b["contribution"] + b["total_paid"] for b in balances.values())
        pool_initial = sum(b["contribution"] for b in balances.values())
        pool_spent_by_treasurer = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses "
            "WHERE trip_id = ? AND paid_by = ? AND type = 'pool_expense'",
            (trip_id, treasurer_id)
        ).fetchone()["total"]
        pool_balance = pool_initial - pool_spent_by_treasurer
    else:
        # Not chosen yet
        pool_collected = sum(b["contribution"] for b in balances.values())
        pool_balance = pool_collected

    categories = conn.execute(
        "SELECT category, SUM(amount) AS total FROM expenses "
        "WHERE trip_id = ? GROUP BY category ORDER BY total DESC",
        (trip_id,),
    ).fetchall()

    member_spending = conn.execute(
        "SELECT m.name, COALESCE(SUM(e.amount), 0) AS total_paid "
        "FROM members m LEFT JOIN expenses e ON e.paid_by = m.id AND e.trip_id = m.trip_id "
        "WHERE m.trip_id = ? GROUP BY m.id ORDER BY total_paid DESC",
        (trip_id,),
    ).fetchall()

    conn.close()
    return {
        "treasurer_id": raw_treasurer,
        "total_expense": total,
        "pool_balance": pool_balance,
        "pool_collected": pool_collected,
        "categories": [dict(c) for c in categories],
        "member_spending": [dict(ms) for ms in member_spending],
    }
