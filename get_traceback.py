import requests, time
BASE = 'https://trippool-ai.onrender.com'
s = requests.Session()
# Wake up the site
s.get(f'{BASE}/login', timeout=120)
time.sleep(2)
# Register
r = s.post(f'{BASE}/register', json={'username': f'Debug_{int(time.time())}'}, timeout=30)
print(f"Status: {r.status_code}")
print(f"Full response:")
import json
try:
    data = r.json()
    if 'traceback' in data:
        print("TRACEBACK:")
        print(data['traceback'])
    else:
        print(json.dumps(data, indent=2))
except:
    print(r.text)
