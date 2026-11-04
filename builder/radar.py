"""🛢️ 원자재 레이더 (Commodity & Capital Radar) 1차 — CFTC COT + EIA 재고 + 공식 가격 → radar.json

원칙
- 가격 숫자는 공식 출처(FRED: EIA 현물 · IMF 월평균)만. 이번 주 방향(등락률)은 공식 일간이 없으면 Yahoo 선물 '등락률만' 참고로.
  Yahoo 원시 시세는 저장소·캐시에 남기지 않음 (공개 data 브랜치에 재배포하지 않기 위해).
- 빠진 주·없는 값은 빈칸. 이웃 값이나 추정으로 채우지 않음.
- 매핑이 불확실한 계약(radar_meta status='check')은 포지션을 기본으로 숨김.
"""
import os
import time
from datetime import date, datetime, timedelta, timezone

import requests

import markets
import radar_meta as M
import radar_store as RS
import sources

UA = {"User-Agent": "MangoUSTMonitor https://mango-ust.netlify.app"}
CFTC_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
YEARS = 3


# ══ 계산 (인터넷 없이 테스트 — tests/test_radar.py) ═══════════════
def _d(s):
    return date.fromisoformat(s[:10])


def find_near(rows, target, tol=3):
    """[(obs, v)]에서 target ±tol일 안의 가장 가까운 값 — 없으면 None (이웃 주로 대체하지 않음)"""
    t = _d(target)
    best = None
    for o, v in rows:
        dd = abs((_d(o) - t).days)
        if dd <= tol and (best is None or dd < best[0]):
            best = (dd, v)
    return best[1] if best else None


def find_before(rows, target, back=3):
    """target 당일 또는 그 이전 back일 안의 가장 최근 값 (가격: 화요일이 휴장이면 직전 영업일)"""
    t = _d(target)
    best = None
    for o, v in rows:
        dd = (t - _d(o)).days
        if 0 <= dd <= back and (best is None or dd < best[0]):
            best = (dd, v)
    return best[1] if best else None


def net_rows(longs, shorts):
    s = dict(shorts)
    return [(o, v - s[o]) for o, v in longs if o in s]


def change(rows, obs, days, tol=3):
    cur = dict(rows).get(obs)
    prev = find_near(rows, (_d(obs) - timedelta(days=days)).isoformat(), tol)
    return None if cur is None or prev is None else cur - prev


def percentile(rows, obs, weeks=156, min_n=130):
    """최근 156주(3년) 중 이번 주 값의 위치 (같은 값은 절반) — 표본 130주 미만이면 None"""
    win = [v for o, v in rows if o <= obs][-weeks:]
    cur = dict(rows).get(obs)
    if cur is None or len(win) < min_n:
        return None
    below = sum(1 for v in win if v < cur)
    eq = sum(1 for v in win if v == cur)
    return round((below + 0.5 * eq) / len(win) * 100, 1)


QUAD = {
    "up_up": ("① 추세 매수", "가격이 오르는데 투기자금도 더 샀어요 — 상승을 돈이 따라붙는 모습이에요."),
    "up_down": ("② 투기자금 없이 상승", "가격은 올랐지만 투기자금은 오히려 줄였어요 — 숏 커버(빌려 판 것 되사기)나 실수요가 끌어올린 상승일 수 있어 지속되는지 확인이 필요해요."),
    "down_up": ("③ 하락 중 저가 매수", "가격이 내리는데 투기자금은 더 샀어요 — 바닥을 찾는 매수일 수도, 성급한 매수일 수도 있어요."),
    "down_down": ("④ 매도 추세 확인", "가격이 내리고 투기자금도 빠져나갔어요 — 하락 흐름을 돈이 확인해 주는 모습이에요."),
    "flat": ("변화 거의 없음", "투기자금 포지션이 거의 그대로예요 (1주 변화가 전체 미결제약정의 0.5% 미만)."),
}


