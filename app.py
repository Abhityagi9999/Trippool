"""
app.py – Main Flask application for TripPool AI
Serves both the frontend templates and the REST API.
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from flask_cors import CORS
from datetime import timedelta
import models
from utils.settlement import compute_settlements, compute_pool_coordinator
from utils.ai_parser import parse_expense_text

app = Flask(__name__)
app.secret_key = "trippool_super_secret_key"
app.permanent_session_lifetime = timedelta(days=365)
CORS(app)

# Initialise the database once at startup
try:
    models.init_db()
except Exception as e:
    import sys, traceback
    sys.stderr.write(f"INIT_DB ERROR: {e}\n")
    traceback.print_exc(file=sys.stderr)

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Cache-Control'] = 'public, max-age=0'
    return r

@app.route('/robots.txt')
def robots(): return send_from_directory('static', 'robots.txt')

@app.route('/sitemap.xml')
def sitemap(): return send_from_directory('static', 'sitemap.xml')

@app.route('/sw.js')
def sw(): return send_from_directory('static', 'sw-v25.js', mimetype='application/javascript')

@app.route('/manifest.json')
def manifest(): return send_from_directory('static', 'manifest.json')


@app.errorhandler(500)
def handle_500(e):
    import traceback
    err_str = str(e).lower()
    # If it's a DB lock, return 503 (Service Unavailable / Retry Later)
    if "locked" in err_str:
        return jsonify({
            "error": "Database Busy", 
            "message": "The system is currently handling another request. Please try again in a moment.",
            "retry_after": 1
        }), 503
    
    return jsonify({"error": "Internal Server Error", "debug": str(e), "traceback": traceback.format_exc()}), 500


# ═══════════════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if not username or not password:
            return jsonify({"error": "Name and password required"}), 400
            
        uid, err = models.auth_user(username, password)
        if err:
            return jsonify({"error": err}), 401
            
        session.permanent = True
        session["user_id"] = uid
        session["username"] = username
        return jsonify({"ok": True}), 200
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "Name is required"}), 400
        
    uid, gen_pass = models.register_user(username)
    session.permanent = True
    session["user_id"] = uid
    session["username"] = username
    return jsonify({"ok": True, "password": gen_pass}), 200

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ═══════════════════════════════════════════════════
#  PAGE ROUTES
# ═══════════════════════════════════════════════════

@app.route("/")
def home():
    """Landing page – list of trips."""
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))
    return render_template("index.html", username=session.get("username", "User"))


@app.route("/offline")
def offline():
    """Offline fallback page."""
    return render_template("offline.html")


@app.route("/trip/<int:trip_id>")
def trip_page(trip_id):
    """Trip dashboard page."""
    trip = models.get_trip(trip_id)
    if not trip:
        return "Trip not found", 404
    return render_template("trip.html", trip=trip)


# ═══════════════════════════════════════════════════
#  API – TRIPS
# ═══════════════════════════════════════════════════

@app.route("/api/trips", methods=["GET"])
def api_get_trips():
    """Return all trips."""
    uid = session.get("user_id")
    if not uid:
        return jsonify([]), 401
    return jsonify(models.get_all_trips(uid))


@app.route("/api/trips", methods=["POST"])
def api_create_trip():
    """Create a new trip. Body: {name, members: [{name, contribution}]}"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Trip name is required"}), 400

    trip_id = models.create_trip(name, owner_id=uid)

    # Add members if provided
    members = data.get("members", [])
    for m in members:
        mname = m.get("name", "").strip()
        if mname:
            models.add_member(trip_id, mname, m.get("contribution", 0))

    return jsonify({"id": trip_id, "name": name}), 201


@app.route("/api/trips/<int:trip_id>", methods=["DELETE"])
def api_delete_trip(trip_id):
    """Delete a trip."""
    models.delete_trip(trip_id)
    return jsonify({"ok": True})


@app.route("/api/trips/<int:trip_id>/treasurer", methods=["PUT"])
def api_set_treasurer(trip_id):
    """Set the trip's treasurer. Body: {member_id}"""
    data = request.get_json()
    if "member_id" not in data:
        return jsonify({"error": "member_id field required"}), 400
    member_id = data.get("member_id")
    models.set_trip_treasurer(trip_id, member_id)
    return jsonify({"ok": True}), 200


# ═══════════════════════════════════════════════════
#  API – MEMBERS
# ═══════════════════════════════════════════════════

