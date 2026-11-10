from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models import (
    Employee, EmployeeSalaryMapping, EmployeePosting, EmployeeStatusHistory,
    GramPanchayat, Mandal, User, DuplicateValidationLog, AuditLog, GPVerification, DiscrepancyRecord,
    InternalReassignment
)
from app.schemas import (
    EmployeeCreateRequest, EmployeeUpdateRequest, GlobalDuplicateCheckResult,
    EmployeeStage1Create, EmployeeStage2SalaryMapping, EmployeeStage3WorkingMapping,
    InternalReassignmentCreate
)
from app.auth import get_current_user, require_super_admin, enforce_mandal_isolation

router = APIRouter(prefix="/api/employees", tags=["Employee Management"])

@router.get("/check-id", response_model=GlobalDuplicateCheckResult)
def check_employee_id(
    employee_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    SECTION 7: GLOBAL EMPLOYEE ID DUPLICATE VALIDATION
    Immediately search the complete district employee database across all 20 Mandals.
    """
    emp_id = employee_id.strip()
    existing = db.query(Employee).filter(func.lower(Employee.employee_id) == emp_id.lower()).first()
    
    if not existing:
        return GlobalDuplicateCheckResult(
            is_duplicate=False,
            message="Employee ID is available for registration"
        )
        
    # Employee exists - retrieve their details
    salary_map = (
        db.query(EmployeeSalaryMapping)
        .filter(EmployeeSalaryMapping.employee_id == existing.employee_id, EmployeeSalaryMapping.is_active == True)
        .first()
    )
    posting = (
        db.query(EmployeePosting)
        .filter(EmployeePosting.employee_id == existing.employee_id, EmployeePosting.is_current == True)
        .first()
    )
    status_rec = (
        db.query(EmployeeStatusHistory)
        .filter(EmployeeStatusHistory.employee_id == existing.employee_id, EmployeeStatusHistory.is_current == True)
        .first()
    )
    
    # Audit log duplicate attempt
    client_ip = request.client.host if request.client else "127.0.0.1"
    existing_mandal_id = salary_map.salary_mandal_id if salary_map else None
    
    dup_log = DuplicateValidationLog(
        attempted_employee_id=existing.employee_id,
        attempting_user=current_user.username,
        attempting_mandal_id=current_user.mandal_id,
        existing_mandal_id=existing_mandal_id,
        ip_address=client_ip,
        timestamp=datetime.utcnow()
    )
    db.add(dup_log)
    db.commit()
    
    # Prepare non-sensitive existing record details (DOB strictly excluded as per Section 7 specs)
    salary_gp_name = salary_map.panchayat.gp_name if salary_map and salary_map.panchayat else "Unknown"
    salary_mandal_name = salary_map.panchayat.mandal_name if salary_map and salary_map.panchayat else "Unknown"
    
    if posting:
        if posting.posting_type == "OTHER_DISTRICT":
            working_gp_name = f"{posting.external_gp_or_office_name or 'External Office'} ({posting.external_district_name} District)"
            working_mandal_name = posting.external_mandal_name or "N/A"
        elif posting.posting_type == "OTHER_DEPARTMENT":
            working_gp_name = f"{posting.external_department_name or 'Other Department'} ({posting.external_gp_or_office_name or 'Office'})"
            working_mandal_name = "Other Department"
        else:
            working_gp_name = posting.working_panchayat.gp_name if posting.working_panchayat else "N/A"
            working_mandal_name = posting.working_panchayat.mandal_name if posting.working_panchayat else "N/A"
    else:
        working_gp_name = salary_gp_name
        working_mandal_name = salary_mandal_name
        
    existing_info = {
        "employee_id": existing.employee_id,
        "name_ifmis": existing.name_ifmis,
        "mobile_number": existing.mobile_number or "N/A",
        "salary_gp_name": salary_gp_name,
        "salary_mandal_name": salary_mandal_name,
        "current_working_gp": working_gp_name,
        "current_working_mandal": working_mandal_name,
        "service_status": status_rec.service_status if status_rec else "WORKING",
        "deputation_status": posting.posting_type if posting else "OWN_GP",
        "verification_status": posting.verification_status if posting else "PENDING"
    }
    
    return GlobalDuplicateCheckResult(
        is_duplicate=True,
        message="EMPLOYEE ALREADY EXISTS! This Employee ID is already registered in Details of Panchayat Secretaries Working in Khammam District. Duplicate employee registration is not permitted.",
        existing_record=existing_info
    )

@router.post("", status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp_id = payload.employee_id.strip()
    
    # 1. Global Employee ID Duplicate Validation
    existing = db.query(Employee).filter(func.lower(Employee.employee_id) == emp_id.lower()).first()
    if existing:
        # Log duplicate attempt
        client_ip = request.client.host if request.client else "127.0.0.1"
        dup_log = DuplicateValidationLog(
            attempted_employee_id=emp_id,
            attempting_user=current_user.username,
            attempting_mandal_id=current_user.mandal_id,
            ip_address=client_ip,
            timestamp=datetime.utcnow()
        )
        db.add(dup_log)
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"EMPLOYEE ALREADY EXISTS! Employee ID {emp_id} is already registered in the district database. Duplicate employee registration is strictly prohibited."
        )

    # 2. Validate Salary Claiming GP
    salary_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == payload.salary_gp_lgd).first()
    if not salary_gp:
        raise HTTPException(status_code=400, detail="Invalid Salary Claiming Gram Panchayat LGD Code")
        
    # Enforce Mandal isolation: Salary GP must belong to logged in Mandal
    enforce_mandal_isolation(current_user, salary_gp.mandal_id)
    
    now = datetime.utcnow()
    
    # 3. Create Employee
    new_employee = Employee(
        employee_id=emp_id,
        name_ifmis=payload.name_ifmis.strip(),
        dob=payload.dob,
        mobile_number=payload.mobile_number.strip() if payload.mobile_number else None,
        created_by=current_user.username,
        created_at=now,
        is_active=True
    )
    db.add(new_employee)
    db.flush()
    
    # 4. Create Salary Mapping
    salary_mapping = EmployeeSalaryMapping(
        employee_id=emp_id,
        salary_gp_lgd=salary_gp.lgd_code,
        salary_mandal_id=salary_gp.mandal_id,
        effective_from=payload.status_effective_from or date.today(),
        is_active=True,
        created_by=current_user.username,
        created_at=now
    )
    db.add(salary_mapping)
    
    # 5. Handle Posting & Deputation logic
    if payload.is_working_in_salary_gp:
        posting_type = "OWN_GP"
        act_working_gp_lgd = salary_gp.lgd_code
        act_working_mandal_id = salary_gp.mandal_id
        ext_dist = None
        ext_mandal = None
        ext_office = None
        ext_dept = None
        ext_lgd = None
        ext_addr = None
        verif_status = "VERIFIED_BOTH"
    else:
        posting_type = payload.posting_type or "WITHIN_MANDAL"
        if posting_type == "OTHER_DISTRICT":
            if not payload.external_district_name:
                raise HTTPException(status_code=400, detail="District Name is mandatory for Other District deputation")
            act_working_gp_lgd = None
            act_working_mandal_id = None
            ext_dist = payload.external_district_name.strip()
            ext_mandal = payload.external_mandal_name.strip() if payload.external_mandal_name else None
            ext_office = payload.external_gp_or_office_name.strip() if payload.external_gp_or_office_name else None
            ext_dept = None
            ext_lgd = payload.external_lgd_code
            ext_addr = payload.external_address
            verif_status = "VERIFIED_SALARY_GP"
        elif posting_type == "OTHER_DEPARTMENT":
            if not payload.external_department_name:
                raise HTTPException(status_code=400, detail="Department Name is mandatory for Other Department deputation")
            act_working_gp_lgd = None
            act_working_mandal_id = None
            ext_dist = payload.external_district_name.strip() if payload.external_district_name else "Telangana"
            ext_mandal = None
            ext_office = payload.external_gp_or_office_name.strip() if payload.external_gp_or_office_name else None
            ext_dept = payload.external_department_name.strip()
            ext_lgd = None
            ext_addr = payload.external_address
            verif_status = "VERIFIED_SALARY_GP"
        else:
            # Within same mandal or another mandal in Khammam
            if not payload.actual_working_gp_lgd:
                raise HTTPException(status_code=400, detail="Please select destination working Gram Panchayat for deputation")
            target_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == payload.actual_working_gp_lgd).first()
            if not target_gp:
                raise HTTPException(status_code=400, detail="Invalid destination Gram Panchayat LGD Code")
            act_working_gp_lgd = target_gp.lgd_code
            act_working_mandal_id = target_gp.mandal_id
            ext_dist = None
            ext_mandal = None
            ext_office = None
            ext_dept = None
            ext_lgd = None
            ext_addr = None
            # Deputations in district start as PENDING receiving confirmation (Section 14)
            verif_status = "PENDING"
            
    new_posting = EmployeePosting(
        employee_id=emp_id,
        is_working_in_salary_gp=payload.is_working_in_salary_gp,
        posting_type=posting_type,
        actual_working_gp_lgd=act_working_gp_lgd,
        actual_working_mandal_id=act_working_mandal_id,
        external_district_name=ext_dist,
        external_mandal_name=ext_mandal,
        external_gp_or_office_name=ext_office,
        external_department_name=ext_dept,
        external_lgd_code=ext_lgd,
        external_address=ext_addr,
        deputation_order_no=payload.deputation_order_no,
        deputation_order_date=payload.deputation_order_date,
        deputation_effective_from=payload.deputation_effective_from,
        deputation_end_date=payload.deputation_end_date,
        remarks=payload.deputation_remarks,
        verification_status=verif_status,
        is_current=True,
        updated_by=current_user.username,
        created_at=now,
        updated_at=now
    )
    db.add(new_posting)
    db.flush()
    
    # 6. Create GP Verification request if deputed inside district
    if not payload.is_working_in_salary_gp and posting_type not in ("OTHER_DISTRICT", "OTHER_DEPARTMENT"):
        gp_verif = GPVerification(
            posting_id=new_posting.id,
            employee_id=emp_id,
            salary_mandal_id=salary_gp.mandal_id,
            receiving_mandal_id=act_working_mandal_id,
            status="PENDING"
        )
        db.add(gp_verif)
        
    # 7. Create Status History record
    status_entry = EmployeeStatusHistory(
        employee_id=emp_id,
        service_status=payload.service_status,
        status_effective_from=payload.status_effective_from,
        status_end_date=payload.status_end_date,
        expected_joining_date=payload.expected_joining_date,
        actual_joining_date=payload.actual_joining_date,
        proceedings_order_no=payload.proceedings_order_no,
        proceedings_order_date=payload.proceedings_order_date,
        suspension_order_no=payload.suspension_order_no,
        suspension_order_date=payload.suspension_order_date,
        suspension_effective_date=payload.suspension_effective_date,
        revocation_order_no=payload.revocation_order_no,
        revocation_effective_date=payload.revocation_effective_date,
        last_working_date=payload.last_working_date,
        date_of_absence=payload.date_of_absence,
        disciplinary_initiated=payload.disciplinary_initiated,
        leave_start_date=payload.leave_start_date,
        expected_return_date=payload.expected_return_date,
        leave_approval_details=payload.leave_approval_details,
        leave_proceedings_no=payload.leave_proceedings_no,
        reason_remarks=payload.reason_remarks,
        is_current=True,
        updated_by=current_user.username,
        updated_at=now
    )
    db.add(status_entry)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=current_user.mandal_id,
        action="CREATE_EMPLOYEE",
        entity_type="EMPLOYEE",
        entity_id=emp_id,
        details=f"Created employee {payload.name_ifmis} for GP {salary_gp.gp_name} (LGD: {salary_gp.lgd_code})",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": f"Panchayat Secretary {payload.name_ifmis} ({emp_id}) registered successfully",
        "employee_id": emp_id
    }

@router.get("")
def list_employees(
    search: Optional[str] = None,
    mandal_id: Optional[int] = None,
    gp_lgd: Optional[int] = None,
    service_status: Optional[str] = None,
    posting_type: Optional[str] = None,
    verification_status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = (
        db.query(
            Employee,
            EmployeeSalaryMapping,
            EmployeePosting,
            EmployeeStatusHistory,
            GramPanchayat
        )
        .join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == Employee.employee_id)
        .join(GramPanchayat, GramPanchayat.lgd_code == EmployeeSalaryMapping.salary_gp_lgd)
        .outerjoin(EmployeePosting, (EmployeePosting.employee_id == Employee.employee_id) & (EmployeePosting.is_current == True))
        .outerjoin(EmployeeStatusHistory, (EmployeeStatusHistory.employee_id == Employee.employee_id) & (EmployeeStatusHistory.is_current == True))
        .filter(EmployeeSalaryMapping.is_active == True)
    )
    
    # Strict Mandal isolation for MANDAL_ADMIN:
    # Mandal admin can view employees who draw salary from their Mandal, OR are deputed into their Mandal!
    if current_user.role == "MANDAL_ADMIN":
        query = query.filter(
            or_(
                EmployeeSalaryMapping.salary_mandal_id == current_user.mandal_id,
                EmployeePosting.actual_working_mandal_id == current_user.mandal_id
            )
        )
    elif mandal_id:
        query = query.filter(
            or_(
                EmployeeSalaryMapping.salary_mandal_id == mandal_id,
                EmployeePosting.actual_working_mandal_id == mandal_id
            )
        )
        
    if gp_lgd:
        query = query.filter(
            or_(
                EmployeeSalaryMapping.salary_gp_lgd == gp_lgd,
                EmployeePosting.actual_working_gp_lgd == gp_lgd
            )
        )
        
    if service_status:
        query = query.filter(EmployeeStatusHistory.service_status == service_status)
        
    if posting_type:
        query = query.filter(EmployeePosting.posting_type == posting_type)
        
    if verification_status:
        query = query.filter(EmployeePosting.verification_status == verification_status)
        
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Employee.employee_id.ilike(s),
                Employee.name_ifmis.ilike(s),
                GramPanchayat.gp_name.ilike(s),
                GramPanchayat.mandal_name.ilike(s)
            )
        )
        
    total_count = query.count()
    records = query.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).offset(skip).limit(limit).all()
    
    results = []
    for emp, sm, post, st, gp in records:
        # Resolve working location
        if post:
            if post.posting_type == "OTHER_DISTRICT":
                working_gp_str = post.external_gp_or_office_name or "External Office"
                working_mandal_str = post.external_mandal_name or "N/A"
                working_district_str = post.external_district_name or "Other District"
            elif post.posting_type == "OTHER_DEPARTMENT":
                working_gp_str = post.external_department_name or "Other Department"
                working_mandal_str = post.external_gp_or_office_name or "N/A"
                working_district_str = post.external_district_name or "State Dept"
            else:
                working_gp_str = post.working_panchayat.gp_name if post.working_panchayat else gp.gp_name
                working_mandal_str = post.working_panchayat.mandal_name if post.working_panchayat else gp.mandal_name
                working_district_str = "Khammam"
        else:
            working_gp_str = gp.gp_name
            working_mandal_str = gp.mandal_name
            working_district_str = "Khammam"

        # Privacy protection: Only Super Admin and the employee's own salary Mandal user can see exact DOB
        can_view_dob = (current_user.role == "SUPER_ADMIN" or (current_user.role == "MANDAL_ADMIN" and current_user.mandal_id == sm.salary_mandal_id))
        
        results.append({
            "employee_id": emp.employee_id,
            "name_ifmis": emp.name_ifmis,
            "mobile_number": emp.mobile_number or "N/A",
            "dob": emp.dob.strftime("%Y-%m-%d") if can_view_dob and emp.dob else "Restricted",
            "salary_gp_lgd": sm.salary_gp_lgd,
            "salary_gp_name": gp.gp_name,
            "salary_mandal_id": sm.salary_mandal_id,
            "salary_mandal_name": gp.mandal_name,
            "is_working_in_salary_gp": post.is_working_in_salary_gp if post else True,
            "posting_type": post.posting_type if post else "OWN_GP",
            "actual_working_gp_lgd": post.actual_working_gp_lgd if post else sm.salary_gp_lgd,
            "actual_working_gp_name": working_gp_str,
            "actual_working_mandal_name": working_mandal_str,
            "actual_working_district": working_district_str,
            "service_status": st.service_status if st else "WORKING",
            "verification_status": post.verification_status if post else "PENDING",
            "deputation_order_no": post.deputation_order_no if post else None,
            "expected_joining_date": st.expected_joining_date.strftime("%Y-%m-%d") if st and st.expected_joining_date else None,
            "created_at": emp.created_at.strftime("%Y-%m-%d %H:%M") if emp.created_at else ""
        })
        
    return {
        "total": total_count,
        "items": results
    }

@router.get("/stage1-list")
def list_stage1_employees(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Employee).filter(Employee.is_active == True)
    if current_user.role == "MANDAL_ADMIN":
        query = query.filter(
            or_(
                Employee.registration_mandal_id == current_user.mandal_id,
                Employee.employee_id.in_(
                    db.query(EmployeeSalaryMapping.employee_id).filter(
                        EmployeeSalaryMapping.salary_mandal_id == current_user.mandal_id,
                        EmployeeSalaryMapping.is_active == True
                    )
                )
            )
        )
    emps = query.order_by(Employee.name_ifmis.asc()).all()
    
    results = []
    for e in emps:
        sm = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == e.employee_id, EmployeeSalaryMapping.is_active == True).first()
        p = db.query(EmployeePosting).filter(EmployeePosting.employee_id == e.employee_id, EmployeePosting.is_current == True).first()
        dob_str = "N/A"
        if e.dob:
            dob_str = e.dob.strftime("%Y-%m-%d") if hasattr(e.dob, "strftime") else str(e.dob)
        results.append({
            "employee_id": e.employee_id,
            "name_ifmis": e.name_ifmis,
            "mobile_number": e.mobile_number or "N/A",
            "dob": dob_str,
            "designation": e.designation or "Panchayat Secretary",
            "registration_mandal_id": e.registration_mandal_id,
            "registration_mandal_name": e.registration_mandal.mandal_name if e.registration_mandal else "N/A",
            "salary_mapped": sm is not None,
            "salary_gp_name": sm.panchayat.gp_name if sm and sm.panchayat else None,
            "working_mapped": p is not None,
            "working_gp_name": p.working_panchayat.gp_name if p and p.working_panchayat else (p.external_gp_or_office_name if p else None)
        })
    return results

@router.get("/dropdown-list")
def get_employees_dropdown(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Employee).filter(Employee.is_active == True)
    if current_user.role == "MANDAL_ADMIN":
        query = query.filter(
            or_(
                Employee.registration_mandal_id == current_user.mandal_id,
                Employee.employee_id.in_(
                    db.query(EmployeeSalaryMapping.employee_id).filter(
                        EmployeeSalaryMapping.salary_mandal_id == current_user.mandal_id,
                        EmployeeSalaryMapping.is_active == True
                    )
                )
            )
        )
    emps = query.order_by(Employee.name_ifmis.asc()).all()
    return [
        {
            "id": e.employee_id,
            "employee_id": e.employee_id,
            "name": e.name_ifmis,
            "name_ifmis": e.name_ifmis,
            "mobile": e.mobile_number or "",
            "mobile_number": e.mobile_number or "",
            "designation": e.designation or "Panchayat Secretary",
            "display_label": f"{e.name_ifmis} ({e.mobile_number or 'No Mobile'}) - {e.employee_id}"
        }
        for e in emps
    ]

@router.get("/{employee_id}")
def get_employee_profile(
    employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    salary_map = (
        db.query(EmployeeSalaryMapping)
        .filter(EmployeeSalaryMapping.employee_id == emp.employee_id, EmployeeSalaryMapping.is_active == True)
        .first()
    )
    
    if current_user.role == "MANDAL_ADMIN":
        # Check if salary or working in this mandal
        current_post = db.query(EmployeePosting).filter(EmployeePosting.employee_id == emp.employee_id, EmployeePosting.is_current == True).first()
        if salary_map and salary_map.salary_mandal_id != current_user.mandal_id:
            if not current_post or current_post.actual_working_mandal_id != current_user.mandal_id:
                raise HTTPException(status_code=403, detail="Access denied: Employee not assigned to your Mandal")

    # Postings history
    postings = (
        db.query(EmployeePosting)
        .filter(EmployeePosting.employee_id == emp.employee_id)
        .order_by(EmployeePosting.created_at.desc())
        .all()
    )
    
    # Status history
    statuses = (
        db.query(EmployeeStatusHistory)
        .filter(EmployeeStatusHistory.employee_id == emp.employee_id)
        .order_by(EmployeeStatusHistory.updated_at.desc())
        .all()
    )
    
    current_posting = next((p for p in postings if p.is_current), None)
    current_status = next((s for s in statuses if s.is_current), None)
    
    can_view_dob = (current_user.role == "SUPER_ADMIN" or (salary_map and current_user.mandal_id == salary_map.salary_mandal_id))
    
    posting_history_list = []
    for p in postings:
        if p.posting_type == "OTHER_DISTRICT":
            working_gp = p.external_gp_or_office_name or "External Office"
            working_mandal = p.external_mandal_name or "N/A"
        elif p.posting_type == "OTHER_DEPARTMENT":
            working_gp = p.external_department_name or "Other Department"
            working_mandal = p.external_gp_or_office_name or "N/A"
        else:
            working_gp = p.working_panchayat.gp_name if p.working_panchayat else "N/A"
            working_mandal = p.working_panchayat.mandal_name if p.working_panchayat else "N/A"
        posting_history_list.append({
            "id": p.id,
            "is_current": p.is_current,
            "posting_type": p.posting_type,
            "working_gp_name": working_gp,
            "working_mandal_name": working_mandal,
            "external_district": p.external_district_name,
            "external_department": p.external_department_name,
            "order_no": p.deputation_order_no,
            "order_date": p.deputation_order_date.strftime("%Y-%m-%d") if p.deputation_order_date else None,
            "effective_from": p.deputation_effective_from.strftime("%Y-%m-%d") if p.deputation_effective_from else None,
            "effective_to": p.deputation_end_date.strftime("%Y-%m-%d") if p.deputation_end_date else None,
            "verification_status": p.verification_status,
            "remarks": p.remarks,
            "updated_by": p.updated_by,
            "updated_at": p.updated_at.strftime("%Y-%m-%d %H:%M") if p.updated_at else ""
        })

    status_history_list = []
    for s in statuses:
        status_history_list.append({
            "id": s.id,
            "is_current": s.is_current,
            "service_status": s.service_status,
            "effective_from": s.status_effective_from.strftime("%Y-%m-%d") if s.status_effective_from else None,
            "end_date": s.status_end_date.strftime("%Y-%m-%d") if s.status_end_date else None,
            "expected_joining_date": s.expected_joining_date.strftime("%Y-%m-%d") if s.expected_joining_date else None,
            "actual_joining_date": s.actual_joining_date.strftime("%Y-%m-%d") if s.actual_joining_date else None,
            "proceedings_order_no": s.proceedings_order_no,
            "suspension_order_no": s.suspension_order_no,
            "suspension_date": s.suspension_order_date.strftime("%Y-%m-%d") if s.suspension_order_date else None,
            "revocation_order_no": s.revocation_order_no,
            "leave_start_date": s.leave_start_date.strftime("%Y-%m-%d") if s.leave_start_date else None,
            "expected_return_date": s.expected_return_date.strftime("%Y-%m-%d") if s.expected_return_date else None,
            "reason_remarks": s.reason_remarks,
            "updated_by": s.updated_by,
            "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M") if s.updated_at else ""
        })

    return {
        "employee_id": emp.employee_id,
        "name_ifmis": emp.name_ifmis,
        "mobile_number": emp.mobile_number or "N/A",
        "dob": emp.dob.strftime("%Y-%m-%d") if can_view_dob and emp.dob else "Restricted",
        "salary_gp_lgd": salary_map.salary_gp_lgd if salary_map else None,
        "salary_gp_name": salary_map.panchayat.gp_name if salary_map and salary_map.panchayat else "N/A",
        "salary_mandal_name": salary_map.panchayat.mandal_name if salary_map and salary_map.panchayat else "N/A",
        "current_posting": {
            "posting_type": current_posting.posting_type if current_posting else "OWN_GP",
            "is_working_in_salary_gp": current_posting.is_working_in_salary_gp if current_posting else True,
            "actual_working_gp_lgd": current_posting.actual_working_gp_lgd if current_posting else None,
            "actual_working_gp_name": current_posting.working_panchayat.gp_name if current_posting and current_posting.working_panchayat else (current_posting.external_gp_or_office_name if current_posting else "N/A"),
            "actual_working_mandal_name": current_posting.working_panchayat.mandal_name if current_posting and current_posting.working_panchayat else (current_posting.external_mandal_name if current_posting else "N/A"),
            "external_district_name": current_posting.external_district_name if current_posting else None,
            "verification_status": current_posting.verification_status if current_posting else "PENDING",
            "deputation_order_no": current_posting.deputation_order_no if current_posting else None,
            "deputation_order_date": current_posting.deputation_order_date.strftime("%Y-%m-%d") if current_posting and current_posting.deputation_order_date else None,
            "remarks": current_posting.remarks if current_posting else None
        },
        "current_service_status": {
            "service_status": current_status.service_status if current_status else "WORKING",
            "effective_from": current_status.status_effective_from.strftime("%Y-%m-%d") if current_status and current_status.status_effective_from else None,
            "expected_joining_date": current_status.expected_joining_date.strftime("%Y-%m-%d") if current_status and current_status.expected_joining_date else None,
            "proceedings_order_no": current_status.proceedings_order_no if current_status else None,
            "suspension_order_no": current_status.suspension_order_no if current_status else None,
            "reason_remarks": current_status.reason_remarks if current_status else None
        },
        "posting_history": posting_history_list,
        "status_history": status_history_list
    }

@router.put("/{employee_id}")
def update_employee(
    employee_id: str,
    payload: EmployeeUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    salary_map = (
        db.query(EmployeeSalaryMapping)
        .filter(EmployeeSalaryMapping.employee_id == emp.employee_id, EmployeeSalaryMapping.is_active == True)
        .first()
    )
    
    if current_user.role == "MANDAL_ADMIN" and salary_map:
        enforce_mandal_isolation(current_user, salary_map.salary_mandal_id)
        
    now = datetime.utcnow()
    
    # Update employee info
    if payload.name_ifmis:
        emp.name_ifmis = payload.name_ifmis.strip()
    if payload.mobile_number is not None:
        emp.mobile_number = payload.mobile_number.strip()
    if payload.dob and current_user.role == "SUPER_ADMIN":
        emp.dob = payload.dob
        
    # If service status is updating, preserve history (Section 16)
    if payload.service_status:
        # Mark previous status as not current
        db.query(EmployeeStatusHistory).filter(
            EmployeeStatusHistory.employee_id == emp.employee_id,
            EmployeeStatusHistory.is_current == True
        ).update({"is_current": False})
        
        new_status = EmployeeStatusHistory(
            employee_id=emp.employee_id,
            service_status=payload.service_status,
            status_effective_from=payload.status_effective_from,
            status_end_date=payload.status_end_date,
            expected_joining_date=payload.expected_joining_date,
            actual_joining_date=payload.actual_joining_date,
            proceedings_order_no=payload.proceedings_order_no,
            proceedings_order_date=payload.proceedings_order_date,
            suspension_order_no=payload.suspension_order_no,
            suspension_order_date=payload.suspension_order_date,
            suspension_effective_date=payload.suspension_effective_date,
            revocation_order_no=payload.revocation_order_no,
            revocation_effective_date=payload.revocation_effective_date,
            last_working_date=payload.last_working_date,
            date_of_absence=payload.date_of_absence,
            disciplinary_initiated=payload.disciplinary_initiated or False,
            leave_start_date=payload.leave_start_date,
            expected_return_date=payload.expected_return_date,
            leave_approval_details=payload.leave_approval_details,
            leave_proceedings_no=payload.leave_proceedings_no,
            reason_remarks=payload.reason_remarks,
            is_current=True,
            updated_by=current_user.username,
            updated_at=now
        )
        db.add(new_status)
        
    # If posting/deputation is changing, preserve history (Section 16)
    if payload.is_working_in_salary_gp is not None:
        db.query(EmployeePosting).filter(
            EmployeePosting.employee_id == emp.employee_id,
            EmployeePosting.is_current == True
        ).update({"is_current": False})
        
        if payload.is_working_in_salary_gp:
            p_type = "OWN_GP"
            act_gp = salary_map.salary_gp_lgd if salary_map else None
            act_mandal = salary_map.salary_mandal_id if salary_map else None
            ext_d = None
            ext_m = None
            ext_o = None
            v_status = "VERIFIED_BOTH"
        else:
            p_type = payload.posting_type or "WITHIN_MANDAL"
            if p_type == "OTHER_DISTRICT":
                act_gp = None
                act_mandal = None
                ext_d = payload.external_district_name
                ext_m = payload.external_mandal_name
                ext_o = payload.external_gp_or_office_name
                v_status = "VERIFIED_SALARY_GP"
            else:
                act_gp = payload.actual_working_gp_lgd
                w_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == act_gp).first() if act_gp else None
                act_mandal = w_gp.mandal_id if w_gp else None
                ext_d = None
                ext_m = None
                ext_o = None
                v_status = "PENDING"
                
        new_posting = EmployeePosting(
            employee_id=emp.employee_id,
            is_working_in_salary_gp=payload.is_working_in_salary_gp,
            posting_type=p_type,
            actual_working_gp_lgd=act_gp,
            actual_working_mandal_id=act_mandal,
            external_district_name=ext_d,
            external_mandal_name=ext_m,
            external_gp_or_office_name=ext_o,
            external_lgd_code=payload.external_lgd_code,
            external_address=payload.external_address,
            deputation_order_no=payload.deputation_order_no,
            deputation_order_date=payload.deputation_order_date,
            deputation_effective_from=payload.deputation_effective_from,
            deputation_end_date=payload.deputation_end_date,
            remarks=payload.deputation_remarks,
            verification_status=v_status,
            is_current=True,
            updated_by=current_user.username,
            created_at=now,
            updated_at=now
        )
        db.add(new_posting)
        db.flush()
        
        if not payload.is_working_in_salary_gp and p_type != "OTHER_DISTRICT":
            db.add(GPVerification(
                posting_id=new_posting.id,
                employee_id=emp.employee_id,
                salary_mandal_id=salary_map.salary_mandal_id if salary_map else 0,
                receiving_mandal_id=act_mandal,
                status="PENDING"
            ))

    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=current_user.mandal_id,
        action="UPDATE_EMPLOYEE",
        entity_type="EMPLOYEE",
        entity_id=emp.employee_id,
        details=f"Updated profile for employee {emp.name_ifmis} ({emp.employee_id})",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {"message": "Employee record updated successfully"}

# ==========================================
# STAGE 1: EMPLOYEE MASTER REGISTRATION
# ==========================================

@router.post("/stage1-register", status_code=status.HTTP_201_CREATED)
def stage1_register_employee(
    payload: EmployeeStage1Create,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp_id = payload.employee_id.strip()
    
    # 1. Immediate Global Duplicate Check across all 20 Mandals
    existing = db.query(Employee).filter(func.lower(Employee.employee_id) == emp_id.lower()).first()
    if existing:
        client_ip = request.client.host if request.client else "127.0.0.1"
        dup_log = DuplicateValidationLog(
            attempted_employee_id=emp_id,
            attempting_user=current_user.username,
            attempting_mandal_id=current_user.mandal_id,
            existing_mandal_id=existing.registration_mandal_id,
            ip_address=client_ip,
            timestamp=datetime.utcnow()
        )
        db.add(dup_log)
        db.commit()
        
        m_name = existing.registration_mandal.mandal_name if existing.registration_mandal else "another Mandal"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"EMPLOYEE ALREADY EXISTS! Employee ID '{emp_id}' is already registered under {m_name} ({existing.name_ifmis}). Duplicate registration is not permitted."
        )
        
    mandal_id = current_user.mandal_id if current_user.role == "MANDAL_ADMIN" else (payload.registration_mandal_id or current_user.mandal_id)
    now = datetime.utcnow()
    
    # Create permanent master record
    new_emp = Employee(
        employee_id=emp_id,
        name_ifmis=payload.name_ifmis.strip(),
        dob=payload.dob or date(1990, 1, 1),
        mobile_number=payload.mobile_number.strip() if payload.mobile_number else None,
        designation=payload.designation or "Panchayat Secretary",
        registration_mandal_id=mandal_id,
        created_by=current_user.username,
        created_at=now,
        is_active=True
    )
    db.add(new_emp)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=mandal_id,
        action="STAGE1_REGISTER_EMPLOYEE",
        entity_type="EMPLOYEE",
        entity_id=emp_id,
        details=f"Stage 1 Registration completed for {new_emp.name_ifmis} ({emp_id}) - Designation: {new_emp.designation}",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    db.refresh(new_emp)
    
    return {
        "message": f"Panchayat Secretary {new_emp.name_ifmis} successfully registered in Master Directory (Stage 1 Complete).",
        "employee_id": new_emp.employee_id,
        "name_ifmis": new_emp.name_ifmis,
        "mobile_number": new_emp.mobile_number,
        "designation": new_emp.designation
    }

# ==========================================
# STAGE 2: SALARY-CLAIMING GP MAPPING
# ==========================================

@router.post("/stage2-salary-mapping")
def stage2_map_salary_gp(
    payload: EmployeeStage2SalaryMapping,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.employee_id == payload.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found in Master Directory. Please register under Stage 1 first.")
        
    gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == payload.salary_gp_lgd).first()
    if not gp:
        raise HTTPException(status_code=400, detail="Invalid Gram Panchayat LGD Code.")
        
    enforce_mandal_isolation(current_user, gp.mandal_id)
    
    now = datetime.utcnow()
    work_from = payload.working_from_date or date.today()
    
    # Deactivate previous active salary mapping
    db.query(EmployeeSalaryMapping).filter(
        EmployeeSalaryMapping.employee_id == emp.employee_id,
        EmployeeSalaryMapping.is_active == True
    ).update({"is_active": False})
    
    new_sm = EmployeeSalaryMapping(
        employee_id=emp.employee_id,
        salary_gp_lgd=gp.lgd_code,
        salary_mandal_id=gp.mandal_id,
        salary_claiming_status=payload.salary_claiming_status,
        service_status=payload.service_status,
        effective_from=work_from,
        is_active=True,
        created_by=current_user.username,
        created_at=now
    )
    db.add(new_sm)
    
    # Update service status history
    db.query(EmployeeStatusHistory).filter(
        EmployeeStatusHistory.employee_id == emp.employee_id,
        EmployeeStatusHistory.is_current == True
    ).update({"is_current": False})
    
    status_effective_date = payload.status_order_date or work_from
    new_sh = EmployeeStatusHistory(
        employee_id=emp.employee_id,
        service_status=payload.service_status,
        status_effective_from=status_effective_date,
        proceedings_order_no=payload.status_order_no,
        proceedings_order_date=payload.status_order_date,
        reason_remarks=payload.remarks or payload.reason_remarks,
        is_current=True,
        updated_by=current_user.username,
        updated_at=now
    )
    if payload.service_status == "SUSPENDED":
        new_sh.suspension_order_no = payload.status_order_no
        new_sh.suspension_effective_date = status_effective_date
    db.add(new_sh)
    
    # Audit log
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=gp.mandal_id,
        action="STAGE2_SALARY_MAPPING",
        entity_type="SALARY_MAPPING",
        entity_id=emp.employee_id,
        details=f"Mapped salary for {emp.name_ifmis} to {gp.gp_name} (LGD: {gp.lgd_code}) - Status: {payload.service_status}",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": f"Salary-Claiming GP mapping saved for {emp.name_ifmis} -> {gp.gp_name} (Stage 2 Complete).",
        "employee_id": emp.employee_id,
        "salary_gp_name": gp.gp_name,
        "salary_mandal_name": gp.mandal_name,
        "service_status": payload.service_status
    }

# ==========================================
# STAGE 3: WORKING STATION & DEPUTATION MAPPING
# ==========================================

@router.get("/stage3-employee-info/{employee_id}")
def get_stage3_employee_info(
    employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    sm = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == emp.employee_id, EmployeeSalaryMapping.is_active == True).first()
    sh = db.query(EmployeeStatusHistory).filter(EmployeeStatusHistory.employee_id == emp.employee_id, EmployeeStatusHistory.is_current == True).first()
    p = db.query(EmployeePosting).filter(EmployeePosting.employee_id == emp.employee_id, EmployeePosting.is_current == True).first()
    
    salary_gp = sm.panchayat if sm else None
    
    return {
        "employee_id": emp.employee_id,
        "name_ifmis": emp.name_ifmis,
        "mobile_number": emp.mobile_number or "N/A",
        "salary_gp_lgd": sm.salary_gp_lgd if sm else None,
        "salary_gp_name": salary_gp.gp_name if salary_gp else "Not Mapped Yet (Stage 2 Pending)",
        "salary_mandal_id": sm.salary_mandal_id if sm else None,
        "salary_mandal_name": salary_gp.mandal_name if salary_gp else "N/A",
        "service_status": sh.service_status if sh else "WORKING",
        "current_posting": {
            "posting_id": p.id if p else None,
            "is_working_in_salary_gp": p.is_working_in_salary_gp if p else True,
            "posting_type": p.posting_type if p else "OWN_GP",
            "actual_working_gp_lgd": p.actual_working_gp_lgd if p else (sm.salary_gp_lgd if sm else None),
            "actual_working_gp_name": p.working_panchayat.gp_name if p and p.working_panchayat else (salary_gp.gp_name if salary_gp else None),
            "official_deputation_gp_lgd": p.official_deputation_gp_lgd if p else None,
            "has_internal_reassignment": p.has_internal_reassignment if p else False,
            "verification_status": p.verification_status if p else "PENDING"
        } if p else None
    }

@router.post("/stage3-working-mapping")
def stage3_map_working_station(
    payload: EmployeeStage3WorkingMapping,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.employee_id == payload.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
        
    sm = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == emp.employee_id, EmployeeSalaryMapping.is_active == True).first()
    if not sm:
        raise HTTPException(status_code=400, detail="Please complete Stage 2 (Salary GP Mapping) before mapping working station.")
        
    now = datetime.utcnow()
    
    # Deactivate previous active posting
    db.query(EmployeePosting).filter(
        EmployeePosting.employee_id == emp.employee_id,
        EmployeePosting.is_current == True
    ).update({"is_current": False})
    
    if payload.is_working_in_salary_gp:
        # Working in own salary GP
        posting_type = "OWN_GP"
        act_gp = sm.salary_gp_lgd
        act_mandal = sm.salary_mandal_id
        off_dep_gp = None
        off_dep_mandal = None
        ext_d = None
        ext_m = None
        ext_o = None
        ext_dept = None
        verif_status = "VERIFIED_BOTH"
    else:
        posting_type = payload.posting_type or "WITHIN_MANDAL"
        if posting_type == "OTHER_DISTRICT":
            act_gp = None
            act_mandal = None
            off_dep_gp = None
            off_dep_mandal = None
            ext_d = payload.external_district_name
            ext_m = payload.external_mandal_name
            ext_o = payload.external_gp_or_office_name
            ext_dept = None
            verif_status = "VERIFIED_SALARY_GP"
        elif posting_type == "OTHER_DEPARTMENT":
            act_gp = None
            act_mandal = None
            off_dep_gp = None
            off_dep_mandal = None
            ext_d = "Telangana"
            ext_m = None
            ext_o = payload.external_gp_or_office_name
            ext_dept = payload.external_department_name
            verif_status = "VERIFIED_SALARY_GP"
        else:
            # Within same mandal or another mandal
            dest_gp_lgd = payload.official_deputation_gp_lgd or payload.actual_working_gp_lgd
            if not dest_gp_lgd:
                raise HTTPException(status_code=400, detail="Destination Gram Panchayat is mandatory for deputation.")
            dest_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == dest_gp_lgd).first()
            if not dest_gp:
                raise HTTPException(status_code=400, detail="Invalid destination Gram Panchayat LGD Code.")
                
            act_gp = dest_gp.lgd_code
            act_mandal = dest_gp.mandal_id
            off_dep_gp = dest_gp.lgd_code
            off_dep_mandal = dest_gp.mandal_id
            ext_d = None
            ext_m = None
            ext_o = None
            ext_dept = None
            verif_status = "PENDING"
            
    new_posting = EmployeePosting(
        employee_id=emp.employee_id,
        is_working_in_salary_gp=payload.is_working_in_salary_gp,
        posting_type=posting_type,
        actual_working_gp_lgd=act_gp,
        actual_working_mandal_id=act_mandal,
        official_deputation_gp_lgd=off_dep_gp,
        official_deputation_mandal_id=off_dep_mandal,
        external_district_name=ext_d,
        external_mandal_name=ext_m,
        external_gp_or_office_name=ext_o,
        external_department_name=ext_dept,
        deputation_effective_from=payload.deputation_effective_from or date.today(),
        deputation_order_no=payload.deputation_order_no,
        deputation_order_date=payload.deputation_order_date,
        remarks=payload.remarks,
        verification_status=verif_status,
        is_current=True,
        updated_by=current_user.username,
        created_at=now,
        updated_at=now
    )
    db.add(new_posting)
    db.flush()
    
    # Create verification record if deputed within district
    if not payload.is_working_in_salary_gp and posting_type in ["WITHIN_MANDAL", "ANOTHER_MANDAL"]:
        db.add(GPVerification(
            posting_id=new_posting.id,
            employee_id=emp.employee_id,
            salary_mandal_id=sm.salary_mandal_id,
            receiving_mandal_id=act_mandal,
            status="PENDING"
        ))
        
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=sm.salary_mandal_id,
        action="STAGE3_WORKING_MAPPING",
        entity_type="POSTING",
        entity_id=str(new_posting.id),
        details=f"Stage 3 Working Station Mapping saved for {emp.name_ifmis} ({emp.employee_id}) - Working in Salary GP: {payload.is_working_in_salary_gp}",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    w_gp_name = None
    w_mandal_name = None
    if payload.is_working_in_salary_gp:
        w_gp_name = sm.panchayat.gp_name if sm.panchayat else None
        w_mandal_name = sm.panchayat.mandal_name if sm.panchayat else (sm.mandal.mandal_name if sm.mandal else None)
    elif posting_type in ["WITHIN_MANDAL", "ANOTHER_MANDAL"]:
        dest_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == act_gp).first()
        w_gp_name = dest_gp.gp_name if dest_gp else str(act_gp)
        w_mandal_name = dest_gp.mandal_name if dest_gp else None
    else:
        w_gp_name = payload.external_gp_or_office_name or payload.external_department_name
        w_mandal_name = payload.external_district_name

    return {
        "message": f"Working station & deputation mapping saved successfully for {emp.name_ifmis} (Stage 3 Complete).",
        "employee_id": emp.employee_id,
        "posting_type": posting_type,
        "is_working_in_salary_gp": payload.is_working_in_salary_gp,
        "actual_working_gp_name": w_gp_name,
        "actual_working_mandal_name": w_mandal_name
    }

# ==========================================
# INTERNAL REASSIGNMENT MODULE
# ==========================================

@router.post("/internal-reassignment")
def create_internal_reassignment(
    payload: InternalReassignmentCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if payload.posting_id:
        posting = db.query(EmployeePosting).filter(EmployeePosting.id == payload.posting_id).first()
    elif payload.employee_id:
        posting = db.query(EmployeePosting).filter(EmployeePosting.employee_id == payload.employee_id, EmployeePosting.is_current == True).first()
    else:
        raise HTTPException(status_code=400, detail="Either employee_id or posting_id must be provided.")

    if not posting:
        raise HTTPException(status_code=404, detail="Active posting record not found for this employee.")
        
    new_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == payload.reassigned_to_gp_lgd).first()
    if not new_gp:
        raise HTTPException(status_code=400, detail="Invalid Reassigned-To Gram Panchayat LGD Code.")
        
    if current_user.role == "MANDAL_ADMIN" and new_gp.mandal_id != current_user.mandal_id:
        raise HTTPException(status_code=403, detail="Cannot internally reassign to a Gram Panchayat outside your Mandal.")
        
    now = datetime.utcnow()
    
    # Preserve original deputation destination permanently
    if not posting.official_deputation_gp_lgd:
        posting.official_deputation_gp_lgd = posting.actual_working_gp_lgd
        posting.official_deputation_mandal_id = posting.actual_working_mandal_id
        
    prev_working_gp_lgd = posting.actual_working_gp_lgd
    
    # Deactivate previous active internal reassignments
    db.query(InternalReassignment).filter(
        InternalReassignment.posting_id == posting.id,
        InternalReassignment.is_current == True
    ).update({"is_current": False})
    
    # Create internal reassignment entry
    reassignment = InternalReassignment(
        posting_id=posting.id,
        employee_id=posting.employee_id,
        original_deputation_gp_lgd=posting.official_deputation_gp_lgd,
        reassigned_from_gp_lgd=prev_working_gp_lgd,
        reassigned_to_gp_lgd=new_gp.lgd_code,
        reassignment_date=payload.reassignment_date or date.today(),
        is_written_proceedings_available=payload.is_written_proceedings_available,
        proceedings_order_no=payload.proceedings_order_no,
        reason_remarks=payload.reason_remarks.strip(),
        is_current=True,
        verified_by_user=current_user.username,
        verified_at=now,
        created_at=now
    )
    db.add(reassignment)
    
    # Update active posting: presently working GP is derived as GP-Z!
    posting.has_internal_reassignment = True
    posting.reassigned_working_gp_lgd = new_gp.lgd_code
    posting.actual_working_gp_lgd = new_gp.lgd_code
    posting.actual_working_mandal_id = new_gp.mandal_id
    posting.updated_by = current_user.username
    posting.updated_at = now
    
    # Update two-side verification if exists
    verif = db.query(GPVerification).filter(GPVerification.posting_id == posting.id).first()
    if verif:
        verif.status = "CONFIRMED"
        verif.receiving_remarks = f"Internally reassigned to {new_gp.gp_name} (LGD: {new_gp.lgd_code}). Remarks: {payload.reason_remarks}"
        verif.verified_by_user = current_user.username
        verif.verified_at = now
        posting.verification_status = "VERIFIED_BOTH"
        
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        mandal_id=new_gp.mandal_id,
        action="INTERNAL_REASSIGNMENT",
        entity_type="POSTING",
        entity_id=str(posting.id),
        details=f"Internal reassignment for employee {posting.employee_id}: {prev_working_gp_lgd} -> {new_gp.gp_name} (LGD: {new_gp.lgd_code}). Reason: {payload.reason_remarks}",
        ip_address=request.client.host if request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": f"Internal reassignment successfully recorded. Employee presently assigned to {new_gp.gp_name}.",
        "employee_id": posting.employee_id,
        "official_deputation_gp_lgd": posting.official_deputation_gp_lgd,
        "original_deputation_gp_lgd": posting.official_deputation_gp_lgd,
        "presently_working_gp_name": new_gp.gp_name,
        "presently_working_gp_lgd": new_gp.lgd_code,
        "reassigned_to_gp_name": new_gp.gp_name,
        "reassigned_to_gp_lgd": new_gp.lgd_code,
        "is_written_proceedings_available": payload.is_written_proceedings_available
    }

@router.get("/internal-reassignments/{employee_id}")
def get_employee_internal_reassignments(
    employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    reassignments = (
        db.query(InternalReassignment)
        .filter(InternalReassignment.employee_id == employee_id)
        .order_by(InternalReassignment.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "original_deputation_gp_name": r.original_gp.gp_name if r.original_gp else "N/A",
            "reassigned_from_gp_name": r.from_gp.gp_name if r.from_gp else "N/A",
            "reassigned_to_gp_name": r.to_gp.gp_name if r.to_gp else "N/A",
            "reassigned_to_gp_lgd": r.reassigned_to_gp_lgd,
            "reassignment_date": r.reassignment_date.strftime("%Y-%m-%d") if r.reassignment_date else "N/A",
            "is_written_proceedings_available": r.is_written_proceedings_available,
            "proceedings_order_no": r.proceedings_order_no or "INTERNAL ARRANGEMENT – WRITTEN PROCEEDINGS NOT AVAILABLE",
            "reason_remarks": r.reason_remarks,
            "is_current": r.is_current,
            "verified_by_user": r.verified_by_user,
            "verified_at": r.verified_at.strftime("%Y-%m-%d %H:%M") if r.verified_at else None
        }
        for r in reassignments
    ]