def quadrant(price_chg, net_chg, oi, oi_chg=None):
    if price_chg is None or net_chg is None or not oi:
        return None
    if abs(net_chg) < 0.005 * oi:
        k = "flat"
    else:
        k = ("up_" if price_chg >= 0 else "down_") + ("up" if net_chg > 0 else "down")
    lab, txt = QUAD[k]
    oi_note = None if oi_chg is None else ("미결제약정도 늘어 새 돈이 들어온 움직임이에요." if oi_chg > 0 else "미결제약정은 줄어 기존 포지션을 정리하는 움직임이에요.")
    return {"key": k, "label": lab, "text": txt, "oi_note": oi_note}


def inv_5y(rows, obs, years=5, min_years=3):
    """직전 5년 같은 주(ISO 주차) 평균·범위 — 올해는 넣지 않음 (EIA 방식)"""
    y, w, _ = _d(obs).isocalendar()
    by = {(_d(o).isocalendar()[0], _d(o).isocalendar()[1]): v for o, v in rows}
    vals = [by[(y - k, w)] for k in range(1, years + 1) if (y - k, w) in by]
    if len(vals) < min_years:
        return None
    return {"avg": sum(vals) / len(vals), "lo": min(vals), "hi": max(vals), "n": len(vals)}


def units_ok(code, units_text):
    exp = M.CONTRACTS[code]["units_text"].replace(" ", "").upper()
    return exp in (units_text or "").replace(" ", "").upper()


# ══ 수집 ══════════════════════════════════════════════════════════
def _get(url, params, tries=2):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=40)
            r.raise_for_status()
            return r.json()
        except Exception:
            if i + 1 == tries:
                raise
            time.sleep(30)


def _cot_raw(full=True):
    # 처음엔 3년치, 그다음부터는 최근 10주만 (15분마다 도는 반복 실행에서 같은 3년치를 계속 받지 않게 — 최근 정정도 이 범위에서 잡힘)
    codes = [c for c in M.CONTRACTS]
    since = (date.today() - timedelta(days=365 * YEARS + 30 if full else 70)).isoformat()
    flds = ["report_date_as_yyyy_mm_dd", "cftc_contract_market_code", "contract_units", "open_interest_all"] + [f for p in M.COT_FIELDS.values() for f in p]

    def load():
        return _get(CFTC_URL, {"$select": ",".join(flds), "$limit": "50000",
                               "$where": f"cftc_contract_market_code in ({','.join(repr(c) for c in codes)}) AND report_date_as_yyyy_mm_dd >= '{since}'"})
    return sources._cached(f"radar_cot_{'full' if full else 'recent'}.json", 6 * 3600, load)


def _pk(obs, pub, seen_day):
    # 발표 예정일 직후 받았으면 '일정 기준', 과거 자료를 한꺼번에 받았으면 '추정 발표일'
    return "schedule" if (seen_day - _d(pub)).days <= 7 else "estimated"


def collect_cot(st, errs):
    have = {r["sid"].split(".")[1] for r in st["rows"] if r["sid"].startswith("cot.")}
    raw = _cot_raw(full=not set(M.CONTRACTS) <= have)
    today = datetime.now(timezone.utc).date()
    rows, warn = [], []
    for x in raw:
        code, obs = x["cftc_contract_market_code"], x["report_date_as_yyyy_mm_dd"][:10]
        if code not in M.CONTRACTS:
            continue
        if not units_ok(code, x.get("contract_units")) and code not in warn:
            warn.append(code)
        pub = (_d(obs) + timedelta(days=3)).isoformat()          # 화요일 기준 → 금요일 발표
        base = {"obs": obs, "pub": pub, "pk": _pk(obs, pub, today), "unit": "contracts", "src": "cftc"}

        def num(f):
            try:
                return int(float(x[f]))
            except (KeyError, TypeError, ValueError):
                return None
        rows.append(dict(base, sid=f"cot.{code}.oi", v=num("open_interest_all")))
        for g, (fl, fs) in M.COT_FIELDS.items():
            rows.append(dict(base, sid=f"cot.{code}.{g}_l", v=num(fl)))
            rows.append(dict(base, sid=f"cot.{code}.{g}_s", v=num(fs)))
    for c in warn:
        errs.append(f"CFTC {c} 계약 단위 문구가 기준표와 달라요 — 확인 필요")
    return RS.upsert(st, rows)