@app.route("/api/trips/<int:trip_id>/members", methods=["GET"])
def api_get_members(trip_id):
    """Return all members of a trip."""
    return jsonify(models.get_members(trip_id))


@app.route("/api/trips/<int:trip_id>/members", methods=["POST"])
def api_add_member(trip_id):
    """Add a single member. Body: {name, contribution}"""
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    try:
        mid = models.add_member(trip_id, name, data.get("contribution", 0))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": mid, "name": name}), 201


@app.route("/api/trips/<int:trip_id>/members/<int:member_id>", methods=["PUT"])
def api_update_member(trip_id, member_id):
    """Update a member's pool contribution. Body: {contribution}"""
    data = request.get_json()
    contribution = data.get("contribution")
    if contribution is None:
        return jsonify({"error": "contribution required"}), 400
    try:
        models.update_member_contribution(member_id, float(contribution))
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True}), 200


# ═══════════════════════════════════════════════════
#  API – EXPENSES
# ═══════════════════════════════════════════════════

@app.route("/api/trips/<int:trip_id>/expenses", methods=["GET"])
def api_get_expenses(trip_id):
    """Return all expenses for a trip."""
    return jsonify(models.get_expenses(trip_id))


@app.route("/api/trips/<int:trip_id>/expenses", methods=["POST"])
def api_add_expense(trip_id):
    """
    Add an expense.
    Body: {
        paid_by: member_id,
        amount: float,
        title: str,
        category: str,
        type: "pool_expense" | "personal_expense",
        splits: [{member_id, amount_consumed, is_participant}]  (optional)
    }
    """
    data = request.get_json()
    paid_by = data.get("paid_by")
    amount = data.get("amount")
    title = data.get("title", "Expense")

    if not paid_by or not amount:
        return jsonify({"error": "paid_by and amount are required"}), 400

    expense_id = models.add_expense(
        trip_id=trip_id,
        paid_by=paid_by,
        amount=float(amount),
        title=title,
        category=data.get("category", "General"),
        expense_type=data.get("type", "pool_expense"),
        splits=data.get("splits"),
    )
    return jsonify({"id": expense_id}), 201


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def api_delete_expense(expense_id):
    """Delete an expense."""
    models.delete_expense(expense_id)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════
#  API – BALANCES & SETTLEMENTS
# ═══════════════════════════════════════════════════

@app.route("/api/trips/<int:trip_id>/balances", methods=["GET"])
def api_get_balances(trip_id):
    """Return per-member balances."""
    balances = models.get_balances(trip_id)
    return jsonify(list(balances.values()))


