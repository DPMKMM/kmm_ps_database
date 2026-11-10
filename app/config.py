import os

class Settings:
    PROJECT_NAME: str = "Details of Panchayat Secretaries Working in Khammam District"
    SHORT_NAME: str = "PS Details – Khammam"
    DEPARTMENT: str = "District Panchayat Office, Khammam, Telangana"
    DISTRICT_NAME: str = "Khammam"
    TOTAL_MANDALS: int = 20
    TOTAL_GPS: int = 571
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "khammam-ps-secret-key-2026-production-secured-98231")
    ALGORITHM: str = "HS256"
    SESSION_INACTIVITY_MINUTES: int = int(os.getenv("SESSION_INACTIVITY_MINUTES", "15"))
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    ALLOW_MULTI_USER_SESSIONS: bool = os.getenv("ALLOW_MULTI_USER_SESSIONS", "true").lower() == "true"
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./khammam_ps.db")
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")

settings = Settings()
