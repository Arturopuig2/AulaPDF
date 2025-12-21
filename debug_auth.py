from app import auth, database, models

db = database.SessionLocal()
user = db.query(models.User).filter(models.User.username == "admin").first()

print(f"User found: {user.username}")
print(f"Stored Hash: {user.hashed_password}")

# Test the password
plain = "admin123"
is_valid = auth.verify_password(plain, user.hashed_password)
print(f"Password '{plain}' is valid? {is_valid}")

# Test generating a new hash
new_hash = auth.get_password_hash(plain)
print(f"New Hash verification: {auth.verify_password(plain, new_hash)}")
