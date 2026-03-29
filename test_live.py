import requests, time

BASE = 'https://trippool-ai.onrender.com'
s = requests.Session()

def check(label, r):
    ok = r.status_code < 400
    print(f"{'OK' if ok else 'FAIL'} {label}: {r.status_code}", end='')
    if not ok:
        try:
            print(f" ERROR: {r.json()}")
        except:
            print(f" ERROR: {r.text[:200]}")
    else:
        print()
    return ok

all_ok = True

# 1. Register
r = s.post(f'{BASE}/register', json={'username': 'StressTest_' + str(int(time.time()))})
all_ok &= check('Register', r)

# 2. Home page
r = s.get(f'{BASE}/')
all_ok &= check('Home Page', r)

# 3. Create trip
r = s.post(f'{BASE}/api/trips', json={'name': 'Debug Trip', 'members': [
    {'name': 'Amit', 'contribution': 1000},
    {'name': 'Raj', 'contribution': 1000},
]})
all_ok &= check('Create Trip', r)
tid = r.json().get('id', 1)

# 4. Get members
r = s.get(f'{BASE}/api/trips/{tid}/members')
all_ok &= check('Get Members', r)

# 5. Trip page (first load)
r = s.get(f'{BASE}/trip/{tid}')
all_ok &= check('Trip Page Load 1', r)

# 6. Summary
r = s.get(f'{BASE}/api/trips/{tid}/summary')
all_ok &= check('Summary', r)

# 7. Balances
r = s.get(f'{BASE}/api/trips/{tid}/balances')
all_ok &= check('Balances', r)

# 8. Expenses
r = s.get(f'{BASE}/api/trips/{tid}/expenses')
all_ok &= check('Expenses', r)

# 9. Settlement
r = s.get(f'{BASE}/api/trips/{tid}/settlement')
all_ok &= check('Settlement', r)

# 10. Trip page RELOAD
r = s.get(f'{BASE}/trip/{tid}')
all_ok &= check('Trip Page Reload', r)

# 11. Home RELOAD
r = s.get(f'{BASE}/')
all_ok &= check('Home Reload', r)

# 12. Trip page RELOAD again 
r = s.get(f'{BASE}/trip/{tid}')
all_ok &= check('Trip Page Reload 2', r)

# 13. Summary RELOAD
r = s.get(f'{BASE}/api/trips/{tid}/summary')
all_ok &= check('Summary Reload', r)

# 14. Balances RELOAD
r = s.get(f'{BASE}/api/trips/{tid}/balances')
all_ok &= check('Balances Reload', r)

print(f"\n{'ALL PASSED' if all_ok else 'SOME FAILED'}")
