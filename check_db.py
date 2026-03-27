import sqlite3
import os

DB_PATH = "trippool.db"

def check_db():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("--- Trips ---")
    cur.execute("SELECT id, name FROM trips WHERE name LIKE '%TripPool%';")
    rows = cur.fetchall()
    for row in rows:
        print(row)
        
    print("--- Members ---")
    cur.execute("SELECT id, name FROM members WHERE name LIKE '%TripPool%';")
    rows = cur.fetchall()
    for row in rows:
        print(row)
        
    conn.close()

if __name__ == "__main__":
    check_db()
