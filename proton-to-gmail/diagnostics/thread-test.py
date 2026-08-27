#!/usr/bin/env python3
"""Ebeveyn->cocuk cifti sirayla yukleyip ayni thread'e dusuyor mu bakar.

    thread-test.py <insert|import> <ebeveyn_id> <cocuk_id>
"""
import base64, sqlite3, sys, time
from pathlib import Path
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env

D = Path("/srv/lexar/Backups/proton-mail-export/mail@egebostanci.me/mail_20260826_140713")
method, ids = sys.argv[1], sys.argv[2:]

env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)
db = sqlite3.connect(str(WORKDIR / "state.sqlite3"))

results = []
for pid in ids:
    raw = base64.urlsafe_b64encode((D / f"{pid}.eml").read_bytes()).decode()
    if method == "insert":
        res = svc.users().messages().insert(
            userId="me", body={"raw": raw}, internalDateSource="dateHeader").execute()
    else:
        res = svc.users().messages().import_(
            userId="me", body={"raw": raw}, internalDateSource="dateHeader",
            neverMarkSpam=True, processForCalendar=False).execute()
    db.execute("INSERT OR REPLACE INTO done VALUES (?,?,?,strftime('%s','now'))",
               (pid, res["id"], "message"))
    db.commit()
    m = svc.users().messages().get(userId="me", id=res["id"], format="metadata",
                                   metadataHeaders=["Subject"]).execute()
    subj = next((h["value"] for h in m["payload"]["headers"] if h["name"] == "Subject"), "-")
    results.append((m["threadId"], subj))
    print(f"    thread={m['threadId']}  {subj[:45]}")
    time.sleep(1)   # ebeveynin indekslenmesi icin

tids = {t for t, _ in results}
print(f"  → {method}: {'AYNI thread — esleme CALISIYOR' if len(tids)==1 else f'{len(tids)} ayri thread — esleme YOK'}")
