from typing import Optional, List, Any
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator

# Auth schemas
class LoginRequest(BaseModel):
    username: str
    password: str
    device_info: Optional[str] = "Web Browser (Desktop/Mobile)"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    session_id: str
    user_id: int
    username: str
    display_name: str
    role: str
    mandal_id: Optional[int] = None
    mandal_name: Optional[str] = None
    mandal_lgd: Optional[int] = None
    must_change_password: bool = False

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class ForceLogoutRequest(BaseModel):
    username: Optional[str] = None
    session_id: Optional[str] = None

class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "MANDAL_ADMIN"  # SUPER_ADMIN, DISTRICT_ADMIN, MANDAL_ADMIN, VIEWER
    mandal_id: Optional[int] = None
    is_active: bool = True
    must_change_password: bool = False

    @field_validator('username')
    def validate_username(cls, v):
        v = str(v).strip()
        if not v or len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return v

    @field_validator('password')
    def validate_password(cls, v):
        v = str(v).strip()
        if not v or len(v) < 6:
            raise ValueError("Password must be at least 6 characters long")
        return v

class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    mandal_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
    must_change_password: Optional[bool] = None

class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    mandal_id: Optional[int] = None
    mandal_name: Optional[str] = None
    mandal_lgd: Optional[int] = None
    is_locked: bool
    must_change_password: bool
    is_active: bool
    created_at: datetime
    active_session: Optional[dict] = None

    class Config:
        from_attributes = True

# GP and Mandal Schemas
class MandalOut(BaseModel):
    id: int
    mandal_name: str
    mandal_lgd: int
    district_name: str
    district_lgd: int
    total_gps: Optional[int] = 0

    class Config:
        from_attributes = True

class GramPanchayatOut(BaseModel):
    id: int
    lgd_code: int
    gp_name: str
    mandal_id: int
    mandal_lgd: int
    mandal_name: str
    is_clear_vacancy: bool
    vacancy_remarks: Optional[str] = None
    vacancy_updated_at: Optional[datetime] = None
    vacancy_updated_by: Optional[str] = None

    class Config:
        from_attributes = True

class ClearVacancyUpdate(BaseModel):
    gp_lgd: int
    is_clear_vacancy: bool
    vacancy_remarks: Optional[str] = None

# Employee & Posting Schemas
class EmployeeCreateRequest(BaseModel):
    employee_id: str
    name_ifmis: str
    dob: date
    mobile_number: Optional[str] = None
    salary_gp_lgd: int
    is_working_in_salary_gp: bool = True
    
    # Service status
    service_status: str = "WORKING"
    status_effective_from: Optional[date] = None
    status_end_date: Optional[date] = None
    expected_joining_date: Optional[date] = None
    actual_joining_date: Optional[date] = None
    proceedings_order_no: Optional[str] = None
    proceedings_order_date: Optional[date] = None
    
    # Suspended specific
    suspension_order_no: Optional[str] = None
    suspension_order_date: Optional[date] = None
    suspension_effective_date: Optional[date] = None
    revocation_order_no: Optional[str] = None
    revocation_effective_date: Optional[date] = None
    
    # Absconding specific
    last_working_date: Optional[date] = None
    date_of_absence: Optional[date] = None
    disciplinary_initiated: bool = False
    
    # Leave specific
    leave_start_date: Optional[date] = None
    expected_return_date: Optional[date] = None
    leave_approval_details: Optional[str] = None
    leave_proceedings_no: Optional[str] = None
    
    reason_remarks: Optional[str] = None
    
    # Deputation details if is_working_in_salary_gp is False
    posting_type: Optional[str] = "OWN_GP" # OWN_GP, WITHIN_MANDAL, ANOTHER_MANDAL, OTHER_DISTRICT
    actual_working_gp_lgd: Optional[int] = None
    actual_working_mandal_id: Optional[int] = None
    
    # External district / department deputation
    external_district_name: Optional[str] = None
    external_mandal_name: Optional[str] = None
    external_gp_or_office_name: Optional[str] = None
    external_department_name: Optional[str] = None
    external_lgd_code: Optional[str] = None
    external_address: Optional[str] = None
    
    deputation_order_no: Optional[str] = None
    deputation_order_date: Optional[date] = None
    deputation_effective_from: Optional[date] = None
    deputation_end_date: Optional[date] = None
    deputation_remarks: Optional[str] = None
    
    # Declaration
    submitter_name: Optional[str] = None
    submitter_designation: Optional[str] = None
    declaration_agreed: bool = True
    is_draft: bool = False

