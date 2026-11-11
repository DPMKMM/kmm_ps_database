import io
import csv
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.database import get_db
from app.models import (
    Employee, EmployeeSalaryMapping, EmployeePosting, EmployeeStatusHistory,
    GramPanchayat, Mandal, User, DataSubmission, DiscrepancyRecord,
    InternalReassignment
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["Reports Generation Module (A-Z)"])

KEY_REPORT_CODES = ("CLEAR_VACANCY", "DEPUTED_PS", "LEAVE", "SUSPENSION")

LEAVE_STATUS_LABELS = {
    "LONG_LEAVE": "Long Leave",
    "MEDICAL_LEAVE": "Medical Leave",
    "MATERNITY_LEAVE": "Maternity Leave",
    "CHILD_CARE_LEAVE": "Child Care Leave (CCL)",
    "EARNED_LEAVE": "Earned Leave",
    "EXTRAORDINARY_LEAVE": "Extraordinary Leave (EOL)",
    "OTHER_APPROVED_LEAVE": "Other Approved Leave",
    "OTHER": "Other Leave",
}

POSTING_TYPE_LABELS = {
    "OWN_GP": "Regular (Own Salary GP)",
    "WITHIN_MANDAL": "Within Same Mandal",
    "ANOTHER_MANDAL": "Another Mandal",
    "OTHER_DISTRICT": "Other District",
    "OTHER_DEPARTMENT": "Other Department",
}

REPORT_DEFINITIONS = {
    "CLEAR_VACANCY": "Clear Vacancy Report (Vacant GPs - Category A)",
    "DEPUTED_PS": "Deputed Panchayat Secretaries Report",
    "LEAVE": "Leave Report (All Approved & Unapproved Leaves)",
    "SUSPENSION": "Suspension Report (Suspended Panchayat Secretaries)",
    "A": "District Employee Master Report",
    "B": "Mandal-wise Panchayat Secretary Status Report",
    "C": "GP-wise Employee Position Report",
    "D": "District PS Master & Working Station Reconciliation Report (22 Columns)",
    "E": "Deputation Within Same Mandal Report",
    "F": "Deputation to Other Mandals Report",
    "G": "Deputation to Other Districts Report",
    "H": "Clear Vacant Gram Panchayats – Category A (No Salary Claimant & No Deputed PS)",
    "I": "Suspended Employees Report",
    "J": "Absconding Employees Report",
    "K": "Long Leave Employees Report",
    "L": "Medical Leave Employees Report",
    "M": "Maternity and Child Care Leave Report",
    "N": "Other Approved Leave Report",
    "O": "Employees Not Available for Regular Work Report",
    "P": "Expected Joining Date Crossed Report",
    "Q": "Employee-wise Deputation Chain Report",
    "R": "Duplicate and Conflicting Employee Report",
    "S": "Unverified Deputation Report",
    "T": "GP-wise Employees Actually Working Report",
    "U": "Salary-Claiming GP with No Employee Actually Working (Category D)",
    "V": "Employees Working on Deputation in Clear Vacancies (Category B)",
    "W": "Mandal-wise Data Submission Status Report",
    "X": "GP-wise Deputation In and Deputation Out Report",
    "Y": "Employee Service Status History Report",
    "Z": "Employee Availability vs Salary Claiming Strength Report"
}

@router.get("/list")
def list_available_reports():
    return [
        {
            "code": k,
            "name": v,
            "category": "KEY" if k in KEY_REPORT_CODES else "STANDARD"
        }
        for k, v in REPORT_DEFINITIONS.items()
    ]

@router.get("/data/{report_code}")
def get_report_data(
    report_code: str,
    mandal_id: Optional[int] = None,
    gp_lgd: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code = report_code.upper()
    if code not in REPORT_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Invalid report code")
        
    title = REPORT_DEFINITIONS[code]
    headers, rows = build_report_data(code, mandal_id, gp_lgd, current_user, db)
    
    return {
        "report_code": code,
        "title": title,
        "district": "Khammam",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_records": len(rows),
        "headers": headers,
        "rows": rows
    }

@router.get("/export/{report_code}")
def export_report(
    report_code: str,
    format: str = "excel", # excel or csv
    mandal_id: Optional[int] = None,
    gp_lgd: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    code = report_code.upper()
    if code not in REPORT_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Invalid report code")
        
    title = REPORT_DEFINITIONS[code]
    headers, rows = build_report_data(code, mandal_id, gp_lgd, current_user, db)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["DETAILS OF PANCHAYAT SECRETARIES WORKING IN KHAMMAM DISTRICT"])
        writer.writerow([f"Report: {title}"])
        writer.writerow([f"Generated On: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"])
        writer.writerow([])
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
            
        csv_data = output.getvalue().encode("utf-8")
        filename = f"Report_{code}_{timestamp}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        # Excel format using openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Report_{code}"[:31]
        
        # Government Header styling
        navy_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        gold_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
        title_font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
        sub_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        hdr_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        cell_font = Font(name="Calibri", size=10)
        
        max_col_letter = get_column_letter(max(len(headers), 8))
        
        # Row 1: Title
        ws.merge_cells(f"A1:{max_col_letter}1")
        cell1 = ws["A1"]
        cell1.value = "DISTRICT PANCHAYAT OFFICE, KHAMMAM DISTRICT, TELANGANA"
        cell1.font = title_font
        cell1.fill = navy_fill
        cell1.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 28
        
        # Row 2: Subtitle
        ws.merge_cells(f"A2:{max_col_letter}2")
        cell2 = ws["A2"]
        cell2.value = f"Details of Panchayat Secretaries – {title}"
        cell2.font = sub_font
        cell2.fill = gold_fill
        cell2.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 22
        
        # Row 3: Meta
        ws.merge_cells(f"A3:{max_col_letter}3")
        cell3 = ws["A3"]
        cell3.value = f"Generated On: {datetime.now().strftime('%d-%m-%Y %I:%M %p')} | Total Records: {len(rows)}"
        cell3.font = Font(italic=True, size=9)
        cell3.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[3].height = 18
        
        # Row 5: Column Headers
        ws.row_dimensions[5].height = 24
        header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=5, column=col_idx, value=h)
            cell.font = hdr_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            
        # Data Rows
        border_thin = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )
        
        for row_idx, r in enumerate(rows, start=6):
            ws.row_dimensions[row_idx].height = 20
            # Alternate row background
            bg_color = "F8FAFC" if row_idx % 2 == 0 else "FFFFFF"
            row_fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
            for col_idx, val in enumerate(r, start=1):
                c = ws.cell(row=row_idx, column=col_idx, value=val)
                c.font = cell_font
                c.fill = row_fill
                c.border = border_thin
                c.alignment = Alignment(vertical="center")
                
        # Auto column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)
            
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        
        filename = f"Report_{code}_{timestamp}.xlsx"
        return StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

