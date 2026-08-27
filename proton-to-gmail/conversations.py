"""Arsivdeki gercek yazisma zincirlerini bulur.

Proton her mesaja kendi ic ID'sini References olarak enjekte ediyor; bu yuzden
sadece arsivdeki BASKA bir mesajin Message-ID'sine isaret eden referanslar
gercek bag sayilir.

Sonuc cache'lenir (conversations.json) — 31 bin dosyayi her calistirmada
yeniden taramak gereksiz.
"""
import json
import re
from pathlib import Path

_MSGID = re.compile(rb"^message-id:(.*)$", re.I | re.M)
_IRT = re.compile(rb"^in-reply-to:(.*)$", re.I | re.M)
_REFS = re.compile(rb"^references:((?:.*\n(?:[ \t].*\n)*))", re.I | re.M)
_ANGLE = re.compile(rb"<[^>]+>")


def _headers(path, limit=64 * 1024):
    """Sadece basliklari oku — tum dosyayi ayristirmak gereksiz ve yavas."""
    with open(path, "rb") as fh:
        blob = fh.read(limit)
    for sep in (b"\r\n\r\n", b"\n\n"):
        i = blob.find(sep)
        if i != -1:
            return blob[:i]
    return blob


def _ids(pattern, head):
    m = pattern.search(head)
    if not m:
        return []
    return [x.decode("ascii", "replace") for x in _ANGLE.findall(m.group(1))]


def analyze(source, cache_path, force=False, log=print):
    source, cache_path = Path(source), Path(cache_path)
    if cache_path.exists() and not force:
        data = json.loads(cache_path.read_text())
        if data.get("source") == str(source):
            return data

    log("  Yazisma zincirleri taraniyor (ilk calistirmada birkac dakika)…")
    byid, refs = {}, {}
    n = 0
    for p in source.glob("*.eml"):
        pid = p.name[:-4]
        head = _headers(p)
        n += 1
        mids = _ids(_MSGID, head)
        mid = mids[0] if mids else None
        if mid:
            byid.setdefault(mid, pid)
        r = set(_ids(_IRT, head)) | set(_ids(_REFS, head))
        r.discard(mid)
        if r:
            refs[pid] = r
        if n % 5000 == 0:
            log(f"    {n} dosya…")

    # union-find
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    edges = 0
    for pid, rs in refs.items():
        for mid in rs:
            tgt = byid.get(mid)
            if tgt and tgt != pid:
                union(pid, tgt)
                edges += 1

    groups = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)

    convs = [sorted(v) for v in groups.values() if len(v) > 1]
    involved = {pid for c in convs for pid in c}

    data = {
        "source": str(source),
        "total": n,
        "edges": edges,
        "conversations": convs,
        "involved_count": len(involved),
    }
    cache_path.write_text(json.dumps(data))
    return data
