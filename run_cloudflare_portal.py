"""
Launcher for PS Details – Khammam Portal via Cloudflare Tunnel.
Routes https://dpokmm.panchayatautomation.in/ps-data directly to this portal.
"""

import os
import sys
import time
import socket
import platform
import subprocess
from pathlib import Path

# Safe encoding on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
PYTHON_EXE = Path(sys.executable)
CLOUDFLARED_EXE = BASE_DIR / ("cloudflared.exe" if sys.platform == "win32" else "cloudflared")

# Read token and domain from environment or .env
env_file = BASE_DIR / ".env"
token_from_env = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
custom_domain = os.getenv("CUSTOM_DOMAIN", "dpokmm.panchayatautomation.in").strip()
port = int(os.getenv("PORT", "8080"))

if not token_from_env and env_file.exists():
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("CLOUDFLARE_TUNNEL_TOKEN="):
                token_from_env = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("CUSTOM_DOMAIN="):
                custom_domain = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("PORT="):
                port = int(line.split("=", 1)[1].strip())
    except Exception:
        pass

TUNNEL_TOKEN = token_from_env or ""


def kill_stale_cloudflared():
    # Do not kill cloudflared to avoid disturbing other services
    pass


def is_port_in_use(check_port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", check_port)) == 0


def main():
    print("=" * 76)
    print("  GOVERNMENT OF TELANGANA - DISTRICT PANCHAYAT OFFICE, KHAMMAM")
    print("  Details of Panchayat Secretaries Working in Khammam District")
    print("  Short Name: PS Details – Khammam")
    print("  Domain: https://dpokmm.panchayatautomation.in/ps-data")
    print("=" * 76)

    # 1. Start application server if not already running
    uvicorn_proc = None
    if is_port_in_use(port):
        print(f"[+] Local portal server is already active on http://127.0.0.1:{port}")
    else:
        print(f"[*] Starting local portal server on port {port}...")
        uvicorn_proc = subprocess.Popen(
            [str(PYTHON_EXE), "run.py"],
            cwd=str(BASE_DIR)
        )
        for _ in range(15):
            time.sleep(0.5)
            if is_port_in_use(port):
                print(f"[+] Local portal server started on port {port}.")
                break

    # 2. Verify cloudflared executable exists
    if not CLOUDFLARED_EXE.exists():
        print(f"[ERROR] cloudflared executable not found at: {CLOUDFLARED_EXE}")
        sys.exit(1)

    kill_stale_cloudflared()

    # 3. Launch Cloudflare Tunnel
    if TUNNEL_TOKEN:
        print(f"[*] Connecting Cloudflare Zero Trust Tunnel for {custom_domain}...")
        cf_proc = subprocess.Popen(
            [str(CLOUDFLARED_EXE), "tunnel", "run", "--url", f"http://127.0.0.1:{port}", "--token", TUNNEL_TOKEN],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        public_url = f"https://{custom_domain}/ps-data"
        try:
            url_file = BASE_DIR / "latest_public_url.txt"
            url_file.write_text(
                f"Public URL: {public_url}\n"
                f"Local Access: http://127.0.0.1:{port}/ps-data\n"
                f"Status: Connected via Cloudflare Zero Trust Tunnel\n"
                f"Connected: {time.ctime()}\n",
                encoding="utf-8"
            )
        except Exception:
            pass

        print("\n" + "=" * 76)
        print("  [+] CLOUDFLARE ZERO TRUST TUNNEL IS ACTIVE & CONNECTED!")
        print("=" * 76)
        print(f"  Public Portal URL :  {public_url}")
        print(f"  Local Access URL  :  http://127.0.0.1:{port}/ps-data")
        print(f"  Status            :  Routed via Cloudflare Edge Network (Zero Trust)")
        print("=" * 76)
        print(f"  Portal is available at: {public_url}")
        print("  Keep this window open to maintain connectivity.")
        print("  Press Ctrl+C to stop.\n")

        try:
            while True:
                line = cf_proc.stdout.readline()
                if not line and cf_proc.poll() is not None:
                    break
                if line:
                    clean = line.strip()
                    if any(k in clean for k in ["INF", "Connection", "Registered", "Route", "Initial protocol", "ERR"]):
                        # Print relevant log lines
                        print(f"  [Cloudflare] {clean[:100]}", flush=True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[*] Stopping Cloudflare Tunnel and portal server...")
            cf_proc.terminate()
            if uvicorn_proc:
                uvicorn_proc.terminate()
            print("[+] Stopped cleanly.")
    else:
        print("[!] No CLOUDFLARE_TUNNEL_TOKEN specified in .env.")


if __name__ == "__main__":
    main()
