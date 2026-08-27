#!/usr/bin/env python3
"""Proton Mail export arsivini Gmail'e yukler.

    uv run --with google-api-python-client --with google-auth-oauthlib \
        migrate.py --source /path/to/mail_YYYYMMDD_HHMMSS

Kesintiye ugrarsa ayni komutla devam eder; yuklenen mesaji tekrar yuklemez.
Durum kaydi: state.sqlite3
"""
import argparse
import base64
import json
import random
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from conversations import analyze
from gauth import DEFAULT_SCOPE, WORKDIR, get_credentials, gmail_service, load_env

# Proton sistem label ID'leri -> Gmail sistem label'lari.
# Bos liste = Gmail'de karsiligi yok (toplayici klasorler, Archive vb.).
SYSTEM_MAP = {
    "0": ["INBOX"],
    "1": [],           # All Drafts (toplayici)
    "2": [],           # All Sent (toplayici)
    "3": ["TRASH"],
    "4": ["SPAM"],
    "5": [],           # All Mail (toplayici)
    "6": [],           # Archive -> Gmail'de INBOX'in yoklugu arsivdir
    "7": ["SENT"],
    "9": [],           # Outbox
    "10": ["STARRED"],
    "12": [],          # All Scheduled
    "15": [],          # All Mail (ikinci kayit)
    "16": [],          # Snoozed
}
DRAFTS_LABEL_ID = "8"

MAX_RAW_BYTES = 35 * 1024 * 1024
# 400/failedPrecondition Gmail'de gecici olarak da cikiyor (26.08.2026'da
# olculdu: ayni mesaj ilk yeniden denemede sorunsuz yuklendi).
RETRY_STATUSES = {400, 403, 429, 500, 502, 503, 504}
MAX_RETRIES = 7