class EmployeeUpdateRequest(BaseModel):
    new_employee_id: Optional[str] = None
    employee_id: Optional[str] = None
    name_ifmis: Optional[str] = None
    dob: Optional[date] = None
    mobile_number: Optional[str] = None
    designation: Optional[str] = None
    registration_mandal_id: Optional[int] = None
    salary_gp_lgd: Optional[int] = None
    salary_claiming_status: Optional[str] = None
    salary_effective_from: Optional[date] = None
    is_working_in_salary_gp: Optional[bool] = None
    posting_type: Optional[str] = None
    actual_working_gp_lgd: Optional[int] = None
    actual_working_mandal_id: Optional[int] = None
    external_district_name: Optional[str] = None
    external_mandal_name: Optional[str] = None
    external_gp_or_office_name: Optional[str] = None
    external_department_name: Optional[str] = None
    external_lgd_code: Optional[str] = None
    external_address: Optional[str] = None
    deputation_order_no: Optional[str] = None
    deputation_order_date: Optional[date] = None
    deputation_effective_from: Optional[date] = None
    deputation_end_date: Optional[date] = None
    deputation_remarks: Optional[str] = None
    
    # Status
    service_status: Optional[str] = None
    status_effective_from: Optional[date] = None
    status_end_date: Optional[date] = None
    expected_joining_date: Optional[date] = None
    actual_joining_date: Optional[date] = None
    proceedings_order_no: Optional[str] = None
    proceedings_order_date: Optional[date] = None
    suspension_order_no: Optional[str] = None
    suspension_order_date: Optional[date] = None
    suspension_effective_date: Optional[date] = None
    revocation_order_no: Optional[str] = None
    revocation_effective_date: Optional[date] = None
    last_working_date: Optional[date] = None
    date_of_absence: Optional[date] = None
    disciplinary_initiated: Optional[bool] = None
    leave_start_date: Optional[date] = None
    expected_return_date: Optional[date] = None
    leave_approval_details: Optional[str] = None
    leave_proceedings_no: Optional[str] = None
    reason_remarks: Optional[str] = None

    @field_validator(
        'dob', 'salary_effective_from', 'deputation_order_date', 'deputation_effective_from',
        'deputation_end_date', 'status_effective_from', 'status_end_date',
        'expected_joining_date', 'actual_joining_date', 'proceedings_order_date',
        'suspension_order_date', 'suspension_effective_date', 'revocation_effective_date',
        'last_working_date', 'date_of_absence', 'leave_start_date', 'expected_return_date',
        mode='before'
    )
    def parse_empty_update_dates(cls, v):
        if v == '' or v is None:
            return None
        return v

    @field_validator('mobile_number', mode='before')
    def parse_empty_update_mobile(cls, v):
        if v == '' or v is None:
            return None
        return str(v).strip()

    @field_validator('new_employee_id', 'employee_id', mode='before')
    def parse_empty_update_emp_id(cls, v):
        if v == '' or v is None:
            return None
        return str(v).strip()

class GlobalDuplicateCheckResult(BaseModel):
    is_duplicate: bool
    message: str
    existing_record: Optional[dict] = None

class TwoSideVerificationAction(BaseModel):
    posting_id: int
    action: str  # CONFIRM, REJECT, DISCREPANCY
    remarks: Optional[str] = None
    corrected_working_gp_lgd: Optional[int] = None

# ==========================================
# THREE INDEPENDENT STAGES SCHEMAS
# ==========================================

class EmployeeStage1Create(BaseModel):
    """STAGE 1: Master Registration (Independent of GP mapping)"""
    employee_id: str
    name_ifmis: str
    mobile_number: Optional[str] = None
    dob: Optional[date] = None
    designation: Optional[str] = "Panchayat Secretary"
    registration_mandal_id: Optional[int] = None
    is_draft: bool = False

    @field_validator('dob', mode='before')
    def parse_empty_dob(cls, v):
        if not v or v == '':
            return None
        return v

    @field_validator('mobile_number', mode='before')
    def parse_empty_mobile(cls, v):
        if not v or v == '':
            return None
        return v