@app.route("/api/trips/<int:trip_id>/settlement", methods=["GET"])
def api_get_settlement(trip_id):
    """Return optimised settlement transactions."""
    trip = models.get_trip(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404
        
    balances = models.get_balances(trip_id)
    settlements = compute_settlements(balances, treasurer_id=trip.get("treasurer_id"))
    return jsonify(settlements)
@app.route("/api/trips/<int:trip_id>/settlement/coordinator/<int:coordinator_id>", methods=["GET"])
def api_get_coordinator_settlement(trip_id, coordinator_id):
    """Return pool-coordinator settlement (one person handles all money)."""
    trip = models.get_trip(trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404
    balances = models.get_balances(trip_id)
    result = compute_pool_coordinator(balances, coordinator_id)
    return jsonify(result)


@app.route("/api/trips/<int:trip_id>/summary", methods=["GET"])
def api_get_summary(trip_id):
    """Return trip summary stats for dashboard."""
    return jsonify(models.get_trip_summary(trip_id))


# ═══════════════════════════════════════════════════
#  API – AI PARSER
# ═══════════════════════════════════════════════════

@app.route("/api/trips/<int:trip_id>/parse", methods=["POST"])
def api_parse_expense(trip_id):
    """
    Parse natural language text into expense fields.
    Body: {text: str}
    Returns parsed fields for preview before saving.
    """
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required"}), 400

    members = models.get_members(trip_id)
    member_names = [m["name"] for m in members]
    current_user = data.get("current_user")

    parsed = parse_expense_text(text, member_names, current_user)

    # Resolve paid_by name to member_id
    if parsed["paid_by"]:
        member = models.get_member_by_name(trip_id, parsed["paid_by"])
        if member:
            parsed["paid_by_id"] = member["id"]

    # Resolve excluded names to member_ids
    excluded_ids = []
    for ename in parsed["excluded"]:
        member = models.get_member_by_name(trip_id, ename)
        if member:
            excluded_ids.append(member["id"])
    parsed["excluded_ids"] = excluded_ids

    # Resolve exact split names to member_ids
    exact_splits_ids = {}
    for ename, amt in parsed.get("exact_splits", {}).items():
        member = models.get_member_by_name(trip_id, ename)
        if member:
            exact_splits_ids[str(member["id"])] = amt
    parsed["exact_splits_ids"] = exact_splits_ids

    return jsonify(parsed)


@app.route("/api/parse-trip", methods=["POST"])
def api_parse_trip_creation():
    """
    Parse text to extract trip name and members.
    Body: {text: str}
    """
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required"}), 400

    from utils.ai_parser import parse_trip_creation_text
    parsed = parse_trip_creation_text(text)
    return jsonify(parsed)

#  SEED DATA
# ═══════════════════════════════════════════════════

@app.route("/api/seed", methods=["POST"])
def api_seed():
    """Insert sample Nainital trip data for demo purposes."""
    # Create trip
    uid = session.get("user_id")
    if not uid:
        uid, _ = models.auth_user("DemoUser", "demo123")
        session["user_id"] = uid
        session["username"] = "DemoUser"

    trip_id = models.create_trip("Nainital Trip 🏔️", owner_id=uid)

    # Add members with initial contributions
    m1 = models.add_member(trip_id, "Kashish", 1000)
    m2 = models.add_member(trip_id, "Yash", 1000)
    m3 = models.add_member(trip_id, "Ankit", 1500)
    m4 = models.add_member(trip_id, "Vansh", 1000)

    # Expense 1: Train tickets – paid by Vansh, split equally
    models.add_expense(
        trip_id, m4, 1200, "Train Tickets", "Travel", "pool_expense",
        splits=[
            {"member_id": m1, "amount_consumed": 300, "is_participant": 1},
            {"member_id": m2, "amount_consumed": 300, "is_participant": 1},
            {"member_id": m3, "amount_consumed": 300, "is_participant": 1},
            {"member_id": m4, "amount_consumed": 300, "is_participant": 1},
        ]
    )

    # Expense 2: Dinner – Kashish didn't eat
    models.add_expense(
        trip_id, m2, 900, "Dinner at Restaurant", "Food", "pool_expense",
        splits=[
            {"member_id": m1, "amount_consumed": 0, "is_participant": 0},
            {"member_id": m2, "amount_consumed": 300, "is_participant": 1},
            {"member_id": m3, "amount_consumed": 300, "is_participant": 1},
            {"member_id": m4, "amount_consumed": 300, "is_participant": 1},
        ]
    )

    # Expense 3: Cab – all
    models.add_expense(
        trip_id, m3, 800, "Cab to Nainital Lake", "Travel", "pool_expense",
        splits=[
            {"member_id": m1, "amount_consumed": 200, "is_participant": 1},
            {"member_id": m2, "amount_consumed": 200, "is_participant": 1},
            {"member_id": m3, "amount_consumed": 200, "is_participant": 1},
            {"member_id": m4, "amount_consumed": 200, "is_participant": 1},
        ]
    )

    # Expense 4: Chai – all
    models.add_expense(
        trip_id, m1, 200, "Evening Chai ☕", "Food", "pool_expense",
        splits=[
            {"member_id": m1, "amount_consumed": 50, "is_participant": 1},
            {"member_id": m2, "amount_consumed": 50, "is_participant": 1},
            {"member_id": m3, "amount_consumed": 50, "is_participant": 1},
            {"member_id": m4, "amount_consumed": 50, "is_participant": 1},
        ]
    )

    # Expense 5: Hotel – all
    models.add_expense(
        trip_id, m4, 2400, "Hotel Stay (2 nights)", "Stay", "pool_expense",
        splits=[
            {"member_id": m1, "amount_consumed": 600, "is_participant": 1},
            {"member_id": m2, "amount_consumed": 600, "is_participant": 1},
            {"member_id": m3, "amount_consumed": 600, "is_participant": 1},
            {"member_id": m4, "amount_consumed": 600, "is_participant": 1},
        ]
    )

    return jsonify({"ok": True, "trip_id": trip_id}), 201


# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
