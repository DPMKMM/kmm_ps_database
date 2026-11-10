from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.config import settings
from app.models import (
    User, Mandal, UserSession, LoginHistory, AuditLog, DataSubmission
)
from app.auth import get_current_user, require_super_admin, hash_password
from app.schemas import DataSubmissionPayload

router = APIRouter(prefix="/api/admin", tags=["District Super Admin Controls"])

@router.get("/users")
def list_users(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    users = db.query(User).order_by(User.role.asc(), User.username.asc()).all()
    results = []
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=settings.SESSION_INACTIVITY_MINUTES)
    
    for u in users:
        # Collect all active non-expired sessions for this user (multi-user concurrent support)
        active_sessions = db.query(UserSession).filter(
            UserSession.user_id == u.id,
            UserSession.session_status == "ACTIVE",
            UserSession.last_activity >= cutoff
        ).order_by(UserSession.last_activity.desc()).all()
        latest_sess = active_sessions[0] if active_sessions else None
        
        m_name = u.mandal.mandal_name if u.mandal else ("All Mandals" if u.role == "SUPER_ADMIN" else "District")
        
        results.append({
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "mandal_id": u.mandal_id,
            "mandal_name": m_name,
            "mandal_lgd": u.mandal_lgd,
            "failed_attempts": u.failed_attempts,
            "is_locked": u.is_locked,
            "is_active": u.is_active,
            "must_change_password": u.must_change_password,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
            "has_active_session": len(active_sessions) > 0,
            "active_session_count": len(active_sessions),
            "active_session_ip": latest_sess.ip_address if latest_sess else None,
            "active_session_device": latest_sess.device_info if latest_sess else None
        })
    return results

@router.post("/users/{user_id}/unlock")
def unlock_user_account(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.is_locked = False
    user.failed_attempts = 0
    user.locked_until = None
    
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="UNLOCK_USER",
        entity_type="USER",
        entity_id=str(user.id),
        details=f"Unlocked user account {user.username}",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=datetime.utcnow()
    )
    db.add(audit)
    db.commit()
    
    return {"message": f"User account {user.username} has been unlocked successfully"}

@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    new_password: str = Query(..., min_length=6),
    request: Request = None,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.password_hash = hash_password(new_password)
    user.must_change_password = True # Force password change on first login (Section 5)
    user.failed_attempts = 0
    user.is_locked = False
    
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="RESET_PASSWORD",
        entity_type="USER",
        entity_id=str(user.id),
        details=f"Reset password for user {user.username}. Forced password change required.",
        ip_address=request.client.host if request and request.client else "127.0.0.1",
        timestamp=datetime.utcnow()
    )
    db.add(audit)
    db.commit()
    
    return {"message": f"Password reset for {user.username}. User will be prompted to change password upon login."}

@router.get("/audit-logs")
def get_audit_logs(
    action: Optional[str] = None,
    username: Optional[str] = None,
    limit: int = 150,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if username:
        query = query.filter(AuditLog.username == username)
        
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "username": l.username,
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "details": l.details,
            "ip_address": l.ip_address,
            "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else ""
        }
        for l in logs
    ]

@router.post("/submissions/submit")
def submit_mandal_data(
    payload: DataSubmissionPayload,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Field 8: Declaration and Final Mandal Submission
    """
    if current_user.role != "MANDAL_ADMIN":
        raise HTTPException(status_code=403, detail="Only Mandal Admins can submit Mandal data")
        
    sub = db.query(DataSubmission).filter(DataSubmission.mandal_id == current_user.mandal_id).first()
    if not sub:
        sub = DataSubmission(mandal_id=current_user.mandal_id)
        db.add(sub)
        
    if sub.is_locked:
        raise HTTPException(status_code=403, detail="Mandal submission has been locked by District Super Admin")
        
    now = datetime.utcnow()
    declaration_text = (
        "I hereby certify that the above employee information, salary-claiming Gram Panchayat, "
        "current working location and employee service status details are verified with available official records."
    )
    
    sub.is_submitted = True
    sub.submitted_by_name = payload.submitted_by_name.strip()
    sub.submitted_by_designation = payload.submitted_by_designation.strip()
    sub.declaration_text = declaration_text
    sub.submitted_at = now
    
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=current_user.mandal_id,
        action="FINAL_SUBMISSION",
        entity_type="SUBMISSION",
        entity_id=str(sub.id),
        details=f"Final data submitted by {sub.submitted_by_name} ({sub.submitted_by_designation})",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Data successfully submitted for District verification with official declaration."}

@router.post("/submissions/{mandal_id}/toggle-lock")
def toggle_submission_lock(
    mandal_id: int,
    lock: bool,
    request: Request,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    sub = db.query(DataSubmission).filter(DataSubmission.mandal_id == mandal_id).first()
    if not sub:
        sub = DataSubmission(mandal_id=mandal_id)
        db.add(sub)
        
    now = datetime.utcnow()
    sub.is_locked = lock
    sub.locked_by = current_user.username if lock else None
    sub.locked_at = now if lock else None
    
    action_str = "LOCK_SUBMISSION" if lock else "REOPEN_SUBMISSION"
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action=action_str,
        entity_type="SUBMISSION",
        entity_id=str(mandal_id),
        details=f"Mandal {mandal_id} data submission {'locked' if lock else 'reopened'} by District Admin",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {"message": f"Mandal submission has been {'locked' if lock else 'reopened'} successfully"}
