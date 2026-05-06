from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Numeric, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
import enum

class GenderEnum(enum.Enum):
    """Gender options - limits choices to Male or Female"""
    MALE = "MALE"
    FEMALE = "FEMALE"

class VerificationStatusEnum(enum.Enum):
    """Receipt verification status"""
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

class RoomStatusEnum(enum.Enum):
    """Room availability status"""
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    MAINTENANCE = "maintenance"

class DepartmentEnum(enum.Enum):
    """7 clearance departments"""
    ADMISSION = "Admission"
    BURSARY = "Bursary"
    CHAPLAINCY = "Chaplaincy"
    CAFETERIA = "Cafeteria"
    FACULTY = "Faculty"
    INTERNAL_AUDIT = "Internal Audit"
    HALL_OF_RESIDENCE = "Hall of Residence"

# ==================== SHARED MODELS ====================
class Student(Base):
    """
    Stores student information
    SHARED by both hostel and clearance modules
    """
    __tablename__ = "students" 
    id = Column(Integer, primary_key=True, index=True) 
    # Student Details
    matric_number = Column(String(20), unique=True, nullable=False, index=True)    
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    gender = Column(Enum(GenderEnum), nullable=False)  # consistent
    level = Column(String(10))  # '100', '200', '300', '400'
    department = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships (connects to other tables)
    user = relationship("User", back_populates="student", uselist=False)    
    receipts = relationship("Receipt", back_populates="student")    
    allocations = relationship("Allocation", back_populates="student")
    # EXPLANATION: One student can have many allocations (one per session)
    qr_codes = relationship("QRCode", back_populates="student")
    clearances = relationship("Clearance", back_populates="student")

class User(Base):
    """
    Authentication table for all users (students, admins, officers)
    SHARED by both modules
    """
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20))    
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)    
    role = Column(String(20), nullable=False, index=True)
    # EXPLANATION: 'student', 'admin', or 'officer' - indexed for fast role-based queries
    
    department = Column(String(50))
    # EXPLANATION: For officers only - which department they belong to
    
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"))
    # EXPLANATION: Links to students table, CASCADE means if student deleted, user also deleted
    
    is_active = Column(Boolean, default=True)    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    student = relationship("Student", back_populates="user")
    clearances_performed = relationship("Clearance", foreign_keys="[Clearance.cleared_by]")
    # EXPLANATION: user.student gives you the Student object for this user

# ==================== HOSTEL ALLOCATION MODELS ====================
class Receipt(Base):
    __tablename__ = "receipts"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    
    # File Information
    file_path = Column(Text, nullable=False)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50))
    file_size = Column(Integer)
    uploaded_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Verification Status
    verification_status = Column(String(20), default='pending')
    verified_by = Column(Integer, ForeignKey("users.id"))
    verified_at = Column(DateTime)
    rejection_reason = Column(Text)
    academic_session = Column(String(20))
    
    # Payment Details
    amount = Column(Numeric(10, 2))
    payment_reference = Column(String(100))
    
    # NEW: Room Preferences (OPTIONAL)
    preferred_block = Column(String(20))
    # EXPLANATION: e.g., "Block A", "Block B" - student's first choice
    
    preferred_room_number = Column(String(10))
    # EXPLANATION: e.g., "22" - specific room they want (optional)
    # Relationships
    student = relationship("Student", back_populates="receipts")
    verified_by_user = relationship("User", foreign_keys=[verified_by])

class Room(Base):
    __tablename__ = "rooms"
    
    id = Column(Integer, primary_key=True, index=True)
    block = Column(String(20), nullable=False)
    room_number = Column(String(10), nullable=False)
    floor = Column(Integer)
    # Capacity tracking
    capacity = Column(Integer, default=6)    
    current_occupants = Column(Integer, default=0)
    # EXPLANATION: How many students are currently in this room
    # UPDATE THIS when allocating/deallocating students
    
    gender = Column(Enum(GenderEnum), nullable=False)  # consistent
    status = Column(String(20), default='available', index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    allocations = relationship("Allocation", back_populates="room")

class Allocation(Base):
    """
    Links students to rooms (room assignments)
    HOSTEL MODULE - Created by FCFS algorithm
    """
    __tablename__ = "allocations"
    id = Column(Integer, primary_key=True, index=True)
    # Foreign Keys
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    
    # Allocation Details
    allocated_at = Column(DateTime, default=datetime.utcnow)
    # EXPLANATION: When was this room assigned
    
    allocation_method = Column(String(20), default='FCFS')
    # EXPLANATION: How was it allocated (always 'FCFS' in your case)
    
    academic_session = Column(String(20), nullable=False)
    # EXPLANATION: '2025/2026' - which academic year
    
    status = Column(String(20), default='active')
    # EXPLANATION: 'active' or 'cancelled'
    
    # Relationships
    student = relationship("Student", back_populates="allocations")
    room = relationship("Room", back_populates="allocations")
    qr_codes = relationship("QRCode", back_populates="allocation")
    # EXPLANATION: allocation.qr_codes gives QR codes generated for this allocation

# ==================== QR CLEARANCE MODELS ====================
class QRCode(Base):
    """
    Stores generated QR codes for students
    QR MODULE - Auto-generated after allocation
    """
    __tablename__ = "qr_codes"
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    allocation_id = Column(Integer, ForeignKey("allocations.id", ondelete="CASCADE"), nullable=False)
    # EXPLANATION: QR code is linked to both student and their allocation
    
    # QR Data
    qr_data = Column(Text, nullable=False)
    # EXPLANATION: JSON string containing student_id, allocation_id, timestamp, signature
    
    hmac_signature = Column(Text, nullable=False)
    # EXPLANATION: Security signature to prevent QR code forgery
    
    qr_image_base64 = Column(Text)
    # EXPLANATION: The actual QR code image as base64 string
    
    # Timestamps
    generated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    # EXPLANATION: Optional expiry (can set QR to expire after some time)
    
    is_active = Column(Boolean, default=True)
    # Relationships
    student = relationship("Student", back_populates="qr_codes")
    allocation = relationship("Allocation", back_populates="qr_codes")
    clearances = relationship("Clearance", back_populates="qr_code")

class Clearance(Base):
    """
    Stores clearance records for each department
    QR MODULE - Created when officer scans QR code
    """
    __tablename__ = "clearances"
    __table_args__ = (
        UniqueConstraint('student_id', 'department', 'academic_session',
                         name='uq_clearance_student_dept_session'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    cleared_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    # EXPLANATION: Which officer cleared this student

    qr_code_id = Column(Integer, ForeignKey("qr_codes.id"))
    # EXPLANATION: Which QR code was scanned (optional, can be NULL if manual)

    # Clearance Details
    department = Column(String(50), nullable=False, index=True)
    # EXPLANATION: Which of the 7 departments cleared this

    cleared_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)
    # EXPLANATION: Officer can add notes like "Paid in full" or "Documents verified"

    academic_session = Column(String(20), nullable=False)

    # Relationships
    student = relationship("Student", back_populates="clearances")
    qr_code = relationship("QRCode", back_populates="clearances")
    cleared_by_user = relationship("User", foreign_keys=[cleared_by])