def collect_eia(st, errs):
    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        errs.append("EIA_API_KEY 없음 — 재고 자료를 받지 못했어요")
        return 0, 0
    today = datetime.now(timezone.utc).date()
    add = rev = 0
    for kind, e in M.EIA_INV.items():
        def load(e=e):
            j = _get(f"https://api.eia.gov/v2/{e['route']}/data/", {"api_key": key, "frequency": "weekly", "data[0]": "value", "facets[series][]": e["series"],
                                                                     "sort[0][column]": "period", "sort[0][direction]": "desc", "length": "420"})
            return [[r["period"], float(r["value"])] for r in j["response"]["data"] if r.get("value") not in (None, "")]
        try:
            data = sources._cached(f"radar_eia_{kind}.json", 3 * 3600, load)
        except Exception as ex:
            errs.append(f"EIA {kind}: {str(ex)[:80]}")
            continue
        lag = 5 if kind == "crude" else 6                            # 금요일 기준 → 수요일(원유)·목요일(가스) 발표
        rows = [{"sid": f"inv.{kind}", "obs": o, "v": v, "unit": e["unit"], "pub": (pub := (_d(o) + timedelta(days=lag)).isoformat()),
                 "pk": _pk(o, pub, today), "src": "eia"} for o, v in data]
        a, r = RS.upsert(st, rows)
        add, rev = add + a, rev + r
    return add, rev


def collect_fred(st, errs):
    today = datetime.now(timezone.utc).date()
    since = (date.today() - timedelta(days=365 * YEARS + 30)).isoformat()
    add = rev = 0
    for s in sorted({c["price"][1] for c in M.COMMODITIES if c["price"]}):
        monthly = s.startswith("P")
        try:
            data = markets.fred(s, start=since)
        except Exception as ex:
            errs.append(f"FRED {s}: {str(ex)[:80]}")
            continue
        rows = [{"sid": f"px.{s}", "obs": o, "v": v, "unit": "USD", "pub": (pub := (_d(o) + timedelta(days=45 if monthly else 7)).isoformat()),
                 "pk": "estimated" if (today - _d(pub)).days > 7 else "seen", "src": "fred_imf" if monthly else "fred_eia"} for o, v in data]
        a, r = RS.upsert(st, rows)
        add, rev = add + a, rev + r
    return add, rev


def _yahoo_daily(sym):
    """참고 등락률용 — 파일로 저장하지 않음"""
    c = markets.yahoo_chart(sym, "5y", "1d")
    off = c.get("gmtoffset") or 0
    return [(datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(), v) for t, v in c["points"] if v is not None]


# ══ 화면용 요약 ════════════════════════════════════════════════════
def _today_et():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def _late(next_pub):
    """다음 발표 예정일(미국 동부)보다 하루 넘게 늦었으면 늦은 일수 — 공휴일이면 하루 밀리는 게 정상이라 하루 여유"""
    days = (_today_et() - _d(next_pub)).days
    return days if days >= 1 else None


def _stale(obs, kind):
    if not obs:
        return None
    days = (date.today() - _d(obs)).days
    return days if days > M.STALE_DAYS[kind] else None