# ── durum kaydi ───────────────────────────────────────────────────────────
class State:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS done (
            proton_id TEXT PRIMARY KEY, gmail_id TEXT, kind TEXT, ts INTEGER)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS failed (
            proton_id TEXT PRIMARY KEY, error TEXT, ts INTEGER)""")
        self.db.commit()

    def done_ids(self):
        with self.lock:
            return {r[0] for r in self.db.execute("SELECT proton_id FROM done")}

    def failed_ids(self):
        with self.lock:
            return {r[0] for r in self.db.execute("SELECT proton_id FROM failed")}

    def mark_done(self, pid, gid, kind):
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO done VALUES (?,?,?,?)",
                (pid, gid, kind, int(time.time())))
            self.db.execute("DELETE FROM failed WHERE proton_id=?", (pid,))
            self.db.commit()

    def mark_failed(self, pid, err):
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO failed VALUES (?,?,?)",
                (pid, str(err)[:2000], int(time.time())))
            self.db.commit()

    def counts(self):
        with self.lock:
            d = self.db.execute("SELECT COUNT(*) FROM done").fetchone()[0]
            f = self.db.execute("SELECT COUNT(*) FROM failed").fetchone()[0]
        return d, f


# ── API cagrisi + geri cekilme ────────────────────────────────────────────
def call(fn):
    """HttpError'da ustel geri cekilmeyle yeniden dener."""
    from googleapiclient.errors import HttpError

    delay = 1.0
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e, "status_code", None) or getattr(e.resp, "status", None)
            last = e
            if status not in RETRY_STATUSES:
                raise
            body = (getattr(e, "content", b"") or b"").decode("utf-8", "replace")
            if status == 403:
                # 403 sadece hiz limiti ise yeniden denenir; yetki hatasi ise hayir.
                if "ateLimitExceeded" not in body and "uotaExceeded" not in body:
                    raise
            if status == 400 and "ailedPrecondition" not in body:
                # Diger 400'ler (bozuk istek) yeniden denemekle duzelmez.
                raise
            time.sleep(delay + random.uniform(0, delay * 0.3))
            delay = min(delay * 2, 64.0)
        except (TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(delay + random.uniform(0, delay * 0.3))
            delay = min(delay * 2, 64.0)
    raise last


# ── label eslemesi ────────────────────────────────────────────────────────
def sanitize(name, prefix):
    name = " ".join(name.split()).replace("/", "-").strip()
    if not name:
        name = "adsiz"
    full = f"{prefix}/{name}" if prefix else name
    return full[:200]


def build_label_map(svc, labels_json, prefix, dry_run):
    """Proton label ID -> Gmail label ID. Eksik olanlari olusturur."""
    payload = json.loads(Path(labels_json).read_text())["Payload"]
    custom = [l for l in payload if not l["ID"].isdigit()]

    existing = {}
    for l in call(lambda: svc.users().labels().list(userId="me").execute()).get("labels", []):
        existing[l["name"]] = l["id"]

    mapping = {}
    created = []
    for l in custom:
        gname = sanitize(l["Name"], prefix)
        gid = existing.get(gname)
        if gid is None:
            if dry_run:
                gid = f"<yeni:{gname}>"
                created.append(gname)
            else:
                body = {"name": gname,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show"}
                try:
                    gid = call(lambda: svc.users().labels().create(
                        userId="me", body=body).execute())["id"]
                    created.append(gname)
                except Exception:
                    # yaris durumu: baska bir sekilde olusmus olabilir
                    fresh = call(lambda: svc.users().labels().list(
                        userId="me").execute()).get("labels", [])
                    gid = {x["name"]: x["id"] for x in fresh}.get(gname)
                    if gid is None:
                        raise
            existing[gname] = gid
        mapping[l["ID"]] = gid
    return mapping, created


def gmail_labels_for(meta, custom_map, unknown_counter):
    labels = set()
    for lid in meta.get("LabelIDs", []):
        if lid.isdigit():
            if lid in SYSTEM_MAP:
                labels.update(SYSTEM_MAP[lid])
            elif lid != DRAFTS_LABEL_ID:
                unknown_counter[lid] = unknown_counter.get(lid, 0) + 1
        else:
            gid = custom_map.get(lid)
            if gid:
                labels.add(gid)

    if meta.get("Unread"):
        labels.add("UNREAD")

    # Gmail'de konum label'lari birbirini dislar.
    if "TRASH" in labels:
        labels -= {"INBOX", "SPAM"}
    elif "SPAM" in labels:
        labels.discard("INBOX")
    return sorted(labels)


# ── tek mesaj ─────────────────────────────────────────────────────────────
def process(pid, source, custom_map, creds, unknown_counter, dry_run, method):
    meta_path = source / f"{pid}.metadata.json"
    eml_path = source / f"{pid}.eml"

    if not eml_path.is_file():
        raise FileNotFoundError(f".eml yok: {eml_path.name}")

    meta = json.loads(meta_path.read_text())["Payload"]
    raw_bytes = eml_path.read_bytes()
    if len(raw_bytes) > MAX_RAW_BYTES:
        raise ValueError(f"cok buyuk ({len(raw_bytes)} bayt), Gmail siniri asiliyor")

    raw = base64.urlsafe_b64encode(raw_bytes).decode("ascii")
    is_draft = DRAFTS_LABEL_ID in meta.get("LabelIDs", [])
    labels = gmail_labels_for(meta, custom_map, unknown_counter)

    if dry_run:
        return ("draft" if is_draft else "message"), f"<dry-run:{len(labels)} label>"

    svc = gmail_service(creds)

    if is_draft:
        # Taslaklar import edilemez; drafts.create ile yazilir.
        # Konum label'lari taslakta anlamsiz, sadece kullanici label'lari kalir.
        keep = [l for l in labels
                if l not in ("INBOX", "SENT", "TRASH", "SPAM", "STARRED", "UNREAD")]
        body = {"message": {"raw": raw}}
        if keep:
            body["message"]["labelIds"] = keep
        res = call(lambda: svc.users().drafts().create(userId="me", body=body).execute())
        return "draft", res.get("id", "")

    body = {"raw": raw}
    if labels:
        body["labelIds"] = labels

    if method == "insert":
        # Teslimat hattini atlar: filtre/siniflandirma yok, cok daha hizli.
        res = call(lambda: svc.users().messages().insert(
            userId="me",
            body=body,
            internalDateSource="dateHeader",
            deleted=False,
        ).execute())
    else:
        res = call(lambda: svc.users().messages().import_(
            userId="me",
            body=body,
            internalDateSource="dateHeader",
            neverMarkSpam=True,
            processForCalendar=False,
            deleted=False,
        ).execute())
    return "message", res.get("id", "")


# ── ana akis ──────────────────────────────────────────────────────────────
def find_source():
    cands = []
    for root in (Path.home() / ".local/lib/proton-mail-export",
                 Path("/srv/lexar/Backups/proton-mail-export")):
        if root.is_dir():
            cands += list(root.glob("*/mail_*"))
    cands = [c for c in cands if (c / "labels.json").is_file()]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def main():
    ap = argparse.ArgumentParser(description="Proton export -> Gmail")
    ap.add_argument("--source", type=Path, help="mail_YYYYMMDD_HHMMSS dizini")
    ap.add_argument("--workers", type=int, default=4, help="es zamanli istek (varsayilan 4)")
    ap.add_argument("--limit", type=int, help="sadece ilk N mesaj (deneme icin)")
    ap.add_argument("--label-prefix", default="Proton",
                    help="ozel label'lar icin on ek; bos birak = on ek yok")
    ap.add_argument("--dry-run", action="store_true", help="hicbir sey yazma, sadece raporla")
    ap.add_argument("--retry-failed", action="store_true",
                    help="daha once basarisiz olanlari tekrar dene")
    ap.add_argument("--method", choices=["hybrid", "import", "insert"], default="hybrid",
                    help="hybrid: yazismalar import (konu eslemesi korunur), "
                         "geri kalani insert (hizli). Varsayilan. "
                         "insert: hepsi hizli ama konu eslemesi yok. "
                         "import: hepsi yavas.")
    ap.add_argument("--rescan", action="store_true",
                    help="yazisma zinciri onbellegini yeniden olustur")
    ap.add_argument("--state", type=Path, default=WORKDIR / "state.sqlite3")
    args = ap.parse_args()

    source = args.source or find_source()
    if not source or not source.is_dir():
        sys.exit("HATA: kaynak dizin bulunamadi. --source ile ver.")
    labels_json = source / "labels.json"
    if not labels_json.is_file():
        sys.exit(f"HATA: {labels_json} yok — bu bir export dizini degil.")

    env = load_env()
    creds = get_credentials(env, [env.get("GWS_SCOPE", DEFAULT_SCOPE)],
                            allow_interactive=False)
    svc = gmail_service(creds)

    prof = call(lambda: svc.users().getProfile(userId="me").execute())
    target = env.get("GWS_TARGET_USER", "")
    if target and prof["emailAddress"].lower() != target.lower():
        sys.exit(f"HATA: token {prof['emailAddress']} hesabina ait, hedef {target}.")

    print(f"  Kaynak : {source}")
    print(f"  Hedef  : {prof['emailAddress']} ({prof['messagesTotal']} mevcut mesaj)")

    state = State(args.state)
    skip = state.done_ids()
    if not args.retry_failed:
        skip |= state.failed_ids()

    ids = sorted(p.name[: -len(".metadata.json")]
                 for p in source.glob("*.metadata.json"))
    total_found = len(ids)
    ids = [i for i in ids if i not in skip]
    if args.limit:
        ids = ids[: args.limit]

    done_n, failed_n = state.counts()
    print(f"  Arsiv  : {total_found} mesaj  ·  yuklenmis {done_n}  ·  basarisiz {failed_n}")
    print(f"  Kuyruk : {len(ids)} mesaj  ·  {args.workers} paralel"
          f"  ·  {args.method}"
          f"{'  ·  DRY-RUN' if args.dry_run else ''}")

    if not ids:
        print("\n  Yapacak is yok.")
        return 0

    custom_map, created = build_label_map(svc, labels_json, args.label_prefix, args.dry_run)
    if created:
        print(f"  Label  : {len(created)} yeni olusturuldu — {', '.join(created)}")
    print()

    unknown = {}
    counts = {"message": 0, "draft": 0, "error": 0}
    started = time.monotonic()

    def run_phase(name, tasks, method, workers):
        """tasks: her biri sirayla islenecek proton_id listesi.

        Liste icinde sira korunur (ebeveyn once), listeler arasinda paralellik var.
        """
        flat = sum(len(t) for t in tasks)
        if not flat:
            return
        print(f"  [{name}] {flat} mesaj · {len(tasks)} is · {workers} paralel · {method}")
        done_n = 0

        def chain(pids):
            out = []
            for pid in pids:
                try:
                    kind, gid = process(pid, source, custom_map, creds,
                                        unknown, args.dry_run, method)
                    out.append((pid, kind, gid, None))
                except Exception as e:
                    out.append((pid, None, None, e))
            return out

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(chain, t) for t in tasks]
            try:
                for fut in as_completed(futures):
                    for pid, kind, gid, err in fut.result():
                        done_n += 1
                        if err is None:
                            counts[kind] += 1
                            if not args.dry_run:
                                state.mark_done(pid, gid, kind)
                        else:
                            counts["error"] += 1
                            state.mark_failed(pid, err)
                            print(f"\n  ! {pid[:16]}… {type(err).__name__}: "
                                  f"{str(err)[:150]}", flush=True)
                        every = 25 if sys.stdout.isatty() else 500
                        if done_n % every == 0 or done_n == flat:
                            el = time.monotonic() - started
                            rate = done_n / el if el > 0 else 0
                            eta = (flat - done_n) / rate if rate > 0 else 0
                            print(f"\r    {done_n}/{flat} ({done_n * 100 // flat}%)  "
                                  f"{rate:.1f}/sn  kalan ~{eta / 60:.0f} dk  "
                                  f"[mesaj {counts['message']} · taslak {counts['draft']} "
                                  f"· hata {counts['error']}]   ",
                                  end="" if sys.stdout.isatty() else "\n", flush=True)
            except KeyboardInterrupt:
                print("\n\n  Durduruldu. Ayni komutla kaldigi yerden devam eder.")
                pool.shutdown(wait=False, cancel_futures=True)
                raise
        print()

    queue = set(ids)
    try:
        if args.method == "hybrid":
            conv = analyze(source, WORKDIR / "conversations.json", force=args.rescan,
                           log=lambda m: print(m, flush=True))
            # Zincir icinde tarih sirasi: ebeveyn once gitmeli
            def when(pid):
                try:
                    meta = json.loads((source / f"{pid}.metadata.json").read_text())
                    return meta["Payload"].get("Time", 0)
                except Exception:
                    return 0

            chains = []
            in_chain = set()
            for c in conv["conversations"]:
                todo = [p for p in c if p in queue]
                if todo:
                    chains.append(sorted(todo, key=when))
                in_chain.update(c)

            singles = [[p] for p in sorted(queue - in_chain)]
            print(f"  Plan   : {sum(len(c) for c in chains)} mesaj yazisma zincirinde "
                  f"({len(chains)} zincir) · {len(singles)} tek basina\n")
            run_phase("1/2 yazismalar", chains, "import", min(args.workers, 8))
            run_phase("2/2 tekil", singles, "insert", args.workers)
        else:
            run_phase("tumu", [[p] for p in ids], args.method, args.workers)
    except KeyboardInterrupt:
        return 130

    el = time.monotonic() - started
    print(f"\n\n  Bitti — {el / 60:.1f} dakika")
    print(f"    mesaj  : {counts['message']}")
    print(f"    taslak : {counts['draft']}")
    print(f"    hata   : {counts['error']}")
    if unknown:
        print(f"    eslenmemis Proton label ID'leri (atlandi): "
              f"{', '.join(f'{k}×{v}' for k, v in sorted(unknown.items()))}")
    if counts["error"]:
        print(f"\n  Hatalari gormek icin:")
        print(f"    sqlite3 {args.state} 'SELECT proton_id, error FROM failed LIMIT 20'")
        print(f"  Tekrar denemek icin ayni komuta --retry-failed ekle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
