from datetime import datetime, date
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models import (
    Employee, EmployeeSalaryMapping, EmployeePosting, EmployeeStatusHistory,
    GramPanchayat, Mandal, User
)
from app.auth import get_current_user

router = APIRouter(prefix="/api/deputations", tags=["Deputation Chain Tracking Engine"])

@router.get("/chains")
def get_deputation_chains(
    mandal_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    SECTION 8: AUTOMATIC DEPUTATION CHAIN TRACKING ENGINE
    Discovers multi-hop deputation chains for District Admin / Viewer roles.
    Disabled for Mandal Admin login.
    """
    if current_user.role == "MANDAL_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Deputation Chains Graph is only available at District level login."
        )
    target_mandal_id = mandal_id

    # 1. Fetch active postings where employee is deputed (not working in own salary GP)
    q = (
        db.query(
            EmployeePosting,
            EmployeeSalaryMapping,
            Employee,
            EmployeeStatusHistory
        )
        .join(EmployeeSalaryMapping, EmployeeSalaryMapping.employee_id == EmployeePosting.employee_id)
        .join(Employee, Employee.employee_id == EmployeePosting.employee_id)
        .outerjoin(EmployeeStatusHistory, (EmployeeStatusHistory.employee_id == EmployeePosting.employee_id) & (EmployeeStatusHistory.is_current == True))
        .filter(
            EmployeePosting.is_current == True,
            EmployeePosting.is_working_in_salary_gp == False,
            EmployeeSalaryMapping.is_active == True
        )
    )
    if target_mandal_id:
        q = q.filter(
            or_(
                EmployeeSalaryMapping.salary_mandal_id == target_mandal_id,
                EmployeePosting.actual_working_mandal_id == target_mandal_id,
                EmployeePosting.official_deputation_mandal_id == target_mandal_id
            )
        )
    deputed_postings = q.all()
    
    # Map by salary GP lgd -> list of employees drawing salary from that GP
    salary_gp_to_emps: Dict[int, List[Dict[str, Any]]] = {}
    emp_by_id: Dict[str, Dict[str, Any]] = {}
    
    for post, sm, emp, st in deputed_postings:
        salary_gp = sm.panchayat
        working_gp = post.working_panchayat
        
        info = {
            "employee_id": emp.employee_id,
            "name_ifmis": emp.name_ifmis,
            "salary_gp_lgd": sm.salary_gp_lgd,
            "salary_gp_name": salary_gp.gp_name if salary_gp else "Unknown",
            "salary_mandal_name": salary_gp.mandal_name if salary_gp else "Unknown",
            "posting_type": post.posting_type,
            "actual_working_gp_lgd": post.actual_working_gp_lgd,
            "actual_working_gp_name": working_gp.gp_name if working_gp else (post.external_gp_or_office_name or "N/A"),
            "actual_working_mandal_name": working_gp.mandal_name if working_gp else (post.external_mandal_name or "N/A"),
            "external_district_name": post.external_district_name,
            "deputation_order_no": post.deputation_order_no,
            "deputation_order_date": post.deputation_order_date.strftime("%Y-%m-%d") if post.deputation_order_date else None,
            "deputation_end_date": post.deputation_end_date.strftime("%Y-%m-%d") if post.deputation_end_date else None,
            "service_status": st.service_status if st else "WORKING",
            "verification_status": post.verification_status,
            "is_expired": post.deputation_end_date < date.today() if post.deputation_end_date else False
        }
        
        emp_by_id[emp.employee_id] = info
        salary_gp_to_emps.setdefault(sm.salary_gp_lgd, []).append(info)
        
    # Build chains
    # A chain is formed when Employee 1 (Salary GP A -> Working GP B) connects to Employee 2 (Salary GP B -> Working GP C)
    chains = []
    visited_emps = set()
    circular_warnings = []
    
    # Helper to traverse forward from an employee
    for start_emp_id, start_info in emp_by_id.items():
        if start_emp_id in visited_emps:
            continue
            
        current_chain = [start_info]
        visited_in_path = {start_info["employee_id"]}
        curr = start_info
        
        is_circular = False
        while curr["actual_working_gp_lgd"] and curr["actual_working_gp_lgd"] in salary_gp_to_emps:
            next_candidates = salary_gp_to_emps[curr["actual_working_gp_lgd"]]
            # Take next candidate not already in path
            next_emp = None
            for cand in next_candidates:
                if cand["employee_id"] in visited_in_path:
                    is_circular = True
                    circular_warnings.append({
                        "from_employee": curr["employee_id"],
                        "to_employee": cand["employee_id"],
                        "gp_lgd": curr["actual_working_gp_lgd"],
                        "message": f"Circular deputation detected involving {curr['name_ifmis']} and {cand['name_ifmis']}"
                    })
                    break
                else:
                    next_emp = cand
                    break
                    
            if next_emp and not is_circular:
                current_chain.append(next_emp)
                visited_in_path.add(next_emp["employee_id"])
                curr = next_emp
            else:
                break
                
        # If chain length >= 1, record it
        for e in current_chain:
            visited_emps.add(e["employee_id"])
            
        chains.append({
            "chain_id": f"CHAIN-{len(chains) + 1}",
            "length": len(current_chain),
            "is_multi_hop": len(current_chain) > 1,
            "is_circular": is_circular,
            "employees": current_chain,
            "summary_path": " -> ".join([f"{e['name_ifmis']} (GP {e['salary_gp_lgd']} -> GP {e['actual_working_gp_lgd'] or 'Other Dist'})" for e in current_chain])
        })
        
    # Sort chains by length descending so complex multi-hop chains appear first
    chains.sort(key=lambda x: x["length"], reverse=True)
    
    # 2. Build full graph representation (Nodes & Edges) for interactive UI graph rendering
    nodes = []
    edges = []
    node_ids = set()
    
    # Add GP and Employee nodes
    for c in chains:
        for emp in c["employees"]:
            # GP Node: Salary GP
            s_node_id = f"GP_{emp['salary_gp_lgd']}"
            if s_node_id not in node_ids:
                nodes.append({
                    "id": s_node_id,
                    "label": f"{emp['salary_gp_name']}\n(M: {emp['salary_mandal_name']})",
                    "type": "GP",
                    "lgd_code": emp["salary_gp_lgd"],
                    "mandal": emp["salary_mandal_name"]
                })
                node_ids.add(s_node_id)
                
            # GP Node: Working GP
            if emp["actual_working_gp_lgd"]:
                w_node_id = f"GP_{emp['actual_working_gp_lgd']}"
                if w_node_id not in node_ids:
                    nodes.append({
                        "id": w_node_id,
                        "label": f"{emp['actual_working_gp_name']}\n(M: {emp['actual_working_mandal_name']})",
                        "type": "GP",
                        "lgd_code": emp["actual_working_gp_lgd"],
                        "mandal": emp["actual_working_mandal_name"]
                    })
                    node_ids.add(w_node_id)
            else:
                w_node_id = f"EXT_{emp['employee_id']}"
                if w_node_id not in node_ids:
                    nodes.append({
                        "id": w_node_id,
                        "label": f"{emp['actual_working_gp_name']}\n(Dist: {emp['external_district_name']})",
                        "type": "EXTERNAL",
                        "district": emp["external_district_name"]
                    })
                    node_ids.add(w_node_id)
                    
            # Edge from Salary GP to Working GP representing the deputed employee
            edges.append({
                "from": s_node_id,
                "to": w_node_id,
                "employee_id": emp["employee_id"],
                "employee_name": emp["name_ifmis"],
                "posting_type": emp["posting_type"],
                "service_status": emp["service_status"],
                "verification_status": emp["verification_status"],
                "order_no": emp["deputation_order_no"],
                "is_expired": emp["is_expired"]
            })
            
    return {
        "total_chains": len(chains),
        "multi_hop_chains_count": len([c for c in chains if c["is_multi_hop"]]),
        "circular_count": len(circular_warnings),
        "circular_warnings": circular_warnings,
        "chains": chains,
        "graph": {
            "nodes": nodes,
            "edges": edges
        }
    }
