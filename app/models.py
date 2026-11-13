import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # SUPER_ADMIN, DISTRICT_ADMIN, MANDAL_ADMIN, VIEWER
    mandal_id = Column(Integer, ForeignKey("mandals.id"), nullable=True)
    mandal_lgd = Column(Integer, nullable=True)
    failed_attempts = Column(Integer, default=0)
    is_locked = Column(Boolean, default=False)
    locked_until = Column(DateTime, nullable=True)
    must_change_password = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    mandal = relationship("Mandal", back_populates="users")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mandal_id = Column(Integer, nullable=True)
    session_token_hash = Column(String(128), nullable=False)
    login_datetime = Column(DateTime, default=datetime.datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.datetime.utcnow)
    ip_address = Column(String(45), nullable=True)
    device_info = Column(String(255), nullable=True)
    session_status = Column(String(20), default="ACTIVE")  # ACTIVE, EXPIRED, TERMINATED, FORCE_LOGGED_OUT
    logout_datetime = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="sessions")

class LoginHistory(Base):
    __tablename__ = "login_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username_attempted = Column(String(50), nullable=False)
    ip_address = Column(String(45), nullable=True)
    device_info = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False)  # SUCCESS, FAILED_PASSWORD, FAILED_ALREADY_LOGGED_IN, FAILED_LOCKED, LOGOUT, FORCE_LOGOUT, TIMEOUT
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Mandal(Base):
    __tablename__ = "mandals"
    
    id = Column(Integer, primary_key=True, index=True)
    mandal_name = Column(String(100), nullable=False)
    mandal_lgd = Column(Integer, unique=True, index=True, nullable=False)
    district_name = Column(String(100), default="Khammam")
    district_lgd = Column(Integer, default=501)
    
    users = relationship("User", back_populates="mandal")
    panchayats = relationship("GramPanchayat", back_populates="mandal")

