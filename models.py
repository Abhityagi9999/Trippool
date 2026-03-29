"""
models.py – Database layer for TripPool AI
Uses raw SQLite for simplicity and zero external deps.
"""

import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "trippool_v25.db")
if os.environ.get('VERCEL') or os.environ.get('RENDER'):
    DB_PATH = "/tmp/trippool_v25.db"


def get_db():
    """Return a new database connection with row_factory."""
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if not os.environ.get('RENDER'):
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn, table_name, column_def):
    """Safely add a column if it doesn't exist. Uses existing connection."""
    col_name = column_def.split()[0]
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if col_name not in columns:
        try:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_def}")
            conn.commit()
        except Exception:
            pass


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT    NOT NULL, -- No UNIQUE here to allow the manual migration below if needed, but we'll include password
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        password    TEXT    DEFAULT NULL
    );

    CREATE TABLE IF NOT EXISTS trips (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id    INTEGER,
        name        TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
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

    # Ensure all legacy columns exist (using same connection)
    _ensure_column(conn, "trips", "treasurer_id INTEGER DEFAULT NULL")
    _ensure_column(conn, "trips", "owner_id INTEGER DEFAULT NULL")
    _ensure_column(conn, "members", "initial_contribution REAL DEFAULT 0")
    _ensure_column(conn, "expenses", "type TEXT DEFAULT 'pool_expense'")
    _ensure_column(conn, "expenses", "category TEXT DEFAULT 'General'")
    _ensure_column(conn, "users", "password TEXT DEFAULT NULL")

    conn.commit()
    conn.close()


# ───────────────── User Registration/Login ────────

def auth_user(username, password):
    """Logs a user in. Returns (user_id, error_msg)."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchall()
    
    for row in rows:
        user_dict = dict(row)
        if user_dict.get("password") and check_password_hash(user_dict["password"], password):
            conn.close()
            return user_dict["id"], None
            
        # Legacy fallback if they have no password set in DB
        elif not user_dict.get("password"):
            hashed = generate_password_hash(password)
            conn.execute("UPDATE users SET password = ? WHERE id = ?", (hashed, user_dict["id"]))
            conn.commit()
            conn.close()
            return user_dict["id"], None

    conn.close()
    return None, "Incorrect name or password"

def register_user(username):
    """Create entirely new user with an auto-generated password."""
    import random
    import string
    conn = get_db()
    
    # Generate random 6 character password
    chars = string.ascii_letters + string.digits
    raw_password = ''.join(random.choices(chars, k=6))
    hashed = generate_password_hash(raw_password)
    
    cur = conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    
    return uid, raw_password

def get_user_by_name(username):
    """Get user by username."""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ───────────────── Trip CRUD ─────────────────

def create_trip(name, owner_id=None):
    """Create a new trip and return its id."""
    conn = get_db()
    cur = conn.execute("INSERT INTO trips (name, owner_id) VALUES (?, ?)", (name, owner_id))
    trip_id = cur.lastrowid
    conn.commit()
    conn.close()
    return trip_id


def get_all_trips(owner_id):
    """Return all trips for a specific user as list of dicts."""
    conn = get_db()
    rows = conn.execute(
        "SELECT t.*, "
        "(SELECT COUNT(*) FROM members m WHERE m.trip_id = t.id) AS member_count, "
        "(SELECT COALESCE(SUM(e.amount),0) FROM expenses e WHERE e.trip_id = t.id) AS total_expense "
        "FROM trips t WHERE t.owner_id = ? ORDER BY t.created_at DESC", (owner_id,)
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

    LOGIC:
    - Treasurer paying pool_expense → money comes from pool, Treasurer's put_in stays same
    - Treasurer paying personal_expense → out of pocket, Treasurer's put_in increases
    - Non-Treasurer paying anything → out of pocket, their put_in increases, pool grows
    - put_in = initial_contribution + personal out-of-pocket payments
    - net_balance = put_in - total_consumed
    """
    conn = get_db()

    trip_row = conn.execute("SELECT treasurer_id FROM trips WHERE id = ?", (trip_id,)).fetchone()
    raw_treasurer = trip_row["treasurer_id"] if trip_row else None
    no_treasurer = (raw_treasurer == -1)
    treasurer_id = None if no_treasurer else raw_treasurer

    members = conn.execute(
        "SELECT * FROM members WHERE trip_id = ?", (trip_id,)
    ).fetchall()

    # Total initial pool from ALL members
    pool_initial = conn.execute(
        "SELECT COALESCE(SUM(initial_contribution), 0) FROM members WHERE trip_id = ?",
        (trip_id,)
    ).fetchone()[0]

    # Total expenses paid by non-treasurer members (these add to pool)
    non_treas_paid = 0
    if treasurer_id:
        non_treas_paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses "
            "WHERE trip_id = ? AND paid_by != ?",
            (trip_id, treasurer_id)
        ).fetchone()[0]

    # Pool Collected = initial contributions + non-treasurer payments
    pool_collected = pool_initial + non_treas_paid

    balances = {}
    for m in members:
        mid = m["id"]
        name = m["name"]
        contribution = m["initial_contribution"]

        # Total paid by this member (ALL expenses)
        raw_paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses "
            "WHERE trip_id = ? AND paid_by = ?",
            (trip_id, mid),
        ).fetchone()[0]

        # Total consumed by this member (their share of all expenses)
        total_consumed = conn.execute(
            "SELECT COALESCE(SUM(s.amount_consumed), 0) "
            "FROM splits s JOIN expenses e ON s.expense_id = e.id "
            "WHERE e.trip_id = ? AND s.member_id = ? AND s.is_participant = 1",
            (trip_id, mid),
        ).fetchone()[0]

        # Calculate put_in based on role
        if mid == treasurer_id:
            # Treasurer: only personal_expense payments count as out-of-pocket
            personal_paid = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses "
                "WHERE trip_id = ? AND paid_by = ? AND type = 'personal_expense'",
                (trip_id, mid),
            ).fetchone()[0]
            total_put_in = contribution + personal_paid
        else:
            # Non-Treasurer: ALL payments are out-of-pocket
            total_put_in = contribution + raw_paid

        # Net balance = what you put in - what you consumed
        net = round(total_put_in - total_consumed, 2)

        # Treasurer's physical cash on hand
        cash_held = 0
        if mid == treasurer_id:
            all_pool_spent = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses "
                "WHERE trip_id = ? AND type = 'pool_expense'",
                (trip_id,)
            ).fetchone()[0]
            cash_held = round(pool_initial - all_pool_spent, 2)

        balances[mid] = {
            "member_id": mid,
            "name": name,
            "contribution": contribution,
            "total_paid": raw_paid,
            "total_put_in": round(total_put_in, 2),
            "total_consumed": round(total_consumed, 2),
            "net_balance": net,
            "cash_on_hand": max(cash_held, 0),
            "pool_collected": round(pool_collected, 2),
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

    # Get pool stats from balances (already computed correctly there)
    balances = get_balances(trip_id)

    if not balances:
        pool_collected = 0
        pool_balance = 0
    elif no_treasurer:
        pool_collected = sum(b.get("contribution", 0) for b in balances.values())
        pool_balance = pool_collected
    else:
        # Use pool_collected from any balance entry (it's the same for all)
        first_bal = next(iter(balances.values()))
        pool_collected = first_bal.get("pool_collected", 0)
        # Treasurer's cash_on_hand IS the pool_balance
        treas_bal = balances.get(treasurer_id, {})
        pool_balance = treas_bal.get("cash_on_hand", 0)

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
