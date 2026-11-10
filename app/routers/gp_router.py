from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, String

from app.database import get_db
from app.models import Mandal, GramPanchayat, EmployeeSalaryMapping, EmployeePosting, EmployeeStatusHistory, User
from app.schemas import GramPanchayatOut, MandalOut, ClearVacancyUpdate
from app.auth import get_current_user, require_super_admin, enforce_mandal_isolation

router = APIRouter(prefix="/api/panchayats", tags=["Gram Panchayats & Mandals"])

@router.get("/mandals", response_model=List[MandalOut])
def get_mandals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # If mandal user, can only list their own mandal if restricted, but seeing all mandal names for deputation is helpful
    query = db.query(Mandal).order_by(Mandal.mandal_name.asc())
    mandals = query.all()
    
    results = []
    for m in mandals:
        gp_count = db.query(func.count(GramPanchayat.id)).filter(GramPanchayat.mandal_id == m.id).scalar()
        results.append(MandalOut(
            id=m.id,
            mandal_name=m.mandal_name,
            mandal_lgd=m.mandal_lgd,
            district_name=m.district_name,
            district_lgd=m.district_lgd,
            total_gps=gp_count or 0
        ))
    return results

@router.get("", response_model=List[GramPanchayatOut])
def get_gram_panchayats(
    mandal_id: Optional[int] = None,
    mandal_lgd: Optional[int] = None,
    search: Optional[str] = None,
    for_salary_entry: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(GramPanchayat)
    
    # Strict backend enforcement:
    # If user is a MANDAL_ADMIN and requesting GPs for salary claiming, force filter to their own Mandal!
    if current_user.role == "MANDAL_ADMIN" and (for_salary_entry or mandal_id is None):
        query = query.filter(GramPanchayat.mandal_id == current_user.mandal_id)
    elif mandal_id:
        query = query.filter(GramPanchayat.mandal_id == mandal_id)
    elif mandal_lgd:
        query = query.filter(GramPanchayat.mandal_lgd == mandal_lgd)
        
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (GramPanchayat.gp_name.ilike(s)) | 
            (cast(GramPanchayat.lgd_code, String).ilike(s))
        )
        
    gps = query.order_by(GramPanchayat.gp_name.asc()).all()
    return gps

@router.get("/all-centralized", response_model=List[GramPanchayatOut])
def get_all_centralized_panchayats(
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Centralized master lookup of all 571 GPs for Deputation Destination selection
    accessible to all authorized users across Khammam District.
    """
    query = db.query(GramPanchayat)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (GramPanchayat.gp_name.ilike(s)) | 
            (GramPanchayat.mandal_name.ilike(s)) |
            (cast(GramPanchayat.lgd_code, String).ilike(s))
        )
    return query.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).all()

@router.get("/{lgd_code}")
def get_gram_panchayat_detail(
    lgd_code: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == lgd_code).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gram Panchayat not found")
        
    # Find employees drawing salary from this GP
    salary_employees = (
        db.query(EmployeeSalaryMapping)
        .filter(EmployeeSalaryMapping.salary_gp_lgd == lgd_code, EmployeeSalaryMapping.is_active == True)
        .all()
    )
    
    # Find employees actually working in this GP
    working_postings = (
        db.query(EmployeePosting)
        .filter(EmployeePosting.actual_working_gp_lgd == lgd_code, EmployeePosting.is_current == True)
        .all()
    )
    
    # Compile employee details
    salary_staff = []
    for sm in salary_employees:
        emp = sm.employee
        posting = db.query(EmployeePosting).filter(EmployeePosting.employee_id == emp.employee_id, EmployeePosting.is_current == True).first()
        status_rec = db.query(EmployeeStatusHistory).filter(EmployeeStatusHistory.employee_id == emp.employee_id, EmployeeStatusHistory.is_current == True).first()
        
        salary_staff.append({
            "employee_id": emp.employee_id,
            "name_ifmis": emp.name_ifmis,
            "is_working_here": posting.actual_working_gp_lgd == lgd_code if posting else False,
            "posting_type": posting.posting_type if posting else "UNKNOWN",
            "actual_working_gp_name": posting.working_panchayat.gp_name if posting and posting.working_panchayat else (posting.external_gp_or_office_name if posting else "N/A"),
            "actual_working_mandal": posting.working_panchayat.mandal_name if posting and posting.working_panchayat else (posting.external_mandal_name if posting else "N/A"),
            "service_status": status_rec.service_status if status_rec else "WORKING",
            "verification_status": posting.verification_status if posting else "PENDING"
        })
        
    working_staff = []
    for wp in working_postings:
        emp = wp.employee
        sm = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == emp.employee_id, EmployeeSalaryMapping.is_active == True).first()
        status_rec = db.query(EmployeeStatusHistory).filter(EmployeeStatusHistory.employee_id == emp.employee_id, EmployeeStatusHistory.is_current == True).first()
        
        working_staff.append({
            "employee_id": emp.employee_id,
            "name_ifmis": emp.name_ifmis,
            "salary_gp_lgd": sm.salary_gp_lgd if sm else None,
            "salary_gp_name": sm.panchayat.gp_name if sm and sm.panchayat else "N/A",
            "salary_mandal_name": sm.panchayat.mandal_name if sm and sm.panchayat else "N/A",
            "posting_type": wp.posting_type,
            "service_status": status_rec.service_status if status_rec else "WORKING",
            "verification_status": wp.verification_status
        })

    return {
        "gp": {
            "lgd_code": gp.lgd_code,
            "gp_name": gp.gp_name,
            "mandal_id": gp.mandal_id,
            "mandal_lgd": gp.mandal_lgd,
            "mandal_name": gp.mandal_name,
            "is_clear_vacancy": gp.is_clear_vacancy,
            "vacancy_remarks": gp.vacancy_remarks,
            "vacancy_updated_at": gp.vacancy_updated_at.strftime("%Y-%m-%d %H:%M") if gp.vacancy_updated_at else None,
            "vacancy_updated_by": gp.vacancy_updated_by
        },
        "salary_claiming_employees": salary_staff,
        "actually_working_employees": working_staff,
        "salary_strength": len(salary_staff),
        "actual_working_strength": len([w for w in working_staff if w["service_status"] == "WORKING"])
    }

@router.post("/{lgd_code}/vacancy")
def update_clear_vacancy(
    lgd_code: int,
    payload: ClearVacancyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == lgd_code).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gram Panchayat not found")
        
    enforce_mandal_isolation(current_user, gp.mandal_id)
    
    # If marking as clear vacancy, check if an active working employee is mapped to it
    if payload.is_clear_vacancy:
        active_emp = db.query(EmployeeSalaryMapping).filter(
            EmployeeSalaryMapping.salary_gp_lgd == lgd_code,
            EmployeeSalaryMapping.is_active == True
        ).first()
        if active_emp:
            # We don't block outright if user specifically wants to register vacancy, but record remarks
            pass

    gp.is_clear_vacancy = payload.is_clear_vacancy
    gp.vacancy_remarks = payload.vacancy_remarks
    gp.vacancy_updated_at = datetime.utcnow()
    gp.vacancy_updated_by = f"{current_user.username} ({current_user.display_name})"
    db.commit()
    
    return {
        "message": f"Vacancy status for {gp.gp_name} updated successfully",
        "is_clear_vacancy": gp.is_clear_vacancy
    }
