import os
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from models import User, Student, Receipt, Room, Allocation
from ..dependencies import require_role
from services.fcfs_allocator import FCFSAllocator
import logging
from fastapi.responses import FileResponse
import mimetypes


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

#  SCHEMAS 

class RoomCreateRequest(BaseModel):
    """Schema for creating a room"""
    block: str = Field(..., min_length=1, max_length=50)
    room_number: str = Field(..., min_length=1, max_length=10)
    capacity: int = Field(..., ge=1, le=10)
    gender: str = Field(..., pattern="^(Male|Female)$")
    status: str = Field(default="available", pattern="^(available|occupied|maintenance|reserved)$")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "summary": "Male Room",
                    "value": {
                        "block": "Block A",
                        "room_number": "101",
                        "capacity": 2,
                        "gender": "Male",
                        "status": "available"
                    }
                },
                {
                    "summary": "Female Room",
                    "value": {
                        "block": "Block B",
                        "room_number": "201",
                        "capacity": 2,
                        "gender": "Female",
                        "status": "available"
                    }
                }
            ]}

class RoomUpdateRequest(BaseModel):
    """Schema for updating a room"""
    capacity: Optional[int] = Field(None, ge=1, le=10)
    status: Optional[str] = Field(None, pattern="^(available|occupied|maintenance|reserved)$")
    
    class Config:
        json_schema_extra = {
            "example": {
                "capacity": 3,
                "status": "maintenance"
            }
        }

class VerifyReceiptRequest(BaseModel):
    """Schema for verifying receipt"""
    amount: Optional[float] = None
    payment_reference: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "amount": 50000,
                "payment_reference": "PAY-2026-001"
            }
        }

class RejectReceiptRequest(BaseModel):
    """Schema for rejecting receipt"""
    rejection_reason: str = Field(..., min_length=10, max_length=500)
    
    class Config:
        json_schema_extra = {
            "example": {
                "rejection_reason": "Receipt is not clear. Please upload a clearer image."
            }
        }

class AllocateRoomsRequest(BaseModel):
    """Schema for triggering room allocation"""
    academic_session: str = Field(..., pattern=r"^\d{4}/\d{4}$")
    gender: Optional[str] = Field(None, pattern="^(Male|Female)$")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "summary": "Allocate All",
                    "value": {
                        "academic_session": "2025/2026"
                    }
                },
                {
                    "summary": "Allocate Males Only",
                    "value": {
                        "academic_session": "2025/2026",
                        "gender": "Male"
                    }
                }
            ]
        }

