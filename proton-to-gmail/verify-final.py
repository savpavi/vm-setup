#!/usr/bin/env python3
"""Gocun sonucunu Gmail tarafinda dogrular: sayilar, etiketler, ornek mesajlar."""
import collections, datetime, json, sqlite3
from pathlib import Path
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env

SRC = Path("/srv/lexar/Backups/proton-mail-export/mail@egebostanci.me/mail_20260826_140713")

env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)

# ── 1. Sayi mutabakati ────────────────────────────────────────────────
labels = {l["id"]: l["name"] for l in svc.users().labels().list(userId="me").execute()["labels"]}
info = {}
for lid, name in labels.items():
    d = svc.users().labels().get(userId="me", id=lid).execute()
    info[name] = d.get("messagesTotal", 0)

prof = svc.users().getProfile(userId="me").execute()
db = sqlite3.connect(str(WORKDIR / "state.sqlite3"))
state_n = db.execute("SELECT COUNT(*) FROM done").fetchone()[0]

# Arsiv beklentisi
arch = collections.Counter()
for p in SRC.glob("*.metadata.json"):
    lids = set(json.loads(p.read_text())["Payload"].get("LabelIDs", []))
    if "3" in lids: arch["TRASH"] += 1
    elif "4" in lids: arch["SPAM"] += 1
    elif "0" in lids: arch["INBOX"] += 1
    if "7" in lids: arch["SENT"] += 1
    if "10" in lids: arch["STARRED"] += 1

print("  SAYI MUTABAKATI")
print(f"    arsivdeki mesaj        : {len(list(SRC.glob('*.eml')))}")
print(f"    state'te yuklendi       : {state_n}")
print(f"    Gmail getProfile toplam : {prof['messagesTotal']}  (cop/spam haric)")
print(f"    Gmail konu sayisi       : {prof['threadsTotal']}")
print()
print("  ETIKET KARSILASTIRMASI        arsiv   Gmail")
for k in ("INBOX", "SENT", "TRASH", "SPAM", "STARRED"):
    print(f"    {k:<24} {arch[k]:>6}  {info.get(k, 0):>6}")
print()
print("  PROTON LABEL'LARI")
for name in sorted(n for n in info if n.startswith("Proton/")):
    print(f"    {name:<40} {info[name]:>5}")

# ── 2. Konu eslemesi ──────────────────────────────────────────────────
print()
print("  KONU (THREAD) ESLEMESI")
conv = json.loads((WORKDIR / "conversations.json").read_text())
gid = {r[0]: r[1] for r in db.execute("SELECT proton_id, gmail_id FROM done")}
ok = bad = 0
for chain in conv["conversations"][:40]:
    tids = set()
    for pid in chain:
        g = gid.get(pid)
        if not g:
            continue
        try:
            m = svc.users().messages().get(userId="me", id=g, format="minimal").execute()
            tids.add(m["threadId"])
        except Exception:
            pass
    if len(tids) == 1:
        ok += 1
    elif tids:
        bad += 1
print(f"    ilk 40 zincirden {ok} tanesi tek thread'de, {bad} tanesi bolunmus")

# ── 3. Ornek mesajlar ─────────────────────────────────────────────────
print()
print("  ORNEK MESAJLAR (Gmail tarihi | orijinal Date | konu)")
rows = db.execute("SELECT gmail_id FROM done ORDER BY RANDOM() LIMIT 6").fetchall()
for (g,) in rows:
    m = svc.users().messages().get(userId="me", id=g, format="metadata",
                                   metadataHeaders=["Subject", "Date"]).execute()
    h = {x["name"]: x["value"] for x in m["payload"].get("headers", [])}
    when = datetime.datetime.fromtimestamp(int(m["internalDate"]) / 1000).strftime("%Y-%m-%d %H:%M")
    print(f"    {when} | {h.get('Date','-')[:31]:<31} | {h.get('Subject','(konusuz)')[:48]}")
