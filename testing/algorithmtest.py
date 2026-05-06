import sys
import os
from datetime import datetime, timedelta
# Go up one level from testing/ folder
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
# Import from root-level files
from database import Base
from models import Student, User, Receipt, Room, Allocation, QRCode
from services.fcfs_allocator import FCFSAllocator
from security import get_password_hash

# SQLite database
TEST_DATABASE_URL = "sqlite:///test_hostel.db"

def setup_test_database():
    print("\n" + "="*60)
    print("Setting up test database...")
    print("="*60)
    
    engine = create_engine(
        TEST_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
    
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    print("✓ Database created")
    return db

def create_test_data(db):
    print("\n" + "="*60)
    print("Creating test data...")
    print("="*60)
    
    # Create rooms
    rooms = [
        Room(block="Block A", room_number="101", capacity=2, gender="Male", status="available"),
        Room(block="Block A", room_number="102", capacity=2, gender="Male", status="available"),
        Room(block="Block B", room_number="101", capacity=2, gender="Female", status="available"),
    ]
    for room in rooms:
        db.add(room)
    db.flush()
    
    # Create students
    students_data = [
        ("22/0001", "John Doe", "Male"),
        ("22/0002", "Jane Smith", "Female"),
    ]
    
    base_time = datetime.now(timezone.utc)
    
    for i, (matric, name, gender) in enumerate(students_data):
        # Create student
        student = Student(
            matric_number=matric,
            full_name=name,
            email=f"{matric.replace('/', '_')}@test.com",
            gender=gender,
            level="400",
            department="Software Engineering"
        )
        db.add(student)
        db.flush()
        
        # Create user
        user = User(
            email=student.email,
            password_hash=get_password_hash("password123"),
            role="student",
            student_id=student.id
        )
        db.add(user)
        
        # Create verified receipt
        receipt = Receipt(
            student_id=student.id,
            file_path=f"/uploads/receipt_{student.id}.pdf",
            file_name=f"receipt_{student.id}.pdf",
            file_type="application/pdf",
            uploaded_at=base_time + timedelta(minutes=i*10),
            verification_status="verified"
        )
        db.add(receipt)
    
    db.commit()
    print(f"✓ Created test data")

def test_allocation(db):
    print("\n" + "="*60)
    print("Running FCFS Allocation...")
    print("="*60)
    
    allocator = FCFSAllocator(db)
    result = allocator.allocate_rooms(academic_session="2025/2026")
    
    print(f"\n📊 Results:")
    print(f"  Total: {result['total_students']}")
    print(f"  Allocated: {result['allocated']}")
    print(f"  Failed: {result['failed']}")
    
    return result

if __name__ == "__main__":
    os.environ["QR_SECRET"] = "test-secret-key"
    
    print("="*60)
    print("FCFS ALLOCATOR TEST")
    print("="*60)
    
    db = setup_test_database()
    create_test_data(db)
    test_allocation(db)
    
    db.close()
    print("\n✓ Test complete!")