#  ROOM MANAGEMENT ENDPOINTS 
@router.post("/rooms", status_code=status.HTTP_201_CREATED)
def create_room(
    room_data: RoomCreateRequest,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Create a new room
    **Requires:** Admin authentication
    **Fields:**
    - block: Building block (e.g., "Block A", "Block B")
    - room_number: Room number within the block
    - capacity: Maximum number of students (1-10)
    - gender: "Male" or "Female"
    - status: "available", "occupied", "maintenance", or "reserved"
    """
    logger.info(
        f"Room creation by {current_user.email}: "
        f"{room_data.block} - {room_data.room_number}"
    )
    
    existing_room = db.query(Room).filter(
        Room.block == room_data.block,
        Room.room_number == room_data.room_number,
        Room.gender == room_data.gender.upper()
    ).first()
    
    if existing_room:
        logger.warning(
            f"Room creation failed: {room_data.block} - {room_data.room_number} already exists"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room {room_data.block} - {room_data.room_number} already exists"
        )
    
    try:
        new_room = Room(
            block=room_data.block,
            room_number=room_data.room_number,
            capacity=room_data.capacity,
            current_occupants=0,
            gender=room_data.gender.upper(),
            status=room_data.status
        )
        
        db.add(new_room)
        db.commit()
        db.refresh(new_room)
        
        logger.info(
            f"✓ Room created: {room_data.block} - {room_data.room_number} "
            f"(capacity: {room_data.capacity}, gender: {room_data.gender})"
        )
        
        return {
            "success": True,
            "message": "Room created successfully",
            "data": {
                "room_id": new_room.id,
                "block": new_room.block,
                "room_number": new_room.room_number,
                "capacity": new_room.capacity,
                "gender": new_room.gender,
                "status": new_room.status
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Room creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create room. Please try again."
        )


@router.get("/rooms")
def get_all_rooms(
    block: Optional[str] = None,
    gender: Optional[str] = None,
    status: Optional[str] = None,
    available_only: bool = False,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Get all rooms with optional filters
    
    **Requires:** Admin authentication
    
    **Filters:**
    - block: Filter by block name
    - gender: Filter by gender (Male/Female)
    - status: Filter by status
    - available_only: Show only rooms with space
    """
    logger.info(f"Rooms list requested by {current_user.email}")
    
    # Build query
    query = db.query(Room)
    
    if block:
        query = query.filter(Room.block == block)
    
    if gender:
        query = query.filter(Room.gender == gender)
    
    if status:
        query = query.filter(Room.status == status)
    
    if available_only:
        query = query.filter(Room.current_occupants < Room.capacity)
    
    # Get rooms
    rooms = query.order_by(Room.block, Room.room_number).all()
    
    # Format response
    rooms_data = [
        {
            "id": room.id,
            "block": room.block,
            "room_number": room.room_number,
            "capacity": room.capacity,
            "current_occupants": room.current_occupants,
            "available_space": room.capacity - room.current_occupants,
            "gender": room.gender,
            "status": room.status,
            "occupancy_rate": int((room.current_occupants / room.capacity) * 100) if room.capacity > 0 else 0
        }
        for room in rooms
    ]
    
    # Summary statistics
    total_rooms = len(rooms)
    total_capacity = sum(r.capacity for r in rooms)
    total_occupied = sum(r.current_occupants for r in rooms)
    available_spaces = total_capacity - total_occupied
    
    logger.info(
        f"Rooms retrieved: {total_rooms} rooms, "
        f"{available_spaces}/{total_capacity} spaces available"
    )
    
    return {
        "success": True,
        "data": {
            "total_rooms": total_rooms,
            "total_capacity": total_capacity,
            "total_occupied": total_occupied,
            "available_spaces": available_spaces,
            "occupancy_percentage": int((total_occupied / total_capacity) * 100) if total_capacity > 0 else 0,
            "rooms": rooms_data
        }
    }

@router.get("/rooms/{room_id}")
def get_room_details(
    room_id: int,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific room
    
    **Requires:** Admin authentication
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    # Get students allocated to this room
    allocations = db.query(Allocation, Student).join(
        Student, Allocation.student_id == Student.id
    ).filter(Allocation.room_id == room_id).all()
    
    students = [
        {
            "student_id": student.id,
            "matric_number": student.matric_number,
            "full_name": student.full_name,
            "level": student.level,
            "department": student.department,
            "allocated_at": allocation.allocated_at
        }
        for allocation, student in allocations
    ]
    
    return {
        "success": True,
        "data": {
            "room": {
                "id": room.id,
                "block": room.block,
                "room_number": room.room_number,
                "capacity": room.capacity,
                "current_occupants": room.current_occupants,
                "gender": room.gender,
                "status": room.status
            },
            "students": students
        }
    }

@router.put("/rooms/{room_id}")
def update_room(
    room_id: int,
    room_data: RoomUpdateRequest,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Update room details
    
    **Requires:** Admin authentication
    
    **Updatable fields:**
    - capacity
    - status
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    # Validate capacity change
    if room_data.capacity is not None:
        if room_data.capacity < room.current_occupants:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reduce capacity below current occupants ({room.current_occupants})"
            )
        room.capacity = room_data.capacity
    
    # Update status
    if room_data.status is not None:
        room.status = room_data.status
    
    try:
        db.commit()
        db.refresh(room)
        
        logger.info(f"✓ Room updated: {room.block} - {room.room_number} by {current_user.email}")
        
        return {
            "success": True,
            "message": "Room updated successfully",
            "data": {
                "room_id": room.id,
                "block": room.block,
                "room_number": room.room_number,
                "capacity": room.capacity,
                "status": room.status
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Room update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update room"
        )

@router.delete("/rooms/{room_id}")
def delete_room(
    room_id: int,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Delete a room
    
    **Requires:** Admin authentication
    
    **Note:** Cannot delete rooms with current allocations
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    # Check if room has allocations
    if room.current_occupants > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete room with {room.current_occupants} current occupant(s). Deallocate students first."
        )
    
    try:
        room_info = f"{room.block} - {room.room_number}"
        db.delete(room)
        db.commit()
        
        logger.info(f"✓ Room deleted: {room_info} by {current_user.email}")
        
        return {
            "success": True,
            "message": f"Room {room_info} deleted successfully"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Room deletion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete room"
        )

@router.get("/receipts/pending")
def get_pending_receipts(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Get all pending receipts
    
    **Requires:** Admin authentication
    """
    logger.info(f"Pending receipts requested by {current_user.email}")
    
    # Build query
    query = db.query(Receipt, Student).join(
        Student, Receipt.student_id == Student.id
    ).filter(Receipt.verification_status == 'pending')
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    results = query.order_by(Receipt.uploaded_at).limit(limit).offset(offset).all()
    
    receipts = [
        {
            "receipt_id": receipt.id,
            "student": {
                "id": student.id,
                "matric_number": student.matric_number,
                "full_name": student.full_name,
                "email": student.email,
                "level": student.level,
                "department": student.department
            },
            "file_name": receipt.file_name,
            "amount": float(receipt.amount) if receipt.amount else None,
            "payment_reference": receipt.payment_reference,
            "uploaded_at": receipt.uploaded_at,
            "academic_session": receipt.academic_session,
            "preferred_block": receipt.preferred_block,
            "preferred_room_number": receipt.preferred_room_number
        }
        for receipt, student in results
    ]
    
    logger.info(f"Pending receipts retrieved: {total} total")
    
    return {
        "success": True,
        "data": {
            "total": total,
            "receipts": receipts,
            "pagination": {
                "limit": limit,
                "offset": offset
            }
        }
    }


@router.put("/receipts/{receipt_id}/verify")
def verify_receipt(
    receipt_id: int,
    verify_data: Optional[VerifyReceiptRequest] = None,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Verify a receipt
    
    **Requires:** Admin authentication
    """
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found"
        )
    
    if receipt.verification_status == 'verified':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Receipt already verified"
        )
    
    try:
        receipt.verification_status = 'verified'
        receipt.verified_by = current_user.id
        receipt.verified_at = datetime.now(timezone.utc)
        
        # Update amount and reference if provided
        if verify_data:
            if verify_data.amount is not None:
                receipt.amount = verify_data.amount
            if verify_data.payment_reference is not None:
                receipt.payment_reference = verify_data.payment_reference
        
        db.commit()
        
        student = receipt.student
        logger.info(
            f"✓ Receipt verified: {student.matric_number} by {current_user.email}"
        )
        
        return {
            "success": True,
            "message": "Receipt verified successfully",
            "data": {
                "receipt_id": receipt.id,
                "student_matric": student.matric_number,
                "verified_by": current_user.email,
                "verified_at": receipt.verified_at
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Receipt verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify receipt"
        )

@router.put("/receipts/{receipt_id}/reject")
def reject_receipt(
    receipt_id: int,
    reject_data: RejectReceiptRequest,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Reject a receipt
    
    **Requires:** Admin authentication
    """
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found"
        )
    
    try:
        receipt.verification_status = 'rejected'
        receipt.verified_by = current_user.id
        receipt.verified_at = datetime.now(timezone.utc)
        receipt.rejection_reason = reject_data.rejection_reason
        
        db.commit()
        
        student = receipt.student
        logger.info(
            f"✓ Receipt rejected: {student.matric_number} by {current_user.email}"
        )
        
        return {
            "success": True,
            "message": "Receipt rejected",
            "data": {
                "receipt_id": receipt.id,
                "student_matric": student.matric_number,
                "rejection_reason": reject_data.rejection_reason
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Receipt rejection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject receipt"
        )

#  ALLOCATION ENDPOINTS 
@router.post("/allocate")
def allocate_rooms(
    allocation_data: AllocateRoomsRequest,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    logger.info(
        f"Room allocation triggered by {current_user.email} "
        f"for session {allocation_data.academic_session}"
    )

    try:
        allocator = FCFSAllocator(db)

        result = allocator.allocate_rooms(
            academic_session=allocation_data.academic_session,
            gender=allocation_data.gender
        )

        logger.info(
            f"✓ Allocation completed: {result['allocated']}/{result['total_students']} students allocated"
        )

        return result

    except Exception as e:
        logger.error(f"Allocation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Allocation failed: {str(e)}"
        )
        
@router.get("/allocations")
def get_all_allocations(
    academic_session: Optional[str] = None,
    gender: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):

    """
    Get all room allocations
    
    **Requires:** Admin authentication
    """
    logger.info(f"Allocations requested by {current_user.email}")
    
    # Build query
    query = db.query(Allocation, Student, Room).join(
        Student, Allocation.student_id == Student.id
    ).join(
        Room, Allocation.room_id == Room.id
    )
    
    if academic_session:
        query = query.filter(Allocation.academic_session == academic_session)
    
    if gender:
        query = query.filter(Student.gender == gender)
    
    # Get total
    total = query.count()
    
    # Get paginated results
    results = query.order_by(Allocation.allocated_at.desc()).limit(limit).offset(offset).all()
    
    allocations = [
        {
            "allocation_id": allocation.id,
            "student": {
                "id": student.id,
                "matric_number": student.matric_number,
                "full_name": student.full_name,
                "gender": student.gender,
                "level": student.level,
                "department": student.department
            },
            "room": {
                "id": room.id,
                "block": room.block,
                "room_number": room.room_number,
                "full_name": f"{room.block} - {room.room_number}"
            },
            "allocated_at": allocation.allocated_at,
            "allocation_method": allocation.allocation_method,
            "academic_session": allocation.academic_session,
            "status": allocation.status
        }
        for allocation, student, room in results
    ]
    
    return {
        "success": True,
        "data": {
            "total": total,
            "allocations": allocations,
            "pagination": {
                "limit": limit,
                "offset": offset
            }
        }
    }

@router.get("/system-status")
def get_system_status(
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):


    """
    Get overall system status for allocation readiness
    
    **Requires:** Admin authentication
    """
    # Count receipts by status
    total_receipts = db.query(Receipt).count()
    pending_receipts = db.query(Receipt).filter(Receipt.verification_status == 'pending').count()
    verified_receipts = db.query(Receipt).filter(Receipt.verification_status == 'verified').count()
    rejected_receipts = db.query(Receipt).filter(Receipt.verification_status == 'rejected').count()
    
    # Count rooms
    total_rooms = db.query(Room).count()
    available_rooms = db.query(Room).filter(
        Room.current_occupants < Room.capacity,
        Room.status == 'available'
    ).count()
    total_capacity = db.query(func.sum(Room.capacity)).scalar() or 0
    total_occupied = db.query(func.sum(Room.current_occupants)).scalar() or 0
    
    # Count allocations
    total_allocations = db.query(Allocation).count()
    
    # Count students
    total_students = db.query(Student).count()
    
    return {
        "success": True,
        "data": {
            "students": {
                "total": total_students,
                "with_receipts": total_receipts,
                "with_verified_receipts": verified_receipts,
                "ready_for_allocation": verified_receipts
            },
            "receipts": {
                "total": total_receipts,
                "pending": pending_receipts,
                "verified": verified_receipts,
                "rejected": rejected_receipts
            },
            "rooms": {
                "total": total_rooms,
                "available": available_rooms,
                "total_capacity": total_capacity,
                "occupied": total_occupied,
                "available_spaces": total_capacity - total_occupied
            },
            "allocations": {
                "total": total_allocations
            },
            "allocation_ready": verified_receipts > 0 and available_rooms > 0
        }
    }

@router.get("/me")
def get_admin_info(
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Get current admin user information
    
    **Requires:** Admin authentication
    
    **Returns:** Admin profile with system stats
    """
    logger.info(f"Admin info requested by {current_user.email}")
    
    # Get basic stats for admin dashboard
    total_students = db.query(Student).count()
    total_receipts = db.query(Receipt).count()
    pending_receipts = db.query(Receipt).filter(
        Receipt.verification_status == 'pending'
    ).count()
    verified_receipts = db.query(Receipt).filter(
        Receipt.verification_status == 'verified'
    ).count()
    total_rooms = db.query(Room).count()
    total_allocations = db.query(Allocation).count()
    
    # Get total capacity and occupancy
    total_capacity = db.query(func.sum(Room.capacity)).scalar() or 0
    total_occupied = db.query(func.sum(Room.current_occupants)).scalar() or 0
    
    return {
        "success": True,
        "data": {
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "role": current_user.role,
                "department": current_user.department,
                "is_active": current_user.is_active,
                "created_at": current_user.created_at
            },
            "quick_stats": {
                "total_students": total_students,
                "total_receipts": total_receipts,
                "pending_receipts": pending_receipts,
                "verified_receipts": verified_receipts,
                "total_rooms": total_rooms,
                "total_capacity": total_capacity,
                "total_occupied": total_occupied,
                "available_spaces": total_capacity - total_occupied,
                "total_allocations": total_allocations,
                "occupancy_percentage": int((total_occupied / total_capacity) * 100) if total_capacity > 0 else 0
            }
        }
    }

from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from datetime import datetime


@router.get("/allocations/export/pdf")
def export_allocations_pdf(
    academic_session: str = Query(..., description="Academic session (e.g., 2025/2026)"),
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Export all allocations as PDF
    
    **Requires:** Admin authentication
    
    **Query Parameters:**
    - academic_session: Required (e.g., "2025/2026")
    
    **Returns:** PDF file download
    """
    logger.info(f"PDF export requested by {current_user.email} for session {academic_session}")
    
    # Get all allocations for the session
    allocations_query = db.query(Allocation, Student, Room).join(
        Student, Allocation.student_id == Student.id
    ).join(
        Room, Allocation.room_id == Room.id
    ).filter(
        Allocation.academic_session == academic_session
    ).order_by(Room.block, Room.room_number, Student.full_name)
    
    allocations = allocations_query.all()
    
    if not allocations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No allocations found for session {academic_session}"
        )
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#2563EB'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#1F2937'),
        spaceAfter=12
    )
    
    # Title
    title = Paragraph(f"Hostel Allocation Report<br/>Academic Session: {academic_session}", title_style)
    elements.append(title)
    
    # Metadata
    metadata = [
        f"<b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
        f"<b>Total Allocations:</b> {len(allocations)}",
        f"<b>Generated by:</b> {current_user.email}"
    ]
    
    for meta in metadata:
        elements.append(Paragraph(meta, styles['Normal']))
    
    elements.append(Spacer(1, 0.3 * inch))
    
    # Summary Statistics
    male_count = sum(1 for a, s, r in allocations if s.gender == 'Male')
    female_count = sum(1 for a, s, r in allocations if s.gender == 'Female')
    
    # Get unique blocks
    blocks = {}
    for allocation, student, room in allocations:
        if room.block not in blocks:
            blocks[room.block] = {'male': 0, 'female': 0}
        if student.gender == 'Male':
            blocks[room.block]['male'] += 1
        else:
            blocks[room.block]['female'] += 1
    
    summary_heading = Paragraph("Summary Statistics", heading_style)
    elements.append(summary_heading)
    
    summary_data = [
        ['Category', 'Count'],
        ['Total Students Allocated', str(len(allocations))],
        ['Male Students', str(male_count)],
        ['Female Students', str(female_count)],
        ['Total Blocks', str(len(blocks))]
    ]
    
    summary_table = Table(summary_data, colWidths=[3 * inch, 2 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 0.5 * inch))
    
    # Allocations Table
    allocations_heading = Paragraph("Student Allocations", heading_style)
    elements.append(allocations_heading)
    
    # Table headers
    table_data = [
        ['#', 'Matric Number', 'Student Name', 'Gender', 'Level', 'Room', 'Block']
    ]
    
    # Table rows
    for idx, (allocation, student, room) in enumerate(allocations, 1):
        table_data.append([
            str(idx),
            student.matric_number,
            student.full_name[:25] + '...' if len(student.full_name) > 25 else student.full_name,
            student.gender,
            student.level or 'N/A',
            room.room_number,
            room.block
        ])
    
    # Create table
    col_widths = [0.4 * inch, 1.2 * inch, 2.2 * inch, 0.7 * inch, 0.6 * inch, 0.8 * inch, 1 * inch]
    allocations_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    allocations_table.setStyle(TableStyle([
        # Header style
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        
        # Body style
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(allocations_table)
    
    # Footer
    elements.append(Spacer(1, 0.5 * inch))
    footer = Paragraph(
        f"<i>This is an official document generated by Allocatr - Hostel Management System</i>",
        styles['Normal']
    )
    elements.append(footer)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    logger.info(f"✓ PDF generated: {len(allocations)} allocations")
    
    # Return as downloadable file
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=Allocations_{academic_session.replace('/', '-')}.pdf"
        }
    )

@router.get("/rooms/{room_id}/diversity")
def get_room_diversity_stats(
    room_id: int,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    """
    Get diversity statistics for a specific room
    
    **Requires:** Admin authentication
    
    **Returns:** Level and department distribution in the room
    """
    room = db.query(Room).filter(Room.id == room_id).first()
    
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )
    
    # Get students in this room
    students = db.query(Student).join(Allocation).filter(
        Allocation.room_id == room_id
    ).all()
    
    # Level distribution
    level_dist = {}
    for student in students:
        if student.level:
            level_dist[student.level] = level_dist.get(student.level, 0) + 1
    
    # Department distribution
    dept_dist = {}
    for student in students:
        if student.department:
            dept_dist[student.department] = dept_dist.get(student.department, 0) + 1
    
    # Check if diversity rules are satisfied
    level_violations = [level for level, count in level_dist.items() if count > 2]
    dept_violations = [dept for dept, count in dept_dist.items() if count > 3]
    
    return {
        "success": True,
        "data": {
            "room": {
                "id": room.id,
                "block": room.block,
                "room_number": room.room_number,
                "capacity": room.capacity,
                "current_occupants": room.current_occupants
            },
            "diversity_stats": {
                "level_distribution": level_dist,
                "department_distribution": dept_dist,
                "diversity_rules_satisfied": len(level_violations) == 0 and len(dept_violations) == 0,
                "violations": {
                    "levels_exceeding_max": level_violations,
                    "departments_exceeding_max": dept_violations
                }
            },
            "students": [
                {
                    "matric_number": s.matric_number,
                    "full_name": s.full_name,
                    "level": s.level,
                    "department": s.department
                }
                for s in students
            ]
        }
    }

@router.get("/receipts/{receipt_id}/file")
def get_receipt_file(
    receipt_id: int,
    current_user: User = Depends(require_role(['admin'])),
    db: Session = Depends(get_db)
):
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if not os.path.exists(receipt.file_path):
        raise HTTPException(status_code=404, detail="File not found on server")

    # Derive media type from file name, fallback to stored value
    media_type, _ = mimetypes.guess_type(receipt.file_name)
    if not media_type:
        media_type = receipt.file_type or "application/octet-stream"

    return FileResponse(
        path=receipt.file_path,
        filename=receipt.file_name,
        media_type=media_type
    )