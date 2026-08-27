#!/usr/bin/env python3
"""Kayip 3 mesajin icerigi Gmail'de baska bir ID altinda var mi?"""
import re, json
from pathlib import Path
from gauth import DEFAULT_SCOPE, get_credentials, gmail_service, load_env

SRC = Path("/srv/lexar/Backups/proton-mail-export/mail@egebostanci.me/mail_20260826_140713")
PIDS = [
    "4QBn068qlre7jY90VlChZFK5L23WUEjiyYgXbb6dGUCVeitI29DaiL1CnVe80QWc3mBp9cwzCfycpS5_RweR1g==",
    "gTLm5cZwnKLAzztB8zzZu4lokLAZhlLREdS56oFolAOVN6C-CDLfa0iHy3krbwU07xrQYuFip5USQ5eIfe5WvQ==",
    "FyCyKOrsCiWdJVHKJWoKOcrnlmILay1kPGtW-H8F9RbH_9SXm4Jd6Pb0WsS2yhNsKzskKi5_mmNrPYNrwfHSEg==",
]
env = load_env()
creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)], allow_interactive=False)
svc = gmail_service(creds)

mid_re = re.compile(rb"^message-id:(.*)$", re.I | re.M)
for pid in PIDS:
    blob = (SRC / f"{pid}.eml").read_bytes()[:64 * 1024]
    i = blob.find(b"\r\n\r\n")
    head = blob[:i] if i > 0 else blob
    m = mid_re.search(head)
    mid = re.findall(rb"<[^>]+>", m.group(1))[0].decode() if m else None
    subj = json.loads((SRC / f"{pid}.metadata.json").read_text())["Payload"].get("Subject", "")
    print(f"  {subj[:50]}")
    print(f"    Message-ID: {mid}")
    if not mid:
        print("    → Message-ID yok, arama yapilamiyor\n")
        continue
    q = f"rfc822msgid:{mid.strip('<>')}"
    r = svc.users().messages().list(userId="me", q=q, includeSpamTrash=True).execute()
    hits = r.get("messages", [])
    if hits:
        print(f"    → Gmail'de VAR: {len(hits)} kayit, id={hits[0]['id']}")
    else:
        print(f"    → Gmail'de YOK — yeniden yuklenmeli")
    print()
