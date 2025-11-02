import os, time, threading, requests
from http.server import BaseHTTPRequestHandler, HTTPServer

WEBHOOK_URL = os.getenv("WEBHOOK_URL")               
CHECK_URL    = os.getenv("CHECK_URL", "https://bandit.camp")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
TIMEOUT_SEC  = int(os.getenv("TIMEOUT_SEC", "15"))
TRIGGER      = os.getenv("TRIGGER", "bandit").lower()

# --- Health server zodat Render denkt dat app 'leeft'
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("", port), HealthHandler)
    print(f"[INFO] Health server running on port {port}")
    threading.Thread(target=server.serve_forever, daemon=True).start()

# --- Discord melding
def send_discord(msg: str):
    if not WEBHOOK_URL:
        print("[FOUT] WEBHOOK_URL ontbreekt (zet env var op Render).")
        return
    try:
        r = requests.post(WEBHOOK_URL, json={"content": msg}, timeout=10)
        if r.status_code < 300:
            print("[OK] Discord-bericht verstuurd.")
        else:
            print(f"[FOUT] Discord {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[FOUT] Discord-post: {e}")

# --- Pagina check
def has_rain() -> bool:
    try:
        r = requests.get(CHECK_URL, timeout=TIMEOUT_SEC, headers={"User-Agent":"RainBotSimple/1"})
        r.raise_for_status()
        return TRIGGER in r.text.lower()
    except Exception as e:
        print(f"[WARN] Check mislukt: {e}")
        return False

# --- Main loop
def main():
    print(f"[START] Check={CHECK_URL} | trigger='{TRIGGER}' | elke {POLL_SECONDS}s")
    if not WEBHOOK_URL:
        print("[LET OP] Geen WEBHOOK_URL → geen meldingen!")
    notified = False
    while True:
        if has_rain() and not notified:
            send_discord("🌧️ Rain gedetecteerd op bandit.camp! (simple)")
            notified = True
        elif not has_rain() and notified:
            notified = False
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    start_health_server()
    main()





