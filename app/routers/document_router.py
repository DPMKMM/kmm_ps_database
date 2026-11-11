import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmployeeDocument, Employee, User, AuditLog
from app.auth import get_current_user, enforce_employee_mandal_scope
from app.config import settings

router = APIRouter(prefix="/api/documents", tags=["Supporting Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE = 10 * 1024 * 1024 # 10MB

@router.post("/upload")
async def upload_document(
    employee_id: str = Form(...),
    document_type: str = Form(...), # PROCEEDINGS, SUSPENSION_ORDER, LEAVE_APPLICATION, JOINING_REPORT, OTHER
    file: UploadFile = File(...),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    emp = db.query(Employee).filter(Employee.employee_id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    enforce_employee_mandal_scope(db, current_user, emp.employee_id, allow_viewer=False)
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Allowed file types: PDF, JPG, PNG")
        
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds maximum allowed limit (10MB)")
        
    clean_emp = employee_id.replace("/", "_").replace("-", "_")
    unique_filename = f"{clean_emp}_{document_type}_{uuid.uuid4().hex[:8]}{ext}"
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    destination_path = os.path.join(settings.UPLOAD_DIR, unique_filename)
    
    with open(destination_path, "wb") as f:
        f.write(content)
        
    now = datetime.utcnow()
    doc = EmployeeDocument(
        employee_id=employee_id,
        document_type=document_type,
        file_name=file.filename,
        file_path=unique_filename,
        file_size=len(content),
        mime_type=file.content_type,
        uploaded_by=current_user.username,
        uploaded_at=now
    )
    db.add(doc)
    
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="UPLOAD_DOCUMENT",
        entity_type="DOCUMENT",
        entity_id=str(doc.id),
        details=f"Uploaded {file.filename} for employee {employee_id}",
        ip_address=request.client.host if request and request.client else "127.0.0.1",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {
        "message": "Supporting document uploaded successfully",
        "document_id": doc.id,
        "file_name": doc.file_name
    }

@router.get("/employee/{employee_id}")
def get_employee_documents(
    employee_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    enforce_employee_mandal_scope(db, current_user, employee_id, allow_viewer=True)
    docs = db.query(EmployeeDocument).filter(EmployeeDocument.employee_id == employee_id).order_by(EmployeeDocument.uploaded_at.desc()).all()
    return [
        {
            "id": d.id,
            "document_type": d.document_type,
            "file_name": d.file_name,
            "file_size_kb": round(d.file_size / 1024, 1),
            "uploaded_by": d.uploaded_by,
            "uploaded_at": d.uploaded_at.strftime("%Y-%m-%d %H:%M") if d.uploaded_at else ""
        }
        for d in docs
    ]

@router.get("/download/{document_id}")
def download_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(EmployeeDocument).filter(EmployeeDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_employee_mandal_scope(db, current_user, doc.employee_id, allow_viewer=True)
        
    file_path = os.path.join(settings.UPLOAD_DIR, doc.file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")
        
    return FileResponse(
        path=file_path,
        filename=doc.file_name,
        media_type=doc.mime_type or "application/octet-stream"
    )
