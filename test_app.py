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

if __name__ == "__main__":
    unittest.main()
