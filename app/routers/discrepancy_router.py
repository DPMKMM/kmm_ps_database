from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import (
    DiscrepancyRecord, GramPanchayat, Mandal, Employee, EmployeePosting,
    EmployeeStatusHistory, EmployeeSalaryMapping, DuplicateValidationLog, User, AuditLog
)
from app.schemas import DiscrepancyResolveAction
from app.auth import get_current_user, require_super_admin

router = APIRouter(prefix="/api/discrepancies", tags=["Discrepancy Detection & Management"])

@router.get("/scan")
def run_discrepancy_scan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    SECTION 15: DISCREPANCY DETECTION MODULE
    Runs real-time rule engine across all 571 GPs and employees.
    """
    now = datetime.utcnow()
    today = date.today()
    discrepancies_found = []
    
    # Rule 1: Clear Vacancy marked but has active salary employee mapped
    vacant_gps = db.query(GramPanchayat).filter(GramPanchayat.is_clear_vacancy == True).all()
    for gp in vacant_gps:
        active_emp = db.query(EmployeeSalaryMapping).filter(
            EmployeeSalaryMapping.salary_gp_lgd == gp.lgd_code,
            EmployeeSalaryMapping.is_active == True
        ).first()
        if active_emp:
            discrepancies_found.append({
                "code": "VACANCY_WITH_ACTIVE_EMP",
                "title": "Clear Vacancy Conflict",
                "description": f"GP {gp.gp_name} (LGD: {gp.lgd_code}) is marked as Clear Vacancy, but employee {active_emp.employee_id} is drawing salary from it.",
                "severity": "CRITICAL",
                "employee_id": active_emp.employee_id,
                "gp_lgd": gp.lgd_code,
                "mandal_id": gp.mandal_id
            })

    # Rule 2: Expected Joining Date Crossed without status update
    # Section 13: "When an expected return date passes, do not automatically mark the employee as Working. Display: STATUS UPDATE REQUIRED – VERIFY ACTUAL EMPLOYEE STATUS."
    statuses_with_exp_date = db.query(EmployeeStatusHistory).filter(
        EmployeeStatusHistory.is_current == True,
        EmployeeStatusHistory.expected_joining_date != None,
        EmployeeStatusHistory.expected_joining_date < today,
        EmployeeStatusHistory.service_status != "WORKING"
    ).all()
    for st in statuses_with_exp_date:
        salary_m = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == st.employee_id, EmployeeSalaryMapping.is_active == True).first()
        discrepancies_found.append({
            "code": "EXP_DATE_PASSED",
            "title": "Expected Joining Date Crossed – Status Update Required",
            "description": f"Employee {st.employee_id} expected return date ({st.expected_joining_date}) has passed. STATUS UPDATE REQUIRED – VERIFY ACTUAL EMPLOYEE STATUS.",
            "severity": "HIGH",
            "employee_id": st.employee_id,
            "gp_lgd": salary_m.salary_gp_lgd if salary_m else None,
            "mandal_id": salary_m.salary_mandal_id if salary_m else None
        })

    # Rule 3: Deputation end date passed (Expired Deputation Order)
    expired_postings = db.query(EmployeePosting).filter(
        EmployeePosting.is_current == True,
        EmployeePosting.is_working_in_salary_gp == False,
        EmployeePosting.deputation_end_date != None,
        EmployeePosting.deputation_end_date < today
    ).all()
    for ep in expired_postings:
        salary_m = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == ep.employee_id, EmployeeSalaryMapping.is_active == True).first()
        discrepancies_found.append({
            "code": "DEP_ORDER_EXPIRED",
            "title": "Expired Deputation Order",
            "description": f"Deputation order for employee {ep.employee_id} expired on {ep.deputation_end_date}. Fresh posting order or return to salary GP required.",
            "severity": "HIGH",
            "employee_id": ep.employee_id,
            "gp_lgd": ep.actual_working_gp_lgd,
            "mandal_id": salary_m.salary_mandal_id if salary_m else None
        })

    # Rule 4: Deputation out without receiving GP confirmation (Two-side unverified)
    unconfirmed_deps = db.query(EmployeePosting).filter(
        EmployeePosting.is_current == True,
        EmployeePosting.is_working_in_salary_gp == False,
        EmployeePosting.posting_type.in_(["WITHIN_MANDAL", "ANOTHER_MANDAL"]),
        EmployeePosting.verification_status.in_(["PENDING", "REJECTED", "DISCREPANCY"])
    ).all()
    for ud in unconfirmed_deps:
        salary_m = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == ud.employee_id, EmployeeSalaryMapping.is_active == True).first()
        discrepancies_found.append({
            "code": "DEP_UNVERIFIED",
            "title": f"Deputation Status: {ud.verification_status}",
            "description": f"Employee {ud.employee_id} deputation to GP {ud.actual_working_gp_lgd} has status {ud.verification_status} by receiving Mandal.",
            "severity": "CRITICAL" if ud.verification_status in ["REJECTED", "DISCREPANCY"] else "PENDING_VERIFICATION",
            "employee_id": ud.employee_id,
            "gp_lgd": ud.actual_working_gp_lgd,
            "mandal_id": ud.actual_working_mandal_id
        })

    # Rule 5: Suspended employee without suspension order number
    suspended_no_order = db.query(EmployeeStatusHistory).filter(
        EmployeeStatusHistory.is_current == True,
        EmployeeStatusHistory.service_status == "SUSPENDED",
        (EmployeeStatusHistory.suspension_order_no == None) | (EmployeeStatusHistory.suspension_order_no == "")
    ).all()
    for sn in suspended_no_order:
        salary_m = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == sn.employee_id, EmployeeSalaryMapping.is_active == True).first()
        discrepancies_found.append({
            "code": "SUSPENDED_NO_ORDER",
            "title": "Suspended Employee Without Proceedings",
            "description": f"Employee {sn.employee_id} is recorded as Suspended without official Suspension Order number.",
            "severity": "HIGH",
            "employee_id": sn.employee_id,
            "gp_lgd": salary_m.salary_gp_lgd if salary_m else None,
            "mandal_id": salary_m.salary_mandal_id if salary_m else None
        })

    # Rule 6: Absconding case without disciplinary inquiry initiated
    absconding_no_inq = db.query(EmployeeStatusHistory).filter(
        EmployeeStatusHistory.is_current == True,
        EmployeeStatusHistory.service_status == "ABSCONDING",
        EmployeeStatusHistory.disciplinary_initiated == False
    ).all()
    for ab in absconding_no_inq:
        salary_m = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == ab.employee_id, EmployeeSalaryMapping.is_active == True).first()
        discrepancies_found.append({
            "code": "ABSCONDING_NO_INQUIRY",
            "title": "Absconding Employee – Disciplinary Action Pending",
            "description": f"Employee {ab.employee_id} is absconding but disciplinary proceedings have not been initiated.",
            "severity": "HIGH",
            "employee_id": ab.employee_id,
            "gp_lgd": salary_m.salary_gp_lgd if salary_m else None,
            "mandal_id": salary_m.salary_mandal_id if salary_m else None
        })

    # Rule 7: Other District Deputation without external destination details
    other_dist_missing = db.query(EmployeePosting).filter(
        EmployeePosting.is_current == True,
        EmployeePosting.posting_type == "OTHER_DISTRICT",
        (EmployeePosting.external_district_name == None) | (EmployeePosting.external_district_name == "")
    ).all()
    for od in other_dist_missing:
        salary_m = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == od.employee_id, EmployeeSalaryMapping.is_active == True).first()
        discrepancies_found.append({
            "code": "OTHER_DIST_INCOMPLETE",
            "title": "Inter-District Deputation Missing Destination",
            "description": f"Employee {od.employee_id} is deputed to other district but destination details are missing.",
            "severity": "MEDIUM",
            "employee_id": od.employee_id,
            "gp_lgd": salary_m.salary_gp_lgd if salary_m else None,
            "mandal_id": salary_m.salary_mandal_id if salary_m else None
        })

    # Sync into discrepancy_records table (avoid duplicating open records)
    for d in discrepancies_found:
        existing_rec = db.query(DiscrepancyRecord).filter(
            DiscrepancyRecord.discrepancy_code == d["code"],
            DiscrepancyRecord.employee_id == d["employee_id"],
            DiscrepancyRecord.status.in_(["OPEN", "ASSIGNED"])
        ).first()
        
        if not existing_rec:
            new_rec = DiscrepancyRecord(
                discrepancy_code=d["code"],
                title=d["title"],
                description=d["description"],
                severity=d["severity"],
                employee_id=d["employee_id"],
                gp_lgd=d["gp_lgd"],
                mandal_id=d["mandal_id"],
                status="OPEN",
                assigned_to_mandal_id=d["mandal_id"],
                detected_at=now
            )
            db.add(new_rec)
            
    db.commit()

    visible_items = (
        [d for d in discrepancies_found if d.get("mandal_id") == current_user.mandal_id]
        if current_user.role == "MANDAL_ADMIN"
        else discrepancies_found
    )

    return {
        "status": "Scan completed",
        "total_discrepancies_detected": len(visible_items),
        "items": visible_items
    }

@router.get("")
def list_discrepancies(
    severity: Optional[str] = None,
    status: Optional[str] = None,
    mandal_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(DiscrepancyRecord)
    
    if current_user.role == "MANDAL_ADMIN":
        query = query.filter(
            (DiscrepancyRecord.assigned_to_mandal_id == current_user.mandal_id) |
            (DiscrepancyRecord.mandal_id == current_user.mandal_id)
        )
    elif mandal_id:
        query = query.filter(
            (DiscrepancyRecord.assigned_to_mandal_id == mandal_id) |
            (DiscrepancyRecord.mandal_id == mandal_id)
        )
        
    if severity:
        query = query.filter(DiscrepancyRecord.severity == severity)
        
    if status:
        query = query.filter(DiscrepancyRecord.status == status)
        
    records = query.order_by(DiscrepancyRecord.detected_at.desc()).all()
    
    results = []
    for r in records:
        mandal_obj = db.query(Mandal).filter(Mandal.id == r.mandal_id).first() if r.mandal_id else None
        gp_obj = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == r.gp_lgd).first() if r.gp_lgd else None
        results.append({
            "id": r.id,
            "discrepancy_code": r.discrepancy_code,
            "title": r.title,
            "description": r.description,
            "severity": r.severity,
            "employee_id": r.employee_id,
            "gp_lgd": r.gp_lgd,
            "gp_name": gp_obj.gp_name if gp_obj else None,
            "mandal_id": r.mandal_id,
            "mandal_name": mandal_obj.mandal_name if mandal_obj else None,
            "status": r.status,
            "resolution_remarks": r.resolution_remarks,
            "resolved_by": r.resolved_by,
            "detected_at": r.detected_at.strftime("%Y-%m-%d %H:%M") if r.detected_at else "",
            "resolved_at": r.resolved_at.strftime("%Y-%m-%d %H:%M") if r.resolved_at else None
        })
        
    return results

@router.post("/{discrepancy_id}/resolve")
def resolve_discrepancy(
    discrepancy_id: int,
    payload: DiscrepancyResolveAction,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rec = db.query(DiscrepancyRecord).filter(DiscrepancyRecord.id == discrepancy_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Discrepancy record not found")
        
    if current_user.role == "MANDAL_ADMIN":
        if rec.assigned_to_mandal_id != current_user.mandal_id and rec.mandal_id != current_user.mandal_id:
            raise HTTPException(status_code=403, detail="Not authorized to resolve discrepancy for another Mandal")
            
    now = datetime.utcnow()
    rec.status = payload.new_status
    rec.resolution_remarks = payload.resolution_remarks
    rec.resolved_by = f"{current_user.username} ({current_user.display_name})"
    rec.resolved_at = now
    
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=current_user.mandal_id,
        action="RESOLVE_DISCREPANCY",
        entity_type="DISCREPANCY",
        entity_id=str(rec.id),
        details=f"Resolved discrepancy {rec.title}: {payload.resolution_remarks}",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Discrepancy marked as resolved", "status": rec.status}
