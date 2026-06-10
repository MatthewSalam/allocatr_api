from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from io import BytesIO
import base64
from database import get_db
from models import User, Student, Receipt, Allocation, Room, QRCode, Clearance
from ..dependencies import require_role
from services.qr_generator import generate_qr_code
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/student", tags=["Student"])

# ==================== SCHEMAS ====================

class AllocationResponse(BaseModel):
    """Schema for student allocation response"""
    success: bool
    data: dict

class QRCodeResponse(BaseModel):
    """Schema for QR code response"""
    success: bool
    data: dict

class ClearanceStatusResponse(BaseModel):
    """Schema for clearance status"""
    success: bool
    data: dict


# ==================== ALLOCATION ENDPOINTS ====================
@router.get("/my-allocation", response_model=AllocationResponse)
def get_my_allocation(
    academic_session: Optional[str] = None,
    current_user: User = Depends(require_role(['student'])),
    db: Session = Depends(get_db)
):
    """
    Get current student's room allocation
    
    **Requires:** Student authentication
    
    **Returns:** Allocation details including room and QR code status
    """
    if not current_user.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record not found"
        )
    
    student_id = current_user.student.id
    
    # Build query
    query = db.query(Allocation, Room).join(
        Room, Allocation.room_id == Room.id
    ).filter(Allocation.student_id == student_id)
    
    # Filter by session if provided
    if academic_session:
        query = query.filter(Allocation.academic_session == academic_session)
    
    # Get latest allocation
    result = query.order_by(Allocation.allocated_at.desc()).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No room allocation found. Please contact admin."
        )
    
    allocation, room = result
    
    # Check if QR code exists
    qr_code = db.query(QRCode).filter(
        QRCode.student_id == student_id,
        QRCode.allocation_id == allocation.id
    ).first()
    
    logger.info(
        f"Allocation retrieved: {current_user.student.matric_number} - "
        f"{room.block} {room.room_number}"
    )
    
    return {
        "success": True,
        "data": {
            "allocation": {
                "id": allocation.id,
                "allocated_at": allocation.allocated_at,
                "allocation_method": allocation.allocation_method,
                "academic_session": allocation.academic_session,
                "status": allocation.status
            },
            "room": {
                "id": room.id,
                "block": room.block,
                "room_number": room.room_number,
                "full_name": f"{room.block} - {room.room_number}",
                "capacity": room.capacity,
                "current_occupants": room.current_occupants,
                "gender": room.gender
            },
            "qr_code_generated": qr_code is not None,
            "student": {
                "matric_number": current_user.student.matric_number,
                "full_name": current_user.student.full_name,
                "level": current_user.student.level,
                "department": current_user.student.department
            }
        }
    }

# ==================== QR CODE ENDPOINTS ====================
@router.get("/my-qr", response_model=QRCodeResponse)
def get_my_qr_code(
    current_user: User = Depends(require_role(['student'])),
    db: Session = Depends(get_db)
):
    """
    Get student's QR code for clearance
    
    **Requires:** Student authentication
    
    **Returns:** QR code as base64 image and raw data
    """
    if not current_user.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record not found"
        )
    
    student_id = current_user.student.id
    
    # Get latest allocation
    allocation = db.query(Allocation).filter(
        Allocation.student_id == student_id
    ).order_by(Allocation.allocated_at.desc()).first()
    
    if not allocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No room allocation found. You must be allocated a room before getting QR code."
        )
    
    # Check if QR code already exists
    existing_qr = db.query(QRCode).filter(
        QRCode.student_id == student_id,
        QRCode.allocation_id == allocation.id
    ).first()
    
    if existing_qr:
        logger.info(f"Existing QR code retrieved: {current_user.student.matric_number}")
        
        return {
            "success": True,
            "data": {
                "qr_code": existing_qr.qr_image_base64,
                "qr_data": existing_qr.qr_data,
                "generated_at": existing_qr.generated_at,
                "allocation": {
                    "room": f"{allocation.room.block} - {allocation.room.room_number}",
                    "academic_session": allocation.academic_session
                }
            }
        }
    
    # Generate new QR code if doesn't exist
    try:
        qr_result = generate_qr_code(
            student_id=student_id,
            allocation_id=allocation.id,
        )
        
        logger.info(f"✓ QR code generated: {current_user.student.matric_number}")
        
        return {
                "success": True,
                "data": {
                    "qr_code": qr_result['qr_image'],
                    "qr_data": qr_result['qr_string'],
                    "generated_at": datetime.utcnow(),
                    "allocation": {
                        "room": f"{allocation.room.block} - {allocation.room.room_number}",
                        "academic_session": allocation.academic_session
                    }
                }
            }
        
    except Exception as e:
        logger.error(f"QR generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR code. Please try again."
        )


