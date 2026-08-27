#!/usr/bin/env python3
"""Tek bir mesaji tekrar yuklemeyi dener — hata gecici mi kalici mi anlamak icin."""
import base64, sys
from pathlib import Path
from gauth import DEFAULT_SCOPE, get_credentials, gmail_service, load_env

D = Path("/srv/lexar/Backups/proton-mail-export/mail@egebostanci.me/mail_20260826_140713")
pid = sys.argv[1]
env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)
raw = base64.urlsafe_b64encode((D / f"{pid}.eml").read_bytes()).decode()
for attempt in (1, 2, 3):
    try:
        res = svc.users().messages().insert(
            userId="me", body={"raw": raw}, internalDateSource="dateHeader").execute()
        print(f"  deneme {attempt}: BASARILI  msg={res['id']}")
        print("  → hata GECICIYDI")
        sys.exit(0)
    except Exception as e:
        print(f"  deneme {attempt}: {type(e).__name__}: {str(e)[:120]}")
print("  → hata KALICI, mesaja ozgu bir sorun var")
