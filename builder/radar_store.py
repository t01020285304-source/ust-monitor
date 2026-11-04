"""원자재 레이더 관측 저장소 — DB 대신 버전이 붙은 JSON 파일 (data 브랜치 cache/radar_store/ 에 함께 보관)

행 형식: {"sid", "obs"(관측일), "v", "unit", "pub"(공식 발표일), "pk"(pub 종류: schedule|estimated), "seen"(처음 받은 시각 UTC), "src", "ver"}
- 같은 (sid, obs) 값이 그대로면 저장하지 않음 (중복 제거)
- 값이 바뀌면 덮어쓰지 않고 ver+1 행을 추가 (정정 이력 보존)
- as_of(t): 그 시각에 실제로 볼 수 있었던 값만 — 실시간으로 받은 행은 seen, 과거 일괄 수집 행은 추정 발표일 기준
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import sources

SCHEMA = 1
STORE_DIR = sources.CACHE_DIR / "radar_store"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _path(name, base=None):
    return Path(base or STORE_DIR) / f"{name}.json"


def load(name, base=None):
    p = _path(name, base)
    if not p.exists():
        return {"schema": SCHEMA, "rows": []}
    d = json.loads(p.read_text(encoding="utf-8"))
    return migrate(d)


def save(name, d, base=None):
    p = _path(name, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def migrate(d):
    """형식이 바뀌면 여기에 migrate_1_to_2 … 를 차례로 추가"""
    d.setdefault("schema", SCHEMA)
    d.setdefault("rows", [])
    return d


def upsert(d, rows, seen=None):
    """rows: [{"sid","obs","v","unit","pub","pk","src"}] → (추가 수, 정정 수)"""
    seen = seen or now_utc()
    latest = {}
    for r in d["rows"]:
        k = (r["sid"], r["obs"])
        if k not in latest or r["ver"] > latest[k]["ver"]:
            latest[k] = r
    add = rev = 0
    for r in rows:
        if r.get("v") is None:
            continue                      # 빈 값은 저장하지 않음 (추정으로 채우지 않음)
        k = (r["sid"], r["obs"])
        cur = latest.get(k)
        if cur and cur["v"] == r["v"]:
            continue
        new = dict(r, seen=seen, ver=(cur["ver"] + 1) if cur else 1)
        if cur:
            new["prev"] = cur["v"]
            rev += 1
        else:
            add += 1
        d["rows"].append(new)
        latest[k] = new
    return add, rev


def _avail(r):
    # 과거 일괄 수집분은 우리가 받은 시각(seen)이 실제 공개 시각보다 한참 뒤 → 추정 발표일 끝 시각을 공개 시각으로 봄
    return (r["pub"] + "T23:59Z") if r.get("pk") == "estimated" else r["seen"]


def series(d, sid, as_of=None):
    """[(obs, v)] — 관측일 순, 관측일마다 as_of 시점까지 나온 최신 버전"""
    best = {}
    for r in d["rows"]:
        if r["sid"] != sid or (as_of and _avail(r) > as_of):
            continue
        if r["obs"] not in best or r["ver"] > best[r["obs"]]["ver"]:
            best[r["obs"]] = r
    return sorted((o, r["v"]) for o, r in best.items())


def revisions(d, since):
    return [r for r in d["rows"] if r["ver"] > 1 and r["seen"] >= since]


def meta(d, sid):
    """가장 최근 관측 행 (발표일·수집 시각 표시용)"""
    rows = [r for r in d["rows"] if r["sid"] == sid]
    return max(rows, key=lambda r: (r["obs"], r["ver"])) if rows else None
