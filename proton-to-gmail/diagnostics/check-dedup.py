#!/usr/bin/env python3
"""Ayni Message-ID'li mesajlarin Gmail'de gercekten birlestigini dogrular."""
import glob, re, collections, os
from pathlib import Path
from gauth import DEFAULT_SCOPE, get_credentials, gmail_service, load_env

SRC = Path("/srv/lexar/Backups/proton-mail-export/mail@egebostanci.me/mail_20260826_140713")
mid_re = re.compile(rb"^message-id:(.*)$", re.I | re.M)
ang = re.compile(rb"<[^>]+>")

groups = collections.defaultdict(list)
for p in SRC.glob("*.eml"):
    blob = p.read_bytes()[:32 * 1024]
    i = blob.find(b"\r\n\r\n")
    m = mid_re.search(blob[:i] if i > 0 else blob)
    if m:
        ids = ang.findall(m.group(1))
        if ids:
            groups[ids[0].decode()].append(p.name[:-4])

dup = {k: v for k, v in groups.items() if len(v) > 1}
print(f"  Arsivde tekrarlayan Message-ID grubu: {len(dup)}")
print(f"  Bu gruplardaki toplam mesaj         : {sum(len(v) for v in dup.values())}")
print(f"  Teorik olarak birlesecek fazlalik   : {sum(len(v)-1 for v in dup.values())}")
print()

env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)

print("  Ornek 8 grup — arsivdeki kopya vs Gmail'deki kayit:")
merged = kept = 0
for mid, pids in list(dup.items())[:8]:
    q = f"rfc822msgid:{mid.strip('<>')}"
    r = svc.users().messages().list(userId="me", q=q, includeSpamTrash=True).execute()
    n = len(r.get("messages", []))
    flag = "BIRLESTI" if n < len(pids) else "ayri kaldi"
    if n < len(pids): merged += 1
    else: kept += 1
    print(f"    arsiv {len(pids)}  →  Gmail {n}   {flag}   {mid[:45]}")
print(f"\n  ornekte birlesen {merged}, ayri kalan {kept}")