def _fmt_date(d) -> str:
    """Format a date/datetime consistently or return N/A."""
    return d.strftime("%Y-%m-%d") if d else "N/A"


def _resolve_working_location(p, gp) -> str:
    """Resolve current physical working location label for an employee posting."""
    if not p:
        return f"{gp.gp_name} ({gp.mandal_name})" if gp else "N/A"
    if p.posting_type == "OTHER_DISTRICT":
        return f"{p.external_gp_or_office_name or 'External Office'} ({p.external_district_name or 'Other Dist'})"
    if p.posting_type == "OTHER_DEPARTMENT":
        return f"{p.external_department_name or 'Other Dept'} ({p.external_gp_or_office_name or 'Office'})"
    if p.has_internal_reassignment and p.reassigned_panchayat:
        return f"{p.reassigned_panchayat.gp_name} ({p.reassigned_panchayat.mandal_name})"
    if p.working_panchayat:
        return f"{p.working_panchayat.gp_name} ({p.working_panchayat.mandal_name})"
    return f"{gp.gp_name} ({gp.mandal_name})" if gp else "N/A"


def _resolve_official_deputation(p):
    """Return (gp_or_office, mandal_or_dept) for an employee's official deputation destination."""
    if not p or p.is_working_in_salary_gp:
        return "N/A (Working in Salary GP)", "N/A"
    if p.posting_type == "OTHER_DISTRICT":
        return p.external_gp_or_office_name or "Other District Office", p.external_district_name or "Other District"
    if p.posting_type == "OTHER_DEPARTMENT":
        return p.external_gp_or_office_name or p.external_department_name or "Department Office", p.external_department_name or "Other Department"
    target_gp = p.official_deputation_panchayat or p.working_panchayat
    if target_gp:
        return target_gp.gp_name, target_gp.mandal_name
    return "Deputed (GP Not Confirmed)", "N/A"


def _build_clear_vacancy_report(db: Session, target_mandal_id: Optional[int]):
    """Build Clear Vacancy (Category A: no salary claimant and no working PS) headers and rows."""
    headers = [
        "S.No", "Mandal Name", "Gram Panchayat Name", "GP LGD Code",
        "Salary Strength", "Deputation In", "Deputation Out",
        "Actual Working Strength", "Available Working Strength",
        "Position Status", "Mandal Confirmation", "Verification Status", "Remarks"
    ]
    sal_counts = dict(
        db.query(EmployeeSalaryMapping.salary_gp_lgd, func.count(EmployeeSalaryMapping.id))
        .filter(EmployeeSalaryMapping.is_active == True)
        .group_by(EmployeeSalaryMapping.salary_gp_lgd)
        .all()
    )
    work_counts = dict(
        db.query(EmployeePosting.actual_working_gp_lgd, func.count(EmployeePosting.id))
        .filter(EmployeePosting.is_current == True, EmployeePosting.actual_working_gp_lgd.isnot(None))
        .group_by(EmployeePosting.actual_working_gp_lgd)
        .all()
    )
    gps = db.query(GramPanchayat)
    if target_mandal_id:
        gps = gps.filter(GramPanchayat.mandal_id == target_mandal_id)
    gps = gps.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).all()

    rows = []
    idx = 1
    for gp in gps:
        if sal_counts.get(gp.lgd_code, 0) == 0 and work_counts.get(gp.lgd_code, 0) == 0:
            rows.append([
                idx,
                gp.mandal_name,
                gp.gp_name,
                gp.lgd_code,
                0,
                0,
                0,
                0,
                0,
                "CATEGORY A: CLEAR VACANCY",
                "CONFIRMED CLEAR VACANT",
                "VERIFIED NO SECRETARY ON DUTY",
                gp.vacancy_remarks or "Sanctioned GP post with no employee claiming salary or working on deputation",
            ])
            idx += 1
    return headers, rows


