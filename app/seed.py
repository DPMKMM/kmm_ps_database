import os
from datetime import date, datetime, timedelta
import openpyxl
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, Base
from app.models import (
    User, Mandal, GramPanchayat, Employee, EmployeeSalaryMapping,
    EmployeePosting, EmployeeStatusHistory, GPVerification, DiscrepancyRecord,
    DataSubmission, AuditLog
)
from app.auth import hash_password

def seed_database(force_reseed: bool = False):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        # Check if already seeded
        gp_count = db.query(GramPanchayat).count()
        if gp_count >= 571 and not force_reseed:
            print(f"Database already seeded with {gp_count} Gram Panchayats.")
            return

        print("Seeding database with 571 Gram Panchayats and 20 Mandals from LGD Codes.xlsx...")
        
        # 1. Read LGD Codes.xlsx
        excel_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LGD Codes.xlsx")
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        
        # Format: S.No, Mandal Name, Mandal LGD, Panchayat Name, Panchayat LGD
        rows = list(ws.iter_rows(values_only=True))[1:]  # skip header
        
        # Extract unique Mandals
        mandals_dict = {}
        for row in rows:
            if not row or not row[1]:
                continue
            mandal_name = str(row[1]).strip()
            mandal_lgd = int(row[2])
            mandals_dict[mandal_lgd] = mandal_name
            
        print(f"Discovered {len(mandals_dict)} Mandals.")
        
        # Insert Mandals
        mandal_obj_map = {}
        for m_lgd, m_name in mandals_dict.items():
            existing = db.query(Mandal).filter(Mandal.mandal_lgd == m_lgd).first()
            if not existing:
                m_obj = Mandal(
                    mandal_name=m_name,
                    mandal_lgd=m_lgd,
                    district_name="Khammam",
                    district_lgd=501
                )
                db.add(m_obj)
                db.flush()
                mandal_obj_map[m_lgd] = m_obj
            else:
                mandal_obj_map[m_lgd] = existing
                
        db.commit()
        
        # Insert 571 Gram Panchayats
        inserted_gps = 0
        for row in rows:
            if not row or not row[1] or not row[4]:
                continue
            m_name = str(row[1]).strip()
            m_lgd = int(row[2])
            gp_name = str(row[3]).strip()
            p_lgd = int(row[4])
            
            existing_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == p_lgd).first()
            if not existing_gp:
                m_obj = mandal_obj_map[m_lgd]
                gp = GramPanchayat(
                    lgd_code=p_lgd,
                    gp_name=gp_name,
                    mandal_id=m_obj.id,
                    mandal_lgd=m_lgd,
                    mandal_name=m_name,
                    is_clear_vacancy=False
                )
                db.add(gp)
                inserted_gps += 1
        
        db.commit()
        print(f"Successfully inserted {inserted_gps} Gram Panchayats.")
        
        # 2. Seed Default Accounts
        # District Super Admin
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            admin_user = User(
                username="admin",
                display_name="District Super Admin (DPO Khammam)",
                password_hash=hash_password("Admin@Khammam2026"),
                role="SUPER_ADMIN",
                is_active=True,
                must_change_password=False
            )
            db.add(admin_user)
            print("Created District Super Admin account: admin / Admin@Khammam2026")
            
        # District Viewer
        viewer_user = db.query(User).filter(User.username == "viewer").first()
        if not viewer_user:
            viewer_user = User(
                username="viewer",
                display_name="District Viewer (Collectorate Khammam)",
                password_hash=hash_password("Viewer@Khammam2026"),
                role="VIEWER",
                is_active=True,
                must_change_password=False
            )
            db.add(viewer_user)
            print("Created District Viewer account: viewer / Viewer@Khammam2026")

        # District Admin (Full Data Modification across all Mandals, no user management / no employee deletion)
        dist_admin_user = db.query(User).filter(User.username == "district_admin").first()
        if not dist_admin_user:
            dist_admin_user = User(
                username="district_admin",
                display_name="District Administrator (DPO Data Modification)",
                password_hash=hash_password("DistAdmin@Khammam2026"),
                role="DISTRICT_ADMIN",
                is_active=True,
                must_change_password=False
            )
            db.add(dist_admin_user)
            print("Created District Admin account: district_admin / DistAdmin@Khammam2026")

        # 20 Mandal Admin Accounts
        for m_lgd, m_name in mandals_dict.items():
            m_obj = mandal_obj_map[m_lgd]
            # Clean username: e.g. enkoor, or mandal_5065
            clean_name = m_name.lower().replace(" ", "").replace("(", "").replace(")", "").replace("-", "")
            username = clean_name
            
            mandal_user = db.query(User).filter(User.username == username).first()
            if not mandal_user:
                mandal_user = User(
                    username=username,
                    display_name=f"MPDO / Mandal Admin - {m_name}",
                    password_hash=hash_password(f"Mandal@{m_lgd}"),
                    role="MANDAL_ADMIN",
                    mandal_id=m_obj.id,
                    mandal_lgd=m_lgd,
                    is_active=True,
                    must_change_password=False
                )
                db.add(mandal_user)
                
            # Create DataSubmission entry for tracking submission status
            sub = db.query(DataSubmission).filter(DataSubmission.mandal_id == m_obj.id).first()
            if not sub:
                db.add(DataSubmission(
                    mandal_id=m_obj.id,
                    is_submitted=False
                ))
                
        db.commit()
        print(f"Created/verified 20 Mandal Admin accounts (Passwords: Mandal@<mandal_lgd>).")
        
        # 3. Test data disabled - Production clean state (571 GPs, 20 Mandals, 22 Users)
        # seed_sample_scenarios(db, mandal_obj_map)
        
        db.commit()
        print("Database initialization and seed completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

def seed_sample_scenarios(db: Session, mandal_obj_map: dict):
    # Dummy sample scenarios disabled - Clean production database
    return
        
    print("Seeding realistic sample scenarios covering all requirements...")
    
    # Helper to create an employee record
    def add_emp(
        emp_id, name, dob_str, salary_gp_lgd, mobile=None, is_own_gp=True,
        posting_type="OWN_GP", actual_gp_lgd=None, external_dist=None,
        external_mandal=None, external_office=None,
        dep_order=None, dep_date=None,
        service_status="WORKING", status_eff_from=None, status_end_date=None,
        exp_join_date=None, susp_order=None, susp_date=None,
        last_work_date=None, disc_init=False, leave_type=None,
        leave_start=None, leave_exp_return=None, leave_proc=None,
        remarks=None, verif_status="VERIFIED_BOTH"
    ):
        emp = Employee(
            employee_id=emp_id,
            name_ifmis=name,
            dob=datetime.strptime(dob_str, "%Y-%m-%d").date(),
            mobile_number=mobile or "98480" + emp_id.replace("TS-", "").zfill(5),
            created_by="system_seed"
        )
        db.add(emp)
        db.flush()
        
        # Find mandal for salary GP
        salary_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == salary_gp_lgd).first()
        salary_map = EmployeeSalaryMapping(
            employee_id=emp_id,
            salary_gp_lgd=salary_gp_lgd,
            salary_mandal_id=salary_gp.mandal_id,
            effective_from=date(2022, 1, 1),
            is_active=True,
            created_by="system_seed"
        )
        db.add(salary_map)
        
        # Working GP mandal
        act_mandal_id = None
        if actual_gp_lgd:
            w_gp = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == actual_gp_lgd).first()
            if w_gp:
                act_mandal_id = w_gp.mandal_id
        elif is_own_gp:
            actual_gp_lgd = salary_gp_lgd
            act_mandal_id = salary_gp.mandal_id
            
        posting = EmployeePosting(
            employee_id=emp_id,
            is_working_in_salary_gp=is_own_gp,
            posting_type=posting_type,
            actual_working_gp_lgd=actual_gp_lgd,
            actual_working_mandal_id=act_mandal_id,
            external_district_name=external_dist,
            external_mandal_name=external_mandal,
            external_gp_or_office_name=external_office,
            deputation_order_no=dep_order,
            deputation_order_date=dep_date,
            deputation_effective_from=dep_date,
            remarks=remarks,
            verification_status=verif_status,
            is_current=True,
            updated_by="system_seed"
        )
        db.add(posting)
        db.flush()
        
        # Two-side verification entry if deputed
        if not is_own_gp and posting_type != "OTHER_DISTRICT":
            verif = GPVerification(
                posting_id=posting.id,
                employee_id=emp_id,
                salary_mandal_id=salary_gp.mandal_id,
                receiving_mandal_id=act_mandal_id,
                status="CONFIRMED" if verif_status == "VERIFIED_BOTH" else "PENDING",
                receiving_remarks="Verified and joined duty as per proceedings" if verif_status == "VERIFIED_BOTH" else None,
                verified_by_user="system_verifier" if verif_status == "VERIFIED_BOTH" else None,
                verified_at=datetime.utcnow() if verif_status == "VERIFIED_BOTH" else None
            )
            db.add(verif)
        
        # Status history
        status = EmployeeStatusHistory(
            employee_id=emp_id,
            service_status=service_status,
            status_effective_from=status_eff_from or date(2022, 1, 1),
            status_end_date=status_end_date,
            expected_joining_date=exp_join_date,
            suspension_order_no=susp_order,
            suspension_order_date=susp_date,
            suspension_effective_date=susp_date,
            last_working_date=last_work_date,
            date_of_absence=last_work_date,
            disciplinary_initiated=disc_init,
            leave_start_date=leave_start,
            expected_return_date=leave_exp_return,
            leave_proceedings_no=leave_proc,
            reason_remarks=remarks,
            is_current=True,
            updated_by="system_seed"
        )
        db.add(status)

    # 1. Regular employees working in their own salary GP
    add_emp("TS-202319", "Ramesh Kumar K", "1988-06-15", 202319, is_own_gp=True, posting_type="OWN_GP", service_status="WORKING")
    add_emp("TS-202320", "Lakshmi Prasanna M", "1992-04-10", 202320, is_own_gp=True, posting_type="OWN_GP", service_status="WORKING")
    add_emp("TS-202321", "Srinivas Rao G", "1985-08-22", 202321, is_own_gp=True, posting_type="OWN_GP", service_status="WORKING")
    
    # 2. Deputation within Same Mandal (Enkoor: Bhagavan Nayak Thanda GP 202320 -> Jannaram GP 202323)
    add_emp("TS-202322", "Venkat Reddy V", "1990-11-05", 202322, is_own_gp=False, posting_type="WITHIN_MANDAL", actual_gp_lgd=202323, dep_order="ROC/A1/104/2024", dep_date=date(2024, 2, 1), service_status="WORKING", verif_status="VERIFIED_BOTH")
    
    # 3. 4-Hop Deputation Chain Example:
    # A draws salary from Kallur/Bathulapally (202361) -> Works at Kallur/China Korukondi (202364)
    add_emp("TS-1001", "Anil Kumar B (Chain Emp A)", "1989-03-12", 202361, is_own_gp=False, posting_type="WITHIN_MANDAL", actual_gp_lgd=202364, dep_order="KMM/DPO/DEP-01", dep_date=date(2023, 6, 1), verif_status="VERIFIED_BOTH")
    
    # B draws salary from Kallur/China Korukondi (202364) -> Works at Penubally/Bayyannagudem (202646)
    add_emp("TS-1002", "Bhavani Devi P (Chain Emp B)", "1991-07-19", 202364, is_own_gp=False, posting_type="ANOTHER_MANDAL", actual_gp_lgd=202646, dep_order="KMM/DPO/DEP-02", dep_date=date(2023, 7, 1), verif_status="VERIFIED_BOTH")
    
    # C draws salary from Penubally/Bayyannagudem (202646) -> Works at Sathupally/Bethupalli (202685)
    add_emp("TS-1003", "Chandra Shekar N (Chain Emp C)", "1987-12-01", 202646, is_own_gp=False, posting_type="ANOTHER_MANDAL", actual_gp_lgd=202685, dep_order="KMM/DPO/DEP-03", dep_date=date(2023, 8, 15), verif_status="VERIFIED_BOTH")
    
    # D draws salary from Sathupally/Bethupalli (202685) -> Works at Thallada/Annargudem (202732)
    add_emp("TS-1004", "Divya Vani T (Chain Emp D)", "1993-09-25", 202685, is_own_gp=False, posting_type="ANOTHER_MANDAL", actual_gp_lgd=202732, dep_order="KMM/DPO/DEP-04", dep_date=date(2023, 9, 1), verif_status="VERIFIED_BOTH")
    
    # 4. Other District Deputation (Kallur -> Suryapet District, Munagala Mandal Office)
    add_emp("TS-202365", "Krishna Murthy Ch", "1984-02-14", 202365, is_own_gp=False, posting_type="OTHER_DISTRICT", external_dist="Suryapet", external_mandal="Munagala", external_office="O/o MPDO Munagala", dep_order="G.O.Rt.No.442/PR", dep_date=date(2023, 10, 1), remarks="On inter-district deputation under special order", verif_status="VERIFIED_SALARY_GP")
    
    # 5. Suspended Employee (Kamepalli)
    add_emp("TS-202384", "Prabhakar Rao M", "1986-05-30", 202384, is_own_gp=True, posting_type="OWN_GP", service_status="SUSPENDED", susp_order="PROC-DISC/554/2025", susp_date=date(2025, 4, 15), status_eff_from=date(2025, 4, 15), remarks="Under suspension pending disciplinary inquiry under CCA rules")
    
    # 6. Absconding Employee (Madhira)
    add_emp("TS-202551", "Rajeshwar Rao P", "1990-10-10", 202551, is_own_gp=True, posting_type="OWN_GP", service_status="ABSCONDING", last_work_date=date(2025, 6, 1), disc_init=True, remarks="Unauthorized absence from duty; Show cause notice issued")
    
    # 7. Medical Leave Employee (Chinthakani) - Expected return date crossed!
    add_emp("TS-202245", "Sunitha Rani D", "1994-01-20", 202245, is_own_gp=True, posting_type="OWN_GP", service_status="MEDICAL_LEAVE", leave_start=date(2026, 8, 1), leave_exp_return=date(2026, 10, 31), exp_join_date=date(2026, 10, 31), leave_proc="ML/MED/2026/89", remarks="Medical treatment for spinal disc injury")
    
    # 8. Maternity Leave (Wyra)
    add_emp("TS-202839", "Kavitha S", "1995-11-12", 202839, is_own_gp=True, posting_type="OWN_GP", service_status="MATERNITY_LEAVE", leave_start=date(2026, 9, 1), leave_exp_return=date(2027, 2, 28), exp_join_date=date(2027, 2, 28), leave_proc="PR/MAT/2026/012", remarks="Maternity leave sanctioned for 180 days")
    
    # 9. Deputation Pending Receiving GP Verification (Yerrupalem -> Nelakondapally)
    add_emp("TS-202867", "Mohan Rao J", "1991-03-05", 202867, is_own_gp=False, posting_type="ANOTHER_MANDAL", actual_gp_lgd=202609, dep_order="DPO/KMM/DEP-771", dep_date=date(2026, 1, 10), verif_status="PENDING", remarks="Deputation order issued, physical verification awaited from receiving GP")
    
    # 10. Mark a clear vacancy GP: Mudigonda - Ammapeta (202581)
    gp_vac = db.query(GramPanchayat).filter(GramPanchayat.lgd_code == 202581).first()
    if gp_vac:
        gp_vac.is_clear_vacancy = True
        gp_vac.vacancy_remarks = "No regular Panchayat Secretary allocated. Clear vacancy since retirement."
        gp_vac.vacancy_updated_at = datetime.utcnow()
        gp_vac.vacancy_updated_by = "District Admin"

if __name__ == "__main__":
    seed_database(force_reseed=True)
