#!/usr/bin/env python3
"""Yuklenen mesajlarin Gmail'deki halini ornekleyerek dogrular."""
import sys, base64, sqlite3
from pathlib import Path
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env

env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)

db = sqlite3.connect(str(WORKDIR / "state.sqlite3"))
rows = db.execute("SELECT proton_id, gmail_id FROM done WHERE kind='message'").fetchall()
print(f"  state kaydi: {len(rows)} mesaj\n")

prof = svc.users().getProfile(userId="me").execute()
print(f"  Gmail kutusu: {prof['messagesTotal']} mesaj, {prof['threadsTotal']} konu\n")

# Etiket dagilimi
labels = {l["id"]: l["name"] for l in svc.users().labels().list(userId="me").execute()["labels"]}

import collections
stats = collections.Counter()
attach = 0
samples = []
for pid, gid in rows[:50]:
    m = svc.users().messages().get(userId="me", id=gid, format="metadata",
                                   metadataHeaders=["Subject", "From", "Date"]).execute()
    for lid in m.get("labelIds", []):
        stats[labels.get(lid, lid)] += 1
    hdrs = {h["name"]: h["value"] for h in m["payload"].get("headers", [])}
    if len(samples) < 8:
        samples.append((m.get("internalDate"), hdrs.get("Date", "-"),
                        hdrs.get("Subject", "(konusuz)")[:60]))

print("  Etiket dagilimi:")
for name, n in stats.most_common():
    print(f"    {n:>4}  {name}")

print("\n  Ornek mesajlar (Gmail internalDate  |  orijinal Date basligi  |  konu):")
import datetime
for ts, dh, subj in samples:
    when = datetime.datetime.fromtimestamp(int(ts)/1000).strftime("%Y-%m-%d %H:%M")
    print(f"    {when}  |  {dh[:31]:<31}  |  {subj}")
