"""
settlement.py – Settlement algorithms for TripPool AI

Two modes:
  1. Optimised (greedy) — minimises number of transactions
  2. Pool Coordinator — everyone pays/receives through one person
"""


def compute_settlements(balances, threshold=5.0):
    """
    Greedy algorithm: match highest debtor ↔ highest creditor.
    Returns list of {from_id, from_name, to_id, to_name, amount}
    """
    debtors, creditors = _split(balances, threshold)

    debtors.sort(key=lambda x: x["amount"], reverse=True)
    creditors.sort(key=lambda x: x["amount"], reverse=True)

    settlements = []
    i, j = 0, 0

    while i < len(debtors) and j < len(creditors):
        d, c = debtors[i], creditors[j]
        amt = round(min(d["amount"], c["amount"]), 2)

        if amt > threshold:
            settlements.append({
                "from_id": d["id"], "from_name": d["name"],
                "to_id": c["id"], "to_name": c["name"],
                "amount": amt,
            })

        d["amount"] = round(d["amount"] - amt, 2)
        c["amount"] = round(c["amount"] - amt, 2)

        if d["amount"] <= threshold:
            i += 1
        if c["amount"] <= threshold:
            j += 1

    return settlements


def compute_pool_coordinator(balances, coordinator_id, threshold=5.0):
    """
    Pool Coordinator mode: one person collects money from everyone
    who owes, and pays out to everyone who should receive.

    This is for the real-world scenario where one person handles
    all the money (like a trip treasurer).

    Returns:
        dict with:
            coordinator: {id, name}
            collect: list of {from_id, from_name, amount}  — people paying the coordinator
            payout:  list of {to_id, to_name, amount}      — coordinator paying out
            net_coordinator: float — coordinator's own net after all transactions
    """
    coordinator_info = balances.get(coordinator_id)
    if not coordinator_info:
        return {"error": "Coordinator not found"}

    collect = []  # People who owe money → pay coordinator
    payout = []   # People who should receive → coordinator pays them

    for mid, info in balances.items():
        if mid == coordinator_id:
            continue
        net = info["net_balance"]
        if net < -threshold:
            collect.append({
                "from_id": mid,
                "from_name": info["name"],
                "amount": round(abs(net), 2),
            })
        elif net > threshold:
            payout.append({
                "to_id": mid,
                "to_name": info["name"],
                "amount": round(net, 2),
            })

    # Sort by amount descending for cleaner display
    collect.sort(key=lambda x: x["amount"], reverse=True)
    payout.sort(key=lambda x: x["amount"], reverse=True)

    return {
        "coordinator": {
            "id": coordinator_id,
            "name": coordinator_info["name"],
        },
        "collect": collect,
        "payout": payout,
        "net_coordinator": round(coordinator_info["net_balance"], 2),
    }


def _split(balances, threshold):
    """Split balances into debtors and creditors lists."""
    debtors, creditors = [], []
    for mid, info in balances.items():
        net = info["net_balance"]
        if net < -threshold:
            debtors.append({"id": mid, "name": info["name"], "amount": abs(net)})
        elif net > threshold:
            creditors.append({"id": mid, "name": info["name"], "amount": net})
    return debtors, creditors
