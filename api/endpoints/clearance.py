from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from models import User, Student, Clearance, QRCode, Allocation
from ..dependencies import get_current_user, require_role
from services.qr_generator import verify_qr_code
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clearance", tags=["Clearance"])

# ==================== SCHEMAS ====================
class QRPayload(BaseModel):
    student_id: int
    allocation_id: int
    timestamp: int
    signature: str

class ScanQRRequest(BaseModel):
    """Schema for scanning QR code"""
    qr_data: QRPayload
    department: str = Field(..., description="Department performing clearance")
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "qr_data": "eyJzdHVkZW50X2lkIjoxLCJhbGxvY2F0aW9uX2lkIjo1fQ==|signature_here",
                "department": "Bursary",
                "notes": "All fees paid in full"
            }
        }

class ClearanceRecordResponse(BaseModel):
    """Schema for single clearance record"""
    id: int
    student_id: int
    student_name: str
    matric_number: str
    department: str
    cleared_by_email: str
    cleared_at: datetime
    notes: Optional[str]
    academic_session: str
    
    class Config:
        from_attributes = True

class ClearanceStatusResponse(BaseModel):
    """Schema for student clearance status"""
    student_id: int
    student_name: str
    matric_number: str
    total_departments: int
    cleared_departments: int
    pending_departments: int
    progress_percentage: int
    clearances: List[dict]
    pending: List[str]

class ScanQRResponse(BaseModel):
    """Schema for QR scan response"""
    success: bool
    message: str
    data: dict

