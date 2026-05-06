from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import Receipt, Student, Room, Allocation, QRCode
from services.qr_generator import generate_qr_code
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FCFSAllocator:
    """
    First-Come-First-Serve Hostel Allocation Algorithm
    Allocates rooms based on receipt upload timestamp
    """ 
    def __init__(self, db: Session):
        self.db = db
        # EXPLANATION: Store database session for queries
    
    def allocate_rooms(self, academic_session: str, gender: str = None) -> dict:
        """
        Allocate hostel rooms using FCFS algorithm
        
        Args:
            academic_session: e.g., "2025/2026"
            gender: Optional - "Male" or "Female" (None = allocate both)
        
        Returns:
            dict with allocation statistics
        """
        logger.info(f"Starting FCFS allocation for session: {academic_session}")
        
        try:
            # Step 1: Get all verified receipts without allocation (FCFS order!)
            query = self.db.query(Receipt, Student).join(
                Student, Receipt.student_id == Student.id
            ).outerjoin(
                Allocation,
                and_(
                    Allocation.student_id == Student.id,
                    Allocation.academic_session == academic_session
                )
            ).filter(
                Receipt.verification_status == 'verified',  # Only verified receipts
                Allocation.id == None  # No allocation yet
            )
            # EXPLANATION: Join students and check they don't have allocation for this session
            
            # Filter by gender if specified
            if gender:
                query = query.filter(Student.gender == gender)
            
            # ORDER BY uploaded_at ASC - This is FCFS!
            pending_students = query.order_by(Receipt.uploaded_at.asc()).all()
            # EXPLANATION: Sort by upload time (earliest first = first come)
            
            logger.info(f"Found {len(pending_students)} students to allocate")
            
            # Counters
            allocated_count = 0
            failed_count = 0
            failed_students = []
            
            # Step 2: Allocate each student (FCFS order)
            for receipt, student in pending_students:
                try:
                    # Find available room for this student's gender
                    available_room = self.db.query(Room).filter(
                        Room.gender == student.gender,
                        Room.current_occupants < Room.capacity,  # Not full
                        Room.status != 'maintenance'  # Not under maintenance
                    ).order_by(Room.block, Room.room_number).first()
                    # EXPLANATION: Get first available room (sorted by block, room number)
                    
                    if not available_room:
                        # No room available for this student
                        failed_count += 1
                        failed_students.append({
                            "matric_number": student.matric_number,
                            "name": student.full_name,
                            "reason": f"No available rooms for {student.gender} students"
                        })
                        logger.warning(f"No room for {student.matric_number}")
                        continue
                    
                    # Step 3: Create allocation
                    allocation = Allocation(
                        student_id=student.id,
                        room_id=available_room.id,
                        allocated_at=datetime.utcnow(),
                        allocation_method='FCFS',
                        academic_session=academic_session,
                        status='active'
                    )
                    self.db.add(allocation)
                    # EXPLANATION: Create record linking student to room
                    
                    # Step 4: Update room occupancy
                    available_room.current_occupants += 1
                    # EXPLANATION: Increment count of students in room
                    
                    # Update room status if now full
                    if available_room.current_occupants >= available_room.capacity:
                        available_room.status = 'occupied'
                    # EXPLANATION: Mark room as occupied when full
                    
                    # Step 5: Flush to get allocation.id
                    self.db.flush()
                    # EXPLANATION: Save to DB but don't commit yet (get the ID)
                    
                    # Step 6: Generate QR code automatically
                    qr_data = generate_qr_code(student.id, allocation.id)
                    # EXPLANATION: Call QR generator service
                    
                    qr_code = QRCode(
                        student_id=student.id,
                        allocation_id=allocation.id,
                        qr_data=qr_data['qr_string'],
                        hmac_signature=qr_data['signature'],
                        qr_image_base64=qr_data['qr_image'],
                        is_active=True
                    )
                    self.db.add(qr_code)
                    # EXPLANATION: Create QR code record
                    
                    allocated_count += 1
                    logger.info(
                        f"✓ Allocated {student.matric_number} to "
                        f"{available_room.block} {available_room.room_number}"
                    )
                    
                except Exception as e:
                    logger.error(f"Error allocating {student.matric_number}: {e}")
                    failed_count += 1
                    failed_students.append({
                        "matric_number": student.matric_number,
                        "name": student.full_name,
                        "reason": str(e)
                    })
            
            # Step 7: Commit all changes at once
            self.db.commit()
            # EXPLANATION: Save everything to database
            
            logger.info(f"Allocation complete: {allocated_count} allocated, {failed_count} failed")
            
            return {
                "total_students": len(pending_students),
                "allocated": allocated_count,
                "failed": failed_count,
                "details": self._format_details(allocated_count, failed_count, failed_students)
            }
            
        except Exception as e:
            self.db.rollback()
            # EXPLANATION: If anything fails, undo all changes
            logger.error(f"Allocation failed: {e}")
            raise
    
    def _format_details(self, allocated: int, failed: int, failed_students: list) -> str:
        """Format allocation details message"""
        if failed == 0:
            return f"All {allocated} students allocated successfully"
        
        details = f"{allocated} students allocated successfully. "
        details += f"{failed} students could not be allocated:\n"
        
        for student in failed_students[:5]:  # Show first 5
            details += f"- {student['matric_number']}: {student['reason']}\n"
        
        if len(failed_students) > 5:
            details += f"... and {len(failed_students) - 5} more"
        
        return details
    
    def get_allocation_summary(self, academic_session: str) -> dict:
        """
        Get summary of allocations for a session
        
        Returns:
            Statistics about allocations
        """
        # Total allocations
        total_allocated = self.db.query(Allocation).filter(
            Allocation.academic_session == academic_session,
            Allocation.status == 'active'
        ).count()
        
        # Male allocations
        male_allocated = self.db.query(Allocation).join(
            Student, Allocation.student_id == Student.id
        ).filter(
            Allocation.academic_session == academic_session,
            Allocation.status == 'active',
            Student.gender == 'Male'
        ).count()
        
        # Female allocations
        female_allocated = self.db.query(Allocation).join(
            Student, Allocation.student_id == Student.id
        ).filter(
            Allocation.academic_session == academic_session,
            Allocation.status == 'active',
            Student.gender == 'Female'
        ).count()
        
        # Available rooms
        male_rooms_available = self.db.query(Room).filter(
            Room.gender == 'Male',
            Room.current_occupants < Room.capacity,
            Room.status != 'maintenance'
        ).count()
        
        female_rooms_available = self.db.query(Room).filter(
            Room.gender == 'Female',
            Room.current_occupants < Room.capacity,
            Room.status != 'maintenance'
        ).count()
        
        return {
            "academic_session": academic_session,
            "total_allocated": total_allocated,
            "male_allocated": male_allocated,
            "female_allocated": female_allocated,
            "male_rooms_available": male_rooms_available,
            "female_rooms_available": female_rooms_available
        }