from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from security import decode_access_token
from models import User
import logging

logger = logging.getLogger(__name__)

http_bearer = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    bearer_token: Optional[HTTPBearer] = Depends(http_bearer),
    oauth_token: Optional[str] = Depends(oauth2_scheme)
) -> User:
    """Get current authenticated user"""
    # Extract token
    token = None
    
    if bearer_token and bearer_token.credentials:
        token = bearer_token.credentials
        logger.debug("Using Bearer token authentication")
    elif oauth_token:
        token = oauth_token
        logger.debug("Using OAuth2 token authentication")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Decode token
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Get user ID from token (it's a string, convert to int)
    user_id_str = payload.get("sub")
    
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload - missing user ID"
        )
    
    # Convert string to integer
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload - invalid user ID format"
        )
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    return user


def require_role(*allowed_roles: str):
    def role_checker(user: User = Depends(get_current_user)):
        roles = []

        for r in allowed_roles:
            if isinstance(r, list):
                roles.extend(r)
            else:
                roles.append(r)

        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(map(str, roles))}. Your role: {user.role}"
            )
        return user

    return role_checker