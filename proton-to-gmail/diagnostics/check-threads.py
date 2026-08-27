#!/usr/bin/env python3
"""Bolunmus zincirleri inceler: neden ayri thread'e dusmusler?"""
import json, sqlite3
from pathlib import Path
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env

SRC = Path("/srv/lexar/Backups/proton-mail-export/mail@egebostanci.me/mail_20260826_140713")
env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)
db = sqlite3.connect(str(WORKDIR / "state.sqlite3"))
gid = {r[0]: r[1] for r in db.execute("SELECT proton_id, gmail_id FROM done")}
conv = json.loads((WORKDIR / "conversations.json").read_text())

whole = split = 0
shown = 0
for chain in conv["conversations"]:
    tids, subs = {}, []
    for pid in chain:
        g = gid.get(pid)
        if not g:
            continue
        try:
            m = svc.users().messages().get(userId="me", id=g, format="metadata",
                                           metadataHeaders=["Subject"]).execute()
        except Exception:
            continue
        s = next((h["value"] for h in m["payload"].get("headers", []) if h["name"] == "Subject"), "")
        tids.setdefault(m["threadId"], []).append(s)
    if len(tids) <= 1:
        whole += 1
        continue
    split += 1
    if shown < 5:
        shown += 1
        print(f"  zincir: {len(chain)} mesaj → {len(tids)} thread")
        for t, ss in tids.items():
            uniq = sorted(set(s[:52] for s in ss))
            print(f"    thread {t}: {len(ss)} mesaj")
            for u in uniq[:3]:
                print(f"       “{u}”")
        print()

print(f"  TOPLAM: {whole} zincir tek thread'de, {split} zincir bolunmus "
      f"({split*100//(whole+split)}%)")
