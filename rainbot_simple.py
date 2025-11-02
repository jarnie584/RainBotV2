import os, time, threading, requests, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---- log direct flushen
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# ---- ENV
WEBHOOK_URL     = os.getenv("WEBHOOK_URL")                      # zet in Render → Environment
CHECK_URL       = os.getenv("CHECK_URL", "https://bandit.camp")
POLL_SECONDS    = int(os.getenv("POLL_SECONDS", "30"))
TIMEOUT_SEC     = int(os.getenv("TIMEOUT_SEC", "15"))
TRIGGER         = os.getenv("TRIGGER", "rain").lower()
USE_PLAYWRIGHT  = os.getenv("USE_PLAYWRIGHT", "0").lower() in ("1", "true", "yes")

# ---- Health server zodat Render je app 'ziet'
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        else:
            self.send_response(404); self.end_headers()
    def do_HEAD(self):
        if self.path in ("/", "/health"):
            self.send_response(200); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

def start_health_server():
    port = int(os.getenv("PORT", "10000"))  # Render geeft dynamische poort
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[INFO] Health server running on port {port}", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()

# ---- Discord helpers
def send_discord(msg: str):
    if not WEBHOOK_URL:
        print("[FOUT] WEBHOOK_URL ontbreekt (zet env var op Render).", flush=True)
        return
    try:
        r = requests.post(WEBHOOK_URL, json={"content": msg}, timeout=10)
        if r.status_code < 300:
            print("[OK] Discord-bericht verstuurd.", flush=True)
        else:
            print(f"[FOUT] Discord {r.status_code}: {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"[FOUT] Discord-post: {e}", flush=True)

def startup_ping():
    send_discord("✅ RainBot opgestart (health ok) – testmelding")

# ---- Checker met requests
def has_rain_requests() -> bool:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(CHECK_URL, timeout=TIMEOUT_SEC, headers=headers)
        print(f"[DBG] (REQ) GET {CHECK_URL} -> {r.status_code}, {len(r.text)} bytes", flush=True)
        r.raise_for_status()
        found = TRIGGER in r.text.lower()
        print(f"[DBG] (REQ) trigger '{TRIGGER}' found? {found}", flush=True)
        return found
    except Exception as e:
        print(f"[WARN] requests-check mislukt: {e}", flush=True)
        return False

# ---- Checker met Playwright (echte browser)
def has_rain_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.set_default_timeout(15000)
            page.goto(CHECK_URL, wait_until="domcontentloaded")
            html = page.content()
            context.close(); browser.close()
            found = TRIGGER in html.lower()
            print(f"[DBG] (PW) trigger '{TRIGGER}' found? {found}", flush=True)
            return found
    except Exception as e:
        print(f"[WARN] Playwright-check mislukt: {e}", flush=True)
        return False

# ---- Main loop
def main():
    print(f"[START] Check={CHECK_URL} | trigger='{TRIGGER}' | elke {POLL_SECONDS}s", flush=True)
    print(f"[INFO] Using {'Playwright' if USE_PLAYWRIGHT else 'requests'} checker", flush=True)
    checker = has_rain_playwright if USE_PLAYWRIGHT else has_rain_requests

    notified = False
    while True:
        try:
            if checker() and not notified:
                send_discord("🌧️ Rain gedetecteerd op bandit.camp! (simple)")
                notified = True
            elif not checker() and notified:
                notified = False
        except Exception as e:
            print(f"[ERR] Loop error: {e}", flush=True)
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    start_health_server()
    startup_ping()   # 1 testmelding bij start
    main()