# ==================== ENDPOINTS ====================
@router.post("/scan", response_model=ScanQRResponse)
def scan_qr_code(
    scan_data: ScanQRRequest,
    current_user: User = Depends(require_role(['admin', 'officer'])),
    db: Session = Depends(get_db)
):
    """
    Scan QR code and record clearance
    
    **Requires:** Admin or Officer authentication
    
    **Process:**
    1. Verify QR code signature (HMAC)
    2. Check if student has allocation
    3. Check if already cleared for this department
    4. Record clearance
    
    **Departments:** Bursary, Faculty, Library, Sports, Hostel, ICT, Student Affairs
    """
    logger.info(f"QR scan by {current_user.email} for department: {scan_data.department}")
    
    # Validate department
    valid_departments = [
        'Bursary', 'Faculty', 'Library', 'Sports', 
        'Hostel', 'ICT', 'Student Affairs'
    ]
    
    if scan_data.department not in valid_departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid department. Must be one of: {', '.join(valid_departments)}"
        )
    
    # Officers can only clear for their own department
    if current_user.role == 'officer':
        if current_user.department != scan_data.department:
            logger.warning(
                f"Officer {current_user.email} attempted to clear for {scan_data.department} "
                f"but is assigned to {current_user.department}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You can only clear for {current_user.department} department"
            )
    
    # Verify QR code
    verification_result = verify_qr_code(scan_data.qr_data)
    
    if not verification_result['valid']:
        logger.warning(f"Invalid QR code scanned by {current_user.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid QR code: {verification_result.get('error', 'Verification failed')}"
        )
    
    student_id = verification_result['student_id']
    allocation_id = verification_result['allocation_id']
    
    # Get student
    student = db.query(Student).filter(Student.id == student_id).first()
    
    if not student:
        logger.error(f"Student {student_id} not found in QR code")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Get allocation
    allocation = db.query(Allocation).filter(Allocation.id == allocation_id).first()
    
    if not allocation:
        logger.error(f"Allocation {allocation_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allocation not found. Student may not have been allocated a room."
        )
    
    # Check if already cleared for this department
    existing_clearance = db.query(Clearance).filter(
        Clearance.student_id == student_id,
        Clearance.department == scan_data.department,
        Clearance.academic_session == allocation.academic_session
    ).first()
    
    if existing_clearance:
        logger.warning(
            f"Student {student.matric_number} already cleared for {scan_data.department} "
            f"by {existing_clearance.cleared_by_user.email} on {existing_clearance.cleared_at}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Student already cleared for {scan_data.department} department on {existing_clearance.cleared_at.strftime('%Y-%m-%d %H:%M')}"
        )
    
    # Get QR code record
    qr_code = db.query(QRCode).filter(
        QRCode.student_id == student_id,
        QRCode.allocation_id == allocation_id
    ).first()
    
    try:
        # Create clearance record
        new_clearance = Clearance(
            student_id=student_id,
            department=scan_data.department,
            cleared_by=current_user.id,
            cleared_at=datetime.now(timezone.utc),
            qr_code_id=qr_code.id if qr_code else None,
            notes=scan_data.notes,
            academic_session=allocation.academic_session
        )
        
        db.add(new_clearance)
        db.commit()
        db.refresh(new_clearance)
        
        # Count total clearances for this student
        total_clearances = db.query(Clearance).filter(
            Clearance.student_id == student_id,
            Clearance.academic_session == allocation.academic_session
        ).count()
        
        logger.info(
            f"✓ Clearance recorded: {student.matric_number} - {scan_data.department} "
            f"by {current_user.email} ({total_clearances}/7 departments)"
        )
        
        return {
            "success": True,
            "message": f"Clearance successful for {scan_data.department}",
            "data": {
                "clearance_id": new_clearance.id,
                "student": {
                    "id": student.id,
                    "matric_number": student.matric_number,
                    "full_name": student.full_name,
                    "level": student.level,
                    "department": student.department
                },
                "clearance": {
                    "department": scan_data.department,
                    "cleared_by": current_user.email,
                    "cleared_at": new_clearance.cleared_at,
                    "notes": scan_data.notes
                },
                "progress": {
                    "cleared_departments": total_clearances,
                    "total_departments": 7,
                    "percentage": int((total_clearances / 7) * 100),
                    "complete": total_clearances == 7
                }
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording clearance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record clearance. Please try again."
        )


@router.get("/student/{student_id}", response_model=ClearanceStatusResponse)
def get_student_clearance_status(
    student_id: int,
    academic_session: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get clearance status for a specific student
    
    **Requires:** Authentication
    
    **Access:**
    - Students can view their own clearance status
    - Admins/Officers can view any student's status
    """
    # Students can only view their own status
    if current_user.role == 'student':
        if not current_user.student or current_user.student.id != student_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own clearance status"
            )
    
    # Get student
    student = db.query(Student).filter(Student.id == student_id).first()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Get student's latest allocation if session not specified
    if not academic_session:
        latest_allocation = db.query(Allocation).filter(
            Allocation.student_id == student_id
        ).order_by(Allocation.allocated_at.desc()).first()
        
        if not latest_allocation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student has no room allocation"
            )
        
        academic_session = latest_allocation.academic_session
    
    # Get all clearances for this student and session
    clearances = db.query(Clearance).filter(
        Clearance.student_id == student_id,
        Clearance.academic_session == academic_session
    ).all()
    
    # All departments
    all_departments = [
        'Bursary', 'Faculty', 'Library', 'Sports', 
        'Hostel', 'ICT', 'Student Affairs'
    ]
    
    # Cleared departments
    cleared_dept_names = [c.department for c in clearances]
    
    # Pending departments
    pending_departments = [d for d in all_departments if d not in cleared_dept_names]
    
    # Format clearance data
    clearance_data = [
        {
            "id": c.id,
            "department": c.department,
            "cleared_by": c.cleared_by,
            "cleared_at": c.cleared_at,
            "notes": c.notes
        }
        for c in clearances
    ]
    
    total_departments = len(all_departments)
    cleared_count = len(clearances)
    pending_count = total_departments - cleared_count
    progress = int((cleared_count / total_departments) * 100)
    
    logger.info(
        f"Clearance status retrieved for {student.matric_number}: "
        f"{cleared_count}/{total_departments} departments"
    )
    
    return {
        "student_id": student.id,
        "student_name": student.full_name,
        "matric_number": student.matric_number,
        "total_departments": total_departments,
        "cleared_departments": cleared_count,
        "pending_departments": pending_count,
        "progress_percentage": progress,
        "clearances": clearance_data,
        "pending": pending_departments
    }


@router.get("/my-status", response_model=ClearanceStatusResponse)
def get_my_clearance_status(
    academic_session: Optional[str] = None,
    current_user: User = Depends(require_role(['student'])),
    db: Session = Depends(get_db)
):
    """
    Get current student's clearance status
    
    **Requires:** Student authentication
    """
    if not current_user.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record not found"
        )
    
    return get_student_clearance_status(
        student_id=current_user.student.id,
        academic_session=academic_session,
        current_user=current_user,
        db=db
    )


@router.get("/department/{department}")
def get_department_clearances(
    department: str,
    academic_session: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_role(['admin', 'officer'])),
    db: Session = Depends(get_db)
):
    """
    Get all clearances for a specific department
    
    **Requires:** Admin or Officer authentication
    
    **Access:**
    - Officers can only view their own department
    - Admins can view any department
    """
    # Validate department
    valid_departments = [
        'Bursary', 'Faculty', 'Library', 'Sports', 
        'Hostel', 'ICT', 'Student Affairs'
    ]
    
    if department not in valid_departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid department. Must be one of: {', '.join(valid_departments)}"
        )
    
    # Officers can only view their own department
    if current_user.role == 'officer':
        if current_user.department != department:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You can only view clearances for {current_user.department} department"
            )
    
    # Build query
    query = db.query(Clearance, Student).join(
        Student, Clearance.student_id == Student.id
    ).filter(Clearance.department == department)
    
    if academic_session:
        query = query.filter(Clearance.academic_session == academic_session)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    results = query.order_by(Clearance.cleared_at.desc()).limit(limit).offset(offset).all()
    
    clearances = [
        {
            "clearance_id": clearance.id,
            "student": {
                "id": student.id,
                "matric_number": student.matric_number,
                "full_name": student.full_name,
                "level": student.level,
                "department": student.department
            },
            "cleared_by": clearance.cleared_by_user.email if clearance.cleared_by_user else None,
            "cleared_at": clearance.cleared_at,
            "notes": clearance.notes,
            "academic_session": clearance.academic_session
        }
        for clearance, student in results
    ]
    
    logger.info(
        f"Department clearances retrieved: {department} "
        f"by {current_user.email} ({total} total)"
    )
    
    return {
        "success": True,
        "data": {
            "department": department,
            "total_clearances": total,
            "clearances": clearances,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total
            }
        }
    }


@router.get("/my-department")
def get_my_department_clearances(
    academic_session: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_role(['officer'])),
    db: Session = Depends(get_db)
):
    """
    Get clearances for officer's assigned department
    
    **Requires:** Officer authentication
    """
    if not current_user.department:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No department assigned to your account"
        )
    
    return get_department_clearances(
        department=current_user.department,
        academic_session=academic_session,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db
    )


@router.get("/stats")
def get_clearance_statistics(
    academic_session: Optional[str] = None,
    current_user: User = Depends(require_role(['admin', 'officer'])),
    db: Session = Depends(get_db)
):
    """
    Get clearance statistics
    
    **Requires:** Admin or Officer authentication
    
    **Returns:** Overall clearance progress and department breakdown
    """
    # Build base query
    query = db.query(Clearance)
    
    if academic_session:
        query = query.filter(Clearance.academic_session == academic_session)
    
    # If officer, filter by their department
    if current_user.role == 'officer':
        if not current_user.department:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No department assigned"
            )
        query = query.filter(Clearance.department == current_user.department)
    
    # Get all clearances
    all_clearances = query.all()
    
    # Department breakdown
    departments = [
        'Bursary', 'Faculty', 'Library', 'Sports', 
        'Hostel', 'ICT', 'Student Affairs'
    ]
    
    department_stats = {}
    for dept in departments:
        count = len([c for c in all_clearances if c.department == dept])
        department_stats[dept] = count
    
    # Get total students with allocations
    total_students_query = db.query(Allocation.student_id).distinct()
    
    if academic_session:
        total_students_query = total_students_query.filter(
            Allocation.academic_session == academic_session
        )
    
    total_students = total_students_query.count()
    
    # Students with complete clearance (7 departments)
    from sqlalchemy import func
    
    clearance_counts = db.query(
        Clearance.student_id,
        func.count(Clearance.id).label('count')
    ).group_by(Clearance.student_id)
    
    if academic_session:
        clearance_counts = clearance_counts.filter(
            Clearance.academic_session == academic_session
        )
    
    complete_clearances = clearance_counts.having(func.count(Clearance.id) == 7).count()
    
    logger.info(f"Clearance stats retrieved by {current_user.email}")
    
    return {
        "success": True,
        "data": {
            "total_students": total_students,
            "students_with_complete_clearance": complete_clearances,
            "total_clearances": len(all_clearances),
            "department_breakdown": department_stats,
            "academic_session": academic_session
        }
    }