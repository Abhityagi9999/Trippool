import models

def test():
    models.init_db()
    uid, pw = models.register_user("TestUser")
    print(f"User created: {uid}")
    
    trip_id = models.create_trip("Test Trip", owner_id=uid)
    print(f"Trip created: {trip_id}")
    
    mid = models.add_member(trip_id, "Alice", 1000)
    print(f"Member added: {mid}")
    
    bals = models.get_balances(trip_id)
    print(f"Balances: {bals}")

if __name__ == "__main__":
    test()