def _build_deputed_ps_report(records):
    """Build unified report covering all deputed Panchayat Secretaries across all deputation types."""
    headers = [
        "S.No", "Employee ID", "Employee Name", "Mobile Number",
        "Salary Mandal", "Salary GP", "Salary GP LGD",
        "Deputation Type", "Official Deputation Mandal / Dept", "Official Deputation GP / Office",
        "Presently Working Location", "Deputation Order No", "Order Date",
        "Effective From", "Service Status", "Verification Status", "Remarks"
    ]
    rows = []
    idx = 1
    for emp, sm, p, st, gp in records:
        if not (p and not p.is_working_in_salary_gp):
            continue
        off_gp, off_mandal = _resolve_official_deputation(p)
        dep_type_label = POSTING_TYPE_LABELS.get(p.posting_type, p.posting_type or "Deputed")
        if p.has_internal_reassignment:
            dep_type_label += " (Internally Reassigned)"
        rows.append([
            idx,
            emp.employee_id,
            emp.name_ifmis,
            emp.mobile_number or "N/A",
            gp.mandal_name,
            gp.gp_name,
            sm.salary_gp_lgd,
            dep_type_label,
            off_mandal,
            off_gp,
            _resolve_working_location(p, gp),
            p.deputation_order_no or "N/A",
            _fmt_date(p.deputation_order_date),
            _fmt_date(p.effective_from),
            st.service_status if st else "WORKING",
            p.verification_status or "PENDING",
            p.remarks or "N/A",
        ])
        idx += 1
    return headers, rows


def _build_suspension_report(records):
    """Build report for all Suspended Panchayat Secretaries."""
    headers = [
        "S.No", "Employee ID", "Employee Name", "Mobile Number",
        "Salary GP", "Salary Mandal", "Working Arrangement",
        "Suspension Order No", "Suspension / Effective Date",
        "Revocation Order No", "Expected Joining Date", "Remarks"
    ]
    rows = []
    idx = 1
    for emp, sm, p, st, gp in records:
        if not (st and st.service_status == "SUSPENDED"):
            continue
        order_no = st.suspension_order_no or st.proceedings_order_no or "N/A"
        susp_date = _fmt_date(st.suspension_effective_date or st.status_effective_from or st.suspension_order_date or st.proceedings_order_date)
        rows.append([
            idx,
            emp.employee_id,
            emp.name_ifmis,
            emp.mobile_number or "N/A",
            gp.gp_name,
            gp.mandal_name,
            _resolve_working_location(p, gp),
            order_no,
            susp_date,
            st.revocation_order_no or "N/A",
            _fmt_date(st.expected_joining_date),
            st.reason_remarks or "N/A",
        ])
        idx += 1
    return headers, rows


def _build_leave_report(records, allowed_statuses=None):
    """Build report for Panchayat Secretaries on any Leave status (or specific subtype)."""
    target_statuses = allowed_statuses if allowed_statuses is not None else set(LEAVE_STATUS_LABELS.keys())
    headers = [
        "S.No", "Employee ID", "Employee Name", "Mobile Number",
        "Salary GP", "Salary Mandal", "Working Arrangement",
        "Leave Type", "Leave Start / Effective Date", "Expected Return / Joining Date",
        "Proceedings / Order No", "Remarks"
    ]
    rows = []
    idx = 1
    for emp, sm, p, st, gp in records:
        if not (st and st.service_status in target_statuses):
            continue
        start_dt = st.leave_start_date or st.status_effective_from or st.proceedings_order_date
        ret_dt = st.expected_return_date or st.expected_joining_date
        proc_no = st.leave_proceedings_no or st.proceedings_order_no or "N/A"
        rows.append([
            idx,
            emp.employee_id,
            emp.name_ifmis,
            emp.mobile_number or "N/A",
            gp.gp_name,
            gp.mandal_name,
            _resolve_working_location(p, gp),
            LEAVE_STATUS_LABELS.get(st.service_status, st.service_status),
            _fmt_date(start_dt),
            _fmt_date(ret_dt),
            proc_no,
            st.reason_remarks or st.leave_approval_details or "N/A",
        ])
        idx += 1
    return headers, rows


