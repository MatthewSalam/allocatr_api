from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import Student, Receipt, Room, Allocation, QRCode
from services.qr_generator import generate_qr_code
from datetime import datetime, timezone
from collections import defaultdict
import logging
import traceback

logger = logging.getLogger(__name__)

class FCFSAllocator:
    """
    First-Come-First-Served Room Allocation with Diversity Rules
    
    Diversity Constraints:
    - Maximum 2 students from the same level per room
    - Maximum 3 students from the same department per room
    - Gender separation enforced
    - FCFS order based on receipt upload timestamp
    """
    def __init__(self, db: Session):
        self.db = db
    
    def allocate_rooms(self, academic_session: str, gender: str = None):
        """
        Allocate rooms using FCFS algorithm with diversity constraints
        
        Args:
            academic_session: Academic session (e.g., "2025/2026")
            gender: Optional filter ('Male' or 'Female')
        
        Returns:
            dict: Allocation results with statistics
        """
        logger.info(f"Starting FCFS allocation for session: {academic_session}")
        
        # Get students with verified receipts who don't have allocations yet
        query = self.db.query(Student, Receipt).join(
            Receipt, Student.id == Receipt.student_id
        ).filter(
            Receipt.verification_status == 'verified',
            Receipt.academic_session == academic_session,
            ~Student.allocations.any(Allocation.academic_session == academic_session)
        )
        
        if gender:
            query = query.filter(Student.gender == gender)
        
        # Order by upload time (FCFS)
        students_with_receipts = query.order_by(Receipt.uploaded_at.asc()).all()
        
        total_students = len(students_with_receipts)
        logger.info(f"Found {total_students} students ready for allocation")
        
        if total_students == 0:
            return {
                "total_students": 0,
                "allocated": 0,
                "failed": 0,
                "details": "No students with verified receipts found"
            }
        
        allocated_students = []
        failed_students = []
        
        # Track room occupancy details for diversity rules
        room_occupancy = {}  # room_id -> {'levels': {}, 'departments': {}, 'count': int}
        
        # Initialize room occupancy tracking
        existing_allocations = self.db.query(Allocation, Student).join(
            Student, Allocation.student_id == Student.id
        ).filter(
            Allocation.academic_session == academic_session
        ).all()
        
        for allocation, student in existing_allocations:
            if allocation.room_id not in room_occupancy:
                room = self.db.query(Room).filter(Room.id == allocation.room_id).first()
                room_occupancy[allocation.room_id] = {
                    'levels': defaultdict(int),
                    'departments': defaultdict(int),
                    'count': 0,
                    'capacity': room.capacity,
                    'gender': room.gender
                }
            
            # Track existing students in room
            if student.level:
                room_occupancy[allocation.room_id]['levels'][student.level] += 1
            if student.department:
                room_occupancy[allocation.room_id]['departments'][student.department] += 1
            room_occupancy[allocation.room_id]['count'] += 1
        
        # Process each student in FCFS order
        for student, receipt in students_with_receipts:
            try:
                # Find suitable room with diversity constraints
                room = self._find_room_with_diversity(
                    student=student,
                    receipt=receipt,
                    academic_session=academic_session,
                    room_occupancy=room_occupancy
                )
                
                if room:
                    # Create allocation
                    allocation = Allocation(
                        student_id=student.id,
                        room_id=room.id,
                        allocated_at=datetime.now(timezone.utc),
                        allocation_method='FCFS',
                        academic_session=academic_session,
                        status='active'
                    )
                    
                    self.db.add(allocation)
                    self.db.flush()
                    
                    # Update room occupancy
                    room.current_occupants += 1
                    if room.current_occupants >= room.capacity:
                        room.status = 'occupied'
                    
                    # Update tracking
                    if room.id not in room_occupancy:
                        room_occupancy[room.id] = {
                            'levels': defaultdict(int),
                            'departments': defaultdict(int),
                            'count': 0,
                            'capacity': room.capacity,
                            'gender': room.gender
                        }
                    
                    if student.level:
                        room_occupancy[room.id]['levels'][student.level] += 1
                    if student.department:
                        room_occupancy[room.id]['departments'][student.department] += 1
                    room_occupancy[room.id]['count'] += 1
                    
                    # Generate QR code
                    qr_result = generate_qr_code(
                        student_id=student.id,
                        allocation_id=allocation.id,
                    )
                    # determine if preference was honoured
                    preferred_desc = None
                    if receipt.preferred_block and receipt.preferred_room_number:
                        preferred_desc = f"{receipt.preferred_block} - {receipt.preferred_room_number}"
                    elif receipt.preferred_block:
                        preferred_desc = f"{receipt.preferred_block} (any room)"

                    room_matched = (
                        preferred_desc is None or
                        (room.block == receipt.preferred_block and
                        (receipt.preferred_room_number is None or
                        room.room_number == receipt.preferred_room_number))
                    )

                    allocated_students.append({
                        "student": f"{student.full_name} ({student.matric_number})",
                        "level": student.level or "N/A",
                        "department": student.department or "N/A",
                        "room": f"{room.block} - {room.room_number}",
                        "preferred_room": preferred_desc,
                        "room_matched": room_matched,
                        "reason": None if room_matched else (
                            "Preferred room unavailable — diversity constraints applied"
                            if preferred_desc else None
                        ),
                        "status": "success"
                    })
                    
                    logger.info(
                        f"✓ Allocated: {student.matric_number} → "
                        f"{room.block}-{room.room_number} "
                        f"(Level: {student.level}, Dept: {student.department})"
                    )
                    
                else:
                    failed_students.append({
                        "student": f"{student.full_name} ({student.matric_number})",
                        "level": student.level or "N/A",
                        "department": student.department or "N/A",
                        "room": None,
                        "status": "failed",
                        "reason": "No available rooms matching diversity constraints"
                    })
                    
                    logger.warning(
                        f"✗ Failed: {student.matric_number} - "
                        f"No rooms available (Level: {student.level}, Dept: {student.department})"
                    )
                
            except Exception as e:
                logger.error(f"Error allocating {student.matric_number}: {e}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                self.db.rollback()
                
                failed_students.append({
                    "student": f"{student.full_name} ({student.matric_number})",
                    "level": student.level or "N/A",
                    "department": student.department or "N/A",
                    "room": None,
                    "status": "failed",
                    "reason": f"Error: {str(e)}"
                })
        
        # Commit all allocations
        self.db.commit()
        
        result = {
            "total_students": total_students,
            "allocated": len(allocated_students),
            "failed": len(failed_students),
            "details": allocated_students + failed_students
        }
        
        logger.info(
            f"Allocation complete: {len(allocated_students)}/{total_students} allocated, "
            f"{len(failed_students)} failed"
        )
        
        return result
    
    def _find_room_with_diversity(
        self, 
        student: Student, 
        receipt: Receipt, 
        academic_session: str,
        room_occupancy: dict
    ) -> Room:
        """
        Find a suitable room respecting diversity constraints
        
        Diversity Rules:
        1. Max 2 students from same level per room
        2. Max 3 students from same department per room
        3. Gender separation
        4. FCFS room preference (exact room → preferred block → any available)
        
        Args:
            student: Student to allocate
            receipt: Student's verified receipt
            academic_session: Current academic session
            room_occupancy: Dictionary tracking room occupancy details
        
        Returns:
            Room object if found, None otherwise
        """
        # Get available rooms for student's gender
        available_rooms_query = self.db.query(Room).filter(
            Room.gender == student.gender,
            Room.current_occupants < Room.capacity,
            Room.status == 'available'
        )
        
        # Priority 1: Try exact room preference
        if receipt.preferred_block and receipt.preferred_room_number:
            preferred_room = available_rooms_query.filter(
                Room.block == receipt.preferred_block,
                Room.room_number == receipt.preferred_room_number
            ).first()
            
            if preferred_room and self._check_diversity_rules(
                preferred_room, student, room_occupancy
            ):
                logger.info(
                    f"Matched preferred room: {preferred_room.block}-{preferred_room.room_number}"
                )
                return preferred_room
        
        # Priority 2: Try any room in preferred block
        if receipt.preferred_block:
            block_rooms = available_rooms_query.filter(
                Room.block == receipt.preferred_block
            ).all()
            
            for room in block_rooms:
                if self._check_diversity_rules(room, student, room_occupancy):
                    logger.info(
                        f"Matched block preference: {room.block}-{room.room_number}"
                    )
                    return room
        
        # Priority 3: Any available room (FCFS fallback)
        all_available_rooms = available_rooms_query.order_by(
            Room.block, Room.room_number
        ).all()
        
        for room in all_available_rooms:
            if self._check_diversity_rules(room, student, room_occupancy):
                logger.info(f"Matched FCFS room: {room.block}-{room.room_number}")
                return room
        
        return None
    
    def _check_diversity_rules(
        self, 
        room: Room, 
        student: Student, 
        room_occupancy: dict
    ) -> bool:
        """
        Check if allocating student to room violates diversity constraints
        
        Rules:
        - Max 2 students from same level
        - Max 3 students from same department
        
        Args:
            room: Room to check
            student: Student to allocate
            room_occupancy: Current occupancy tracking
        
        Returns:
            True if allocation respects diversity rules, False otherwise
        """
        # If room is empty or not tracked yet, allow allocation
        if room.id not in room_occupancy:
            return True
        
        occupancy = room_occupancy[room.id]
        
        # Rule 1: Check level constraint (max 2 from same level)
        if student.level:
            current_level_count = occupancy['levels'].get(student.level, 0)
            if current_level_count >= 2:
                logger.debug(
                    f"Room {room.block}-{room.room_number} rejected: "
                    f"Already has {current_level_count} {student.level} students (max: 2)"
                )
                return False
        
        # Rule 2: Check department constraint (max 3 from same department)
        if student.department:
            current_dept_count = occupancy['departments'].get(student.department, 0)
            if current_dept_count >= 3:
                logger.debug(
                    f"Room {room.block}-{room.room_number} rejected: "
                    f"Already has {current_dept_count} {student.department} students (max: 3)"
                )
                return False
        
        # All diversity rules satisfied
        return True