import os
import sys

# Ensure pure-Python mode for SQLAlchemy to avoid Windows AppControl policy blocking cython DLLs
os.environ["DISABLE_SQLALCHEMY_CEXT"] = "1"

import uvicorn
from app.config import settings
from app.database import engine, Base
from app.seed import seed_database

def main():
    print("=" * 80)
    print(" " * 15 + "GOVERNMENT OF TELANGANA - DISTRICT PANCHAYAT OFFICE")
    print(" " * 10 + settings.PROJECT_NAME.upper())
    print(" " * 28 + settings.SHORT_NAME)
    print("=" * 80)
    print(f"District: {settings.DISTRICT_NAME} | Mandals: {settings.TOTAL_MANDALS} | Gram Panchayats: {settings.TOTAL_GPS}")
    print("-" * 80)
    
    # 1. Initialize Tables & Seed Master Data
    print("Checking database schema and centralized master records...")
    Base.metadata.create_all(bind=engine)
    seed_database(force_reseed=False)
    
    print("-" * 80)
    print("ACCESS CREDENTIALS:")
    print("1. District Super Admin (All 571 GPs & 20 Mandals):")
    print("   Username: admin")
    print("   Password: Admin@Khammam2026")
    print("\n2. Mandal Admin Accounts (20 Mandals with Single Active Device Session Enforcement):")
    print("   Examples: enkoor, kallur, sathupally, penubally, thallada, mudigonda, khammam_rural")
    print("   Passwords: Mandal@<Mandal_LGD>  (e.g. Mandal@5065 for Enkoor, Mandal@5069 for Kallur)")
    print("\n3. District Viewer (Collectorate Read-Only Access):")
    print("   Username: viewer")
    print("   Password: Viewer@Khammam2026")
    print("-" * 80)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Web Application Server at: http://{host}:{port} (Dual-Stack IPv4/IPv6 supported)")
    print("=" * 80)
    
    try:
        import socket
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(('::', port))
        sock.listen(256)
        config = uvicorn.Config("app.main:app", reload=False, access_log=True)
        server = uvicorn.Server(config)
        server.run(sockets=[sock])
    except Exception as exc:
        print(f"[!] Dual-stack bind fallback: {exc}")
        uvicorn.run("app.main:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
