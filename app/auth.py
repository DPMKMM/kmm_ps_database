import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserSession, LoginHistory, AuditLog

ph = PasswordHasher()
security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError):
        return False

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.SESSION_INACTIVITY_MINUTES * 4)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def authenticate_and_create_session(
    username: str,
    password: str,
    ip_address: str,
    device_info: str,
    db: Session
) -> dict:
    user = db.query(User).filter(User.username == username).first()
    
    if not user:
        # Record failed attempt
        log = LoginHistory(
            username_attempted=username,
            ip_address=ip_address,
            device_info=device_info,
            status="FAILED_NOT_FOUND",
            reason="User not found"
        )
        db.add(log)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Check if locked
    if user.is_locked:
        log = LoginHistory(
            user_id=user.id,
            username_attempted=username,
            ip_address=ip_address,
            device_info=device_info,
            status="FAILED_LOCKED",
            reason="Account is locked"
        )
        db.add(log)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been locked due to 5 consecutive failed login attempts. Please contact District Super Admin to unlock."
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact District Super Admin."
        )

    # Check password
    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        is_now_locked = False
        if user.failed_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.is_locked = True
            is_now_locked = True
            
        log = LoginHistory(
            user_id=user.id,
            username_attempted=username,
            ip_address=ip_address,
            device_info=device_info,
            status="FAILED_PASSWORD",
            reason=f"Failed attempt {user.failed_attempts}" + (" - Account locked" if is_now_locked else "")
        )
        db.add(log)
        db.commit()
        
        if is_now_locked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account locked after 5 consecutive failed attempts. Contact District Super Admin."
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid username or password. Remaining attempts: {settings.MAX_FAILED_LOGIN_ATTEMPTS - user.failed_attempts}"
        )

    # Password is correct - clean up expired sessions and handle multi-user vs single-session policy
    now = datetime.utcnow()
    inactivity_cutoff = now - timedelta(minutes=settings.SESSION_INACTIVITY_MINUTES)
    
    # Clean up expired sessions for this user
    active_sessions = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.session_status == "ACTIVE"
    ).all()
    
    for s in active_sessions:
        if s.last_activity < inactivity_cutoff:
            s.session_status = "EXPIRED"
            s.logout_datetime = now
    db.commit()
    
    if not settings.ALLOW_MULTI_USER_SESSIONS:
        still_active = db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.session_status == "ACTIVE"
        ).first()
        if still_active:
            if user.role == "MANDAL_ADMIN":
                log = LoginHistory(
                    user_id=user.id,
                    username_attempted=username,
                    ip_address=ip_address,
                    device_info=device_info,
                    status="FAILED_ALREADY_LOGGED_IN",
                    reason="Concurrent login blocked - active Mandal session exists"
                )
                db.add(log)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This Mandal account is already logged in on another device. Please logout from the existing device before attempting a new login."
                )
            else:
                still_active.session_status = "TERMINATED"
                still_active.logout_datetime = now
                db.commit()

    # Reset failed attempts
    user.failed_attempts = 0
    
    # Create new session
    session_id = uuid.uuid4().hex
    token_data = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "mandal_id": user.mandal_id,
        "mandal_lgd": user.mandal_lgd,
        "session_id": session_id
    }
    
    token = create_access_token(token_data)
    token_hash = hash_token(token)
    
    new_session = UserSession(
        session_id=session_id,
        user_id=user.id,
        mandal_id=user.mandal_id,
        session_token_hash=token_hash,
        login_datetime=now,
        last_activity=now,
        ip_address=ip_address,
        device_info=device_info,
        session_status="ACTIVE"
    )
    db.add(new_session)
    
    log = LoginHistory(
        user_id=user.id,
        username_attempted=username,
        ip_address=ip_address,
        device_info=device_info,
        status="SUCCESS",
        reason="Login successful"
    )
    db.add(log)
    
    audit = AuditLog(
        user_id=user.id,
        username=user.username,
        mandal_id=user.mandal_id,
        action="LOGIN",
        entity_type="SESSION",
        entity_id=session_id,
        details=f"Login from {ip_address} using {device_info}",
        ip_address=ip_address,
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    mandal_name = user.mandal.mandal_name if user.mandal else None
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "session_id": session_id,
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "mandal_id": user.mandal_id,
        "mandal_name": mandal_name,
        "mandal_lgd": user.mandal_lgd,
        "must_change_password": user.must_change_password
    }

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        session_id: str = payload.get("session_id")
        if username is None or session_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")

    # Validate active session in database
    now = datetime.utcnow()
    inactivity_cutoff = now - timedelta(minutes=settings.SESSION_INACTIVITY_MINUTES)
    
    user_session = db.query(UserSession).filter(
        UserSession.session_id == session_id,
        UserSession.session_status == "ACTIVE"
    ).first()
    
    if not user_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or been terminated. Please login again."
        )
        
    if user_session.last_activity < inactivity_cutoff:
        user_session.session_status = "EXPIRED"
        user_session.logout_datetime = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Session timed out due to {settings.SESSION_INACTIVITY_MINUTES} minutes of inactivity. Please login again."
        )
        
    # Update last activity timestamp to keep active
    user_session.last_activity = now
    db.commit()
    
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or user.is_locked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account disabled or locked")
        
    # Attach session to user object for easy handler inspection
    user.current_session_id = session_id
    return user

def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="District Super Admin privileges required"
        )
    return current_user

def require_mandal_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ["SUPER_ADMIN", "MANDAL_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mandal Admin access required"
        )
    return current_user

def enforce_mandal_isolation(current_user: User, mandal_id: int):
    """
    STRICT ACCESS RESTRICTION:
    A Mandal user must never access, edit or delete another Mandal's records.
    Enforce this restriction at the backend and database query level.
    """
    if current_user.role == "SUPER_ADMIN":
        return
    if current_user.role == "MANDAL_ADMIN":
        if current_user.mandal_id != mandal_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not authorized to view or modify records of another Mandal."
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
