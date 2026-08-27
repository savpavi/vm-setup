#!/usr/bin/env python3
"""state.sqlite3'te kayitli mesajlari Gmail'den siler ve durumu sifirlar.

Sadece bu araclarin yukledigi mesajlara dokunur; kutudaki digerleri kalir.
"""
import sqlite3, sys
from pathlib import Path
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env

env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)

state = WORKDIR / "state.sqlite3"
if not state.exists():
    sys.exit("state.sqlite3 yok — silinecek bir sey yok.")

db = sqlite3.connect(str(state))
rows = db.execute("SELECT gmail_id, kind FROM done WHERE gmail_id != ''").fetchall()
msg_ids = [g for g, k in rows if k == "message"]
draft_ids = [g for g, k in rows if k == "draft"]

prof = svc.users().getProfile(userId="me").execute()
print(f"  Hedef: {prof['emailAddress']}")
print(f"  Silinecek: {len(msg_ids)} mesaj, {len(draft_ids)} taslak")

for i in range(0, len(msg_ids), 900):
    chunk = msg_ids[i:i + 900]
    svc.users().messages().batchDelete(userId="me", body={"ids": chunk}).execute()
    print(f"    silindi {i + len(chunk)}/{len(msg_ids)}")

for d in draft_ids:
    try:
        svc.users().drafts().delete(userId="me", id=d).execute()
    except Exception as e:
        print(f"    taslak silinemedi {d}: {e}")

# Proton/ label'larini kaldir
removed = 0
for l in svc.users().labels().list(userId="me").execute().get("labels", []):
    if l.get("type") == "user" and l["name"].startswith("Proton/"):
        svc.users().labels().delete(userId="me", id=l["id"]).execute()
        removed += 1
print(f"  Silinen Proton/ label: {removed}")

db.execute("DELETE FROM done")
db.execute("DELETE FROM failed")
db.commit()
db.close()

prof = svc.users().getProfile(userId="me").execute()
print(f"\n  Temizlendi. Kutuda kalan: {prof['messagesTotal']} mesaj")
