#!/usr/bin/env python3
"""Gmail'deki mesajlari cop/spam dahil tek tek sayar ve state ile karsilastirir."""
import sqlite3
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env

env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)

seen = set()
tok = None
while True:
    r = svc.users().messages().list(userId="me", includeSpamTrash=True,
                                    maxResults=500, pageToken=tok).execute()
    seen.update(m["id"] for m in r.get("messages", []))
    tok = r.get("nextPageToken")
    if not tok:
        break
    if len(seen) % 5000 < 500:
        print(f"    {len(seen)}…", flush=True)

db = sqlite3.connect(str(WORKDIR / "state.sqlite3"))
state_ids = {r[0] for r in db.execute("SELECT gmail_id FROM done WHERE gmail_id != ''")}

print(f"\n  Gmail'de gercekte duran mesaj : {len(seen)}")
print(f"  state'te kayitli gmail_id      : {len(state_ids)}")
print(f"  state'te var, Gmail'de yok     : {len(state_ids - seen)}")
print(f"  Gmail'de var, state'te yok     : {len(seen - state_ids)}  (goc oncesi mevcutlar)")
