#!/usr/bin/env python3
"""state'te kayitli olup Gmail'de bulunmayan mesajlari tespit eder."""
import sqlite3, json
from pathlib import Path
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env
from googleapiclient.errors import HttpError

SRC = Path("/srv/lexar/Backups/proton-mail-export/mail@egebostanci.me/mail_20260826_140713")
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

db = sqlite3.connect(str(WORKDIR / "state.sqlite3"))
missing = [(p, g) for p, g in db.execute("SELECT proton_id, gmail_id FROM done")
           if g and g not in seen]
print(f"  Gmail'de bulunamayan: {len(missing)}\n")
for pid, g in missing:
    meta = json.loads((SRC / f"{pid}.metadata.json").read_text())["Payload"]
    print(f"  proton={pid[:20]}…  gmail={g}")
    print(f"    konu   : {meta.get('Subject','')[:60]}")
    print(f"    gonderen: {meta['Sender']['Address']}")
    print(f"    labels : {meta.get('LabelIDs')}")
    try:
        m = svc.users().messages().get(userId="me", id=g, format="minimal").execute()
        print(f"    → get() ile ERISILEBILIYOR: thread={m['threadId']}, "
              f"labels={m.get('labelIds')}")
    except HttpError as e:
        st = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
        print(f"    → get() basarisiz ({st}) — gercekten yok")
    print()