@router.get("/my-qr/download")
def download_qr_code(
    format: str = "png",
    current_user: User = Depends(require_role(['student'])),
    db: Session = Depends(get_db)
):
    """
    Download QR code as image file
    
    **Requires:** Student authentication
    
    **Query Params:**
    - format: "png" (default) or "pdf"
    
    **Returns:** Image file for download
    """
    if not current_user.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record not found"
        )
    
    student_id = current_user.student.id
    
    # Get QR code
    allocation = db.query(Allocation).filter(
        Allocation.student_id == student_id
    ).order_by(Allocation.allocated_at.desc()).first()
    
    if not allocation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No allocation found"
        )
    
    qr_code = db.query(QRCode).filter(
        QRCode.student_id == student_id,
        QRCode.allocation_id == allocation.id
    ).first()
    
    if not qr_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="QR code not found. Please generate it first at /api/student/my-qr"
        )
    
    # Extract base64 data
    base64_data = qr_code.qr_image_base64
    if base64_data.startswith('data:image/png;base64,'):
        base64_data = base64_data.replace('data:image/png;base64,', '')
    
    # Decode base64 to bytes
    image_bytes = base64.b64decode(base64_data)
    
    if format.lower() == "png":
        # Return as PNG
        logger.info(f"QR code downloaded (PNG): {current_user.student.matric_number}")
        
        return StreamingResponse(
            BytesIO(image_bytes),
            media_type="image/png",
            headers={
                "Content-Disposition": f"attachment; filename=QR_Code_{current_user.student.matric_number}.png"
            }
        )
    
    elif format.lower() == "pdf":
        # Convert to PDF
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.utils import ImageReader
            
            # Create PDF
            pdf_buffer = BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=letter)
            
            # Add title
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, 750, "Hostel Allocation - Clearance QR Code")
            
            # Add student info
            c.setFont("Helvetica", 12)
            c.drawString(50, 720, f"Name: {current_user.student.full_name}")
            c.drawString(50, 700, f"Matric Number: {current_user.student.matric_number}")
            c.drawString(50, 680, f"Room: {allocation.room.block} - {allocation.room.room_number}")
            c.drawString(50, 660, f"Session: {allocation.academic_session}")
            
            # Add QR code image
            img = ImageReader(BytesIO(image_bytes))
            c.drawImage(img, 200, 300, width=250, height=250)
            
            # Add instructions
            c.setFont("Helvetica", 10)
            c.drawString(50, 250, "Instructions:")
            c.drawString(50, 235, "1. Present this QR code to officers at each clearance department")
            c.drawString(50, 220, "2. Ensure you have completed all requirements before scanning")
            c.drawString(50, 205, "3. Keep this QR code safe - do not share with others")
            
            c.save()
            
            pdf_buffer.seek(0)
            
            logger.info(f"QR code downloaded (PDF): {current_user.student.matric_number}")
            
            return StreamingResponse(
                pdf_buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=QR_Code_{current_user.student.matric_number}.pdf"
                }
            )
            
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="PDF generation not available. Please download as PNG instead."
            )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use 'png' or 'pdf'"
        )

