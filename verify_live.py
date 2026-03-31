"""Final live site verification matching user's exact scenario"""
import requests, time

BASE = 'https://trippool-ai.onrender.com'
s = requests.Session()

print("Waking up site...")
for i in range(3):
    try:
        r = s.get(f'{BASE}/login', timeout=120)
        print(f"  Up: {r.status_code}")
        break
    except Exception as e:
        print(f"  Try {i+1}: {type(e).__name__}")
        time.sleep(5)

# Register
r = s.post(f'{BASE}/register', json={'username': f'U_{int(time.time())}'}, timeout=30)
print(f"Register: {r.status_code}")

# Create trip: A(1000), B(1000), C(1000), D(1000)
r = s.post(f'{BASE}/api/trips', json={
    'name': 'Goa Trip',
    'members': [
        {'name': 'A', 'contribution': 1000},
        {'name': 'B', 'contribution': 1000},
        {'name': 'C', 'contribution': 1000},
        {'name': 'D', 'contribution': 1000},
    ]
}, timeout=30)
tid = r.json()['id']
mids = {m['name']: m['id'] for m in s.get(f'{BASE}/api/trips/{tid}/members', timeout=30).json()}
s.put(f'{BASE}/api/trips/{tid}/treasurer', json={'member_id': mids['A']}, timeout=30)

def show(label):
    r = s.get(f'{BASE}/api/trips/{tid}/balances', timeout=30)
    bals = {b['name']: b for b in r.json()}
    pc = list(bals.values())[0]['pool_collected']
    print(f"\n[{label}] Pool={pc}")
    for n, b in bals.items():
        st = 'REMAINING' if b['net_balance'] >= 0 else 'OWES'
        print(f"  {n}: PutIn={b['total_put_in']}, Used={b['total_consumed']}, {st}={abs(b['net_balance'])}")

show("Initial")

# A pays 400 pool_expense
s.post(f'{BASE}/api/trips/{tid}/expenses', json={'paid_by': mids['A'], 'amount': 400, 'title': 'Tickets', 'category': 'Travel', 'type': 'pool_expense'}, timeout=30)
show("After A pays 400 pool_expense")

# D pays 400 personal
s.post(f'{BASE}/api/trips/{tid}/expenses', json={'paid_by': mids['D'], 'amount': 400, 'title': 'Food', 'category': 'Food', 'type': 'personal_expense'}, timeout=30)
show("After D pays 400 personal")

print("\n[5 Reloads]")
for i in range(5):
    r1 = s.get(f'{BASE}/trip/{tid}', timeout=30)
    r2 = s.get(f'{BASE}/api/trips/{tid}/balances', timeout=30)
    r3 = s.get(f'{BASE}/api/trips/{tid}/summary', timeout=30)
    print(f"  Reload {i+1}: page={r1.status_code} bals={r2.status_code} sum={r3.status_code}")

print("\nDONE - All passed!" if all(x == 200 for x in [r1.status_code, r2.status_code, r3.status_code]) else "\nSOME FAILURES!")
