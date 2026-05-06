from database import SessionLocal
from models import User, Student

db = SessionLocal()

# Delete all users and students
db.query(User).delete()
db.query(Student).delete()
db.commit()

print("✓ Database cleared!")
print("You can now register again.")

db.close()