"""
Comprehensive live site test - tests EVERY possible error scenario.
Tests the EXACT flow a real user would do in their browser.
"""
import requests
import time
import json

BASE = 'https://trippool-ai.onrender.com'

def test():
    s = requests.Session()
    errors = []
    
    # Step 1: Hit login page
    print("1. Login page...")
    r = s.get(f'{BASE}/login', timeout=120)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Login page: {r.status_code}")
        return errors
    
    # Step 2: Register
    uname = f'Test_{int(time.time())}'
    print(f"2. Register as {uname}...")
    r = s.post(f'{BASE}/register', json={'username': uname}, timeout=30)
    print(f"   Status: {r.status_code} Body: {r.text[:200]}")
    if r.status_code != 200:
        errors.append(f"Register: {r.status_code} {r.text[:500]}")
        return errors
    
    # Step 3: Home page after login
    print("3. Home page...")
    r = s.get(f'{BASE}/', timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Home: {r.status_code} {r.text[:500]}")
    
    # Step 4: Get trips (should be empty)
    print("4. API get trips...")
    r = s.get(f'{BASE}/api/trips', timeout=30)
    print(f"   Status: {r.status_code} Body: {r.text[:200]}")
    if r.status_code != 200:
        errors.append(f"Get trips: {r.status_code} {r.text[:500]}")
    
    # Step 5: Create trip with members
    print("5. Create trip...")
    r = s.post(f'{BASE}/api/trips', json={
        'name': 'Test Trip',
        'members': [
            {'name': 'A', 'contribution': 1000},
            {'name': 'B', 'contribution': 1000},
            {'name': 'C', 'contribution': 1000},
            {'name': 'D', 'contribution': 1000},
        ]
    }, timeout=30)
    print(f"   Status: {r.status_code} Body: {r.text[:200]}")
    if r.status_code not in [200, 201]:
        errors.append(f"Create trip: {r.status_code} {r.text[:500]}")
        return errors
    tid = r.json()['id']
    
    # Step 6: Get members
    print("6. Get members...")
    r = s.get(f'{BASE}/api/trips/{tid}/members', timeout=30)
    print(f"   Status: {r.status_code}")
    members = r.json()
    mids = {m['name']: m['id'] for m in members}
    print(f"   Members: {mids}")
    
    # Step 7: Set treasurer
    print("7. Set A as treasurer...")
    r = s.put(f'{BASE}/api/trips/{tid}/treasurer', json={'member_id': mids['A']}, timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Set treasurer: {r.status_code} {r.text[:500]}")
    
    # Step 8: Trip page
    print("8. Trip page (first load)...")
    r = s.get(f'{BASE}/trip/{tid}', timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Trip page: {r.status_code} {r.text[:500]}")
    
    # Step 9: Summary
    print("9. Trip summary...")
    r = s.get(f'{BASE}/api/trips/{tid}/summary', timeout=30)
    print(f"   Status: {r.status_code} Body: {r.text[:200]}")
    if r.status_code != 200:
        errors.append(f"Summary: {r.status_code} {r.text[:500]}")
    
    # Step 10: Balances
    print("10. Balances...")
    r = s.get(f'{BASE}/api/trips/{tid}/balances', timeout=30)
    print(f"   Status: {r.status_code} Body: {r.text[:200]}")
    if r.status_code != 200:
        errors.append(f"Balances: {r.status_code} {r.text[:500]}")
    
    # Step 11: Add expense (A pays 400 pool_expense)
    print("11. Add expense (A pool_expense 400)...")
    r = s.post(f'{BASE}/api/trips/{tid}/expenses', json={
        'paid_by': mids['A'],
        'amount': 400,
        'title': 'Tickets',
        'category': 'Travel',
        'type': 'pool_expense',
        'splits': [
            {'member_id': mids['A'], 'amount_consumed': 100, 'is_participant': 1},
            {'member_id': mids['B'], 'amount_consumed': 100, 'is_participant': 1},
            {'member_id': mids['C'], 'amount_consumed': 100, 'is_participant': 1},
            {'member_id': mids['D'], 'amount_consumed': 100, 'is_participant': 1},
        ]
    }, timeout=30)
    print(f"   Status: {r.status_code} Body: {r.text[:200]}")
    if r.status_code not in [200, 201]:
        errors.append(f"Add expense: {r.status_code} {r.text[:500]}")
    
    # Step 12: Balances after expense
    print("12. Balances after expense...")
    r = s.get(f'{BASE}/api/trips/{tid}/balances', timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        for b in r.json():
            print(f"   {b['name']}: Put In={b['total_put_in']}, Used={b['total_consumed']}, Remaining={b['net_balance']}")
    else:
        errors.append(f"Balances after expense: {r.status_code} {r.text[:500]}")
    
    # Step 13: Trip page RELOAD
    print("13. Trip page RELOAD...")
    r = s.get(f'{BASE}/trip/{tid}', timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Trip reload: {r.status_code} {r.text[:500]}")
    
    # Step 14: Summary after expense
    print("14. Summary after expense...")
    r = s.get(f'{BASE}/api/trips/{tid}/summary', timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Summary after: {r.status_code} {r.text[:500]}")
    
    # Step 15: Settlement
    print("15. Settlement...")
    r = s.get(f'{BASE}/api/trips/{tid}/settlement', timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Settlement: {r.status_code} {r.text[:500]}")
    
    # Step 16: Parse expense text
    print("16. Parse expense text...")
    r = s.post(f'{BASE}/api/trips/{tid}/parse', json={'text': 'A paid 200 for food'}, timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Parse: {r.status_code} {r.text[:500]}")
    
    # Step 17: Delete trip
    print("17. Delete trip...")
    r = s.delete(f'{BASE}/api/trips/{tid}', timeout=30)
    print(f"   Status: {r.status_code}")
    
    # Step 18: Home after delete
    print("18. Home after delete...")
    r = s.get(f'{BASE}/', timeout=30)
    print(f"   Status: {r.status_code}")
    if r.status_code != 200:
        errors.append(f"Home after delete: {r.status_code}")
    
    return errors

print("=" * 60)
print("COMPREHENSIVE LIVE SITE TEST")
print("=" * 60)
errs = test()
print("\n" + "=" * 60)
if errs:
    print(f"FAILED - {len(errs)} errors:")
    for e in errs:
        print(f"  - {e}")
else:
    print("ALL TESTS PASSED - NO ERRORS")
print("=" * 60)