class EmployeeStage2SalaryMapping(BaseModel):
    """STAGE 2: Salary-Claiming GP Mapping"""
    employee_id: str
    salary_gp_lgd: int
    salary_claiming_status: str = "YES"  # YES, NO
    working_from_date: Optional[date] = None
    service_status: str = "WORKING"
    reason_remarks: Optional[str] = None
    status_order_no: Optional[str] = None
    status_order_date: Optional[date] = None
    remarks: Optional[str] = None

    @field_validator('working_from_date', 'status_order_date', mode='before')
    def parse_empty_working_date(cls, v):
        if not v or v == '':
            return None
        return v

class EmployeeStage3WorkingMapping(BaseModel):
    """STAGE 3: Working Station & Deputation Mapping"""
    employee_id: str
    is_working_in_salary_gp: bool = True
    posting_type: Optional[str] = "OWN_GP"  # OWN_GP, WITHIN_MANDAL, ANOTHER_MANDAL, OTHER_DISTRICT, OTHER_DEPARTMENT
    official_deputation_gp_lgd: Optional[int] = None
    official_deputation_mandal_id: Optional[int] = None
    actual_working_gp_lgd: Optional[int] = None
    actual_working_mandal_id: Optional[int] = None
    external_district_name: Optional[str] = None
    external_mandal_name: Optional[str] = None
    external_gp_or_office_name: Optional[str] = None
    external_department_name: Optional[str] = None
    deputation_effective_from: Optional[date] = None
    deputation_order_no: Optional[str] = None
    deputation_order_date: Optional[date] = None
    remarks: Optional[str] = None

    @field_validator('deputation_effective_from', 'deputation_order_date', mode='before')
    def parse_empty_dates(cls, v):
        if not v or v == '':
            return None
        return v

class EmployeeCombinedStage2And3Mapping(BaseModel):
    """COMBINED STAGE 2: Salary GP, Service Status & Working Station Mapping"""
    employee_id: str
    # Salary GP & Service Status fields
    salary_gp_lgd: int
    salary_claiming_status: str = "YES"  # YES, NO
    working_from_date: Optional[date] = None
    service_status: str = "WORKING"
    reason_remarks: Optional[str] = None
    status_order_no: Optional[str] = None
    status_order_date: Optional[date] = None
    remarks: Optional[str] = None
    # Working Station & Deputation fields
    is_working_in_salary_gp: bool = True
    posting_type: Optional[str] = "OWN_GP"
    official_deputation_gp_lgd: Optional[int] = None
    official_deputation_mandal_id: Optional[int] = None
    actual_working_gp_lgd: Optional[int] = None
    actual_working_mandal_id: Optional[int] = None
    external_district_name: Optional[str] = None
    external_mandal_name: Optional[str] = None
    external_gp_or_office_name: Optional[str] = None
    external_department_name: Optional[str] = None
    deputation_effective_from: Optional[date] = None
    deputation_order_no: Optional[str] = None
    deputation_order_date: Optional[date] = None
    deputation_remarks: Optional[str] = None

    @field_validator('working_from_date', 'status_order_date', 'deputation_effective_from', 'deputation_order_date', mode='before')
    def parse_empty_combined_dates(cls, v):
        if not v or v == '':
            return None
        return v

class InternalReassignmentCreate(BaseModel):
    """INTERNAL REASSIGNMENT: MPDO / Receiving Mandal local arrangement change"""
    employee_id: Optional[str] = None
    posting_id: Optional[int] = None
    reassigned_to_gp_lgd: int
    reassignment_date: Optional[date] = None
    is_written_proceedings_available: bool = True
    proceedings_order_no: Optional[str] = None
    reason_remarks: str

    @field_validator('reassignment_date', mode='before')
    def parse_empty_reassign_date(cls, v):
        if not v or v == '':
            return None
        return v

class DiscrepancyResolveAction(BaseModel):
    resolution_remarks: str
    new_status: str = "RESOLVED"

class DataSubmissionPayload(BaseModel):
    submitted_by_name: str
    submitted_by_designation: str
    declaration_agreed: bool = True
