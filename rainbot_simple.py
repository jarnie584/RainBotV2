import os, time, requests

WEBHOOK_URL  = os.getenv("WEBHOOK_URL")                 # <-- verplicht
CHECK_URL    = os.getenv("CHECK_URL", "https://bandit.camp")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
TIMEOUT_SEC  = int(os.getenv("TIMEOUT_SEC", "15"))

# Simpel trefwoord dat op de pagina moet staan om te triggeren
TRIGGER      = os.getenv("TRIGGER", "rain").lower()

def send_discord(msg: str):
    if not WEBHOOK_URL:
        print("[FOUT] WEBHOOK_URL ontbreekt (zet env var op Render).")
        return
    try:
        r = requests.post(WEBHOOK_URL, json={"content": msg}, timeout=10)
        if r.status_code >= 300:
            print(f"[FOUT] Discord {r.status_code}: {r.text[:200]}")
        else:
            print("[OK] Discord-bericht verstuurd.")
    except Exception as e:
        print(f"[FOUT] Discord-post: {e}")

def has_rain() -> bool:
    try:
        r = requests.get(CHECK_URL, timeout=TIMEOUT_SEC, headers={"User-Agent":"RainBotSimple/1"})
        r.raise_for_status()
        return TRIGGER in r.text.lower()
    except Exception as e:
        print(f"[WARN] Check mislukt: {e}")
        return False

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
    main()