def build_report_data(code: str, mandal_id: Optional[int], gp_lgd: Optional[int], current_user: User, db: Session):
    # Enforce Mandal isolation if user is Mandal Admin
    target_mandal_id = current_user.mandal_id if current_user.role == "MANDAL_ADMIN" else mandal_id
    today = date.today()
    
    # Common helper query for active employees
    def base_emp_query():
        q = (
            db.query(
                Employee, EmployeeSalaryMapping, EmployeePosting,
                EmployeeStatusHistory, GramPanchayat
            )
            .join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == Employee.employee_id)
            .join(GramPanchayat, GramPanchayat.lgd_code == EmployeeSalaryMapping.salary_gp_lgd)
            .outerjoin(EmployeePosting, (EmployeePosting.employee_id == Employee.employee_id) & (EmployeePosting.is_current == True))
            .outerjoin(EmployeeStatusHistory, (EmployeeStatusHistory.employee_id == Employee.employee_id) & (EmployeeStatusHistory.is_current == True))
            .filter(EmployeeSalaryMapping.is_active == True)
        )
        if target_mandal_id:
            q = q.filter(
                or_(
                    EmployeeSalaryMapping.salary_mandal_id == target_mandal_id,
                    EmployeePosting.actual_working_mandal_id == target_mandal_id,
                    EmployeePosting.official_deputation_mandal_id == target_mandal_id
                )
            )
        if gp_lgd:
            q = q.filter(
                or_(
                    EmployeeSalaryMapping.salary_gp_lgd == gp_lgd,
                    EmployeePosting.actual_working_gp_lgd == gp_lgd
                )
            )
        return q.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).all()

    if code == "CLEAR_VACANCY":
        return _build_clear_vacancy_report(db, target_mandal_id)
    elif code == "DEPUTED_PS":
        return _build_deputed_ps_report(base_emp_query())
    elif code == "LEAVE":
        return _build_leave_report(base_emp_query())
    elif code == "SUSPENSION":
        return _build_suspension_report(base_emp_query())

    # Report A: District Employee Master Report
    if code == "A":
        headers = ["S.No", "Employee ID", "Employee Name", "Mobile Number", "Salary GP LGD", "Salary GP Name", "Salary Mandal", "Posting Type", "Working Location", "Service Status", "Verification Status"]
        records = base_emp_query()
        rows = []
        for idx, (emp, sm, p, st, gp) in enumerate(records, start=1):
            if p and p.posting_type == "OTHER_DISTRICT":
                w_loc = f"{p.external_gp_or_office_name or 'External Office'} ({p.external_district_name or 'Other Dist'})"
            elif p and p.posting_type == "OTHER_DEPARTMENT":
                w_loc = f"{p.external_department_name or 'Other Dept'} ({p.external_gp_or_office_name or 'Office'})"
            elif p and p.working_panchayat:
                w_loc = f"{p.working_panchayat.gp_name} ({p.working_panchayat.mandal_name})"
            else:
                w_loc = gp.gp_name
            rows.append([idx, emp.employee_id, emp.name_ifmis, emp.mobile_number or "N/A", sm.salary_gp_lgd, gp.gp_name, gp.mandal_name, p.posting_type if p else "OWN_GP", w_loc, st.service_status if st else "WORKING", p.verification_status if p else "PENDING"])
        return headers, rows

    # Report B: Mandal-wise Panchayat Secretary Status Report
    elif code == "B":
        headers = ["S.No", "Mandal Name", "Mandal LGD", "Total GPs", "Clear Vacancies", "Salary Strength", "Working Strength", "Deputed Out", "Deputed In", "Not Available Strength"]
        if current_user.role == "MANDAL_ADMIN":
            mandals = db.query(Mandal).filter(Mandal.id == current_user.mandal_id).all()
        elif target_mandal_id:
            mandals = db.query(Mandal).filter(Mandal.id == target_mandal_id).all()
        else:
            mandals = db.query(Mandal).order_by(Mandal.mandal_name.asc()).all()
        rows = []
        for idx, m in enumerate(mandals, start=1):
            if target_mandal_id and m.id != target_mandal_id:
                continue
            total_gps = db.query(func.count(GramPanchayat.id)).filter(GramPanchayat.mandal_id == m.id).scalar() or 0
            vac = db.query(func.count(GramPanchayat.id)).filter(GramPanchayat.mandal_id == m.id, GramPanchayat.is_clear_vacancy == True).scalar() or 0
            sal = db.query(func.count(EmployeeSalaryMapping.id)).filter(EmployeeSalaryMapping.salary_mandal_id == m.id, EmployeeSalaryMapping.is_active == True).scalar() or 0
            act = db.query(func.count(EmployeePosting.id)).filter(EmployeePosting.actual_working_mandal_id == m.id, EmployeePosting.is_current == True).scalar() or 0
            dep_out = db.query(func.count(EmployeePosting.id)).join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id).filter(
                EmployeeSalaryMapping.salary_mandal_id == m.id, EmployeeSalaryMapping.is_active == True, EmployeePosting.is_current == True,
                (EmployeePosting.actual_working_mandal_id != m.id) | (EmployeePosting.posting_type == "OTHER_DISTRICT")
            ).scalar() or 0
            dep_in = db.query(func.count(EmployeePosting.id)).join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id).filter(
                EmployeePosting.actual_working_mandal_id == m.id, EmployeePosting.is_current == True, EmployeeSalaryMapping.salary_mandal_id != m.id, EmployeeSalaryMapping.is_active == True
            ).scalar() or 0
            unavail = db.query(func.count(EmployeeStatusHistory.id)).join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeeStatusHistory.employee_id).filter(
                EmployeeSalaryMapping.salary_mandal_id == m.id, EmployeeSalaryMapping.is_active == True, EmployeeStatusHistory.is_current == True, EmployeeStatusHistory.service_status != "WORKING"
            ).scalar() or 0
            rows.append([idx, m.mandal_name, m.mandal_lgd, total_gps, vac, sal, act, dep_out, dep_in, unavail])
        return headers, rows

    # Report C: GP-wise Employee Position Report
    elif code == "C":
        headers = ["S.No", "GP LGD", "GP Name", "Mandal Name", "Salary Strength", "Working Strength", "Deputed Out", "Deputed In", "Clear Vacancy?"]
        gps = db.query(GramPanchayat)
        if target_mandal_id:
            gps = gps.filter(GramPanchayat.mandal_id == target_mandal_id)
        gps = gps.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).all()
        rows = []
        for idx, gp in enumerate(gps, start=1):
            sal = db.query(func.count(EmployeeSalaryMapping.id)).filter(EmployeeSalaryMapping.salary_gp_lgd == gp.lgd_code, EmployeeSalaryMapping.is_active == True).scalar() or 0
            act = db.query(func.count(EmployeePosting.id)).filter(EmployeePosting.actual_working_gp_lgd == gp.lgd_code, EmployeePosting.is_current == True).scalar() or 0
            dep_out = db.query(func.count(EmployeePosting.id)).join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id).filter(
                EmployeeSalaryMapping.salary_gp_lgd == gp.lgd_code, EmployeeSalaryMapping.is_active == True, EmployeePosting.is_current == True, EmployeePosting.is_working_in_salary_gp == False
            ).scalar() or 0
            dep_in = db.query(func.count(EmployeePosting.id)).join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id).filter(
                EmployeePosting.actual_working_gp_lgd == gp.lgd_code, EmployeePosting.is_current == True, EmployeeSalaryMapping.salary_gp_lgd != gp.lgd_code, EmployeeSalaryMapping.is_active == True
            ).scalar() or 0
            rows.append([idx, gp.lgd_code, gp.gp_name, gp.mandal_name, sal, act, dep_out, dep_in, "YES" if gp.is_clear_vacancy else "NO"])
        return headers, rows

    # Report D: District PS Master & Working Station Reconciliation Report (22 Mandatory Columns)
    elif code == "D":
        headers = [
            "S.No",
            "Employee Name",
            "Employee ID",
            "Mobile Number",
            "Employee Registration Mandal",
            "Salary-Claiming GP",
            "Salary-Claiming Mandal",
            "Official Deputation GP",
            "Official Deputation Mandal",
            "Deputation Order Number",
            "Deputation Order Date",
            "Deputation Effective Date",
            "Internal Reassignment From GP",
            "Internal Reassignment To GP",
            "Internal Reassignment Date",
            "Presently Working GP",
            "Presently Working Mandal",
            "Service Status",
            "Deputation Type",
            "Receiving Mandal Confirmation",
            "Verification Status",
            "Remarks"
        ]
        records = base_emp_query()
        rows = []
        for idx, (emp, sm, p, st, gp) in enumerate(records, start=1):
            # 1. Registration Mandal
            reg_mandal = emp.registration_mandal.mandal_name if emp.registration_mandal else (gp.mandal_name if gp else "N/A")
            
            # 2. Salary GP & Mandal
            sal_gp = gp.gp_name if gp else "N/A"
            sal_mandal = gp.mandal_name if gp else "N/A"
            
            # 3. Official Deputation GP & Mandal
            if p and not p.is_working_in_salary_gp:
                if p.posting_type == "OTHER_DISTRICT":
                    off_dep_gp = p.external_gp_or_office_name or "Other District Office"
                    off_dep_mandal = p.external_district_name or "Other District"
                elif p.posting_type == "OTHER_DEPARTMENT":
                    off_dep_gp = p.external_gp_or_office_name or p.external_department_name or "Department Office"
                    off_dep_mandal = p.external_department_name or "Other Department"
                elif p.official_deputation_panchayat:
                    off_dep_gp = p.official_deputation_panchayat.gp_name
                    off_dep_mandal = p.official_deputation_panchayat.mandal_name
                elif p.working_panchayat:
                    off_dep_gp = p.working_panchayat.gp_name
                    off_dep_mandal = p.working_panchayat.mandal_name
                else:
                    off_dep_gp = "Deputed (GP Not Confirmed)"
                    off_dep_mandal = "N/A"
                dep_order_no = p.deputation_order_no or "N/A"
                dep_order_date = p.deputation_order_date.strftime("%Y-%m-%d") if p.deputation_order_date else "N/A"
                dep_eff_date = p.effective_from.strftime("%Y-%m-%d") if p.effective_from else "N/A"
                dep_type = p.posting_type
            else:
                off_dep_gp = "N/A (Working in Salary GP)"
                off_dep_mandal = "N/A"
                dep_order_no = "N/A"
                dep_order_date = "N/A"
                dep_eff_date = p.effective_from.strftime("%Y-%m-%d") if (p and p.effective_from) else "N/A"
                dep_type = "REGULAR (OWN GP)"

            # 4. Internal Reassignment Details
            latest_ir = (
                db.query(InternalReassignment)
                .filter(InternalReassignment.employee_id == emp.employee_id, InternalReassignment.is_current == True)
                .order_by(InternalReassignment.id.desc())
                .first()
            )
            if latest_ir:
                ir_from = latest_ir.original_gp.gp_name if latest_ir.original_gp else (latest_ir.from_gp.gp_name if latest_ir.from_gp else "Original Deputation GP")
                ir_to = latest_ir.to_gp.gp_name if latest_ir.to_gp else "Reassigned GP"
                ir_date = latest_ir.reassignment_date.strftime("%Y-%m-%d") if latest_ir.reassignment_date else "N/A"
                ir_remarks = latest_ir.reason_remarks or ""
            else:
                ir_from = "N/A"
                ir_to = "N/A"
                ir_date = "N/A"
                ir_remarks = ""

            # 5. Presently Working GP & Mandal
            if p and p.has_internal_reassignment and p.reassigned_panchayat:
                pres_gp = p.reassigned_panchayat.gp_name
                pres_mandal = p.reassigned_panchayat.mandal_name
            elif p and p.posting_type == "OTHER_DISTRICT":
                pres_gp = p.external_gp_or_office_name or "External Office"
                pres_mandal = p.external_district_name or "Other District"
            elif p and p.posting_type == "OTHER_DEPARTMENT":
                pres_gp = p.external_gp_or_office_name or p.external_department_name or "Dept Office"
                pres_mandal = p.external_department_name or "Other Dept"
            elif p and p.working_panchayat:
                pres_gp = p.working_panchayat.gp_name
                pres_mandal = p.working_panchayat.mandal_name
            else:
                pres_gp = gp.gp_name if gp else "N/A"
                pres_mandal = gp.mandal_name if gp else "N/A"

            # 6. Service Status
            srv_status = st.service_status if st else "WORKING"

            # 7. Confirmation & Verification
            verif_stat = p.verification_status if p else "VERIFIED"
            if p and p.is_working_in_salary_gp:
                conf = "CONFIRMED (OWN GP)"
            elif p and p.verification_status == "VERIFIED":
                conf = "CONFIRMED BY RECEIVING MANDAL"
            elif p and p.verification_status == "DISCREPANCY":
                conf = "DISCREPANCY REPORTED"
            else:
                conf = "PENDING RECEIVING MANDAL CONFIRMATION"

            # 8. Remarks
            remarks_parts = []
            if ir_remarks:
                remarks_parts.append(f"Internal Reassignment: {ir_remarks}")
            if p and p.remarks:
                remarks_parts.append(p.remarks)
            if st and st.reason_remarks and st.service_status != "WORKING":
                remarks_parts.append(f"Status ({st.service_status}): {st.reason_remarks}")
            remarks_str = " | ".join(remarks_parts) if remarks_parts else "Regular Active Record"

            rows.append([
                idx,
                emp.name_ifmis,
                emp.employee_id,
                emp.mobile_number or "N/A",
                reg_mandal,
                sal_gp,
                sal_mandal,
                off_dep_gp,
                off_dep_mandal,
                dep_order_no,
                dep_order_date,
                dep_eff_date,
                ir_from,
                ir_to,
                ir_date,
                pres_gp,
                pres_mandal,
                srv_status,
                dep_type,
                conf,
                verif_stat,
                remarks_str
            ])
        return headers, rows

    # Report E: Deputation Within Same Mandal Report
    elif code == "E":
        headers = ["S.No", "Employee ID", "Employee Name", "Mobile Number", "Mandal", "Salary GP", "Actual Working GP", "Deputation Order", "Order Date", "Verification Status"]
        records = base_emp_query()
        rows = []
        idx = 1
        for emp, sm, p, st, gp in records:
            if p and p.posting_type == "WITHIN_MANDAL":
                w_gp = p.working_panchayat.gp_name if p.working_panchayat else "N/A"
                rows.append([idx, emp.employee_id, emp.name_ifmis, emp.mobile_number or "N/A", gp.mandal_name, gp.gp_name, w_gp, p.deputation_order_no or "N/A", p.deputation_order_date.strftime("%Y-%m-%d") if p.deputation_order_date else "N/A", p.verification_status])
                idx += 1
        return headers, rows

    # Report F: Deputation to Other Mandals Report
    elif code == "F":
        headers = ["S.No", "Employee ID", "Employee Name", "Mobile Number", "Salary Mandal", "Salary GP", "Destination Mandal", "Destination Working GP", "Order Details", "Verification Status"]
        records = base_emp_query()
        rows = []
        idx = 1
        for emp, sm, p, st, gp in records:
            if p and p.posting_type == "ANOTHER_MANDAL":
                w_gp = p.working_panchayat.gp_name if p.working_panchayat else "N/A"
                w_m = p.working_panchayat.mandal_name if p.working_panchayat else "N/A"
                rows.append([idx, emp.employee_id, emp.name_ifmis, emp.mobile_number or "N/A", gp.mandal_name, gp.gp_name, w_m, w_gp, p.deputation_order_no or "N/A", p.verification_status])
                idx += 1
        return headers, rows

    # Report G: Deputation to Other Districts Report
    elif code == "G":
        headers = ["S.No", "Employee ID", "Employee Name", "Mobile Number", "Salary GP", "Salary Mandal", "External District", "External Mandal", "External Office / Destination", "Proceedings No"]
        records = base_emp_query()
        rows = []
        idx = 1
        for emp, sm, p, st, gp in records:
            if p and p.posting_type == "OTHER_DISTRICT":
                rows.append([idx, emp.employee_id, emp.name_ifmis, emp.mobile_number or "N/A", gp.gp_name, gp.mandal_name, p.external_district_name or "N/A", p.external_mandal_name or "N/A", p.external_gp_or_office_name or "N/A", p.deputation_order_no or "N/A"])
                idx += 1
        return headers, rows

    # Report H: Clear Vacant Gram Panchayats – Category A ONLY (No Salary Claimant & No Deputed PS Working)
    elif code == "H":
        return _build_clear_vacancy_report(db, target_mandal_id)

    # Report I: Suspended Employees Report
    elif code == "I":
        return _build_suspension_report(base_emp_query())

    # Report J: Absconding Employees Report
    elif code == "J":
        headers = ["S.No", "Employee ID", "Employee Name", "Salary GP", "Salary Mandal", "Last Working Date", "Disciplinary Initiated?", "Remarks"]
        records = base_emp_query()
        rows = []
        idx = 1
        for emp, sm, p, st, gp in records:
            if st and st.service_status == "ABSCONDING":
                rows.append([idx, emp.employee_id, emp.name_ifmis, gp.gp_name, gp.mandal_name, _fmt_date(st.last_working_date or st.status_effective_from), "YES" if st.disciplinary_initiated else "NO", st.reason_remarks or "N/A"])
                idx += 1
        return headers, rows

    # Report K: Long Leave Employees Report
    elif code == "K":
        return _build_leave_report(base_emp_query(), {"LONG_LEAVE"})

    # Report L: Medical Leave Employees Report
    elif code == "L":
        return _build_leave_report(base_emp_query(), {"MEDICAL_LEAVE"})

    # Report M: Maternity and Child Care Leave Report
    elif code == "M":
        return _build_leave_report(base_emp_query(), {"MATERNITY_LEAVE", "CHILD_CARE_LEAVE"})

    # Report N: Other Approved Leave Report
    elif code == "N":
        return _build_leave_report(base_emp_query(), {"EARNED_LEAVE", "EXTRAORDINARY_LEAVE", "OTHER_APPROVED_LEAVE", "OTHER"})

    # Report Q: Employee-wise Deputation Chain Report
    elif code == "Q":
        return _build_deputed_ps_report(base_emp_query())

    # Report P: Expected Joining Date Crossed Report
    elif code == "P":
        headers = ["S.No", "Employee ID", "Employee Name", "Salary GP", "Salary Mandal", "Current Status", "Expected Joining Date", "Days Overdue", "Alert Notice"]
        records = base_emp_query()
        rows = []
        idx = 1
        for emp, sm, p, st, gp in records:
            if st and st.service_status != "WORKING" and st.expected_joining_date and st.expected_joining_date < today:
                overdue = (today - st.expected_joining_date).days
                rows.append([idx, emp.employee_id, emp.name_ifmis, gp.gp_name, gp.mandal_name, st.service_status, st.expected_joining_date.strftime("%Y-%m-%d"), f"{overdue} days", "STATUS UPDATE REQUIRED – VERIFY ACTUAL EMPLOYEE STATUS"])
                idx += 1
        return headers, rows

    # Report O: Employees Not Available for Regular Work Report
    elif code == "O":
        headers = ["S.No", "Employee ID", "Employee Name", "Salary GP", "Salary Mandal", "Service Status", "Effective Date", "Expected Return", "Remarks"]
        records = base_emp_query()
        rows = []
        idx = 1
        for emp, sm, p, st, gp in records:
            if st and st.service_status != "WORKING":
                rows.append([idx, emp.employee_id, emp.name_ifmis, gp.gp_name, gp.mandal_name, st.service_status, st.status_effective_from.strftime("%Y-%m-%d") if st.status_effective_from else "N/A", st.expected_joining_date.strftime("%Y-%m-%d") if st.expected_joining_date else "N/A", st.reason_remarks or "N/A"])
                idx += 1
        return headers, rows

    # Report W: Mandal-wise Data Submission Status Report
    elif code == "W":
        headers = ["S.No", "Mandal Name", "Mandal LGD", "Submission Status", "Submitted By", "Designation", "Submission Timestamp", "Locked?"]
        mandals_q = db.query(Mandal)
        if target_mandal_id:
            mandals_q = mandals_q.filter(Mandal.id == target_mandal_id)
        mandals = mandals_q.order_by(Mandal.mandal_name.asc()).all()
        rows = []
        for idx, m in enumerate(mandals, start=1):
            sub = db.query(DataSubmission).filter(DataSubmission.mandal_id == m.id).first()
            status_str = "SUBMITTED" if sub and sub.is_submitted else "PENDING SUBMISSION"
            sub_by = sub.submitted_by_name if sub and sub.is_submitted else "N/A"
            desig = sub.submitted_by_designation if sub and sub.is_submitted else "N/A"
            sub_date = sub.submitted_at.strftime("%Y-%m-%d %H:%M") if sub and sub.submitted_at else "N/A"
            locked = "YES" if sub and sub.is_locked else "NO"
            rows.append([idx, m.mandal_name, m.mandal_lgd, status_str, sub_by, desig, sub_date, locked])
        return headers, rows

    # Report T: GP-wise Employees Actually Working Report
    elif code == "T":
        headers = [
            "S.No", "GP LGD Code", "Gram Panchayat Name", "Mandal Name",
            "Position Status", "Actually Working Employee Name", "Mobile Number",
            "Employee ID", "Salary Claiming GP", "Salary Claiming Mandal", "Working Arrangement"
        ]
        gps = db.query(GramPanchayat)
        if target_mandal_id:
            gps = gps.filter(GramPanchayat.mandal_id == target_mandal_id)
        gps = gps.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).all()
        rows = []
        for idx, gp in enumerate(gps, start=1):
            working_posting = (
                db.query(EmployeePosting)
                .filter(EmployeePosting.actual_working_gp_lgd == gp.lgd_code, EmployeePosting.is_current == True)
                .first()
            )
            if working_posting:
                w_emp = db.query(Employee).filter(Employee.employee_id == working_posting.employee_id).first()
                w_sm = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == working_posting.employee_id, EmployeeSalaryMapping.is_active == True).first()
                w_sal_gp = w_sm.panchayat if w_sm else None
                
                pos_status = "CLEAR VACANCY" if gp.is_clear_vacancy else "SANCTIONED POST"
                emp_name = w_emp.name_ifmis if w_emp else working_posting.employee_id
                mobile = w_emp.mobile_number if w_emp and w_emp.mobile_number else "N/A"
                emp_id = working_posting.employee_id
                sal_gp_name = w_sal_gp.gp_name if w_sal_gp else "N/A"
                sal_mandal_name = w_sal_gp.mandal_name if w_sal_gp else "N/A"
                
                if working_posting.is_working_in_salary_gp:
                    arrangement = "Regular Working (Own Salary GP)"
                else:
                    arrangement = f"Deputed In from {sal_gp_name} ({sal_mandal_name})"
                    
                rows.append([
                    idx, gp.lgd_code, gp.gp_name, gp.mandal_name,
                    pos_status, emp_name, mobile, emp_id,
                    sal_gp_name, sal_mandal_name, arrangement
                ])
            else:
                pos_status = "CLEAR VACANCY" if gp.is_clear_vacancy else "VACANT (NO SECRETARY ON DUTY)"
                rows.append([
                    idx, gp.lgd_code, gp.gp_name, gp.mandal_name,
                    pos_status, "NO SECRETARY WORKING", "N/A", "N/A",
                    "N/A", "N/A", "Unattended Position"
                ])
        return headers, rows

    # Report U: Salary-Claiming GP with No Employee Actually Working (Category D)
    elif code == "U":
        headers = [
            "S.No", "GP LGD Code", "Gram Panchayat Name", "Mandal Name",
            "Salary Drawing Employee", "Mobile Number", "Employee ID",
            "Present Working Location", "Reason"
        ]
        records = base_emp_query()
        rows = []
        idx = 1
        for emp, sm, p, st, gp in records:
            is_deputed_out = p and not p.is_working_in_salary_gp
            is_unavailable = st and st.service_status != "WORKING"
            if is_deputed_out or is_unavailable:
                if p and p.posting_type == "OTHER_DISTRICT":
                    w_loc = f"Other District: {p.external_gp_or_office_name or 'Office'} ({p.external_district_name or ''})"
                elif p and p.posting_type == "OTHER_DEPARTMENT":
                    w_loc = f"Other Dept: {p.external_department_name or ''} ({p.external_gp_or_office_name or ''})"
                elif p and p.working_panchayat:
                    w_loc = f"{p.working_panchayat.gp_name} ({p.working_panchayat.mandal_name} Mandal)"
                else:
                    w_loc = "Not Working in GP"
                    
                reason = []
                if is_deputed_out:
                    reason.append(f"Deputed Out ({p.posting_type})")
                if is_unavailable:
                    reason.append(f"Service Status: {st.service_status}")
                    
                rows.append([
                    idx, gp.lgd_code, gp.gp_name, gp.mandal_name,
                    emp.name_ifmis, emp.mobile_number or "N/A", emp.employee_id,
                    w_loc, "; ".join(reason)
                ])
                idx += 1
        return headers, rows

    # Report V: Employees Working on Deputation in Clear Vacancies (Category B)
    elif code == "V":
        headers = [
            "S.No", "Working GP LGD Code", "Working Gram Panchayat Name", "Working Mandal Name",
            "Actually Working Employee Name", "Mobile Number", "Employee ID",
            "Salary Claiming GP", "Salary Claiming Mandal",
            "Deputation Arrangement", "Verification Status", "Vacancy Status"
        ]
        gps = db.query(GramPanchayat)
        if target_mandal_id:
            gps = gps.filter(GramPanchayat.mandal_id == target_mandal_id)
        gps = gps.order_by(GramPanchayat.mandal_name.asc(), GramPanchayat.gp_name.asc()).all()
        rows = []
        idx = 1
        for gp in gps:
            sal_count = db.query(func.count(EmployeeSalaryMapping.id)).filter(
                EmployeeSalaryMapping.salary_gp_lgd == gp.lgd_code,
                EmployeeSalaryMapping.is_active == True
            ).scalar() or 0
            
            # Find working postings in this GP
            working_postings = (
                db.query(EmployeePosting)
                .filter(EmployeePosting.actual_working_gp_lgd == gp.lgd_code, EmployeePosting.is_current == True)
                .all()
            )
            
            # CATEGORY B CONDITION: No salary claimant attached, but employee is actively working here on deputation
            if sal_count == 0 and len(working_postings) > 0:
                for wp in working_postings:
                    w_emp = db.query(Employee).filter(Employee.employee_id == wp.employee_id).first()
                    w_sm = db.query(EmployeeSalaryMapping).filter(EmployeeSalaryMapping.employee_id == wp.employee_id, EmployeeSalaryMapping.is_active == True).first()
                    w_sal_gp = w_sm.panchayat if w_sm else None
                    
                    emp_name = w_emp.name_ifmis if w_emp else wp.employee_id
                    mobile = w_emp.mobile_number if (w_emp and w_emp.mobile_number) else "N/A"
                    sal_gp_name = w_sal_gp.gp_name if w_sal_gp else "Other Office/GP"
                    sal_mandal_name = w_sal_gp.mandal_name if w_sal_gp else "N/A"
                    
                    arrangement = f"Working on Deputation ({wp.posting_type})"
                    if wp.has_internal_reassignment:
                        arrangement += " [Internally Reassigned]"
                        
                    rows.append([
                        idx,
                        gp.lgd_code,
                        gp.gp_name,
                        gp.mandal_name,
                        emp_name,
                        mobile,
                        wp.employee_id,
                        sal_gp_name,
                        sal_mandal_name,
                        arrangement,
                        wp.verification_status,
                        "CATEGORY B (CLEAR VACANCY WITH DEPUTED PS WORKING)"
                    ])
                    idx += 1
        return headers, rows

    # Fallback for remaining reports
    else:
        headers = ["S.No", "Employee ID", "Employee Name", "Salary GP", "Salary Mandal", "Posting Type", "Working Location", "Service Status", "Verification Status"]
        records = base_emp_query()
        rows = []
        for idx, (emp, sm, p, st, gp) in enumerate(records, start=1):
            if p and p.posting_type == "OTHER_DISTRICT":
                w_loc = f"{p.external_gp_or_office_name or 'External Office'} ({p.external_district_name or 'Other Dist'})"
            elif p and p.posting_type == "OTHER_DEPARTMENT":
                w_loc = f"{p.external_department_name or 'Other Dept'} ({p.external_gp_or_office_name or 'Office'})"
            elif p and p.working_panchayat:
                w_loc = f"{p.working_panchayat.gp_name} ({p.working_panchayat.mandal_name})"
            else:
                w_loc = gp.gp_name
            rows.append([idx, emp.employee_id, emp.name_ifmis, gp.gp_name, gp.mandal_name, p.posting_type if p else "OWN_GP", w_loc, st.service_status if st else "WORKING", p.verification_status if p else "PENDING"])
        return headers, rows
