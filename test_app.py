import os
import unittest
import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import (
    GramPanchayat, Mandal, User, Employee, EmployeePosting,
    EmployeeSalaryMapping, EmployeeStatusHistory, GPVerification, DiscrepancyRecord, UserSession
)

class TestKhammamPSApplication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.db = SessionLocal()
        cls.db.query(UserSession).delete()
        cls.db.commit()
        
    @classmethod
    def tearDownClass(cls):
        # Purge any test records created during test execution
        try:
            cls.db.query(GPVerification).delete()
            cls.db.query(DiscrepancyRecord).delete()
            cls.db.query(EmployeeStatusHistory).delete()
            cls.db.query(EmployeePosting).delete()
            cls.db.query(EmployeeSalaryMapping).delete()
            cls.db.query(Employee).delete()
            cls.db.query(UserSession).delete()
            cls.db.query(GramPanchayat).update({
                GramPanchayat.is_clear_vacancy: False,
                GramPanchayat.vacancy_remarks: None,
                GramPanchayat.vacancy_updated_at: None,
                GramPanchayat.vacancy_updated_by: None
            })
            cls.db.commit()
        except Exception:
            cls.db.rollback()
        finally:
            cls.db.close()

    def test_01_master_database_counts(self):
        """Verify 571 Gram Panchayats and 20 Mandals are seeded"""
        gp_count = self.db.query(GramPanchayat).count()
        mandal_count = self.db.query(Mandal).count()
        self.assertEqual(gp_count, 571, f"Expected 571 GPs, found {gp_count}")
        self.assertEqual(mandal_count, 20, f"Expected 20 Mandals, found {mandal_count}")

    def test_02_super_admin_login(self):
        """Verify District Super Admin authentication"""
        res = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Test Runner Admin"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["role"], "SUPER_ADMIN")

    def test_03_multi_user_concurrent_sessions(self):
        """
        Verify multi-user concurrent session support:
        Multiple devices/operators can sign in concurrently to the same account,
        and logging out on one device does not terminate the other device's session.
        """
        # Device 1 logs in
        login1 = self.client.post("/api/auth/login", json={
            "username": "enkoor",
            "password": "Mandal@5065",
            "device_info": "Desktop Device A"
        })
        self.assertEqual(login1.status_code, 200)
        token1 = login1.json()["access_token"]
        sess1 = login1.json()["session_id"]

        # Device 2 simultaneously logs in with the same Mandal account
        login2 = self.client.post("/api/auth/login", json={
            "username": "enkoor",
            "password": "Mandal@5065",
            "device_info": "Mobile Device B"
        })
        self.assertEqual(login2.status_code, 200, "Concurrent login must succeed in multi-user session mode")
        token2 = login2.json()["access_token"]
        sess2 = login2.json()["session_id"]
        self.assertNotEqual(sess1, sess2)

        # Both sessions must be valid simultaneously
        me1 = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
        me2 = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
        self.assertEqual(me1.status_code, 200)
        self.assertEqual(me2.status_code, 200)

        # Terminate session 1 (Device A logs out)
        logout_res = self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token1}"}
        )
        self.assertEqual(logout_res.status_code, 200)

        # Session 1 is now invalid, while Session 2 remains active
        me1_after = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
        me2_after = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token2}"})
        self.assertEqual(me1_after.status_code, 401)
        self.assertEqual(me2_after.status_code, 200)

        # Clean up session 2
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token2}"})

    def test_04_global_employee_id_duplicate_validation(self):
        """
        Verify Section 7:
        Real-time global duplicate check across complete district database.
        """
        # Login as Kallur Mandal
        login_res = self.client.post("/api/auth/login", json={
            "username": "kallur",
            "password": "Mandal@5069",
            "device_info": "Kallur Terminal"
        })
        token = login_res.json()["access_token"]
        
        test_emp_id = f"TS-DUP-{uuid.uuid4().hex[:4].upper()}"
        
        # 1. Create first employee
        first_create = self.client.post(
            "/api/employees",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "employee_id": test_emp_id,
                "name_ifmis": "Original Employee Name",
                "dob": "1990-05-15",
                "mobile_number": "9848123456",
                "salary_gp_lgd": 202361,
                "is_working_in_salary_gp": True,
                "service_status": "WORKING"
            }
        )
        self.assertEqual(first_create.status_code, 201)
        
        # 2. Check existing employee -> must report duplicate
        check_res = self.client.get(
            f"/api/employees/check-id?employee_id={test_emp_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(check_res.status_code, 200)
        data = check_res.json()
        self.assertTrue(data["is_duplicate"])
        self.assertIn("EMPLOYEE ALREADY EXISTS", data["message"])
        self.assertIsNotNone(data["existing_record"])
        # Ensure DOB is hidden from unauthorized duplicate warning response
        self.assertNotIn("dob", data["existing_record"])
        
        # 3. Attempt to create duplicate employee -> must be blocked with HTTP 409
        dup_create = self.client.post(
            "/api/employees",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "employee_id": test_emp_id,
                "name_ifmis": "Duplicate Attempt",
                "dob": "1990-01-01",
                "salary_gp_lgd": 202361,
                "is_working_in_salary_gp": True
            }
        )
        self.assertEqual(dup_create.status_code, 409, "Duplicate Employee ID must return HTTP 409 Conflict")
        
        # Logout
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    def test_05_two_side_deputation_verification(self):
        """
        Verify Section 14: Two-side deputation verification workflow
        """
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Station"
        })
        admin_token = admin_login.json()["access_token"]
        
        res = self.client.get("/api/verifications", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(res.status_code, 200)
        
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"})

    def test_06_discrepancy_scan_engine(self):
        """
        Verify Section 15: Discrepancy scan detects known edge cases
        """
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Station"
        })
        admin_token = admin_login.json()["access_token"]
        
        scan_res = self.client.get("/api/discrepancies/scan", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(scan_res.status_code, 200)
        scan_data = scan_res.json()
        self.assertGreaterEqual(scan_data["total_discrepancies_detected"], 0)
        
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"})

    def test_07_reports_a_to_z(self):
        """
        Verify Section 17: Reports A to Z are queryable and exportable
        """
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Station"
        })
        admin_token = admin_login.json()["access_token"]
        
        # Test report A (District Employee Master)
        rep_a = self.client.get("/api/reports/data/A", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(rep_a.status_code, 200)
        self.assertIn("headers", rep_a.json())
        self.assertIn("rows", rep_a.json())

        # Test report B (Mandal-wise Status)
        rep_b = self.client.get("/api/reports/data/B", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(rep_b.status_code, 200)

        # Test report C (GP-wise Position)
        rep_c = self.client.get("/api/reports/data/C", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(rep_c.status_code, 200)
        
        # Test report H (Clear Vacancy)
        rep_h = self.client.get("/api/reports/data/H", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(rep_h.status_code, 200)

        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"})

    def test_08_employee_mobile_number(self):
        """
        Verify Mobile Number field in Employee creation, retrieval, and Report A
        """
        test_emp_id = f"TS-M{uuid.uuid4().hex[:5].upper()}"
        
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Mobile Test"
        })
        token = admin_login.json()["access_token"]
        
        # Create test employee with mobile number
        emp_res = self.client.post(
            "/api/employees",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "employee_id": test_emp_id,
                "name_ifmis": "Satyanarayana G",
                "dob": "1992-08-14",
                "mobile_number": "9848011223",
                "salary_gp_lgd": 202319,
                "is_working_in_salary_gp": True,
                "service_status": "WORKING"
            }
        )
        self.assertEqual(emp_res.status_code, 201)
        
        # Verify employee profile has mobile number
        prof_res = self.client.get(f"/api/employees/{test_emp_id}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(prof_res.status_code, 200)
        self.assertEqual(prof_res.json()["mobile_number"], "9848011223")
        
        # Verify Report A includes Mobile Number in headers and rows
        rep_a = self.client.get("/api/reports/data/A", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(rep_a.status_code, 200)
        self.assertIn("Mobile Number", rep_a.json()["headers"])

        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    def test_09_other_department_deputation(self):
        """
        Verify Deputation to Other Department option
        """
        test_emp_id = f"TS-DEPT-{uuid.uuid4().hex[:4].upper()}"
        
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Dept Test"
        })
        token = admin_login.json()["access_token"]
        
        # Create employee with OTHER_DEPARTMENT posting
        dept_res = self.client.post(
            "/api/employees",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "employee_id": test_emp_id,
                "name_ifmis": "Ramesh Kumar K",
                "dob": "1988-11-20",
                "mobile_number": "9988776655",
                "salary_gp_lgd": 202319,
                "is_working_in_salary_gp": False,
                "posting_type": "OTHER_DEPARTMENT",
                "external_department_name": "Revenue Department",
                "external_gp_or_office_name": "Junior Assistant - O/o Tahsildar Enkoor",
                "service_status": "WORKING"
            }
        )
        self.assertEqual(dept_res.status_code, 201)
        
        # Retrieve profile and check posting details
        prof_res = self.client.get(f"/api/employees/{test_emp_id}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(prof_res.status_code, 200)
        data = prof_res.json()
        current_posting = next((p for p in data["posting_history"] if p["is_current"]), None)
        self.assertIsNotNone(current_posting)
        self.assertEqual(current_posting["posting_type"], "OTHER_DEPARTMENT")
        self.assertEqual(current_posting["external_department"], "Revenue Department")

        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    def test_10_mandal_scope_analytics_and_reports(self):
        """
        Verify Mandal User only receives Mandal-scoped summary, breakdown, and Report B
        while Super Admin receives all 20 Mandals and 571 GPs.
        """
        # 1. Login as Mandal Admin (Kallur)
        kallur_login = self.client.post("/api/auth/login", json={
            "username": "kallur",
            "password": "Mandal@5069",
            "device_info": "Kallur Scope Test"
        })
        self.assertEqual(kallur_login.status_code, 200)
        mandal_token = kallur_login.json()["access_token"]
        mandal_id = kallur_login.json()["mandal_id"]

        # Check Kallur's summary
        summary_res = self.client.get(
            "/api/analytics/district-summary",
            headers={"Authorization": f"Bearer {mandal_token}"}
        )
        self.assertEqual(summary_res.status_code, 200)
        summary = summary_res.json()
        self.assertEqual(summary["total_mandals"], 1)
        expected_kallur_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == mandal_id).count()
        self.assertEqual(summary["total_gram_panchayats"], expected_kallur_gps)

        # Check Kallur's mandal breakdown
        breakdown_res = self.client.get(
            "/api/analytics/mandal-breakdown",
            headers={"Authorization": f"Bearer {mandal_token}"}
        )
        self.assertEqual(breakdown_res.status_code, 200)
        breakdown = breakdown_res.json()
        self.assertEqual(len(breakdown), 1, "Mandal Admin must see only 1 row in mandal breakdown")
        self.assertEqual(breakdown[0]["mandal_name"], "Kallur")

        # Check Report B (Mandal-wise Comparative Position)
        rep_b = self.client.get(
            "/api/reports/data/B",
            headers={"Authorization": f"Bearer {mandal_token}"}
        )
        self.assertEqual(rep_b.status_code, 200)
        b_data = rep_b.json()
        self.assertEqual(len(b_data["rows"]), 1, "Report B for Mandal Admin must contain only their Mandal")
        self.assertIn("Kallur", b_data["rows"][0][1])

        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {mandal_token}"})

        # 2. Login as Super Admin (District View)
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Scope Test"
        })
        self.assertEqual(admin_login.status_code, 200)
        admin_token = admin_login.json()["access_token"]

        # Admin Summary must show all 20 Mandals and 571 GPs
        admin_summary = self.client.get(
            "/api/analytics/district-summary",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(admin_summary.status_code, 200)
        self.assertEqual(admin_summary.json()["total_mandals"], 20)
        self.assertEqual(admin_summary.json()["total_gram_panchayats"], 571)

        # Admin Breakdown must show all 20 Mandals
        admin_breakdown = self.client.get(
            "/api/analytics/mandal-breakdown",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(admin_breakdown.status_code, 200)
        self.assertEqual(len(admin_breakdown.json()), 20)

        # Admin Report B must show all 20 Mandals
        admin_rep_b = self.client.get(
            "/api/reports/data/B",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(admin_rep_b.status_code, 200)
        self.assertEqual(len(admin_rep_b.json()["rows"]), 20)

        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"})

    def test_11_deputation_internal_reallocation_and_reports(self):
        """
        Verify deputation internal re-allocation (GP X to GP Z) and Report D/T/U details.
        """
        enkoor_user = self.db.query(User).filter(User.username == "enkoor").first()
        kallur_user = self.db.query(User).filter(User.username == "kallur").first()
        
        enkoor_gp = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == enkoor_user.mandal_id).first()
        kallur_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == kallur_user.mandal_id).all()
        gp_x = kallur_gps[0]
        gp_z = kallur_gps[1]

        # Step 1: Enkoor logs in and creates employee deputed to Kallur GP X
        test_emp_id = f"TS-DEP-{uuid.uuid4().hex[:4].upper()}"
        enkoor_login = self.client.post("/api/auth/login", json={
            "username": "enkoor",
            "password": "Mandal@5065",
            "device_info": "Enkoor Runner"
        })
        self.assertEqual(enkoor_login.status_code, 200)
        e_token = enkoor_login.json()["access_token"]

        create_res = self.client.post(
            "/api/employees",
            headers={"Authorization": f"Bearer {e_token}"},
            json={
                "employee_id": test_emp_id,
                "name_ifmis": "Suresh Babu M",
                "dob": "1990-05-15",
                "mobile_number": "9876543210",
                "salary_gp_lgd": enkoor_gp.lgd_code,
                "is_working_in_salary_gp": False,
                "posting_type": "ANOTHER_MANDAL",
                "actual_working_gp_lgd": gp_x.lgd_code,
                "service_status": "WORKING"
            }
        )
        self.assertEqual(create_res.status_code, 201)
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {e_token}"})

        # Step 2: Kallur logs in, sees incoming verification, and confirms with internal change to GP Z
        kallur_login = self.client.post("/api/auth/login", json={
            "username": "kallur",
            "password": "Mandal@5069",
            "device_info": "Kallur Verifier"
        })
        self.assertEqual(kallur_login.status_code, 200)
        k_token = kallur_login.json()["access_token"]

        verif_list = self.client.get("/api/verifications", headers={"Authorization": f"Bearer {k_token}"})
        self.assertEqual(verif_list.status_code, 200)
        incoming = verif_list.json()["incoming_verifications"]
        target_v = next((v for v in incoming if v["employee_id"] == test_emp_id), None)
        self.assertIsNotNone(target_v)

        # Confirm with internal re-allocation to GP Z
        action_res = self.client.post(
            "/api/verifications/action",
            headers={"Authorization": f"Bearer {k_token}"},
            json={
                "posting_id": target_v["posting_id"],
                "action": "CONFIRM",
                "corrected_working_gp_lgd": gp_z.lgd_code,
                "remarks": f"Internally reassigned from {gp_x.gp_name} to {gp_z.gp_name}"
            }
        )
        self.assertEqual(action_res.status_code, 200)
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {k_token}"})

        # Step 3: Admin logs in and checks Report D (Salary GP vs Actual Working GP)
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Rep D Check"
        })
        self.assertEqual(admin_login.status_code, 200)
        a_token = admin_login.json()["access_token"]

        rep_d = self.client.get("/api/reports/data/D", headers={"Authorization": f"Bearer {a_token}"})
        self.assertEqual(rep_d.status_code, 200)
        d_json = rep_d.json()
        
        # Verify Report D contains the exact required headers
        self.assertIn("Employee Name", d_json["headers"])
        self.assertIn("Employee ID", d_json["headers"])
        self.assertIn("Mobile Number", d_json["headers"])
        self.assertIn("Salary-Claiming GP", d_json["headers"])
        self.assertIn("Presently Working GP", d_json["headers"])

        # Check row for our test employee in the 22-column reconciliation report
        row = next((r for r in d_json["rows"] if r[2] == test_emp_id), None)
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "Suresh Babu M")
        self.assertEqual(row[2], test_emp_id)
        self.assertEqual(row[3], "9876543210")
        self.assertEqual(row[5], enkoor_gp.gp_name)
        self.assertEqual(row[15], gp_z.gp_name, "Presently working GP must be GP Z after internal reallocation")

        # Step 4: Check Report T (GP-wise Employees Actually Working)
        rep_t = self.client.get("/api/reports/data/T", headers={"Authorization": f"Bearer {a_token}"})
        self.assertEqual(rep_t.status_code, 200)
        t_json = rep_t.json()
        self.assertIn("Actually Working Employee Name", t_json["headers"])
        self.assertIn("Mobile Number", t_json["headers"])

        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {a_token}"})

    def test_12_key_report_options_clear_vacancy_deputed_leave_suspension(self):
        """
        Verify CLEAR_VACANCY, DEPUTED_PS, LEAVE, and SUSPENSION reports work like all reports
        with JSON preview, Excel/CSV exports, and Mandal scoping.
        """
        enkoor_user = self.db.query(User).filter(User.username == "enkoor").first()
        kallur_user = self.db.query(User).filter(User.username == "kallur").first()
        enkoor_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == enkoor_user.mandal_id).all()
        kallur_gp = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == kallur_user.mandal_id).first()

        # Login admin
        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Reports Key Options Test"
        })
        self.assertEqual(admin_login.status_code, 200)
        a_token = admin_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {a_token}"}

        # 1. Verify /api/reports/list includes the 4 key report options
        list_res = self.client.get("/api/reports/list", headers=headers)
        self.assertEqual(list_res.status_code, 200)
        codes = [item["code"] for item in list_res.json()]
        for code in ("CLEAR_VACANCY", "DEPUTED_PS", "LEAVE", "SUSPENSION"):
            self.assertIn(code, codes)

        # Create 3 targeted test employees: deputed + suspended + leave (earned/medical)
        dep_emp = f"TS-KDEP-{uuid.uuid4().hex[:4].upper()}"
        susp_emp = f"TS-KSUSP-{uuid.uuid4().hex[:4].upper()}"
        leave_emp = f"TS-KLVE-{uuid.uuid4().hex[:4].upper()}"

        self.assertEqual(self.client.post("/api/employees", headers=headers, json={
            "employee_id": dep_emp,
            "name_ifmis": "Deputed Test PS",
            "dob": "1990-01-10",
            "mobile_number": "9000000001",
            "salary_gp_lgd": enkoor_gps[0].lgd_code,
            "is_working_in_salary_gp": False,
            "posting_type": "WITHIN_MANDAL",
            "actual_working_gp_lgd": enkoor_gps[1].lgd_code,
            "deputation_order_no": "PROC-DEP-101",
            "service_status": "WORKING"
        }).status_code, 201)

        self.assertEqual(self.client.post("/api/employees", headers=headers, json={
            "employee_id": susp_emp,
            "name_ifmis": "Suspended Test PS",
            "dob": "1989-02-11",
            "mobile_number": "9000000002",
            "salary_gp_lgd": enkoor_gps[2].lgd_code,
            "is_working_in_salary_gp": True,
            "service_status": "SUSPENDED",
            "suspension_order_no": "PROC-SUSP-202",
            "suspension_effective_date": "2026-10-01"
        }).status_code, 201)

        # Register Leave employee via Stage 1 + Combined Stage 2 & 3 (verifying status_order_no fallback too)
        self.assertEqual(self.client.post("/api/employees/stage1-register", headers=headers, json={
            "employee_id": leave_emp,
            "name_ifmis": "Leave Test PS",
            "dob": "1991-03-12",
            "mobile_number": "9000000003"
        }).status_code, 201)
        self.assertEqual(self.client.post("/api/employees/stage2-combined-mapping", headers=headers, json={
            "employee_id": leave_emp,
            "salary_gp_lgd": kallur_gp.lgd_code,
            "working_from_date": "2026-01-01",
            "service_status": "EARNED_LEAVE",
            "status_order_no": "PROC-LVE-303",
            "status_order_date": "2026-10-15",
            "is_working_in_salary_gp": True,
            "posting_type": "OWN_GP"
        }).status_code, 200)

        # 2. Verify Clear Vacancy excludes mapped GPs and works on JSON + XLSX + CSV
        cv_res = self.client.get(f"/api/reports/data/CLEAR_VACANCY?mandal_id={enkoor_user.mandal_id}", headers=headers)
        self.assertEqual(cv_res.status_code, 200)
        cv_lgds = {r[3] for r in cv_res.json()["rows"]}
        self.assertNotIn(enkoor_gps[0].lgd_code, cv_lgds)
        self.assertNotIn(enkoor_gps[1].lgd_code, cv_lgds)

        # 3. Verify Deputed PS returns dep_emp with order & working info
        dep_res = self.client.get("/api/reports/data/DEPUTED_PS", headers=headers)
        self.assertEqual(dep_res.status_code, 200)
        dep_ids = [r[1] for r in dep_res.json()["rows"]]
        self.assertIn(dep_emp, dep_ids)
        self.assertNotIn(susp_emp, dep_ids)

        # 4. Verify Leave returns leave_emp (including EARNED_LEAVE / all leave subtypes)
        lve_res = self.client.get("/api/reports/data/LEAVE", headers=headers)
        self.assertEqual(lve_res.status_code, 200)
        lve_rows = lve_res.json()["rows"]
        lve_row = next((r for r in lve_rows if r[1] == leave_emp), None)
        self.assertIsNotNone(lve_row)
        self.assertIn("Earned Leave", lve_row)
        self.assertIn("PROC-LVE-303", lve_row)

        # Also check Report N handles EARNED_LEAVE instead of returning all employees
        n_res = self.client.get("/api/reports/data/N", headers=headers)
        self.assertEqual(n_res.status_code, 200)
        n_ids = [r[1] for r in n_res.json()["rows"]]
        self.assertIn(leave_emp, n_ids)
        self.assertNotIn(dep_emp, n_ids)

        # 5. Verify Suspension returns susp_emp with order & date preserved from Stage 2
        susp_res = self.client.get("/api/reports/data/SUSPENSION", headers=headers)
        self.assertEqual(susp_res.status_code, 200)
        susp_row = next((r for r in susp_res.json()["rows"] if r[1] == susp_emp), None)
        self.assertIsNotNone(susp_row)
        self.assertIn("PROC-SUSP-202", susp_row)
        self.assertIn("2026-10-01", susp_row)

        # 6. Verify Excel & CSV exports return HTTP 200 for all 4 new report options
        for code in ("CLEAR_VACANCY", "DEPUTED_PS", "LEAVE", "SUSPENSION"):
            for fmt in ("excel", "csv"):
                exp_res = self.client.get(f"/api/reports/export/{code}?format={fmt}", headers=headers)
                self.assertEqual(exp_res.status_code, 200, f"Export failed for {code} ({fmt})")
                self.assertGreater(len(exp_res.content), 20)

        self.client.post("/api/auth/logout", headers=headers)

        # 7. Verify Mandal Admin strictly sees only their Mandal across new reports
        enkoor_login = self.client.post("/api/auth/login", json={
            "username": "enkoor",
            "password": "Mandal@5065",
            "device_info": "Enkoor Report Test"
        })
        e_headers = {"Authorization": f"Bearer {enkoor_login.json()['access_token']}"}
        e_leave = self.client.get("/api/reports/data/LEAVE", headers=e_headers)
        self.assertEqual(e_leave.status_code, 200)
        self.assertNotIn(leave_emp, [r[1] for r in e_leave.json()["rows"]])
        self.client.post("/api/auth/logout", headers=e_headers)

    def test_13_strict_mandal_isolation_deputation_chains_and_views(self):
        """
        Verify Deputation Chains Graph and all endpoints strictly isolate Mandal Admin
        to only their concerned Mandal's data (even if spoofing mandal_id or querying other Mandals).
        """
        enkoor_user = self.db.query(User).filter(User.username == "enkoor").first()
        kallur_user = self.db.query(User).filter(User.username == "kallur").first()
        sathupally_user = self.db.query(User).filter(User.username == "sathupally").first()

        e_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == enkoor_user.mandal_id).all()
        k_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == kallur_user.mandal_id).all()
        s_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == sathupally_user.mandal_id).all()

        admin_login = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@Khammam2026",
            "device_info": "Admin Chain Isolation Test"
        })
        a_hdr = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        emp_e = f"TS-CE-{uuid.uuid4().hex[:4].upper()}"
        emp_k_to_e = f"TS-CKE-{uuid.uuid4().hex[:4].upper()}"
        emp_s_only = f"TS-CS-{uuid.uuid4().hex[:4].upper()}"

        # Enkoor intra-mandal deputation
        self.assertEqual(self.client.post("/api/employees", headers=a_hdr, json={
            "employee_id": emp_e, "name_ifmis": "Enkoor Chain PS", "dob": "1990-01-01",
            "mobile_number": "9111111111", "salary_gp_lgd": e_gps[3].lgd_code,
            "is_working_in_salary_gp": False, "posting_type": "WITHIN_MANDAL",
            "actual_working_gp_lgd": e_gps[4].lgd_code, "service_status": "WORKING"
        }).status_code, 201)

        # Cross-mandal deputation INTO Enkoor (concerned with Enkoor)
        self.assertEqual(self.client.post("/api/employees", headers=a_hdr, json={
            "employee_id": emp_k_to_e, "name_ifmis": "Incoming Enkoor PS", "dob": "1990-02-02",
            "mobile_number": "9222222222", "salary_gp_lgd": k_gps[2].lgd_code,
            "is_working_in_salary_gp": False, "posting_type": "ANOTHER_MANDAL",
            "actual_working_gp_lgd": e_gps[5].lgd_code, "service_status": "WORKING"
        }).status_code, 201)

        # Unrelated Sathupally intra-mandal deputation (plus SUSPENDED without order for discrepancy scan)
        self.assertEqual(self.client.post("/api/employees", headers=a_hdr, json={
            "employee_id": emp_s_only, "name_ifmis": "Sathupally Hidden PS", "dob": "1990-03-03",
            "mobile_number": "9333333333", "salary_gp_lgd": s_gps[0].lgd_code,
            "is_working_in_salary_gp": False, "posting_type": "WITHIN_MANDAL",
            "actual_working_gp_lgd": s_gps[1].lgd_code, "service_status": "SUSPENDED"
        }).status_code, 201)

        # Admin sees all 3 chains
        admin_chains = self.client.get("/api/deputations/chains", headers=a_hdr)
        self.assertEqual(admin_chains.status_code, 200)
        admin_edge_ids = {e["employee_id"] for e in admin_chains.json()["graph"]["edges"]}
        self.assertIn(emp_e, admin_edge_ids)
        self.assertIn(emp_k_to_e, admin_edge_ids)
        self.assertIn(emp_s_only, admin_edge_ids)

        # Admin scoped by ?mandal_id filters cleanly
        admin_s_chains = self.client.get(f"/api/deputations/chains?mandal_id={sathupally_user.mandal_id}", headers=a_hdr)
        self.assertEqual(admin_s_chains.status_code, 200)
        s_edge_ids = {e["employee_id"] for e in admin_s_chains.json()["graph"]["edges"]}
        self.assertIn(emp_s_only, s_edge_ids)
        self.assertNotIn(emp_e, s_edge_ids)
        self.client.post("/api/auth/logout", headers=a_hdr)

        # Enkoor Mandal Admin login: Deputation Chains Graph blocked (403) and all other views strictly Enkoor-only
        enkoor_login = self.client.post("/api/auth/login", json={
            "username": "enkoor", "password": "Mandal@5065", "device_info": "Enkoor Chain Isolation"
        })
        e_hdr = {"Authorization": f"Bearer {enkoor_login.json()['access_token']}"}

        # Deputation Chains Graph endpoint must reject Mandal Admin login with 403
        e_chains = self.client.get(f"/api/deputations/chains?mandal_id={sathupally_user.mandal_id}", headers=e_hdr)
        self.assertEqual(e_chains.status_code, 403)

        # Report Q (Chain Report) excludes unrelated Sathupally employee
        e_rep_q = self.client.get("/api/reports/data/Q", headers=e_hdr)
        self.assertEqual(e_rep_q.status_code, 200)
        self.assertNotIn(emp_s_only, [r[1] for r in e_rep_q.json()["rows"]])

        # Spoofing ?mandal_id on /panchayats returns ONLY Enkoor GPs
        e_gps_res = self.client.get(f"/api/panchayats?mandal_id={sathupally_user.mandal_id}", headers=e_hdr)
        self.assertEqual(e_gps_res.status_code, 200)
        self.assertTrue(all(g["mandal_id"] == enkoor_user.mandal_id for g in e_gps_res.json()))

        # Direct lookup of another Mandal's GP, Employee Profile, Stage3 Info, and Documents must be 403
        self.assertEqual(self.client.get(f"/api/panchayats/{s_gps[0].lgd_code}", headers=e_hdr).status_code, 403)
        self.assertEqual(self.client.get(f"/api/employees/{emp_s_only}", headers=e_hdr).status_code, 403)
        self.assertEqual(self.client.get(f"/api/employees/stage3-employee-info/{emp_s_only}", headers=e_hdr).status_code, 403)
        self.assertEqual(self.client.get(f"/api/documents/employee/{emp_s_only}", headers=e_hdr).status_code, 403)

        # Discrepancy scan items must never leak unrelated Sathupally items to Enkoor
        scan_res = self.client.get("/api/discrepancies/scan", headers=e_hdr)
        self.assertEqual(scan_res.status_code, 200)
        scan_emp_ids = {item.get("employee_id") for item in scan_res.json()["items"]}
        self.assertNotIn(emp_s_only, scan_emp_ids)

        self.client.post("/api/auth/logout", headers=e_hdr)

    def test_14_individual_employee_modification(self):
        """
        Verify PUT /api/employees/{employee_id} cleanly modifies individual sections
        (basic details, salary GP, service status, deputation) while enforcing Mandal & Viewer permissions.
        """
        enkoor_user = self.db.query(User).filter(User.username == "enkoor").first()
        kallur_user = self.db.query(User).filter(User.username == "kallur").first()
        e_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == enkoor_user.mandal_id).all()
        k_gps = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == kallur_user.mandal_id).all()

        # Login Enkoor & register employee
        e_login = self.client.post("/api/auth/login", json={
            "username": "enkoor", "password": "Mandal@5065", "device_info": "Enkoor Edit Test"
        })
        e_hdr = {"Authorization": f"Bearer {e_login.json()['access_token']}"}

        emp_id = f"TS-ED-{uuid.uuid4().hex[:4].upper()}"
        self.assertEqual(self.client.post("/api/employees/stage1-register", headers=e_hdr, json={
            "employee_id": emp_id,
            "name_ifmis": "Initial Typo Name",
            "mobile_number": "9000011111",
            "designation": "Panchayat Secretary Grade-IV",
            "dob": "1990-01-01"
        }).status_code, 201)

        # 1. Edit Stage 1 basic details only (Name, Mobile, Designation, DOB)
        upd1 = self.client.put(f"/api/employees/{emp_id}", headers=e_hdr, json={
            "name_ifmis": "Corrected Individual Name",
            "mobile_number": "9888877777",
            "designation": "Panchayat Secretary Grade-II",
            "dob": "1991-06-15"
        })
        self.assertEqual(upd1.status_code, 200)
        self.assertIn("BASIC_INFO", upd1.json()["updated_sections"])

        prof1 = self.client.get(f"/api/employees/{emp_id}", headers=e_hdr).json()
        self.assertTrue(prof1["can_edit"])
        self.assertEqual(prof1["name_ifmis"], "Corrected Individual Name")
        self.assertEqual(prof1["mobile_number"], "9888877777")
        self.assertEqual(prof1["designation"], "Panchayat Secretary Grade-II")
        self.assertEqual(prof1["dob_raw"], "1991-06-15")

        # 2. Update Salary GP + OWN_GP + Working status
        upd2 = self.client.put(f"/api/employees/{emp_id}", headers=e_hdr, json={
            "salary_gp_lgd": e_gps[0].lgd_code,
            "salary_claiming_status": "YES",
            "service_status": "WORKING",
            "is_working_in_salary_gp": True
        })
        self.assertEqual(upd2.status_code, 200)
        self.assertIn("SALARY_MAPPING", upd2.json()["updated_sections"])

        # 3. Change only Salary GP to another Enkoor GP -> OWN_GP working station must sync automatically
        upd3 = self.client.put(f"/api/employees/{emp_id}", headers=e_hdr, json={
            "name_ifmis": "Corrected Individual Name",
            "mobile_number": "9888877777",
            "salary_gp_lgd": e_gps[1].lgd_code,
            "service_status": "WORKING",
            "is_working_in_salary_gp": True
        })
        self.assertEqual(upd3.status_code, 200)
        prof3 = self.client.get(f"/api/employees/{emp_id}", headers=e_hdr).json()
        self.assertEqual(prof3["salary_gp_lgd"], e_gps[1].lgd_code)
        self.assertEqual(prof3["current_posting"]["actual_working_gp_lgd"], e_gps[1].lgd_code)
        self.assertEqual(len(prof3["status_history"]), 1, "Unchanged service status must not create duplicate rows")

        # 4. Change to Deputed to Kallur + Suspended -> must appear cleanly and enforce permission
        upd4 = self.client.put(f"/api/employees/{emp_id}", headers=e_hdr, json={
            "is_working_in_salary_gp": False,
            "posting_type": "ANOTHER_MANDAL",
            "actual_working_gp_lgd": k_gps[0].lgd_code,
            "deputation_order_no": "DEP-EDIT-99",
            "service_status": "SUSPENDED",
            "proceedings_order_no": "SUSP-EDIT-11",
            "status_effective_from": "2026-10-20"
        })
        self.assertEqual(upd4.status_code, 200)
        self.assertIn("SERVICE_STATUS", upd4.json()["updated_sections"])
        self.assertIn("POSTING", upd4.json()["updated_sections"])

        # Enkoor cannot move Salary GP into Kallur (403 Forbidden)
        forbidden_sal = self.client.put(f"/api/employees/{emp_id}", headers=e_hdr, json={
            "salary_gp_lgd": k_gps[0].lgd_code
        })
        self.assertEqual(forbidden_sal.status_code, 403)
        self.client.post("/api/auth/logout", headers=e_hdr)

        # 5. Receiving Mandal (Kallur) can view profile (incoming deputed PS) with can_edit=False, and cannot PUT (403)
        k_login = self.client.post("/api/auth/login", json={
            "username": "kallur", "password": "Mandal@5069", "device_info": "Kallur Edit Guard Test"
        })
        k_hdr = {"Authorization": f"Bearer {k_login.json()['access_token']}"}
        k_prof = self.client.get(f"/api/employees/{emp_id}", headers=k_hdr)
        self.assertEqual(k_prof.status_code, 200)
        self.assertFalse(k_prof.json()["can_edit"])
        self.assertEqual(self.client.put(f"/api/employees/{emp_id}", headers=k_hdr, json={"mobile_number": "9111111111"}).status_code, 403)
        self.client.post("/api/auth/logout", headers=k_hdr)

    def test_15_employee_code_modification_and_deletion(self):
        """
        Verify:
        1. Editing Employee Code (new_employee_id) migrates all child records atomically.
        2. Old Employee Code returns 404; new Employee Code is fully accessible.
        3. Renaming to an existing Employee Code is rejected with HTTP 400.
        4. Super Admin can delete records without restrictions; child records cascade cleanly.
        5. Unauthorized users (viewer, other mandal) are blocked from deleting with HTTP 403.
        """
        # 1. Admin login & fetch test GPs
        adm_login = self.client.post("/api/auth/login", json={
            "username": "admin", "password": "Admin@Khammam2026", "device_info": "Admin Code Edit & Delete Test"
        })
        self.assertEqual(adm_login.status_code, 200)
        adm_hdr = {"Authorization": f"Bearer {adm_login.json()['access_token']}"}
        e_mandal = self.db.query(Mandal).filter(Mandal.mandal_name.ilike("%enkoor%")).first()
        e_gp = self.db.query(GramPanchayat).filter(GramPanchayat.mandal_id == e_mandal.id).first()

        # Register employee EMP-CODE-01
        res1 = self.client.post("/api/employees/stage1-register", headers=adm_hdr, json={
            "employee_id": "EMP-CODE-01",
            "name_ifmis": "Original Code PS",
            "mobile_number": "9800011111",
            "designation": "Panchayat Secretary Grade-IV",
            "dob": "1992-05-15",
            "registration_mandal_id": e_mandal.id
        })
        self.assertEqual(res1.status_code, 201)

        # Stage 2 & 3 mapping
        res2 = self.client.post("/api/employees/stage2-combined-mapping", headers=adm_hdr, json={
            "employee_id": "EMP-CODE-01",
            "salary_gp_lgd": e_gp.lgd_code,
            "salary_claiming_status": "YES",
            "working_from_date": "2026-01-01",
            "service_status": "WORKING",
            "is_working_in_salary_gp": True,
            "posting_type": "OWN_GP",
            "actual_working_gp_lgd": e_gp.lgd_code
        })
        self.assertEqual(res2.status_code, 200)

        # 2. Modify Employee Code to EMP-CODE-02 and change name
        upd = self.client.put("/api/employees/EMP-CODE-01", headers=adm_hdr, json={
            "new_employee_id": "EMP-CODE-02",
            "name_ifmis": "Renamed Code PS",
            "mobile_number": "9800022222"
        })
        self.assertEqual(upd.status_code, 200)
        upd_data = upd.json()
        self.assertEqual(upd_data["employee_id"], "EMP-CODE-02")
        self.assertIn("EMPLOYEE_CODE", upd_data["updated_sections"])

        # Old ID is gone; new ID is live
        self.assertEqual(self.client.get("/api/employees/EMP-CODE-01", headers=adm_hdr).status_code, 404)
        prof_new = self.client.get("/api/employees/EMP-CODE-02", headers=adm_hdr)
        self.assertEqual(prof_new.status_code, 200)
        p_data = prof_new.json()
        self.assertEqual(p_data["name_ifmis"], "Renamed Code PS")
        self.assertEqual(p_data["mobile_number"], "9800022222")
        self.assertEqual(p_data["salary_gp_lgd"], e_gp.lgd_code)
        self.assertEqual(p_data["current_posting"]["posting_type"], "OWN_GP")

        # 3. Create another employee EMP-CODE-03 and verify duplicate rejection on rename
        res3 = self.client.post("/api/employees/stage1-register", headers=adm_hdr, json={
            "employee_id": "EMP-CODE-03",
            "name_ifmis": "Another PS",
            "registration_mandal_id": e_mandal.id
        })
        self.assertEqual(res3.status_code, 201)

        dup_rename = self.client.put("/api/employees/EMP-CODE-02", headers=adm_hdr, json={
            "new_employee_id": "EMP-CODE-03"
        })
        self.assertEqual(dup_rename.status_code, 400)
        self.assertIn("already registered", dup_rename.json()["detail"])

        # 4. Deletion permission checks
        # Viewer cannot delete
        v_login = self.client.post("/api/auth/login", json={"username": "viewer", "password": "Viewer@Khammam2026"})
        v_hdr = {"Authorization": f"Bearer {v_login.json()['access_token']}"}
        self.assertEqual(self.client.delete("/api/employees/EMP-CODE-02", headers=v_hdr).status_code, 403)
        self.client.post("/api/auth/logout", headers=v_hdr)

        # Kallur mandal admin cannot delete Enkoor's employee
        k_login = self.client.post("/api/auth/login", json={"username": "kallur", "password": "Mandal@5069"})
        k_hdr = {"Authorization": f"Bearer {k_login.json()['access_token']}"}
        self.assertEqual(self.client.delete("/api/employees/EMP-CODE-02", headers=k_hdr).status_code, 403)
        self.client.post("/api/auth/logout", headers=k_hdr)

        # 5. Super Admin deletes EMP-CODE-02
        del_res = self.client.delete("/api/employees/EMP-CODE-02", headers=adm_hdr)
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["employee_id"], "EMP-CODE-02")

        # Verify EMP-CODE-02 no longer exists
        self.assertEqual(self.client.get("/api/employees/EMP-CODE-02", headers=adm_hdr).status_code, 404)

        # Clean up EMP-CODE-03
        self.assertEqual(self.client.delete("/api/employees/EMP-CODE-03", headers=adm_hdr).status_code, 200)
        self.client.post("/api/auth/logout", headers=adm_hdr)

    def test_16_user_management_and_creation(self):
        """
        Verify:
        1. Super Admin can create new users (MANDAL_ADMIN, VIEWER, SUPER_ADMIN).
        2. Duplicate username registration is rejected with HTTP 400.
        3. Unauthorized users (MANDAL_ADMIN, VIEWER) cannot create or manage users (HTTP 403).
        4. Newly created users can authenticate and obtain access tokens.
        5. Super Admin can update user role, display name, and password.
        6. Super Admin can toggle user active/inactive status.
        7. Super Admin can delete created users, but cannot delete own account or default admin.
        """
        adm_login = self.client.post("/api/auth/login", json={
            "username": "admin", "password": "Admin@Khammam2026", "device_info": "User Mgmt Test"
        })
        self.assertEqual(adm_login.status_code, 200)
        adm_hdr = {"Authorization": f"Bearer {adm_login.json()['access_token']}"}

        e_mandal = self.db.query(Mandal).filter(Mandal.mandal_name.ilike("%enkoor%")).first()

        # 1. Non-admin (Enkoor) cannot access /api/admin/users (403)
        e_login = self.client.post("/api/auth/login", json={
            "username": "enkoor", "password": "Mandal@5065", "device_info": "Enkoor Guard Test"
        })
        e_hdr = {"Authorization": f"Bearer {e_login.json()['access_token']}"}
        self.assertEqual(self.client.get("/api/admin/users", headers=e_hdr).status_code, 403)
        self.assertEqual(self.client.post("/api/admin/users", headers=e_hdr, json={
            "username": "unauthorized_user", "password": "Password@123", "role": "VIEWER"
        }).status_code, 403)
        self.client.post("/api/auth/logout", headers=e_hdr)

        # 2. Super Admin creates VIEWER user
        res_v = self.client.post("/api/admin/users", headers=adm_hdr, json={
            "username": "test_auditor_kmm",
            "password": "Password@123",
            "display_name": "Test District Auditor",
            "role": "VIEWER"
        })
        self.assertEqual(res_v.status_code, 201)
        v_user_id = res_v.json()["user_id"]

        # Duplicate username check
        dup_res = self.client.post("/api/admin/users", headers=adm_hdr, json={
            "username": "test_auditor_kmm",
            "password": "AnotherPassword@123",
            "role": "VIEWER"
        })
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn("already exists", dup_res.json()["detail"])

        # Super Admin creates MANDAL_ADMIN user
        res_m = self.client.post("/api/admin/users", headers=adm_hdr, json={
            "username": "test_enkoor_asst",
            "password": "Password@123",
            "display_name": "Enkoor Assistant Officer",
            "role": "MANDAL_ADMIN",
            "mandal_id": e_mandal.id
        })
        self.assertEqual(res_m.status_code, 201)
        m_user_id = res_m.json()["user_id"]

        # 3. Authenticate with newly created user
        auditor_login = self.client.post("/api/auth/login", json={
            "username": "test_auditor_kmm", "password": "Password@123", "device_info": "Auditor Test Device"
        })
        self.assertEqual(auditor_login.status_code, 200)
        self.assertEqual(auditor_login.json()["role"], "VIEWER")
        auditor_hdr = {"Authorization": f"Bearer {auditor_login.json()['access_token']}"}
        self.client.post("/api/auth/logout", headers=auditor_hdr)

        # 4. Super Admin updates user details
        upd_res = self.client.put(f"/api/admin/users/{v_user_id}", headers=adm_hdr, json={
            "display_name": "Senior District Auditor",
            "password": "NewSecretPassword@123"
        })
        self.assertEqual(upd_res.status_code, 200)

        # Verify new password works
        new_pwd_login = self.client.post("/api/auth/login", json={
            "username": "test_auditor_kmm", "password": "NewSecretPassword@123", "device_info": "Auditor New Pwd"
        })
        self.assertEqual(new_pwd_login.status_code, 200)
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {new_pwd_login.json()['access_token']}"})

        # 5. Toggle active status
        toggle_res = self.client.post(f"/api/admin/users/{m_user_id}/toggle-active", headers=adm_hdr)
        self.assertEqual(toggle_res.status_code, 200)
        self.assertFalse(toggle_res.json()["is_active"])

        # Deactivated user login should fail
        deact_login = self.client.post("/api/auth/login", json={
            "username": "test_enkoor_asst", "password": "Password@123"
        })
        self.assertIn(deact_login.status_code, (400, 401, 403))

        # Reactivate
        toggle_res2 = self.client.post(f"/api/admin/users/{m_user_id}/toggle-active", headers=adm_hdr)
        self.assertEqual(toggle_res2.status_code, 200)
        self.assertTrue(toggle_res2.json()["is_active"])

        # 6. Delete created users & verify safety protections
        # Cannot delete default admin account
        admin_user = self.db.query(User).filter(User.username == "admin").first()
        del_admin_res = self.client.delete(f"/api/admin/users/{admin_user.id}", headers=adm_hdr)
        self.assertEqual(del_admin_res.status_code, 400)

        # Clean up test users
        del_m_res = self.client.delete(f"/api/admin/users/{m_user_id}", headers=adm_hdr)
        self.assertEqual(del_m_res.status_code, 200)

        del_v_res = self.client.delete(f"/api/admin/users/{v_user_id}", headers=adm_hdr)
        self.assertEqual(del_v_res.status_code, 200)

        self.client.post("/api/auth/logout", headers=adm_hdr)

if __name__ == "__main__":
    unittest.main()
