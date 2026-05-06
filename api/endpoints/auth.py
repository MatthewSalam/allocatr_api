from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Annotated
from database import get_db
from security import verify_password, get_password_hash, create_access_token
from models import User, Student
from ..dependencies import get_current_user, require_role
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class StudentRegisterRequest(BaseModel):
    """Schema for student registration"""
    matric_number: str = Field(..., min_length=5, max_length=20)
    full_name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    gender: str = Field(pattern="^(?i)(Male|Female)$")    
    level: Optional[str] = Field(None, pattern="^(100|200|300|400|500)$")
    department: Optional[str] = Field(None, max_length=100)
    password: str = Field(..., min_length=8)
    
    class Config:
        json_schema_extra = {
            "example": {
                "matric_number": "22/0336",
                "full_name": "Salam Oluwatunmise Jomiloju",
                "email": "salam@adeleke.edu.ng",
                "phone": "08012345678",
                "gender": "MALE",
                "level": "400",
                "department": "Software Engineering",
                "password": "SecurePass123"
            }
        }

class AdminRegisterRequest(BaseModel):
    """Schema for Admin registration (FIRST admin or super admin creation)"""
    
    full_name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    password: str = Field(..., min_length=8)

    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Admin User",
                "email": "admin@adeleke.edu.ng",
                "phone": "08012345678",
                "password": "admin123"
            }
        }

class OfficerRegisterRequest(BaseModel):
    """Schema for Officer registration"""
    full_name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    role: str = Field(..., pattern="^(admin|officer)$")
    department: Optional[str] = None
    password: str = Field(..., min_length=8)

    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Bursary Officer",
                "email": "bursary@adeleke.edu.ng",
                "phone": "08022222222",
                "role": "officer",
                "department": "Bursary",
                "password": "bursary123"
            }
        }

class LoginRequest(BaseModel):
    """Schema for JSON login"""
    email: EmailStr
    password: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "salam@adeleke.edu.ng",
                "password": "SecurePass123"
            }
        }

class LoginResponse(BaseModel):
    """Schema for login response"""
    success: bool
    message: str
    data: dict

class RegisterResponse(BaseModel):
    """Schema for registration response"""
    success: bool
    message: str
    data: dict

