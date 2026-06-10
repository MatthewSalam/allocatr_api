import os
import uuid
import shutil
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Receipt, Student, Allocation
from api.dependencies import get_current_user, require_role

load_dotenv()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads/receipts")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "5"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/receipts", tags=["Receipts"])

class ReceiptResponse(BaseModel):
    id: int
    student_id: int
    file_name: str
    file_type: Optional[str]
    file_size: Optional[int]
    uploaded_at: datetime
    verification_status: str
    amount: Optional[float]
    payment_reference: Optional[str]
    preferred_block: Optional[str]
    preferred_room_number: Optional[str]
    rejection_reason: Optional[str]
    academic_session: str

    class Config:
        from_attributes = True


class ReceiptStatusResponse(BaseModel):
    """Lightweight status check response"""
    id: int
    verification_status: str
    uploaded_at: datetime
    rejection_reason: Optional[str]
    academic_session: str

    class Config:
        from_attributes = True

def validate_file(file: UploadFile) -> None:
    """Raise HTTPException if file type or size is invalid"""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )


def save_file(file: UploadFile, student_id: int) -> tuple[str, int]:
    """
    Save uploaded file to disk.
    Returns (file_path, file_size_in_bytes).
    Uses UUID in filename to prevent collisions.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    unique_name = f"{student_id}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    file.file.seek(0, 2)           # seek to end
    file_size = file.file.tell()   # get size
    file.file.seek(0)              # reset to start

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB."
        )

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return file_path, file_size


def get_active_receipt(student_id: int, academic_session: str, db: Session) -> Optional[Receipt]:

    return (
        db.query(Receipt)
        .filter(
            Receipt.student_id == student_id,
            Receipt.academic_session == academic_session,
            Receipt.verification_status.in_(["pending", "verified"])
        )
        .first()
    )


@router.post("/upload", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    # File
    file: UploadFile = File(..., description="Payment receipt image or PDF"),

    # Optional payment details (student fills these in)
    amount: Optional[float] = Form(None, description="Amount paid e.g. 50000.00"),
    payment_reference: Optional[str] = Form(None, description="Bank/payment reference number"),
    academic_session: str = Form(..., description="e.g. 2025/2026"),

    # Optional room preferences
    preferred_block: Optional[str] = Form(None, description="e.g. Block A"),
    preferred_room_number: Optional[str] = Form(None, description="e.g. 22"),

    # Injected by FastAPI
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Student uploads a payment receipt.

    Rules:
    - Student must be authenticated
    - Only one active (pending/verified) receipt per session allowed
    - Resubmission is allowed ONLY if the previous receipt was rejected
    - File must be JPG, JPEG, PNG, or PDF and under 5MB
    """
    require_role(current_user, "student")

    student = db.query(Student).filter(Student.id == current_user.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")

    # Block resubmission if a pending or verified receipt already exists
    active = get_active_receipt(student.id, academic_session, db)
    if active:
        status_msg = "pending review" if active.verification_status == "pending" else "already verified"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a receipt that is {status_msg} for session {academic_session}. "
                   f"You can only resubmit after a rejection."
        )

    # Validate and save file
    validate_file(file)
    file_path, file_size = save_file(file, student.id)

    # Persist to DB
    receipt = Receipt(
        student_id=student.id,
        file_path=file_path,
        file_name=file.filename,
        file_type=os.path.splitext(file.filename)[1].lower(),
        file_size=file_size,
        verification_status="pending",
        amount=amount,
        payment_reference=payment_reference,
        academic_session=academic_session,
        preferred_block=preferred_block,
        preferred_room_number=preferred_room_number,
    )

    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    return receipt


@router.get("/my-receipts", response_model=List[ReceiptResponse])
def get_my_receipts(
    academic_session: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    require_role(current_user, "student")
    query = db.query(Receipt).filter(Receipt.student_id == current_user.student_id)
    if academic_session:
        query = query.filter(Receipt.academic_session == academic_session)

    receipts = query.order_by(Receipt.uploaded_at.desc()).all()

    if not receipts:
        raise HTTPException(status_code=404, detail="No receipts found.")

    return receipts


@router.get("/my-status", response_model=ReceiptStatusResponse)
def get_my_receipt_status(
    academic_session: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Student checks the status of their LATEST receipt for a given session.
    Returns: pending / verified / rejected + rejection reason if applicable.
    """
    require_role(current_user, "student")

    receipt = (
        db.query(Receipt)
        .filter(
            Receipt.student_id == current_user.student_id,
            Receipt.academic_session == academic_session,
        )
        .order_by(Receipt.uploaded_at.desc())
        .first()
    )

    if not receipt:
        raise HTTPException(
            status_code=404,
            detail=f"No receipt found for session {academic_session}."
        )

    return receipt


@router.delete("/cancel/{receipt_id}", status_code=status.HTTP_200_OK)
def cancel_receipt(
    receipt_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(current_user, "student")

    receipt = (
        db.query(Receipt)
        .filter(
            Receipt.id == receipt_id,
            Receipt.student_id == current_user.student_id
        )
        .first()
    )

    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found.")

    if receipt.verification_status == "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot cancel a verified receipt. Please contact the admin."
        )

    if receipt.verification_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a receipt with status '{receipt.verification_status}'."
        )

    allocation = (
        db.query(Allocation)
        .filter(
            Allocation.student_id == current_user.student_id,
            Allocation.academic_session == receipt.academic_session,
            Allocation.status == "active"
        )
        .first()
    )
    if allocation:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You already have an active room allocation for this session. Cannot cancel receipt."
        )

    # Delete file from disk
    if os.path.exists(receipt.file_path):
        os.remove(receipt.file_path)

    db.delete(receipt)
    db.commit()

    return {"detail": "Receipt cancelled and deleted successfully."}

