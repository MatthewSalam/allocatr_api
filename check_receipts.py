from database import SessionLocal
from models import Receipt, Student

db = SessionLocal()

receipts = db.query(Receipt, Student).join(Student).all()

print("\n" + "="*60)
print("RECEIPTS IN DATABASE")
print("="*60)

for receipt, student in receipts:
    print(f"\n📄 Receipt ID: {receipt.id}")
    print(f"   Student: {student.full_name} ({student.matric_number})")
    print(f"   Status: {receipt.verification_status}")
    print(f"   Amount: {receipt.amount}")
    print(f"   Uploaded: {receipt.uploaded_at}")
    print(f"   Session: {receipt.academic_session}")

print("\n" + "="*60)

# Count by status
pending = len([r for r, s in receipts if r.verification_status == 'pending'])
verified = len([r for r, s in receipts if r.verification_status == 'verified'])
rejected = len([r for r, s in receipts if r.verification_status == 'rejected'])

print(f"Total: {len(receipts)}")
print(f"Pending: {pending}")
print(f"Verified: {verified}")
print(f"Rejected: {rejected}")
print("="*60)

db.close()