class GramPanchayat(Base):
    __tablename__ = "gram_panchayats"
    
    id = Column(Integer, primary_key=True, index=True)
    lgd_code = Column(Integer, unique=True, index=True, nullable=False)
    gp_name = Column(String(150), nullable=False)
    mandal_id = Column(Integer, ForeignKey("mandals.id"), nullable=False)
    mandal_lgd = Column(Integer, nullable=False)
    mandal_name = Column(String(100), nullable=False)
    is_clear_vacancy = Column(Boolean, default=False)
    vacancy_remarks = Column(String(255), nullable=True)
    vacancy_updated_at = Column(DateTime, nullable=True)
    vacancy_updated_by = Column(String(100), nullable=True)
    
    mandal = relationship("Mandal", back_populates="panchayats")

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), unique=True, index=True, nullable=False)
    name_ifmis = Column(String(150), nullable=False)
    dob = Column(Date, nullable=True)
    mobile_number = Column(String(15), nullable=True, index=True)
    designation = Column(String(100), default="Panchayat Secretary", nullable=True)
    registration_mandal_id = Column(Integer, ForeignKey("mandals.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    registration_mandal = relationship("Mandal", foreign_keys=[registration_mandal_id])
    salary_mappings = relationship("EmployeeSalaryMapping", back_populates="employee", cascade="all, delete-orphan")
    postings = relationship("EmployeePosting", back_populates="employee", cascade="all, delete-orphan")
    status_history = relationship("EmployeeStatusHistory", back_populates="employee", cascade="all, delete-orphan")
    internal_reassignments = relationship("InternalReassignment", back_populates="employee", cascade="all, delete-orphan")

class EmployeeSalaryMapping(Base):
    __tablename__ = "employee_salary_mapping"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    salary_gp_lgd = Column(Integer, ForeignKey("gram_panchayats.lgd_code"), nullable=False)
    salary_mandal_id = Column(Integer, ForeignKey("mandals.id"), nullable=False)
    salary_claiming_status = Column(String(20), default="YES")  # YES, NO
    service_status = Column(String(50), default="WORKING")
    effective_from = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    employee = relationship("Employee", back_populates="salary_mappings")
    panchayat = relationship("GramPanchayat", foreign_keys=[salary_gp_lgd], primaryjoin="EmployeeSalaryMapping.salary_gp_lgd == GramPanchayat.lgd_code")
    mandal = relationship("Mandal", foreign_keys=[salary_mandal_id])

class EmployeePosting(Base):
    __tablename__ = "employee_postings"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    is_working_in_salary_gp = Column(Boolean, default=True, nullable=False)
    posting_type = Column(String(50), default="OWN_GP")  # OWN_GP, WITHIN_MANDAL, ANOTHER_MANDAL, OTHER_DISTRICT, OTHER_DEPARTMENT
    actual_working_gp_lgd = Column(Integer, ForeignKey("gram_panchayats.lgd_code"), nullable=True)
    actual_working_mandal_id = Column(Integer, ForeignKey("mandals.id"), nullable=True)
    
    # Official deputation destination (preserved permanently even if internally reassigned)
    official_deputation_gp_lgd = Column(Integer, ForeignKey("gram_panchayats.lgd_code"), nullable=True)
    official_deputation_mandal_id = Column(Integer, ForeignKey("mandals.id"), nullable=True)
    
    # Internal reassignment tracking
    has_internal_reassignment = Column(Boolean, default=False)
    reassigned_working_gp_lgd = Column(Integer, ForeignKey("gram_panchayats.lgd_code"), nullable=True)

    # External district / department fields
    external_district_name = Column(String(100), nullable=True)
    external_mandal_name = Column(String(100), nullable=True)
    external_gp_or_office_name = Column(String(150), nullable=True)
    external_department_name = Column(String(150), nullable=True)
    external_lgd_code = Column(String(50), nullable=True)
    external_address = Column(String(255), nullable=True)
    
    # Deputation order fields
    deputation_order_no = Column(String(100), nullable=True)
    deputation_order_date = Column(Date, nullable=True)
    deputation_effective_from = Column(Date, nullable=True)
    deputation_end_date = Column(Date, nullable=True)
    remarks = Column(Text, nullable=True)
    
    # Two-side verification status
    verification_status = Column(String(50), default="PENDING")  # PENDING, VERIFIED_SALARY_GP, VERIFIED_RECEIVING_GP, VERIFIED_BOTH, REJECTED, DISCREPANCY
    is_current = Column(Boolean, default=True, index=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    updated_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    employee = relationship("Employee", back_populates="postings")
    working_panchayat = relationship("GramPanchayat", foreign_keys=[actual_working_gp_lgd], primaryjoin="EmployeePosting.actual_working_gp_lgd == GramPanchayat.lgd_code")
    official_deputation_panchayat = relationship("GramPanchayat", foreign_keys=[official_deputation_gp_lgd], primaryjoin="EmployeePosting.official_deputation_gp_lgd == GramPanchayat.lgd_code")
    reassigned_panchayat = relationship("GramPanchayat", foreign_keys=[reassigned_working_gp_lgd], primaryjoin="EmployeePosting.reassigned_working_gp_lgd == GramPanchayat.lgd_code")
    internal_reassignments = relationship("InternalReassignment", back_populates="posting", cascade="all, delete-orphan")

class InternalReassignment(Base):
    __tablename__ = "internal_reassignments"
    
    id = Column(Integer, primary_key=True, index=True)
    posting_id = Column(Integer, ForeignKey("employee_postings.id"), nullable=False)
    employee_id = Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    original_deputation_gp_lgd = Column(Integer, ForeignKey("gram_panchayats.lgd_code"), nullable=True)
    reassigned_from_gp_lgd = Column(Integer, ForeignKey("gram_panchayats.lgd_code"), nullable=True)
    reassigned_to_gp_lgd = Column(Integer, ForeignKey("gram_panchayats.lgd_code"), nullable=False)
    reassignment_date = Column(Date, nullable=True)
    is_written_proceedings_available = Column(Boolean, default=True)
    proceedings_order_no = Column(String(100), nullable=True)
    reason_remarks = Column(Text, nullable=False)
    is_current = Column(Boolean, default=True, index=True)
    verified_by_user = Column(String(50), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    employee = relationship("Employee", back_populates="internal_reassignments")
    posting = relationship("EmployeePosting", back_populates="internal_reassignments")
    original_gp = relationship("GramPanchayat", foreign_keys=[original_deputation_gp_lgd], primaryjoin="InternalReassignment.original_deputation_gp_lgd == GramPanchayat.lgd_code")
    from_gp = relationship("GramPanchayat", foreign_keys=[reassigned_from_gp_lgd], primaryjoin="InternalReassignment.reassigned_from_gp_lgd == GramPanchayat.lgd_code")
    to_gp = relationship("GramPanchayat", foreign_keys=[reassigned_to_gp_lgd], primaryjoin="InternalReassignment.reassigned_to_gp_lgd == GramPanchayat.lgd_code")

class EmployeeStatusHistory(Base):
    __tablename__ = "employee_status_history"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), ForeignKey("employees.employee_id"), nullable=False)
    service_status = Column(String(50), nullable=False) 
    # WORKING, SUSPENDED, ABSCONDING, LONG_LEAVE, MEDICAL_LEAVE, MATERNITY_LEAVE, CHILD_CARE_LEAVE, EARNED_LEAVE, EXTRAORDINARY_LEAVE, OTHER_APPROVED_LEAVE, OTHER
    
    status_effective_from = Column(Date, nullable=True)
    status_end_date = Column(Date, nullable=True)
    expected_joining_date = Column(Date, nullable=True)
    actual_joining_date = Column(Date, nullable=True)
    proceedings_order_no = Column(String(100), nullable=True)
    proceedings_order_date = Column(Date, nullable=True)
    
    # Suspended
    suspension_order_no = Column(String(100), nullable=True)
    suspension_order_date = Column(Date, nullable=True)
    suspension_effective_date = Column(Date, nullable=True)
    revocation_order_no = Column(String(100), nullable=True)
    revocation_effective_date = Column(Date, nullable=True)
    
    # Absconding
    last_working_date = Column(Date, nullable=True)
    date_of_absence = Column(Date, nullable=True)
    disciplinary_initiated = Column(Boolean, default=False)
    absconding_verification_status = Column(String(50), nullable=True)
    
    # Leaves
    leave_start_date = Column(Date, nullable=True)
    expected_return_date = Column(Date, nullable=True)
    leave_approval_details = Column(String(255), nullable=True)
    leave_proceedings_no = Column(String(100), nullable=True)
    
    reason_remarks = Column(Text, nullable=True)
    document_path = Column(String(255), nullable=True)
    is_current = Column(Boolean, default=True, index=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    employee = relationship("Employee", back_populates="status_history")

class GPVerification(Base):
    __tablename__ = "gp_verifications"
    
    id = Column(Integer, primary_key=True, index=True)
    posting_id = Column(Integer, ForeignKey("employee_postings.id"), nullable=False)
    employee_id = Column(String(50), nullable=False)
    salary_mandal_id = Column(Integer, nullable=False)
    receiving_mandal_id = Column(Integer, nullable=True)
    status = Column(String(50), default="PENDING")  # PENDING, CONFIRMED, REJECTED, DISCREPANCY
    receiving_remarks = Column(Text, nullable=True)
    verified_by_user = Column(String(50), nullable=True)
    verified_at = Column(DateTime, nullable=True)

class DiscrepancyRecord(Base):
    __tablename__ = "discrepancy_records"
    
    id = Column(Integer, primary_key=True, index=True)
    discrepancy_code = Column(String(50), nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(20), default="MEDIUM")  # CRITICAL, HIGH, MEDIUM, PENDING_VERIFICATION
    employee_id = Column(String(50), nullable=True)
    gp_lgd = Column(Integer, nullable=True)
    mandal_id = Column(Integer, nullable=True)
    status = Column(String(20), default="OPEN")  # OPEN, ASSIGNED, IN_REVIEW, RESOLVED
    assigned_to_mandal_id = Column(Integer, nullable=True)
    resolution_remarks = Column(Text, nullable=True)
    resolved_by = Column(String(50), nullable=True)
    detected_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

class DuplicateValidationLog(Base):
    __tablename__ = "duplicate_validation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    attempted_employee_id = Column(String(50), nullable=False)
    attempting_user = Column(String(50), nullable=False)
    attempting_mandal_id = Column(Integer, nullable=True)
    existing_mandal_id = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(50), nullable=False)
    mandal_id = Column(Integer, nullable=True)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(50), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class DataSubmission(Base):
    __tablename__ = "data_submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    mandal_id = Column(Integer, ForeignKey("mandals.id"), unique=True, nullable=False)
    is_submitted = Column(Boolean, default=False)
    submitted_by_name = Column(String(100), nullable=True)
    submitted_by_designation = Column(String(100), nullable=True)
    declaration_text = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    is_locked = Column(Boolean, default=False)
    locked_by = Column(String(50), nullable=True)
    locked_at = Column(DateTime, nullable=True)

class EmployeeDocument(Base):
    __tablename__ = "employee_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String(50), nullable=False)
    document_type = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=True)
    uploaded_by = Column(String(50), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)

class StatusNotification(Base):
    __tablename__ = "status_notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String(50), nullable=False)
    employee_id = Column(String(50), nullable=True)
    gp_lgd = Column(Integer, nullable=True)
    mandal_id = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    severity = Column(String(20), default="INFO")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