def _item(c, st, ymove):
    out = {k: c.get(k) for k in ("id", "name", "group", "status", "why", "alt", "see")}
    out["group_kr"] = M.GROUPS[c["group"]]
    warn = []
    # 가격 숫자 (공식)
    px_rows = []
    if c["price"]:
        _, s, unit, freq = c["price"]
        px_rows = RS.series(st, f"px.{s}")
        if px_rows:
            o, v = px_rows[-1]
            kind = "fred_month" if s.startswith("P") else "fred_day"
            out["price"] = {"v": v, "unit": unit, "obs": o, "freq": freq, "series": s, "url": f"https://fred.stlouisfed.org/series/{s}", "stale": _stale(o, kind)}
            if out["price"]["stale"]:
                warn.append(f"가격 자료가 {out['price']['stale']}일 지났어요")
    # 이번 주 방향 (공식 일간 또는 Yahoo 등락률)
    mv_rows = []
    if c["move"]:
        src, s = c["move"]
        mv_rows = px_rows if src == "fred" else ymove.get(s) or []
        if mv_rows:
            o, v = mv_rows[-1]
            p1, p4 = find_before(mv_rows, (_d(o) - timedelta(days=7)).isoformat()), find_before(mv_rows, (_d(o) - timedelta(days=28)).isoformat())
            out["move"] = {"obs": o, "w1": (v / p1 - 1) * 100 if p1 else None, "w4": (v / p4 - 1) * 100 if p4 else None,
                           "src": "공식 (EIA 현물, FRED)" if src == "fred" else "참고 (Yahoo 선물 등락률)", "ref": src == "yahoo",
                           "stale": _stale(o, "fred_day" if src == "fred" else "yahoo")}
    # COT
    code = c["cot"]
    if code:
        g = {}
        oi = RS.series(st, f"cot.{code}.oi")
        if oi:
            obs = oi[-1][0]
            oi_now = oi[-1][1]
            for k in M.COT_FIELDS:
                L, S_ = RS.series(st, f"cot.{code}.{k}_l"), RS.series(st, f"cot.{code}.{k}_s")
                net = net_rows(L, S_)
                cur = dict(net).get(obs)
                g[k] = {"name": M.GROUP_KR[k], "long": dict(L).get(obs), "short": dict(S_).get(obs), "net": cur,
                        "c1": change(net, obs, 7), "c4": change(net, obs, 28), "c13": change(net, obs, 91),
                        "pct_oi": (cur / oi_now * 100) if cur is not None and oi_now else None, "pctile": percentile(net, obs)}
            mm = net_rows(RS.series(st, f"cot.{code}.mm_l"), RS.series(st, f"cot.{code}.mm_s"))
            meta = RS.meta(st, f"cot.{code}.oi")
            ct = M.CONTRACTS[code]
            out["cot"] = {"code": code, "exch": ct["exch"], "contract": ct["name"], "size": ct["size"], "unit": ct["unit"],
                          "obs": obs, "pub": meta["pub"], "seen": meta["seen"], "oi": oi_now, "oi_c1": change(oi, obs, 7), "groups": g,
                          "next": (_d(meta["pub"]) + timedelta(days=7)).isoformat()}
            out["cot"]["stale"] = _late(out["cot"]["next"])
            if out["cot"]["stale"]:
                warn.append(f"CFTC가 발표 예정일({out['cot']['next'][5:]})보다 {out['cot']['stale']}일 늦어요 — 공식 지연일 수 있어 값을 채우지 않았어요")
            # 차트: 투기자금 순포지션 + 같은 주 화요일 가격 (Yahoo는 3년 전=100 지수로만)
            hist = mm[-156:]
            ph = []
            if mv_rows:
                raw = [find_before(mv_rows, o) for o, _ in hist]
                if c["move"][0] == "yahoo":
                    b = next((x for x in raw if x), None)
                    raw = [round(x / b * 100, 1) if x and b else None for x in raw]
                ph = raw
            out["chart"] = {"obs": [o for o, _ in hist], "mm": [v for _, v in hist], "px": ph,
                            "px_kind": None if not ph else ("index" if c["move"][0] == "yahoo" else "price")}
            # 가격 × 포지션 사분면 — 이번 주 + 지난 13주 궤적
            if mv_rows:
                traj = []
                for o, _ in mm[-14:]:
                    p0, p1_ = find_before(mv_rows, o), find_before(mv_rows, (_d(o) - timedelta(days=7)).isoformat())
                    nc, oo = change(mm, o, 7), dict(oi).get(o)
                    if p0 and p1_ and nc is not None and oo:
                        traj.append({"obs": o, "pc": round((p0 / p1_ - 1) * 100, 2), "nc": round(nc / oo * 100, 2)})
                pc = traj[-1]["pc"] if traj and traj[-1]["obs"] == obs else None
                q = quadrant(pc, g["mm"]["c1"], oi_now, out["cot"]["oi_c1"])
                if q:
                    pt = g["mm"]["pctile"]
                    q["extreme"] = ("투기자금 순매수가 3년 중 상위 10% 안이에요 — 이미 많이 쏠려 있어 반대로 움직일 위험이 커요." if pt is not None and pt >= 90 else
                                    "투기자금 순매수가 3년 중 하위 10% 안이에요 — 비관이 극단이라 반대로 튈 위험이 있어요." if pt is not None and pt <= 10 else None)
                out["quad"] = q
                out["traj"] = traj
    # 재고
    if c["inv"]:
        rows = RS.series(st, f"inv.{c['inv']}")
        if rows:
            o, v = rows[-1]
            e = M.EIA_INV[c["inv"]]
            meta = RS.meta(st, f"inv.{c['inv']}")
            f5 = inv_5y(rows, o)
            prev = find_near(rows, (_d(o) - timedelta(days=7)).isoformat())
            band = []
            for oo, vv in rows[-53:]:
                b5 = inv_5y(rows, oo)
                band.append([oo, vv, b5 and round(b5["avg"]), b5 and b5["lo"], b5 and b5["hi"]])
            out["inv"] = {"name": e["name"], "unit": e["unit"], "obs": o, "v": v, "pub": meta["pub"], "seen": meta["seen"], "pub_rule": e["pub"],
                          "w1": None if prev is None else v - prev, "avg5": f5 and f5["avg"], "lo5": f5 and f5["lo"], "hi5": f5 and f5["hi"],
                          "vs5": (v / f5["avg"] - 1) * 100 if f5 else None, "band": band,
                          "next": (_d(meta["pub"]) + timedelta(days=7)).isoformat()}
            out["inv"]["stale"] = _late(out["inv"]["next"])
            if out["inv"]["stale"]:
                warn.append(f"EIA가 발표 예정일({out['inv']['next'][5:]})보다 {out['inv']['stale']}일 늦어요 — 공식 지연일 수 있어 값을 채우지 않았어요")
    out["warn"] = warn
    out["line"] = (out.get("quad") or {}).get("label")
    return out


