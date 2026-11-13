from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    GPVerification, EmployeePosting, Employee, EmployeeSalaryMapping,
    GramPanchayat, Mandal, User, DiscrepancyRecord, AuditLog
)
from app.schemas import TwoSideVerificationAction
from app.auth import get_current_user

router = APIRouter(prefix="/api/verifications", tags=["Two-Side Deputation Verification Centre"])

@router.get("")
def get_pending_verifications(
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    SECTION 14: TWO-SIDE DEPUTATION VERIFICATION
    Lists deputation verification tasks.
    If Mandal Admin, shows both requests sent out from this Mandal and incoming deputations into this Mandal.
    """
    query = (
        db.query(
            GPVerification,
            EmployeePosting,
            Employee,
            EmployeeSalaryMapping
        )
        .join(EmployeePosting, EmployeePosting.id == GPVerification.posting_id)
        .join(Employee, Employee.employee_id == GPVerification.employee_id)
        .join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == GPVerification.employee_id)
        .filter(EmployeeSalaryMapping.is_active == True, EmployeePosting.is_current == True)
    )
    
    if current_user.role == "MANDAL_ADMIN":
        # Show incoming to this mandal or outgoing from this mandal
        query = query.filter(
            (GPVerification.receiving_mandal_id == current_user.mandal_id) |
            (GPVerification.salary_mandal_id == current_user.mandal_id)
        )
        
    if status_filter:
        query = query.filter(GPVerification.status == status_filter)
        
    verifs = query.order_by(GPVerification.id.desc()).all()
    
    incoming = []
    outgoing = []
    
    for v, p, emp, sm in verifs:
        salary_gp = sm.panchayat
        working_gp = p.working_panchayat
        
        item = {
            "verification_id": v.id,
            "posting_id": p.id,
            "employee_id": emp.employee_id,
            "name_ifmis": emp.name_ifmis,
            "salary_gp_lgd": sm.salary_gp_lgd,
            "salary_gp_name": salary_gp.gp_name if salary_gp else "N/A",
            "salary_mandal_id": v.salary_mandal_id,
            "salary_mandal_name": salary_gp.mandal_name if salary_gp else "N/A",
            "receiving_gp_lgd": p.actual_working_gp_lgd,
            "receiving_gp_name": working_gp.gp_name if working_gp else (p.external_gp_or_office_name or "N/A"),
            "receiving_mandal_id": v.receiving_mandal_id,
            "receiving_mandal_name": working_gp.mandal_name if working_gp else (p.external_mandal_name or "N/A"),
            "deputation_type": p.posting_type,
            "deputation_order_no": p.deputation_order_no,
            "deputation_order_date": p.deputation_order_date.strftime("%Y-%m-%d") if p.deputation_order_date else None,
            "status": v.status,
            "posting_verification_status": p.verification_status,
            "receiving_remarks": v.receiving_remarks,
            "verified_by_user": v.verified_by_user,
            "verified_at": v.verified_at.strftime("%Y-%m-%d %H:%M") if v.verified_at else None
        }
        
        if current_user.role == "MANDAL_ADMIN":
            if v.receiving_mandal_id == current_user.mandal_id:
                incoming.append(item)
            else:
                outgoing.append(item)
        else:
            incoming.append(item)
            
    return {
        "incoming_verifications": incoming,
        "outgoing_verifications": outgoing,
        "total_incoming": len(incoming),
        "total_outgoing": len(outgoing)
    }

@router.post("/action")
def take_verification_action(
    payload: TwoSideVerificationAction,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    posting = db.query(EmployeePosting).filter(EmployeePosting.id == payload.posting_id).first()
    if not posting:
        raise HTTPException(status_code=404, detail="Posting record not found")
        
    verif = db.query(GPVerification).filter(GPVerification.posting_id == posting.id).first()
    if not verif:
        raise HTTPException(status_code=404, detail="Verification entry not found")
        
    if current_user.role == "VIEWER":
        raise HTTPException(
            status_code=403,
            detail="Read-only access: District Viewer cannot verify deputations."
        )

    # Check permission: Only the receiving Mandal admin OR District Admins can verify incoming deputation
    if current_user.role == "MANDAL_ADMIN":
        if verif.receiving_mandal_id != current_user.mandal_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Only the receiving Mandal official can confirm or reject incoming deputations."
            )
            
    now = datetime.utcnow()
    action = payload.action.upper()
    
    if action == "CONFIRM":
        # Handle internal reallocation to a different GP within receiving mandal if specified
        if payload.corrected_working_gp_lgd:
            new_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == payload.corrected_working_gp_lgd).first()
            if not new_gp:
                raise HTTPException(status_code=400, detail="Specified re-allocation Gram Panchayat not found.")
            if current_user.role == "MANDAL_ADMIN" and new_gp.mandal_id != current_user.mandal_id:
                raise HTTPException(status_code=403, detail="Cannot re-allocate to a Gram Panchayat outside your Mandal.")
            posting.actual_working_gp_lgd = new_gp.lgd_code
            posting.actual_working_mandal_id = new_gp.mandal_id
            verif.receiving_remarks = f"Internally assigned to {new_gp.gp_name} (LGD: {new_gp.lgd_code}). {payload.remarks or ''}"
        else:
            verif.receiving_remarks = payload.remarks or "Physical joining verified and confirmed by receiving Mandal."
        verif.status = "CONFIRMED"
        verif.verified_by_user = current_user.username
        verif.verified_at = now
        posting.verification_status = "VERIFIED_BOTH"
    elif action == "REJECT":
        verif.status = "REJECTED"
        verif.receiving_remarks = payload.remarks or "Rejected: Employee not physically working in this Gram Panchayat."
        verif.verified_by_user = current_user.username
        verif.verified_at = now
        posting.verification_status = "REJECTED"
        
        # Log discrepancy
        disc = DiscrepancyRecord(
            discrepancy_code="DEP_REJECTED",
            title="Deputation Rejected by Receiving Mandal",
            description=f"Receiving Mandal rejected deputation for {posting.employee_id} ({payload.remarks or 'Employee not joined'}).",
            severity="HIGH",
            employee_id=posting.employee_id,
            gp_lgd=posting.actual_working_gp_lgd,
            mandal_id=verif.salary_mandal_id,
            status="OPEN",
            assigned_to_mandal_id=verif.salary_mandal_id,
            detected_at=now
        )
        db.add(disc)
    elif action == "DISCREPANCY":
        verif.status = "DISCREPANCY"
        verif.receiving_remarks = payload.remarks or "Discrepancy noted in posting details."
        verif.verified_by_user = current_user.username
        verif.verified_at = now
        posting.verification_status = "DISCREPANCY"
        
        disc = DiscrepancyRecord(
            discrepancy_code="DEP_DISCREPANCY",
            title="Two-Side Deputation Discrepancy",
            description=f"Receiving Mandal raised discrepancy for {posting.employee_id}: {payload.remarks}",
            severity="CRITICAL",
            employee_id=posting.employee_id,
            gp_lgd=posting.actual_working_gp_lgd,
            mandal_id=verif.salary_mandal_id,
            status="OPEN",
            assigned_to_mandal_id=verif.salary_mandal_id,
            detected_at=now
        )
        db.add(disc)
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use CONFIRM, REJECT, or DISCREPANCY.")
        
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=current_user.mandal_id,
        action="VERIFY_DEPUTATION",
        entity_type="POSTING",
        entity_id=str(posting.id),
        details=f"Deputation action {action} by {current_user.username}. Remarks: {payload.remarks}",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {"message": f"Deputation verification updated to {action}", "status": verif.status}