# ==================== ENDPOINTS ====================
@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register_student(
    student_data: StudentRegisterRequest,
    db: Session = Depends(get_db)):
    """Register a new student account"""
    logger.info(f"Registration attempt for: {student_data.email}")
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == student_data.email).first()
    if existing_user:
        logger.warning(f"Registration failed: Email {student_data.email} already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if matric number already exists
    existing_student = db.query(Student).filter(
        Student.matric_number == student_data.matric_number
    ).first()
    if existing_student:
        logger.warning(f"Registration failed: Matric {student_data.matric_number} already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Matric number already registered"
        )
    
    try:
        # Create student record
        new_student = Student(
            matric_number=student_data.matric_number,
            full_name=student_data.full_name,
            email=student_data.email,
            phone=student_data.phone,
            gender=student_data.gender.upper(),
            level=student_data.level,
            department=student_data.department
        )
        db.add(new_student)
        db.flush()
        
        # Create user account
        hashed_password = get_password_hash(student_data.password)
        new_user = User(
            email=student_data.email,
            full_name=student_data.full_name,
            phone=student_data.phone,
            password_hash=hashed_password,
            role='student',
            student_id=new_student.id,
            is_active=True
        )
        db.add(new_user)
        db.commit()
        
        logger.info(f"✓ Student registered: {student_data.matric_number}")
        
        return {
            "success": True,
            "message": "Student registered successfully",
            "data": {
                "student_id": new_student.id,
                "matric_number": new_student.matric_number,
                "email": new_student.email
            }
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )

@router.post("/register-staff", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register_staff(
    staff_data: AdminRegisterRequest,
    db: Session = Depends(get_db)
):
    existing_admins = db.query(User).filter(User.role == 'admin').count()

    if existing_admins > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin authentication required. The first admin has already been created."
        )

    existing_user = db.query(User).filter(User.email == staff_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    try:
        hashed_password = get_password_hash(staff_data.password)

        new_user = User(
            email=staff_data.email,
            password_hash=hashed_password,
            role="admin",              # hardcoded because first user must be admin
            department=None,           # first admin has no department
            student_id=None,
            is_active=True,
            full_name=staff_data.full_name,
            phone=staff_data.phone
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "success": True,
            "message": "First admin account created successfully.",
            "data": {
                "user_id": new_user.id,
                "email": new_user.email,
                "role": new_user.role,
                "department": new_user.department
            }
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Staff registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Staff registration failed. Please try again."
        )

@router.post("/register-staff-authenticated", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register_staff_authenticated(
    staff_data: OfficerRegisterRequest,
    current_user: User = Depends(require_role('admin')),
    db: Session = Depends(get_db)
):
    """
    Register additional staff (admin or officer)
    
    **Requires:** Admin authentication
    
    Use this endpoint to create staff AFTER the first admin is created.
    """
    logger.info(f"Staff registration by admin {current_user.email} for: {staff_data.email}")
    
    # Validate: Officers must have a department
    if staff_data.role == 'officer' and not staff_data.department:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department is required for officer role"
        )
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == staff_data.email).first()
    if existing_user:
        logger.warning(f"Staff registration failed: Email {staff_data.email} already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    try:
        # Create user account
        hashed_password = get_password_hash(staff_data.password)
        new_user = User(
            email=staff_data.email,
            password_hash=hashed_password,
            role=staff_data.role,
            department=staff_data.department,
            student_id=None,
            is_active=True,
            full_name=staff_data.full_name,
            phone=staff_data.phone
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"✓ Staff registered by {current_user.email}: {staff_data.email} (role: {staff_data.role})")
        
        return {
            "success": True,
            "message": f"{staff_data.role.capitalize()} account created successfully",
            "data": {
                "user_id": new_user.id,
                "email": new_user.email,
                "role": new_user.role,
                "department": new_user.department
            }
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Staff registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Staff registration failed. Please try again."
        )

@router.post("/login", response_model=LoginResponse)
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login with JSON (for API clients, mobile apps, etc.)
    
    Returns full user info + token
    """
    logger.info(f"JSON login attempt for: {login_data.email}")
    
    # Find user by email
    user = db.query(User).filter(User.email == login_data.email).first()
    
    if not user:
        logger.warning(f"Login failed: User {login_data.email} not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Verify password
    if not verify_password(login_data.password, user.password_hash):
        logger.warning(f"Login failed: Wrong password for {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Check if account is active
    if not user.is_active:
        logger.warning(f"Login failed: Account {login_data.email} is inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact administrator."
        )
    
    # Create access token
    token_data = {
        "sub": str(user.id),
        "role": user.role
    }
    access_token = create_access_token(data=token_data)
    
    # Get full name if student
    full_name = None
    if user.student:
        full_name = user.student.full_name
    
    logger.info(f"✓ JSON login successful: {login_data.email}")
    
    return {
        "success": True,
        "message": "Login successful",
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "student_id": user.student_id,
                "full_name": full_name,
                "department": user.department
            }
        }
    }

@router.post("/token")
def oauth2_login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
):
    """
    OAuth2 compatible login (for Swagger UI "Authorize" button)
    
    Allows users to login with username/password form
    Returns simple token response (OAuth2 spec)
    """
    logger.info(f"OAuth2 login attempt for: {form_data.username}")
    
    # Find user by email (username field contains email)
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user:
        logger.warning(f"OAuth2 login failed: User {form_data.username} not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Verify password
    if not verify_password(form_data.password, user.password_hash):
        logger.warning(f"OAuth2 login failed: Wrong password for {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check if active
    if not user.is_active:
        logger.warning(f"OAuth2 login failed: Account {form_data.username} is inactive")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Create token
    token_data = {
        "sub": str(user.id),
        "role": user.role
    }
    access_token = create_access_token(data=token_data)
    
    logger.info(f"✓ OAuth2 login successful: {form_data.username}")
    
    # OAuth2 spec requires this exact format (no extra fields!)
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me")
def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user's information
    
    Requires: Valid JWT token (via Bearer or OAuth2)
    """
    # Get full name if student
    full_name = None
    if current_user.student:
        full_name = current_user.student.full_name
    
    return {
        "success": True,
        "data": {
            "id": current_user.id,
            "email": current_user.email,
            "role": current_user.role,
            "student_id": current_user.student_id,
            "full_name": full_name,
            "is_active": current_user.is_active
        }
    }