# ==================== CLEARANCE STATUS ENDPOINTS ====================
@router.get("/my-clearance", response_model=ClearanceStatusResponse)
def get_my_clearance_status(
    academic_session: Optional[str] = None,
    current_user: User = Depends(require_role(['student'])),
    db: Session = Depends(get_db)
):
    """Get current student's clearance status"""
    
    if not current_user.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record not found"
        )
    
    student_id = current_user.student.id
    
    # Get student's latest allocation if session not specified
    if not academic_session:
        latest_allocation = db.query(Allocation).filter(
            Allocation.student_id == student_id
        ).order_by(Allocation.allocated_at.desc()).first()
        
        if not latest_allocation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No allocation found. You must be allocated a room before clearance."
            )
        
        academic_session = latest_allocation.academic_session
    
    # Get all clearances
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
    
    # Format clearance data - FIXED VERSION
    clearance_data = []
    for c in clearances:
        # Get the user who cleared this
        cleared_by_email = None
        if c.cleared_by:
            user = db.query(User).filter(User.id == c.cleared_by).first()
            if user:
                cleared_by_email = user.email
        
        clearance_data.append({
            "id": c.id,
            "department": c.department,
            "cleared_by": cleared_by_email,
            "cleared_at": c.cleared_at,
            "notes": c.notes
        })
    
    total_departments = len(all_departments)
    cleared_count = len(clearances)
    pending_count = total_departments - cleared_count
    progress = int((cleared_count / total_departments) * 100)
    
    logger.info(
        f"Clearance status retrieved: {current_user.student.matric_number} - "
        f"{cleared_count}/{total_departments} departments"
    )
    
    return {
        "success": True,
        "data": {
            "student": {
                "matric_number": current_user.student.matric_number,
                "full_name": current_user.student.full_name
            },
            "progress": {
                "total_departments": total_departments,
                "cleared_departments": cleared_count,
                "pending_departments": pending_count,
                "progress_percentage": progress,
                "is_complete": cleared_count == total_departments
            },
            "clearances": clearance_data,
            "pending": pending_departments,
            "academic_session": academic_session
        }
    }

# ==================== DASHBOARD ENDPOINT ====================
@router.get("/dashboard")
def get_student_dashboard(
    current_user: User = Depends(require_role(['student'])),
    db: Session = Depends(get_db)
):
    """
    Get student dashboard data (all-in-one)
    
    **Requires:** Student authentication
    
    **Returns:** 
    - Student info
    - Receipt status
    - Allocation status
    - QR code status
    - Clearance progress
    """
    if not current_user.student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student record not found"
        )
    
    student = current_user.student
    
    # Get latest receipt
    latest_receipt = db.query(Receipt).filter(
        Receipt.student_id == student.id
    ).order_by(Receipt.uploaded_at.desc()).first()
    
    receipt_status = None
    if latest_receipt:
        receipt_status = {
            "status": latest_receipt.verification_status,
            "uploaded_at": latest_receipt.uploaded_at,
            "amount": float(latest_receipt.amount) if latest_receipt.amount else None
        }
    
    # Get latest allocation
    latest_allocation = db.query(Allocation, Room).join(
        Room, Allocation.room_id == Room.id
    ).filter(
        Allocation.student_id == student.id
    ).order_by(Allocation.allocated_at.desc()).first()
    
    allocation_status = None
    qr_code_status = None
    
    if latest_allocation:
        allocation, room = latest_allocation
        allocation_status = {
            "room": f"{room.block} - {room.room_number}",
            "allocated_at": allocation.allocated_at,
            "academic_session": allocation.academic_session
        }
        
        # Check QR code
        qr_code = db.query(QRCode).filter(
            QRCode.student_id == student.id,
            QRCode.allocation_id == allocation.id
        ).first()
        
        qr_code_status = {
            "generated": qr_code is not None,
            "generated_at": qr_code.generated_at if qr_code else None
        }
    
    # Get clearance progress
    clearances_count = 0
    academic_session = None
    
    if latest_allocation:
        allocation, room = latest_allocation
        academic_session = allocation.academic_session
        clearances_count = db.query(Clearance).filter(
            Clearance.student_id == student.id,
            Clearance.academic_session == academic_session
        ).count()
    
    total_departments = 7
    clearance_progress = {
        "cleared": clearances_count,
        "total": total_departments,
        "percentage": int((clearances_count / total_departments) * 100),
        "complete": clearances_count == total_departments
    }
    
    logger.info(f"Dashboard data retrieved: {student.matric_number}")
    
    return {
        "success": True,
        "data": {
            "student": {
                "matric_number": student.matric_number,
                "full_name": student.full_name,
                "email": student.email,
                "level": student.level,
                "department": student.department,
                "gender": student.gender
            },
            "receipt": receipt_status,
            "allocation": allocation_status,
            "qr_code": qr_code_status,
            "clearance": clearance_progress,
            "academic_session": academic_session
        }
    }