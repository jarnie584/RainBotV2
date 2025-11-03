import os, time, threading, requests, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---- log direct flushen
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# ==== ENV ====
WEBHOOK_URL     = os.getenv("WEBHOOK_URL")                              # verplicht: Render → Environment
CHECK_URL       = os.getenv("CHECK_URL", "https://bandit.camp")
POLL_SECONDS    = int(os.getenv("POLL_SECONDS", "30"))
TIMEOUT_SEC     = int(os.getenv("TIMEOUT_SEC", "15"))
TRIGGER         = os.getenv("TRIGGER", "rain").lower()
TRIGGERS_EXTRA  = [w.strip().lower() for w in os.getenv("TRIGGERS","").split(",") if w.strip()]
USE_PLAYWRIGHT  = os.getenv("USE_PLAYWRIGHT", "1").lower() in ("1", "true", "yes")

# ==== Health server ====
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

# ==== Discord ====
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

# ==== Helpers ====
def trigger_words():
    words = [TRIGGER] if TRIGGER else []
    words += TRIGGERS_EXTRA
    # unieke, niet-lege
    return [w for w in dict.fromkeys(words) if w]

def build_url_list():
    # Zorgt voor een paar varianten, uniek en in volgorde
    candidates = []
    def add(u): 
        if u and u not in candidates: candidates.append(u)
    add(CHECK_URL)
    add(CHECK_URL.replace("https://bandit.camp", "https://www.bandit.camp"))
    add("https://bandit.camp")
    add("https://www.bandit.camp")
    return candidates

# ==== Checker (requests) ====
def has_rain_requests() -> bool:
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(CHECK_URL, timeout=TIMEOUT_SEC, headers=headers)
        print(f"[DBG] (REQ) GET {CHECK_URL} -> {r.status_code}, {len(r.text)} bytes", flush=True)
        r.raise_for_status()
        lower = r.text.lower()
        words = trigger_words()
        found = any(w in lower for w in words) if words else (TRIGGER in lower)
        print(f"[DBG] (REQ) triggers={words} -> found? {found}", flush=True)
        return found
    except Exception as e:
        print(f"[WARN] requests-check mislukt: {e}", flush=True)
        return False

# ==== Checker (Playwright) ====
def has_rain_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"),
                locale="en-US",
                timezone_id="Europe/Amsterdam",
                viewport={"width": 1366, "height": 768},
                java_script_enabled=True,
            )

            # Blokkeer zware assets om sneller te laden
            def route_handler(route):
                try:
                    if route.request.resource_type in {"image", "media", "font"}:
                        return route.abort()
                except Exception:
                    pass
                return route.continue_()
            context.route("**/*", route_handler)

            page = context.new_page()
            page.set_default_timeout(60000)                 # algemene timeout
            page.set_default_navigation_timeout(60000)      # navigatie specifiek

            html = ""
            last_err = None
            urls = build_url_list()

            for attempt in range(1, 4):
                for u in urls:
                    try:
                        print(f"[DBG] (PW) goto attempt {attempt} url={u}", flush=True)
                        page.goto(u, wait_until="commit", referer="https://www.google.com/", timeout=60000)
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass
                        html = page.content()
                        print(f"[DBG] (PW) final_url={page.url}", flush=True)  # <-- property, geen ()
                        break
                    except Exception as e:
                        last_err = e
                        print(f"[DBG] (PW) attempt failed for {u}: {e}", flush=True)
                        time.sleep(2)
                if html:
                    break

            try:
                context.close()
            finally:
                browser.close()

            if not html:
                print(f"[WARN] Playwright-check mislukt: {last_err}", flush=True)
                return False

            lower = html.lower().replace("\n"," ")
            print(f"[DBG] (PW) html head: {lower[:300]}", flush=True)

            words = trigger_words()
            found = any(w in lower for w in words) if words else False
            print(f"[DBG] (PW) triggers={words} -> found? {found}", flush=True)
            return found

    except Exception as e:
        print(f"[WARN] Playwright-check mislukt: {e}", flush=True)
        return False

# ==== Main loop ====
def main():
    print(f"[START] Check={CHECK_URL} | trigger='{TRIGGER}' | elke {POLL_SECONDS}s", flush=True)
    print(f"[INFO] Using {'Playwright' if USE_PLAYWRIGHT else 'requests'} checker", flush=True)
    checker = has_rain_playwright if USE_PLAYWRIGHT else has_rain_requests

    notified = False
    while True:
        try:
            found = checker()  # exact één keer per cyclus
            if found and not notified:
                send_discord("🌧️ Rain gedetecteerd op bandit.camp! (simple)")
                notified = True
            elif (not found) and notified:
                notified = False
        except Exception as e:
            print(f"[ERR] Loop error: {e}", flush=True)
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    start_health_server()
    startup_ping()   # 1 testmelding bij start
    main()
