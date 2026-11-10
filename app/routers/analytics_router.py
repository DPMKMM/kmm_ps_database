from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, cast, String

from app.database import get_db
from app.models import (
    GramPanchayat, Mandal, Employee, EmployeeSalaryMapping,
    EmployeePosting, EmployeeStatusHistory, DataSubmission, User, DiscrepancyRecord,
    GPVerification, InternalReassignment
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Dashboards"])

@router.get("/district-summary")
def get_district_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    SECTION 12: DISTRICT / MANDAL SUMMARY DASHBOARD
    Calculated dynamically from database.
    If logged in as Mandal Admin, returns strictly that Mandal's analytics.
    """
    if current_user.role == "MANDAL_ADMIN":
        m_id = current_user.mandal_id
        total_gps = db.query(func.count(GramPanchayat.id)).filter(GramPanchayat.mandal_id == m_id).scalar() or 0
        total_mandals = 1
        
        # Stage 1, 2, 3 counts for Mandal
        stage1_count = db.query(func.count(Employee.id)).filter(
            Employee.registration_mandal_id == m_id,
            Employee.is_active == True
        ).scalar() or 0
        
        stage2_count = db.query(func.count(EmployeeSalaryMapping.id)).filter(
            EmployeeSalaryMapping.salary_mandal_id == m_id,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0
        
        stage3_count = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeeSalaryMapping.salary_mandal_id == m_id,
            EmployeeSalaryMapping.is_active == True,
            EmployeePosting.is_current == True
        ).scalar() or 0

        internal_reassignments = db.query(func.count(InternalReassignment.id)).join(
            EmployeePosting, EmployeePosting.id == InternalReassignment.posting_id
        ).filter(
            EmployeePosting.actual_working_mandal_id == m_id,
            InternalReassignment.is_current == True
        ).scalar() or 0

        total_registered_emps = stage1_count
        total_clear_vacancies = db.query(func.count(GramPanchayat.id)).filter(
            GramPanchayat.mandal_id == m_id,
            GramPanchayat.is_clear_vacancy == True
        ).scalar() or 0

        # Postings for this mandal's employees
        own_gp = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.is_working_in_salary_gp == True,
            EmployeeSalaryMapping.salary_mandal_id == m_id,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0

        dep_same_mandal = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.posting_type == "WITHIN_MANDAL",
            EmployeeSalaryMapping.salary_mandal_id == m_id,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0

        dep_other_mandal = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.posting_type == "ANOTHER_MANDAL",
            EmployeeSalaryMapping.salary_mandal_id == m_id,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0

        dep_other_district = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.posting_type.in_(["OTHER_DISTRICT", "OTHER_DEPARTMENT"]),
            EmployeeSalaryMapping.salary_mandal_id == m_id,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0

        def status_q(statuses):
            return db.query(func.count(EmployeeStatusHistory.id)).join(
                EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeeStatusHistory.employee_id
            ).filter(
                EmployeeStatusHistory.is_current == True,
                EmployeeStatusHistory.service_status.in_(statuses),
                EmployeeSalaryMapping.salary_mandal_id == m_id,
                EmployeeSalaryMapping.is_active == True
            ).scalar() or 0

        working_count = status_q(["WORKING"])
        suspended_count = status_q(["SUSPENDED"])
        absconding_count = status_q(["ABSCONDING"])
        long_leave_count = status_q(["LONG_LEAVE"])
        medical_leave_count = status_q(["MEDICAL_LEAVE"])
        maternity_leave_count = status_q(["MATERNITY_LEAVE", "CHILD_CARE_LEAVE"])
        other_leave_count = status_q(["EARNED_LEAVE", "EXTRAORDINARY_LEAVE", "OTHER_APPROVED_LEAVE", "OTHER"])

        discrepancy_count = db.query(func.count(DiscrepancyRecord.id)).filter(
            DiscrepancyRecord.mandal_id == m_id,
            DiscrepancyRecord.status.in_(["OPEN", "ASSIGNED"])
        ).scalar() or 0

        pending_verif = db.query(func.count(GPVerification.id)).filter(
            or_(GPVerification.salary_mandal_id == m_id, GPVerification.receiving_mandal_id == m_id),
            GPVerification.status == "PENDING"
        ).scalar() or 0

        sub = db.query(DataSubmission).filter(DataSubmission.mandal_id == m_id).first()
        submissions_done = 1 if sub and sub.is_submitted else 0

    else:
        total_gps = db.query(func.count(GramPanchayat.id)).scalar() or 571
        total_mandals = db.query(func.count(Mandal.id)).scalar() or 20
        
        # Stage 1, 2, 3 counts for District
        stage1_count = db.query(func.count(Employee.id)).filter(Employee.is_active == True).scalar() or 0
        stage2_count = db.query(func.count(EmployeeSalaryMapping.id)).filter(EmployeeSalaryMapping.is_active == True).scalar() or 0
        stage3_count = db.query(func.count(EmployeePosting.id)).filter(EmployeePosting.is_current == True).scalar() or 0
        internal_reassignments = db.query(func.count(InternalReassignment.id)).filter(InternalReassignment.is_current == True).scalar() or 0

        total_registered_emps = stage1_count
        total_clear_vacancies = db.query(func.count(GramPanchayat.id)).filter(GramPanchayat.is_clear_vacancy == True).scalar() or 0

        # Active postings breakdown
        own_gp = db.query(func.count(EmployeePosting.id)).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.is_working_in_salary_gp == True
        ).scalar() or 0

        dep_same_mandal = db.query(func.count(EmployeePosting.id)).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.posting_type == "WITHIN_MANDAL"
        ).scalar() or 0

        dep_other_mandal = db.query(func.count(EmployeePosting.id)).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.posting_type == "ANOTHER_MANDAL"
        ).scalar() or 0

        dep_other_district = db.query(func.count(EmployeePosting.id)).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.posting_type.in_(["OTHER_DISTRICT", "OTHER_DEPARTMENT"])
        ).scalar() or 0

        # Service status breakdown (Section 11: Employee Availability Classification)
        working_count = db.query(func.count(EmployeeStatusHistory.id)).filter(
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status == "WORKING"
        ).scalar() or 0

        suspended_count = db.query(func.count(EmployeeStatusHistory.id)).filter(
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status == "SUSPENDED"
        ).scalar() or 0

        absconding_count = db.query(func.count(EmployeeStatusHistory.id)).filter(
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status == "ABSCONDING"
        ).scalar() or 0

        long_leave_count = db.query(func.count(EmployeeStatusHistory.id)).filter(
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status == "LONG_LEAVE"
        ).scalar() or 0

        medical_leave_count = db.query(func.count(EmployeeStatusHistory.id)).filter(
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status == "MEDICAL_LEAVE"
        ).scalar() or 0

        maternity_leave_count = db.query(func.count(EmployeeStatusHistory.id)).filter(
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status.in_(["MATERNITY_LEAVE", "CHILD_CARE_LEAVE"])
        ).scalar() or 0

        other_leave_count = db.query(func.count(EmployeeStatusHistory.id)).filter(
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status.in_(["EARNED_LEAVE", "EXTRAORDINARY_LEAVE", "OTHER_APPROVED_LEAVE", "OTHER"])
        ).scalar() or 0

        # Verification stats
        pending_verif = db.query(func.count(EmployeePosting.id)).filter(
            EmployeePosting.is_current == True,
            EmployeePosting.verification_status == "PENDING"
        ).scalar() or 0

        discrepancy_count = db.query(func.count(DiscrepancyRecord.id)).filter(
            DiscrepancyRecord.status.in_(["OPEN", "ASSIGNED"])
        ).scalar() or 0

        submissions_done = db.query(func.count(DataSubmission.id)).filter(
            DataSubmission.is_submitted == True
        ).scalar() or 0
    
    unavailable_count = (
        suspended_count + absconding_count + long_leave_count +
        medical_leave_count + maternity_leave_count + other_leave_count
    )

    # Dynamic Category Counts
    gps_q = db.query(GramPanchayat)
    if current_user.role == "MANDAL_ADMIN":
        gps_q = gps_q.filter(GramPanchayat.mandal_id == current_user.mandal_id)
    all_target_gps = gps_q.all()

    cat_a = 0
    cat_b = 0
    cat_c = 0
    cat_d = 0

    for g in all_target_gps:
        sal_cnt = db.query(func.count(EmployeeSalaryMapping.id)).filter(
            EmployeeSalaryMapping.salary_gp_lgd == g.lgd_code,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0

        work_cnt = db.query(func.count(EmployeePosting.id)).filter(
            EmployeePosting.actual_working_gp_lgd == g.lgd_code,
            EmployeePosting.is_current == True
        ).scalar() or 0

        dep_out_cnt = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeeSalaryMapping.salary_gp_lgd == g.lgd_code,
            EmployeeSalaryMapping.is_active == True,
            EmployeePosting.is_current == True,
            EmployeePosting.is_working_in_salary_gp == False
        ).scalar() or 0

        if sal_cnt == 0 and work_cnt == 0:
            cat_a += 1
        elif sal_cnt == 0 and work_cnt > 0:
            cat_b += 1
        
        if sal_cnt > 0 and dep_out_cnt > 0:
            cat_c += 1

        if sal_cnt > 0 and work_cnt == 0:
            cat_d += 1

    return {
        "total_gram_panchayats": total_gps,
        "total_mandals": total_mandals,
        "total_registered_employees": total_registered_emps,
        "total_clear_vacancies": total_clear_vacancies,

        # Three-Stage Architecture Progress
        "stage_progress": {
            "stage1_registered": stage1_count,
            "stage2_salary_mapped": stage2_count,
            "stage3_working_mapped": stage3_count,
            "internal_reassignments": internal_reassignments
        },

        # GP Position Categories
        "categories": {
            "category_a_clear_vacancies": cat_a,
            "category_b_deputed_in_clear_vacancies": cat_b,
            "category_c_deputed_out": cat_c,
            "category_d_no_staff_working": cat_d
        },
        
        # Availability classification
        "available_for_regular_work": working_count,
        "not_available_for_regular_work": unavailable_count,
        "pending_verifications": pending_verif,
        "active_discrepancies": discrepancy_count,
        "submissions_completed": submissions_done,
        
        # Deputation Breakdown
        "posting_breakdown": {
            "own_gp": own_gp,
            "within_same_mandal": dep_same_mandal,
            "another_mandal": dep_other_mandal,
            "other_district": dep_other_district
        },
        
        # Service status Breakdown
        "service_status_breakdown": {
            "working": working_count,
            "suspended": suspended_count,
            "absconding": absconding_count,
            "long_leave": long_leave_count,
            "medical_leave": medical_leave_count,
            "maternity_and_ccl": maternity_leave_count,
            "other_leaves": other_leave_count
        }
    }

    return {
        "total_gram_panchayats": total_gps,
        "total_mandals": total_mandals,
        "total_registered_employees": total_registered_emps,
        "total_clear_vacancies": total_clear_vacancies,
        
        # Availability classification
        "available_for_regular_work": working_count,
        "not_available_for_regular_work": unavailable_count,
        "pending_verifications": pending_verif,
        "active_discrepancies": discrepancy_count,
        "submissions_completed": submissions_done,
        
        # Deputation Breakdown
        "posting_breakdown": {
            "own_gp": own_gp,
            "within_same_mandal": dep_same_mandal,
            "another_mandal": dep_other_mandal,
            "other_district": dep_other_district
        },
        
        # Service status Breakdown
        "service_status_breakdown": {
            "working": working_count,
            "suspended": suspended_count,
            "absconding": absconding_count,
            "long_leave": long_leave_count,
            "medical_leave": medical_leave_count,
            "maternity_and_ccl": maternity_leave_count,
            "other_leaves": other_leave_count
        }
    }

@router.get("/mandal-breakdown")
def get_mandal_breakdown(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    SECTION 12: MANDAL-WISE ANALYTICS TABLE
    Dynamic metrics for each of the 20 Mandals.
    """
    if current_user.role == "MANDAL_ADMIN":
        mandals = db.query(Mandal).filter(Mandal.id == current_user.mandal_id).all()
    else:
        mandals = db.query(Mandal).order_by(Mandal.mandal_name.asc()).all()
    results = []
    
    for m in mandals:
        # If user is Mandal Admin, they can view the full table or highlight their mandal
        gp_count = db.query(func.count(GramPanchayat.id)).filter(GramPanchayat.mandal_id == m.id).scalar() or 0
        vacancies = db.query(func.count(GramPanchayat.id)).filter(GramPanchayat.mandal_id == m.id, GramPanchayat.is_clear_vacancy == True).scalar() or 0
        
        # Employees drawing salary from this Mandal
        salary_emps = db.query(func.count(EmployeeSalaryMapping.id)).filter(
            EmployeeSalaryMapping.salary_mandal_id == m.id,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0
        
        # Employees actually working in this Mandal
        working_in_mandal = db.query(func.count(EmployeePosting.id)).filter(
            EmployeePosting.actual_working_mandal_id == m.id,
            EmployeePosting.is_current == True
        ).scalar() or 0
        
        # Deputed out of this Mandal (salary here, working elsewhere or other district)
        deputed_out = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeeSalaryMapping.salary_mandal_id == m.id,
            EmployeeSalaryMapping.is_active == True,
            EmployeePosting.is_current == True,
            (EmployeePosting.actual_working_mandal_id != m.id) | (EmployeePosting.posting_type == "OTHER_DISTRICT")
        ).scalar() or 0
        
        # Deputed INTO this Mandal (salary in another mandal, working here)
        deputed_in = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeePosting.actual_working_mandal_id == m.id,
            EmployeePosting.is_current == True,
            EmployeeSalaryMapping.salary_mandal_id != m.id,
            EmployeeSalaryMapping.is_active == True
        ).scalar() or 0
        
        # Working in other districts
        other_dist = db.query(func.count(EmployeePosting.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id
        ).filter(
            EmployeeSalaryMapping.salary_mandal_id == m.id,
            EmployeeSalaryMapping.is_active == True,
            EmployeePosting.is_current == True,
            EmployeePosting.posting_type == "OTHER_DISTRICT"
        ).scalar() or 0
        
        # Unavailable (Suspended, Absconding, Leave attached to this mandal)
        unavailable = db.query(func.count(EmployeeStatusHistory.id)).join(
            EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeeStatusHistory.employee_id
        ).filter(
            EmployeeSalaryMapping.salary_mandal_id == m.id,
            EmployeeSalaryMapping.is_active == True,
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status != "WORKING"
        ).scalar() or 0
        
        # Available for regular work
        available_working = db.query(func.count(EmployeeStatusHistory.id)).join(
            EmployeePosting, EmployeePosting.employee_id == EmployeeStatusHistory.employee_id
        ).filter(
            EmployeePosting.actual_working_mandal_id == m.id,
            EmployeePosting.is_current == True,
            EmployeeStatusHistory.is_current == True,
            EmployeeStatusHistory.service_status == "WORKING"
        ).scalar() or 0

        # Submission status
        sub = db.query(DataSubmission).filter(DataSubmission.mandal_id == m.id).first()
        is_sub = sub.is_submitted if sub else False
        
        results.append({
            "mandal_id": m.id,
            "mandal_name": m.mandal_name,
            "mandal_lgd": m.mandal_lgd,
            "total_gps": gp_count,
            "clear_vacancies": vacancies,
            "salary_drawing_strength": salary_emps,
            "actually_working_strength": working_in_mandal,
            "deputed_out": deputed_out,
            "deputed_in": deputed_in,
            "deputed_to_other_districts": other_dist,
            "unavailable_strength": unavailable,
            "available_regular_strength": available_working,
            "is_submitted": is_sub
        })
        
    return results

@router.get("/gp-positions")
def get_gp_positions(
    mandal_id: Optional[int] = None,
    vacancy_only: bool = False,
    category: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    SECTION 10: GRAM PANCHAYAT-WISE EMPLOYEE POSITION STATEMENT
    All 571 GPs with dynamic calculation of:
    - Salary Claiming Strength
    - Employee Attachment Strength
    - Actual Available Working Strength
    - Deputation In / Deputation Out
    - Clear Vacancy Status & Dynamic Categories (Category A, B, C, D)
    """
    query = db.query(GramPanchayat)
    
    if current_user.role == "MANDAL_ADMIN":
        query = query.filter(GramPanchayat.mandal_id == current_user.mandal_id)
    elif mandal_id:
        query = query.filter(GramPanchayat.mandal_id == mandal_id)
        
    if vacancy_only:
        query = query.filter(GramPanchayat.is_clear_vacancy == True)
        
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (GramPanchayat.gp_name.ilike(s)) |
            (GramPanchayat.mandal_name.ilike(s)) |
            (cast(GramPanchayat.lgd_code, String).ilike(s))
        )
        
    all_gps = query.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).all()
    
    results = []
    for gp in all_gps:
        # A. Salary Claiming Strength
        salary_emps = db.query(EmployeeSalaryMapping).filter(
            EmployeeSalaryMapping.salary_gp_lgd == gp.lgd_code,
            EmployeeSalaryMapping.is_active == True
        ).all()
        salary_strength = len(salary_emps)
        
        # B. Deputation Out (salary here, but working elsewhere)
        dep_out = 0
        for sm in salary_emps:
            post = db.query(EmployeePosting).filter(EmployeePosting.employee_id == sm.employee_id, EmployeePosting.is_current == True).first()
            if post and not post.is_working_in_salary_gp:
                dep_out += 1
                
        # C. Deputation In (working here, salary elsewhere)
        working_postings = db.query(EmployeePosting).filter(
            EmployeePosting.actual_working_gp_lgd == gp.lgd_code,
            EmployeePosting.is_current == True
        ).all()
        
        dep_in = 0
        available_working_strength = 0
        suspended_count = 0
        absconding_count = 0
        leave_count = 0
        
        for wp in working_postings:
            sm = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == wp.employee_id, EmployeeSalaryMapping.is_active == True).first()
            if sm and sm.salary_gp_lgd != gp.lgd_code:
                dep_in += 1
                
            # Check availability
            st = db.query(EmployeeStatusHistory).filter(EmployeeStatusHistory.employee_id == wp.employee_id, EmployeeStatusHistory.is_current == True).first()
            if st:
                if st.service_status == "WORKING":
                    available_working_strength += 1
                elif st.service_status == "SUSPENDED":
                    suspended_count += 1
                elif st.service_status == "ABSCONDING":
                    absconding_count += 1
                else:
                    leave_count += 1
            else:
                available_working_strength += 1

        # Dynamic Classification into Categories
        if salary_strength == 0 and len(working_postings) == 0:
            gp_cat = "CATEGORY_A"
            gp_cat_name = "Category A: Clear Vacancy (No Salary & No Deputed PS)"
        elif salary_strength == 0 and len(working_postings) > 0:
            gp_cat = "CATEGORY_B"
            gp_cat_name = "Category B: Clear Vacancy with Deputed PS Working"
        elif salary_strength > 0 and dep_out > 0:
            gp_cat = "CATEGORY_C"
            gp_cat_name = "Category C: Salary GP with PS Deputed Out"
        elif salary_strength > 0 and available_working_strength == 0:
            gp_cat = "CATEGORY_D"
            gp_cat_name = "Category D: Salary GP with No PS Actually Working"
        else:
            gp_cat = "REGULAR_ACTIVE"
            gp_cat_name = "Regular Active Duty (Own GP)"

        if category and category.upper() != gp_cat:
            continue

        results.append({
            "lgd_code": gp.lgd_code,
            "gp_name": gp.gp_name,
            "mandal_id": gp.mandal_id,
            "mandal_name": gp.mandal_name,
            "is_clear_vacancy": gp.is_clear_vacancy,
            "vacancy_remarks": gp.vacancy_remarks,
            "salary_claiming_strength": salary_strength,
            "actual_working_strength": available_working_strength,
            "deputation_out": dep_out,
            "deputation_in": dep_in,
            "suspended_count": suspended_count,
            "absconding_count": absconding_count,
            "leave_count": leave_count,
            "category": gp_cat,
            "category_name": gp_cat_name,
            "is_mismatched": (salary_strength > 0 and available_working_strength == 0)
        })
        
    total_count = len(results)
    paged_results = results[skip : skip + limit]

    return {
        "total": total_count,
        "items": paged_results
    }