def build(errs=None):
    errs = errs if errs is not None else []
    t0 = time.time()
    st = RS.load("radar")
    log = {}
    for name, f in (("cot", collect_cot), ("eia", collect_eia), ("fred", collect_fred)):
        try:
            log[name] = f(st, errs)
        except Exception as ex:
            errs.append(f"원자재 {name}: {str(ex)[:100]}")
    RS.save("radar", st)
    ymove = {}
    for c in M.COMMODITIES:
        if c["move"] and c["move"][0] == "yahoo":
            try:
                ymove[c["move"][1]] = _yahoo_daily(c["move"][1])
            except Exception as ex:
                errs.append(f"참고 등락률 {c['move'][1]}: {str(ex)[:60]}")
    items = []
    for c in M.COMMODITIES:
        try:
            items.append(_item(c, st, ymove))
        except Exception as ex:
            errs.append(f"원자재 {c['id']}: {str(ex)[:100]}")
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%MZ")
    revs = [{"sid": r["sid"], "obs": r["obs"], "prev": r.get("prev"), "v": r["v"], "seen": r["seen"]} for r in RS.revisions(st, since)][-40:]
    print(f"원자재 레이더 ({time.time() - t0:.0f}초) · 추가/정정 {log} · 오류 {len(errs)}개")
    return {"schema": 1, "built_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes"),
            "groups": M.GROUPS, "items": items, "revisions": revs, "errors": errs, "sources": M.SOURCES,
            "store": {"rows": len(st["rows"])}}
